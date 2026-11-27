from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dashboard.models import TeamMembership

from . import test_reservations
from .models import LotCertificate, StockCount, StockMovement, StockPosition, StockReservation


@override_settings(INTERNAL_INVENTORY=True)
class InventoryScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_reservations.ReservationTests.setUpTestData.__func__(cls)
        cls.staff = get_user_model().objects.create_user(username="synthetic-stock-staff")
        TeamMembership.objects.create(user=cls.staff, account=cls.workspace, role=TeamMembership.Role.MANAGER)

    def setUp(self):
        self.client.force_login(self.owner)
        self.overview = reverse("accounting:inventory:overview")

    def action(self, kind):
        return reverse("accounting:inventory:action", args=[kind])

    def payload(self, reference, **fields):
        return {"posted_on": (self.day + timedelta(days=1)).isoformat(), "reference": reference,
                "submission_key": str(uuid4()), **fields}

    def test_owner_movements_counts_reorder_and_reservations(self):
        self.assertContains(self.client.get(reverse("accounting:home")), self.overview)
        self.assertContains(self.client.get(self.action("movement")), "Use the unit registered on the lot.")
        transfer = self.payload("SYN-UI-TRANSFER", kind="transfer", lot_id=self.lot.pk, quantity="3",
                                source_id=self.a.pk, destination_id=self.b.pk, actual_kg="90.5")
        self.assertRedirects(self.client.post(self.action("movement"), transfer), self.overview)
        target = StockPosition.objects.get(location=self.b, lot=self.lot)
        hold = self.payload("SYN-UI-HOLD", position_id=target.pk, quantity="2")
        self.assertRedirects(self.client.post(self.action("reservation"), hold), self.overview)
        reservation = StockReservation.objects.get(reference="SYN-UI-HOLD")
        url = reverse("accounting:inventory:reservation_action", args=[reservation.pk])
        self.assertRedirects(self.client.post(url, self.payload("SYN-UI-ISSUE", kind="issue", quantity="1")), self.overview)
        count = self.payload("SYN-UI-COUNT", counted="1", location_id=self.b.pk, lot_id=self.lot.pk)
        self.assertRedirects(self.client.post(self.action("count"), count), self.overview)
        reorder = {"warehouse_id": self.b.warehouse_id, "product_id": self.product.pk, "minimum_available": "1"}
        response = self.client.post(self.action("reorder"), reorder, follow=True)
        for label in ("Steel inventory", "Reorder alert", "Count adjustment", "SYN-UI-COUNT", "90.5", "94.2"):
            self.assertContains(response, label)
        target.refresh_from_db()
        self.assertEqual((target.on_hand, target.reserved, target.available), (1, 1, 0))
        self.assertEqual(StockCount.objects.get().adjustment.quantity, Decimal(1))
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_default_off_permission_and_foreign_choices(self):
        with self.settings(INTERNAL_INVENTORY=False):
            self.assertEqual(self.client.get(self.overview).status_code, 404)
            self.assertNotContains(self.client.get(reverse("accounting:home")), self.overview)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.overview).status_code, 403)
        self.assertEqual(self.client.post(self.action("count")).status_code, 403)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.overview), self.lot.code)
        data = self.payload("FOREIGN", lot_id=self.lot.pk, counted="7", location_id=self.a.pk)
        self.assertContains(self.client.post(self.action("count"), data), "Select a valid choice.")
        self.assertFalse(StockCount.objects.exists())

    def test_certificate_download_is_private_and_upload_requires_csrf(self):
        upload = reverse("accounting:inventory:certificate_upload", args=[self.lot.pk])
        download = reverse("accounting:inventory:certificate_download", args=[self.lot.pk])
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.get(download).status_code, 404)
        self.assertEqual(secure.post(upload, {}).status_code, 403)
        self.assertContains(secure.get(upload), "csrfmiddlewaretoken")
        csrf = secure.cookies["csrftoken"].value
        malformed = {"certificate": SimpleUploadedFile("bad.pdf", b"invalid"), "csrfmiddlewaretoken": csrf}
        self.assertContains(secure.post(upload, malformed), "Choose a PDF certificate up to 512 KB.")
        self.assertFalse(LotCertificate.objects.exists())
        content = b"%PDF-1.4\nSynthetic certificate test only\n%%EOF"
        valid = {"certificate": SimpleUploadedFile("synthetic.pdf", content), "csrfmiddlewaretoken": csrf}
        self.assertRedirects(secure.post(upload, valid), self.overview)
        response = secure.get(download)
        self.assertEqual(response.content, content)
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(download).status_code, 404)
        self.assertEqual(self.client.get(upload).status_code, 404)

    def test_read_only_requests_never_post_stock(self):
        payload = self.payload("SYN-GET", kind="issue", lot_id=self.lot.pk, quantity="3", source_id=self.a.pk)
        self.assertEqual(self.client.get(self.action("movement"), payload).status_code, 200)
        self.assertEqual(self.client.put(self.action("movement")).status_code, 405)
        self.assertEqual(self.client.post(self.overview).status_code, 405)
        self.assertEqual(StockMovement.objects.count(), 1)
