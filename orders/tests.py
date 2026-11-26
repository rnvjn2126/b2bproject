from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.models import Journal
from dashboard.models import Customer, Product, Quote, RFQ, RFQLine, Supplier, SupplierOffer, TeamMembership

from .models import OrderMovement, PurchaseOrder, SalesOrder


class SalesOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="order-owner")
        cls.outsider = get_user_model().objects.create_user(username="other-company")
        cls.buyer = Customer.objects.create(owner=cls.owner, name="Synthetic buyer", company_name="Sample Steel Buyer")
        cls.supplier = Supplier.objects.create(owner=cls.owner, name="Private Synthetic Supplier")
        cls.rfq = RFQ.objects.create(owner=cls.owner, customer=cls.buyer, received_on=timezone.localdate())
        cls.line = RFQLine.objects.create(owner=cls.owner, rfq=cls.rfq, description="Steel round bar",
                                           grade="304", dimensions="25 mm", quantity="10", unit=Product.Unit.KG)
        cls.offer = SupplierOffer.objects.create(owner=cls.owner, rfq_line=cls.line, supplier=cls.supplier,
                                                available_quantity="10", unit=Product.Unit.KG, unit_price="90", delivery_days=3)

    def setUp(self):
        self.client.force_login(self.owner)

    def create_quote(self, accept=True):
        response = self.client.post(reverse("dashboard:quote_create", args=[self.rfq.pk]), {
            f"offer_{self.line.pk}": self.offer.pk, f"discount_{self.line.pk}": "0",
            "valid_until": "2099-12-31", "payment_terms": "Synthetic terms",
        })
        self.assertEqual(response.status_code, 302)
        quote = Quote.objects.get()
        if accept:
            status_url = reverse("dashboard:quote_update_status", args=[quote.pk])
            for status in (Quote.Status.SENT, Quote.Status.ACCEPTED):
                self.assertEqual(self.client.post(status_url, {"status": status}).status_code, 302)
            quote.refresh_from_db()
        return quote

    def convert(self, quote):
        return self.client.post(reverse("orders:convert", args=[quote.pk]), {
            "customer_reference": "SYN-PO-1", "delivery_on": "2098-06-10",
        })

    def test_accepted_quote_copies_selling_terms_approves_and_prints_without_posting(self):
        quote = self.create_quote()
        self.assertContains(self.client.get(reverse("dashboard:quote_detail", args=[quote.pk])), "Prepare sales order")
        first = self.convert(quote)
        order = SalesOrder.objects.get()
        self.assertRedirects(first, reverse("orders:sales_detail", args=[order.pk]))
        self.assertRedirects(self.convert(quote), first.url)
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(order.status, "draft")
        self.assertEqual(order.subtotal, quote.total_selling_price)
        self.assertEqual(order.lines.get().unit_price, quote.lines.get().selling_price_per_unit)
        self.assertEqual(order.payment_terms, "Synthetic terms")
        self.buyer.company_name = "New buyer name"
        self.buyer.save()
        order.refresh_from_db()
        self.assertEqual(order.customer_name, "Sample Steel Buyer")
        pdf = reverse("orders:sales_pdf", args=[order.pk])
        self.assertEqual(self.client.get(pdf).status_code, 404)
        self.client.post(reverse("orders:sales_approve", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.approved_by, self.owner)
        self.assertEqual(order.status, "approved")
        response = self.client.get(pdf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn(b"Sample Steel Buyer", response.content)
        self.assertIn(b"SYN-PO-1", response.content)
        self.assertNotIn(b"Private Synthetic Supplier", response.content)
        self.assertNotIn(b"margin", response.content.lower())
        self.assertFalse(Journal.objects.exists())

    def test_invalid_source_and_margin_review_are_enforced_on_post(self):
        quote = self.create_quote(accept=False)
        self.assertContains(self.convert(quote), "recorded quotation acceptance", status_code=200)
        now = timezone.now()
        Quote.objects.filter(pk=quote.pk).update(status="accepted", sent_at=now, closed_at=now)
        quote.lines.update(selling_price_per_unit=Decimal("90"))
        self.assertContains(self.convert(quote), "requires gross-margin approval")
        self.assertFalse(SalesOrder.objects.exists())

    def test_cancel_is_audited_and_approval_cannot_reopen(self):
        self.convert(self.create_quote())
        order = SalesOrder.objects.get()
        cancel = reverse("orders:sales_cancel", args=[order.pk])
        self.assertEqual(self.client.get(cancel).status_code, 405)
        self.client.post(cancel, {"reason": "Synthetic cancellation"})
        self.client.post(reverse("orders:sales_approve", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.cancelled_by, self.owner)
        self.assertEqual(order.cancellation_reason, "Synthetic cancellation")
        self.assertFalse(Journal.objects.exists())

    def test_company_permissions_and_csrf(self):
        quote = self.create_quote()
        self.convert(quote)
        order = SalesOrder.objects.get()
        approve = reverse("orders:sales_approve", args=[order.pk])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(approve).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.convert(quote).status_code, 404)
        self.assertEqual(self.client.get(reverse("orders:sales_detail", args=[order.pk])).status_code, 404)
        self.assertEqual(self.client.post(approve).status_code, 404)
        employee = get_user_model().objects.create_user(username="order-sales")
        TeamMembership.objects.create(account=order.workspace, user=employee, role=TeamMembership.Role.SALES)
        self.client.force_login(employee)
        self.assertEqual(self.client.post(approve).status_code, 403)
        self.assertEqual(self.convert(quote).status_code, 403)

    def purchase_payload(self, offer, quantity):
        return {"offer": offer.pk, "quantity": quantity, "delivery_on": "2098-06-10",
                "supplier_reference": "SYN-MILL-PO", "submission_key": str(uuid4())}

    def test_split_procurement_receipts_dispatch_and_pending_report(self):
        self.convert(self.create_quote())
        order = SalesOrder.objects.get()
        requirement = order.lines.get()
        create = reverse("orders:purchase_create", args=[requirement.pk])
        first = self.purchase_payload(self.offer, "6.00")
        self.assertContains(self.client.post(create, first), "Approve the sales order")
        self.client.post(reverse("orders:sales_approve", args=[order.pk]))
        purchase_response = self.client.post(create, first)
        self.assertEqual(purchase_response.status_code, 302)
        self.assertRedirects(self.client.post(create, first), purchase_response.url)
        other_mill = Supplier.objects.create(owner=self.owner, name="Second synthetic mill")
        other_offer = SupplierOffer.objects.create(
            owner=self.owner, rfq_line=self.line, supplier=other_mill, available_quantity="0.004",
            unit=Product.Unit.TONNE, unit_price="95000", delivery_days=5,
        )
        self.assertContains(self.client.post(create, self.purchase_payload(other_offer, "5")), "exceed the sales requirement")
        self.assertEqual(self.client.post(create, self.purchase_payload(other_offer, "4")).status_code, 302)
        purchases = list(PurchaseOrder.objects.order_by("pk"))
        self.assertEqual(purchases[1].unit_price, Decimal("95.0000"))
        self.assertEqual(purchases[1].supplier, other_mill)
        self.assertContains(self.client.get(reverse("orders:pending")), "4.000 kg")
        for purchase in purchases:
            self.client.post(reverse("orders:purchase_approve", args=[purchase.pk]))
        supplier_pdf = self.client.get(reverse("orders:purchase_pdf", args=[purchases[1].pk]))
        self.assertEqual(supplier_pdf.status_code, 200)
        self.assertIn(b"Second synthetic mill", supplier_pdf.content)
        self.assertNotIn(b"Sample Steel Buyer", supplier_pdf.content)

        day = timezone.localdate().isoformat()
        def movement(name, pk, amount, reference):
            return self.client.post(reverse("orders:" + name, args=[pk]), {
                "date": day, "quantity": amount, "reference": reference,
            })
        self.assertContains(movement("dispatch", requirement.pk, "1", "SHIP-1"), "exceed the outstanding or received")
        self.assertEqual(movement("receipt", purchases[0].pk, "3", "GR-1").status_code, 302)
        self.assertEqual(movement("receipt", purchases[0].pk, "3", "GR-1").status_code, 302)
        self.assertContains(movement("receipt", purchases[0].pk, "2", "GR-1"), "different movement")
        self.assertContains(movement("receipt", purchases[0].pk, "4", "GR-2"), "exceed the outstanding or received")
        self.assertEqual(movement("dispatch", requirement.pk, "2", "SHIP-1").status_code, 302)
        self.assertEqual(OrderMovement.objects.count(), 2)
        self.assertEqual(movement("receipt", purchases[0].pk, "3", "GR-2").status_code, 302)
        self.assertEqual(movement("receipt", purchases[1].pk, "4", "GR-3").status_code, 302)
        self.assertEqual(movement("dispatch", requirement.pk, "8", "SHIP-2").status_code, 302)
        pending = self.client.get(reverse("orders:pending"))
        self.assertContains(pending, "No pending sales orders.")
        self.assertContains(pending, "No pending purchase orders.")
        self.assertFalse(Journal.objects.exists())

    def test_cancellation_releases_unreceived_allocations_and_is_company_scoped(self):
        self.convert(self.create_quote())
        order = SalesOrder.objects.get()
        self.client.post(reverse("orders:sales_approve", args=[order.pk]))
        create = reverse("orders:purchase_create", args=[order.lines.get().pk])
        self.assertEqual(self.client.post(create, self.purchase_payload(self.offer, "10")).status_code, 302)
        purchase = PurchaseOrder.objects.get()
        self.client.post(reverse("orders:sales_cancel", args=[order.pk]), {"reason": "Cancel sale"})
        order.refresh_from_db()
        self.assertEqual(order.status, "approved")
        cancel = reverse("orders:purchase_cancel", args=[purchase.pk])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(cancel, {"reason": "Other company"}).status_code, 404)
        self.client.force_login(self.owner)
        self.client.post(cancel, {"reason": "Supplier could not deliver"})
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "cancelled")
        self.assertEqual(self.client.post(create, self.purchase_payload(self.offer, "10")).status_code, 302)
