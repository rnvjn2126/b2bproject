import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AuditEvent, BusinessAccount, Customer, Quote, QuotePricingSettings, RFQ, TeamInvitation, TeamMembership


class TeamWorkspaceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="workspace-owner", password="Owner-Test-Password-9!")
        self.account = BusinessAccount.objects.create(owner=self.owner, name="Synthetic Steel Co")
        self.customer = Customer.objects.create(owner=self.owner, name="Company-wide customer")
        self.rfq = RFQ.objects.create(owner=self.owner, customer=self.customer, reference="TEAM-001", received_on="2026-11-22")
        self.quote = Quote.objects.create(
            owner=self.owner, rfq=self.rfq, number="QT-TEAM-001",
            target_margin_percent="12", minimum_margin_percent="8", maximum_discount_percent="5",
            status=Quote.Status.NEEDS_REVIEW,
        )
        self.client.force_login(self.owner)

    def invite(self, email="teammate@example.test", role=TeamMembership.Role.SALES):
        token = "team-invite-token-for-tests"
        invitation = TeamInvitation.objects.create(
            account=self.account, email=email, role=role,
            token_digest=hashlib.sha256(token.encode()).hexdigest(), created_by=self.owner,
            expires_at=timezone.now() + timedelta(hours=72),
        )
        return invitation, reverse("dashboard:team_invite_accept", args=[token])

    def test_owner_can_invite_new_member_and_member_shares_workspace(self):
        response = self.client.post(reverse("dashboard:team_list"), {
            "action": "invite", "email": "Teammate@Example.test", "role": TeamMembership.Role.MANAGER,
        })
        self.assertEqual(response.status_code, 302)
        invitation = TeamInvitation.objects.get()
        self.assertEqual(invitation.email, "teammate@example.test")
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=self.owner, action=AuditEvent.Action.INVITATION_CREATED,
        ).exists())
        invite_url = self.client.session["team_invite_url"]
        token = invite_url.split("/team/invitations/", 1)[1].split("/", 1)[0]
        self.assertEqual(invitation.token_digest, hashlib.sha256(token.encode()).hexdigest())
        token_path = f"/team/invitations/{token}/accept/"

        self.client.logout()
        response = self.client.post(token_path, {
            "username": "new-teammate",
            "password1": "Violet-Cylinder-Mountain-482!",
            "password2": "Violet-Cylinder-Mountain-482!",
        })
        self.assertRedirects(response, reverse("dashboard:home"))
        teammate = get_user_model().objects.get(username="new-teammate")
        self.assertEqual(teammate.email, "teammate@example.test")
        self.assertEqual(teammate.team_membership.account, self.account)
        self.assertEqual(teammate.team_membership.role, TeamMembership.Role.MANAGER)
        self.assertIsNotNone(TeamInvitation.objects.get(pk=invitation.pk).accepted_at)
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=teammate, action=AuditEvent.Action.INVITATION_ACCEPTED,
        ).exists())
        self.assertEqual(Customer.objects.filter(owner=self.owner).count(), 1)

        self.assertContains(self.client.get(reverse("dashboard:customer_list")), "Company-wide customer")
        created = self.client.post(reverse("dashboard:customer_create"), {"name": "Added by teammate"})
        self.assertEqual(created.status_code, 302)
        self.assertEqual(Customer.objects.get(name="Added by teammate").owner, self.owner)
        self.assertEqual(self.client.get(token_path).status_code, 404)

    def test_owner_and_manager_can_approve_but_sales_cannot(self):
        manager = get_user_model().objects.create_user(username="workspace-manager", password="Manager-Test-Password-9!")
        sales = get_user_model().objects.create_user(username="workspace-sales", password="Sales-Test-Password-9!")
        TeamMembership.objects.create(account=self.account, user=manager, role=TeamMembership.Role.MANAGER)
        TeamMembership.objects.create(account=self.account, user=sales, role=TeamMembership.Role.SALES)
        approve_url = reverse("dashboard:quote_approve", args=[self.quote.pk])

        self.client.force_login(sales)
        detail = reverse("dashboard:quote_detail", args=[self.quote.pk])
        self.assertNotContains(self.client.get(detail), "Approve after manager review")
        self.assertEqual(self.client.post(approve_url).status_code, 403)
        settings_url = reverse("dashboard:quote_pricing_settings")
        self.assertContains(self.client.get(settings_url), "Only the owner or a manager can change")
        self.assertEqual(self.client.post(settings_url, {
            "target_margin_percent": "15", "minimum_margin_percent": "8", "maximum_discount_percent": "5",
        }).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:team_member_remove", args=[sales.team_membership.pk])).status_code, 403)

        self.client.force_login(manager)
        self.assertContains(self.client.get(detail), "Approve after manager review")
        approved = self.client.post(approve_url)
        self.assertRedirects(approved, reverse("dashboard:quote_detail", args=[self.quote.pk]))
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.approved_by, manager)
        self.assertEqual(self.quote.status, Quote.Status.APPROVED)
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=manager, action=AuditEvent.Action.QUOTE_APPROVED,
        ).exists())
        manager_settings = self.client.post(settings_url, {
            "target_margin_percent": "15", "minimum_margin_percent": "8", "maximum_discount_percent": "5",
        })
        self.assertRedirects(manager_settings, settings_url)
        self.assertEqual(QuotePricingSettings.objects.get(owner=self.owner).target_margin_percent, 15)
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=manager, action=AuditEvent.Action.PRICING_UPDATED,
        ).exists())
        self.assertContains(self.client.get(reverse("dashboard:activity_log")), "Quotation approved")

        self.client.force_login(sales)
        self.assertEqual(self.client.get(reverse("dashboard:activity_log")).status_code, 403)

    def test_team_members_cannot_access_another_business_workspace(self):
        teammate = get_user_model().objects.create_user(username="workspace-member", password="Member-Test-Password-9!")
        TeamMembership.objects.create(account=self.account, user=teammate, role=TeamMembership.Role.SALES)
        other = get_user_model().objects.create_user(username="other-business", password="Other-Test-Password-9!")
        private = Customer.objects.create(owner=other, name="Other business customer")

        self.client.force_login(teammate)
        response = self.client.get(reverse("dashboard:customer_list"))
        self.assertContains(response, "Company-wide customer")
        self.assertNotContains(response, "Other business customer")
        self.assertEqual(self.client.get(reverse("dashboard:customer_update", args=[private.pk])).status_code, 404)

    def test_owner_can_revoke_a_pending_invitation(self):
        invitation, invite_url = self.invite()
        self.assertEqual(self.client.get(invite_url).status_code, 200)
        response = self.client.post(reverse("dashboard:team_invitation_revoke", args=[invitation.pk]))
        self.assertRedirects(response, reverse("dashboard:team_list"))
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=self.owner, action=AuditEvent.Action.INVITATION_REVOKED,
        ).exists())
        self.assertEqual(self.client.get(invite_url).status_code, 404)

    def test_invitation_is_bound_to_email_and_an_existing_user_can_join(self):
        invitation, invite_url = self.invite(email="joiner@example.test")
        user_model = get_user_model()
        wrong_user = user_model.objects.create_user(
            username="wrong-invitee", email="wrong@example.test", password="Wrong-Invitee-Password-98!",
        )
        self.client.force_login(wrong_user)
        rejected = self.client.post(invite_url)
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(TeamMembership.objects.filter(user=wrong_user).exists())
        self.assertIsNone(TeamInvitation.objects.get(pk=invitation.pk).accepted_at)

        invited_user = user_model.objects.create_user(
            username="existing-invitee", email="joiner@example.test", password="Existing-Invitee-Password-98!",
        )
        self.client.force_login(invited_user)
        accepted = self.client.post(invite_url)
        self.assertRedirects(accepted, reverse("dashboard:home"))
        self.assertEqual(invited_user.team_membership.account, self.account)

    def test_invite_rejects_users_who_already_own_business_data(self):
        existing = get_user_model().objects.create_user(
            username="existing-business", email="busy@example.test", password="Existing-Business-Password-98!",
        )
        Customer.objects.create(owner=existing, name="Private customer")
        response = self.client.post(reverse("dashboard:team_list"), {
            "action": "invite", "email": "busy@example.test", "role": TeamMembership.Role.SALES,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a workspace or company membership")
        self.assertFalse(TeamInvitation.objects.filter(email="busy@example.test").exists())

    def test_owner_alone_can_change_member_roles(self):
        teammate = get_user_model().objects.create_user(username="role-target", password="Role-Target-Password-98!")
        membership = TeamMembership.objects.create(account=self.account, user=teammate, role=TeamMembership.Role.SALES)
        self.client.force_login(teammate)
        self.assertEqual(self.client.post(
            reverse("dashboard:team_member_role", args=[membership.pk]), {"role": TeamMembership.Role.MANAGER},
        ).status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dashboard:team_member_role", args=[membership.pk]), {"role": TeamMembership.Role.MANAGER},
        )
        self.assertRedirects(response, reverse("dashboard:team_list"))
        membership.refresh_from_db()
        self.assertEqual(membership.role, TeamMembership.Role.MANAGER)
        self.assertTrue(AuditEvent.objects.filter(
            owner=self.owner, actor=self.owner, action=AuditEvent.Action.MEMBER_ROLE_CHANGED,
        ).exists())

    def test_activity_log_is_scoped_to_the_company(self):
        other = get_user_model().objects.create_user(username="audit-outsider", password="Audit-Outsider-Password-98!")
        AuditEvent.objects.create(
            owner=other, actor=other, action=AuditEvent.Action.WORKSPACE_RENAMED,
            object_type="workspace", object_id="private-company",
        )
        self.assertContains(self.client.get(reverse("dashboard:activity_log")), "No recorded activity yet")
        self.assertNotContains(self.client.get(reverse("dashboard:activity_log")), "audit-outsider")
