import csv
import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    BusinessAccountForm, CustomerForm, FollowUpForm, ProductCSVImportForm, ProductForm,
    QuoteCreateForm, QuotePricingSettingsForm, QuoteStatusForm, RFQForm, RFQLineFormSet,
    RFQStatusForm, SupplierForm, SupplierOfferForm, TeamInvitationAcceptForm, TeamInvitationForm,
)
from .accounts import (
    account_owner, business_account_for, can_manage_account, can_manage_team, user_can_join_account,
)
from .models import (
    AuditEvent, BusinessAccount, Customer, FollowUp, Product, Quote, QuoteLine, QuotePricingSettings,
    RFQ, RFQLine, Supplier, SupplierOffer, TeamInvitation, TeamMembership,
)


def _safe_csv_cell(value):
    text = "" if value is None else str(value)
    # Spreadsheet programs may execute cells that begin with formula characters.
    return "'" + text if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else text


@login_required
def home(request):
    owner = account_owner(request.user)
    active_follow_ups = FollowUp.objects.filter(
        owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
        completed_at__isnull=True,
    ).select_related("rfq", "rfq__customer").order_by("due_on", "id")
    # Derive progress from this account's records; never seed demo data into a workspace.
    setup_steps = [
        {
            "label": "Add your first customer", "url": reverse("dashboard:customer_create"),
            "done": Customer.objects.filter(owner=owner).exists(),
        },
        {
            "label": "Add your first supplier", "url": reverse("dashboard:supplier_create"),
            "done": Supplier.objects.filter(owner=owner).exists(),
        },
        {
            "label": "Add your first product", "url": reverse("dashboard:product_create"),
            "done": Product.objects.filter(owner=owner).exists(),
        },
        {
            "label": "Record your first enquiry", "url": reverse("dashboard:rfq_create"),
            "done": RFQ.objects.filter(owner=owner, customer__owner=owner).exists(),
        },
        {
            "label": "Prepare your first quotation", "url": reverse("dashboard:rfq_list"),
            "done": Quote.objects.filter(
                owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
            ).exists(),
        },
    ]
    return render(request, "dashboard/home.html", {
        "customer_count": Customer.objects.filter(owner=owner).count(),
        "supplier_count": Supplier.objects.filter(owner=owner).count(),
        "product_count": Product.objects.filter(owner=owner).count(),
        "rfq_count": RFQ.objects.filter(owner=owner, customer__owner=owner).count(),
        "follow_up_count": active_follow_ups.count(),
        "overdue_follow_up_count": active_follow_ups.filter(due_on__lt=timezone.localdate()).count(),
        "upcoming_follow_ups": active_follow_ups[:5],
        "today": timezone.localdate(),
        "setup_steps": setup_steps,
        "setup_completed": sum(step["done"] for step in setup_steps),
        "setup_total": len(setup_steps),
    })


@login_required
@require_http_methods(["GET", "POST"])
def team_list(request):
    account = business_account_for(request.user, create=True)
    is_owner = can_manage_team(request.user, account)
    account_form = BusinessAccountForm(instance=account)
    invitation_form = TeamInvitationForm(account=account)

    if request.method == "POST":
        if not is_owner:
            raise PermissionDenied("Only the business owner can manage team membership.")

        action = request.POST.get("action")
        if action == "rename":
            old_name = account.name
            account_form = BusinessAccountForm(request.POST, instance=account)
            if account_form.is_valid():
                with transaction.atomic():
                    account_form.save()
                    if account.name != old_name:
                        AuditEvent.objects.create(
                            owner=account.owner, actor=request.user,
                            action=AuditEvent.Action.WORKSPACE_RENAMED,
                            object_type="workspace", object_id=str(account.pk),
                        )
                return redirect("dashboard:team_list")
        elif action == "invite":
            invitation_form = TeamInvitationForm(request.POST, account=account)
            if invitation_form.is_valid():
                email = invitation_form.cleaned_data["email"]
                existing_user = get_user_model().objects.filter(email__iexact=email).first()
                if existing_user and not user_can_join_account(existing_user):
                    invitation_form.add_error("email", "This user already has a workspace or company membership.")
                else:
                    token = secrets.token_urlsafe(32)
                    # A database leak must not reveal a usable invitation link.
                    invitation = TeamInvitation(
                        account=account,
                        email=email,
                        role=invitation_form.cleaned_data["role"],
                        token_digest=hashlib.sha256(token.encode()).hexdigest(),
                        created_by=request.user,
                        expires_at=timezone.now() + timedelta(hours=72),
                    )
                    invitation.full_clean()
                    with transaction.atomic():
                        invitation.save()
                        AuditEvent.objects.create(
                            owner=account.owner, actor=request.user,
                            action=AuditEvent.Action.INVITATION_CREATED,
                            object_type="invitation", object_id=str(invitation.pk),
                        )
                    request.session["team_invite_url"] = request.build_absolute_uri(
                        reverse("dashboard:team_invite_accept", args=[token]),
                    )
                    return redirect("dashboard:team_list")
        else:
            return HttpResponseBadRequest("Choose a valid team action.")

    return render(request, "dashboard/team.html", {
        "account": account,
        "account_form": account_form,
        "invitation_form": invitation_form,
        "members": account.memberships.select_related("user"),
        "invitations": account.invitations.filter(
            accepted_at__isnull=True, revoked_at__isnull=True,
        ),
        "role_choices": TeamMembership.Role.choices,
        "is_owner": is_owner,
        "can_manage_account": can_manage_account(request.user, account),
        "invite_url": request.session.pop("team_invite_url", "") if is_owner else "",
    })


@login_required
@require_POST
def team_member_remove(request, pk):
    account = business_account_for(request.user)
    if not account or not can_manage_team(request.user, account):
        raise PermissionDenied("Only the business owner can remove team members.")
    member = get_object_or_404(account.memberships, pk=pk)
    with transaction.atomic():
        member.delete()
        AuditEvent.objects.create(
            owner=account.owner, actor=request.user,
            action=AuditEvent.Action.MEMBER_REMOVED,
            object_type="team_member", object_id=str(pk),
        )
    return redirect("dashboard:team_list")


@login_required
@require_POST
def team_member_role(request, pk):
    account = business_account_for(request.user)
    if not account or not can_manage_team(request.user, account):
        raise PermissionDenied("Only the business owner can change team roles.")
    member = get_object_or_404(account.memberships, pk=pk)
    role = request.POST.get("role")
    if role not in TeamMembership.Role.values:
        return HttpResponseBadRequest("Choose a valid team role.")
    if role != member.role:
        with transaction.atomic():
            member.role = role
            member.full_clean()
            member.save(update_fields=["role"])
            AuditEvent.objects.create(
                owner=account.owner, actor=request.user,
                action=AuditEvent.Action.MEMBER_ROLE_CHANGED,
                object_type="team_member", object_id=str(member.pk),
            )
    return redirect("dashboard:team_list")


@login_required
@require_POST
def team_invitation_revoke(request, pk):
    account = business_account_for(request.user)
    if not account or not can_manage_team(request.user, account):
        raise PermissionDenied("Only the business owner can revoke invitations.")
    invitation = get_object_or_404(
        account.invitations.filter(accepted_at__isnull=True, revoked_at__isnull=True), pk=pk,
    )
    invitation.revoked_at = timezone.now()
    with transaction.atomic():
        invitation.save(update_fields=["revoked_at"])
        AuditEvent.objects.create(
            owner=account.owner, actor=request.user,
            action=AuditEvent.Action.INVITATION_REVOKED,
            object_type="invitation", object_id=str(invitation.pk),
        )
    return redirect("dashboard:team_list")


@require_http_methods(["GET", "POST"])
def team_invite_accept(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    pending = TeamInvitation.objects.filter(
        token_digest=digest, accepted_at__isnull=True, revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    invitation = get_object_or_404(pending.select_related("account", "account__owner"))
    form = None if request.user.is_authenticated else TeamInvitationAcceptForm(request.POST or None)
    error = ""
    accepted_user = None

    if request.method == "POST":
        with transaction.atomic():
            invitation = get_object_or_404(
                TeamInvitation.objects.select_for_update().filter(
                    accepted_at__isnull=True, revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ),
                pk=invitation.pk,
            )
            if request.user.is_authenticated:
                accepted_user = request.user
                if accepted_user.email.casefold() != invitation.email.casefold():
                    error = "Sign in with the email address this invitation was sent to."
                elif not user_can_join_account(accepted_user):
                    error = "This user already has a workspace or company membership."
            elif form.is_valid():
                if get_user_model().objects.filter(email__iexact=invitation.email).exists():
                    form.add_error(None, "This email already has an account. Sign in to accept the invitation.")
                else:
                    accepted_user = form.save(commit=False)
                    accepted_user.email = invitation.email
                    accepted_user.save()

            if accepted_user and not error:
                membership = TeamMembership(
                    account=invitation.account, user=accepted_user, role=invitation.role,
                )
                membership.full_clean()
                membership.save()
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["accepted_at"])
                AuditEvent.objects.create(
                    owner=invitation.account.owner, actor=accepted_user,
                    action=AuditEvent.Action.INVITATION_ACCEPTED,
                    object_type="invitation", object_id=str(invitation.pk),
                )
            else:
                accepted_user = None

        if accepted_user:
            login(request, accepted_user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("dashboard:home")

    can_accept = bool(
        request.user.is_authenticated
        and request.user.email.casefold() == invitation.email.casefold()
        and user_can_join_account(request.user)
    )
    return render(request, "registration/team_invite_accept.html", {
        "invitation": invitation, "form": form, "error": error, "can_accept": can_accept,
    })


@login_required
def activity_log(request):
    if not can_manage_account(request.user):
        raise PermissionDenied("Only the owner or a manager can view workspace activity.")
    owner = account_owner(request.user)
    events = AuditEvent.objects.filter(owner=owner).select_related("actor")
    page = Paginator(events, 50).get_page(request.GET.get("page"))
    return render(request, "dashboard/activity_log.html", {"page": page})


@login_required
def reports(request):
    owner = account_owner(request.user)
    today = timezone.localdate()
    period_start = today - timedelta(days=29)
    quotes = Quote.objects.filter(owner=owner, rfq__owner=owner, rfq__customer__owner=owner)
    counts = {
        row["status"]: row["total"]
        for row in quotes.values("status").annotate(total=Count("id"))
    }
    accepted = counts.get(Quote.Status.ACCEPTED, 0)
    lost = counts.get(Quote.Status.LOST, 0)
    decided = accepted + lost
    win_rate = (
        (Decimal(accepted) * 100 / decided).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if decided else None
    )
    due_follow_ups = FollowUp.objects.filter(
        owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
        due_on__range=(period_start, today),
    )
    due_count = due_follow_ups.count()
    completed_count = due_follow_ups.filter(completed_at__isnull=False).count()
    follow_up_completion_rate = (
        (Decimal(completed_count) * 100 / due_count).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if due_count else None
    )
    return render(request, "dashboard/reports.html", {
        "pipeline": [
            {"label": label, "count": counts.get(status, 0)}
            for status, label in Quote.Status.choices
        ],
        "open_quote_count": sum(counts.get(status, 0) for status in (
            Quote.Status.READY, Quote.Status.NEEDS_REVIEW, Quote.Status.APPROVED, Quote.Status.SENT,
        )),
        "accepted_count": accepted,
        "lost_count": lost,
        "decided_count": decided,
        "win_rate": win_rate,
        "has_win_rate": win_rate is not None,
        "period_start": period_start,
        "today": today,
        "overdue_follow_up_count": FollowUp.objects.filter(
            owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
            completed_at__isnull=True, due_on__lt=today,
        ).count(),
        "due_follow_up_count": due_count,
        "completed_follow_up_count": completed_count,
        "follow_up_completion_rate": follow_up_completion_rate,
        "has_follow_up_completion_rate": follow_up_completion_rate is not None,
        "new_enquiry_count": RFQ.objects.filter(
            owner=owner, customer__owner=owner, received_on__range=(period_start, today),
        ).count(),
    })


@login_required
def rfq_list(request):
    owner = account_owner(request.user)
    rfqs = RFQ.objects.filter(owner=owner, customer__owner=owner).select_related("customer")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        rfqs = rfqs.filter(
            Q(reference__icontains=query) | Q(customer__name__icontains=query)
            | Q(customer__company_name__icontains=query) | Q(notes__icontains=query),
        )
    if status not in RFQ.Status.values:
        status = ""
    if status:
        rfqs = rfqs.filter(status=status)
    return render(request, "dashboard/rfq_list.html", {
        "rfqs": Paginator(rfqs, 25).get_page(request.GET.get("page")),
        "query": query, "status": status, "status_choices": RFQ.Status.choices,
    })


@login_required
@require_http_methods(["GET", "POST"])
def rfq_create(request):
    from .models import RFQLine
    owner = account_owner(request.user)
    rfq = RFQ(owner=owner)
    form = RFQForm(request.POST or None, owner=owner)
    formset = RFQLineFormSet(request.POST or None, instance=rfq, form_kwargs={"owner": owner}, prefix="lines")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            rfq = form.save(commit=False)
            rfq.owner = owner
            rfq.full_clean()
            rfq.save()
            formset.instance = rfq
            lines = formset.save(commit=False)
            for line in lines:
                line.owner = owner
                line.rfq = rfq
                line.full_clean()
                line.save()
            for line in formset.deleted_objects:
                line.delete()
        messages.success(request, "Enquiry recorded.")
        return redirect("dashboard:rfq_detail", pk=rfq.pk)
    return render(request, "dashboard/rfq_form.html", {"form": form, "formset": formset})


@login_required
def rfq_detail(request, pk):
    owner = account_owner(request.user)
    offers = SupplierOffer.objects.filter(
        owner=owner, supplier__owner=owner, rfq_line__owner=owner,
    ).select_related("supplier", "rfq_line__product")
    lines = RFQLine.objects.filter(Q(product__isnull=True) | Q(product__owner=owner), owner=owner).select_related("product").prefetch_related(
        Prefetch("supplier_offers", queryset=offers)
    )
    follow_ups = FollowUp.objects.filter(
        owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
    ).order_by("due_on", "id")
    rfq = get_object_or_404(
            RFQ.objects.filter(owner=owner, customer__owner=owner).select_related("customer").prefetch_related(
            Prefetch("lines", queryset=lines), Prefetch("follow_ups", queryset=follow_ups),
        ),
        pk=pk,
    )
    for line in rfq.lines.all():
        line.comparison_offers = sorted(
            line.supplier_offers.all(),
            key=lambda offer: (
                offer.landed_cost_per_requested_unit is None,
                offer.landed_cost_per_requested_unit or 0,
                offer.pk,
            ),
        )
        full = [offer for offer in line.comparison_offers if offer.covers_full_quantity and offer.landed_cost_per_requested_unit is not None]
        if full:
            line.lowest_rate = full[0].landed_cost_per_requested_unit
            line.fastest_days = min(offer.delivery_days for offer in full)
    return render(request, "dashboard/rfq_detail.html", {
        "rfq": rfq, "status_form": RFQStatusForm(initial={"status": rfq.status}),
        "today": timezone.localdate(),
    })


@login_required
@require_POST
def rfq_update_status(request, pk):
    owner = account_owner(request.user)
    rfq = get_object_or_404(
        RFQ.objects.filter(owner=owner, customer__owner=owner), pk=pk,
    )
    form = RFQStatusForm(request.POST)
    if form.is_valid():
        rfq.status = form.cleaned_data["status"]
        rfq.full_clean()
        rfq.save(update_fields=["status", "updated_at"])
    return redirect("dashboard:rfq_detail", pk=rfq.pk)


@login_required
@require_http_methods(["GET", "POST"])
def followup_create(request, pk):
    owner = account_owner(request.user)
    rfq = get_object_or_404(
        RFQ.objects.filter(owner=owner, customer__owner=owner).select_related("customer"),
        pk=pk,
    )
    form = FollowUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        follow_up = form.save(commit=False)
        follow_up.owner = owner
        follow_up.rfq = rfq
        follow_up.full_clean()
        follow_up.save()
        messages.success(request, "Follow-up scheduled.")
        return redirect("dashboard:rfq_detail", pk=rfq.pk)
    return render(request, "dashboard/followup_form.html", {"form": form, "rfq": rfq})


@login_required
@require_POST
def followup_complete(request, pk):
    owner = account_owner(request.user)
    follow_up = get_object_or_404(
        FollowUp.objects.filter(
            owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
            completed_at__isnull=True,
        ).select_related("rfq"),
        pk=pk,
    )
    follow_up.completed_at = timezone.now()
    follow_up.full_clean()
    follow_up.save(update_fields=["completed_at", "updated_at"])
    return redirect("dashboard:rfq_detail", pk=follow_up.rfq_id)


@login_required
def followup_list(request):
    owner = account_owner(request.user)
    follow_ups = FollowUp.objects.filter(
        owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
    ).select_related("rfq", "rfq__customer").order_by("due_on", "id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "open")
    if status not in {"open", "completed", "all"}:
        status = "open"
    if status == "open":
        follow_ups = follow_ups.filter(completed_at__isnull=True)
    elif status == "completed":
        follow_ups = follow_ups.filter(completed_at__isnull=False)
    if query:
        follow_ups = follow_ups.filter(
            Q(rfq__reference__icontains=query) | Q(rfq__customer__name__icontains=query)
            | Q(rfq__customer__company_name__icontains=query) | Q(note__icontains=query),
        )
    return render(request, "dashboard/followup_list.html", {
        "follow_ups": Paginator(follow_ups, 25).get_page(request.GET.get("page")),
        "query": query, "status": status,
        "today": timezone.localdate(),
    })


@login_required
@require_http_methods(["GET"])
def product_csv_export(request):
    """Export only the signed-in user's non-sensitive product catalogue fields."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="steel-products.csv"'
    response["Cache-Control"] = "no-store"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(ProductCSVImportForm.EXPECTED_HEADERS)
    products = Product.objects.filter(owner=account_owner(request.user)).order_by("name", "id")
    for product in products:
        writer.writerow(_safe_csv_cell(value) for value in (
            product.name, product.grade, product.shape, product.dimensions,
            product.unit, product.weight_basis, product.weight_kg, product.notes,
        ))
    return response


@login_required
@require_http_methods(["GET"])
def customer_csv_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="steel-customers.csv"'
    response["Cache-Control"] = "no-store"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(("name", "company_name", "email", "phone", "billing_address", "notes"))
    customers = Customer.objects.filter(owner=account_owner(request.user)).order_by("name", "id")
    for customer in customers:
        writer.writerow(_safe_csv_cell(value) for value in (
            customer.name, customer.company_name, customer.email, customer.phone,
            customer.billing_address, customer.notes,
        ))
    return response


@login_required
@require_http_methods(["GET"])
def supplier_csv_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="steel-suppliers.csv"'
    response["Cache-Control"] = "no-store"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(("name", "company_name", "email", "phone", "address", "notes"))
    suppliers = Supplier.objects.filter(owner=account_owner(request.user)).order_by("name", "id")
    for supplier in suppliers:
        writer.writerow(_safe_csv_cell(value) for value in (
            supplier.name, supplier.company_name, supplier.email, supplier.phone,
            supplier.address, supplier.notes,
        ))
    return response


@login_required
@require_http_methods(["GET", "POST"])
def product_csv_import(request):
    owner = account_owner(request.user)
    form = ProductCSVImportForm(request.POST or None, request.FILES or None, owner=owner)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            for product in form.products:
                product.save()
        return redirect("dashboard:product_list")
    return render(request, "dashboard/product_csv_import.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def supplier_offer_create(request, pk, line_pk):
    owner = account_owner(request.user)
    rfq = get_object_or_404(RFQ.objects.filter(owner=owner, customer__owner=owner), pk=pk)
    line = get_object_or_404(
        RFQLine.objects.filter(Q(product__isnull=True) | Q(product__owner=owner), owner=owner, rfq=rfq).select_related("product"),
        pk=line_pk,
    )
    form = SupplierOfferForm(
        request.POST or None, owner=owner, rfq_line=line,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            offer = form.save(commit=False)
            offer.owner = owner
            offer.rfq_line = line
            offer.full_clean()
            offer.save()
        return redirect("dashboard:rfq_detail", pk=rfq.pk)
    return render(request, "dashboard/supplier_offer_form.html", {"form": form, "rfq": rfq, "line": line})


@login_required
@require_http_methods(["GET", "POST"])
def quote_pricing_settings(request):
    owner = account_owner(request.user)
    settings, _ = QuotePricingSettings.objects.get_or_create(owner=owner)
    can_edit = can_manage_account(request.user)
    if request.method == "POST" and not can_edit:
        raise PermissionDenied("Only the owner or a manager can change quote pricing guardrails.")
    form = QuotePricingSettingsForm(request.POST or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        if form.has_changed():
            with transaction.atomic():
                form.save()
                AuditEvent.objects.create(
                    owner=owner, actor=request.user,
                    action=AuditEvent.Action.PRICING_UPDATED,
                    object_type="pricing_settings", object_id=str(settings.pk),
                )
        return redirect("dashboard:quote_pricing_settings")
    return render(request, "dashboard/quote_pricing_settings.html", {"form": form, "can_edit": can_edit})


@login_required
@require_http_methods(["GET", "POST"])
def quote_create(request, pk):
    owner = account_owner(request.user)
    rfq = get_object_or_404(
        RFQ.objects.filter(owner=owner, customer__owner=owner).select_related("customer"), pk=pk,
    )
    return _quote_create_page(request, rfq)


@login_required
@require_http_methods(["GET", "POST"])
def quote_revision_create(request, pk):
    owner = account_owner(request.user)
    source_quote = get_object_or_404(
        Quote.objects.filter(owner=owner, rfq__owner=owner, rfq__customer__owner=owner)
        .select_related("rfq", "rfq__customer"),
        pk=pk,
    )
    return _quote_create_page(request, source_quote.rfq, source_quote=source_quote)


def _quote_create_page(request, rfq, source_quote=None):
    owner = account_owner(request.user)
    all_lines = RFQLine.objects.filter(owner=owner, rfq=rfq)
    lines = list(all_lines.filter(
        Q(product__isnull=True) | Q(product__owner=owner),
    ).select_related("product"))
    has_foreign_product_line = len(lines) != all_lines.count()
    if source_quote:
        pricing_settings = source_quote
        initial = {
            "issue_date": timezone.localdate(),
            "valid_until": timezone.localdate() + timedelta(days=7),
            "tax_rate_percent": source_quote.tax_rate_percent,
            "payment_terms": source_quote.payment_terms,
            "delivery_terms": source_quote.delivery_terms,
        }
    else:
        pricing_settings, _ = QuotePricingSettings.objects.get_or_create(owner=owner)
        today = timezone.localdate()
        initial = {
            "issue_date": today,
            "valid_until": today + timedelta(days=7),
            "tax_rate_percent": 0,
        }
    prior_lines = {
        line.rfq_line_id: line for line in source_quote.lines.select_related("supplier_offer")
    } if source_quote else {}
    for line in lines:
        prior = prior_lines.get(line.pk)
        if prior:
            initial[f"offer_{line.pk}"] = prior.supplier_offer_id
            initial[f"discount_{line.pk}"] = prior.discount_percent
    form = QuoteCreateForm(
        request.POST or None, owner=owner, lines=lines,
        pricing_settings=pricing_settings, initial=initial,
    )
    line_rows = []
    for line in lines:
        offer_name, discount_name = form.line_fields[line.pk]
        has_offer = form.fields[offer_name].queryset.exists()
        line_rows.append({
            "line": line,
            "offer_field": form[offer_name],
            "discount_field": form[discount_name],
            "has_offer": has_offer,
        })
    can_create = bool(lines) and not has_foreign_product_line and all(row["has_offer"] for row in line_rows)
    valid_pricing = request.method == "POST" and can_create and form.is_valid()
    preview = form.pricing_rows if valid_pricing and request.POST.get("action") == "preview" else []
    if valid_pricing and not preview:
        with transaction.atomic():
            if source_quote:
                previous = Quote.objects.select_for_update().get(pk=source_quote.pk, owner=owner)
                newer = previous.revisions.filter(owner=owner).first()
                if newer:
                    messages.info(request, "A newer revision exists. Open it to prepare another revision.")
                    return redirect("dashboard:quote_detail", pk=newer.pk)
            quote = Quote(
                owner=owner,
                rfq=rfq,
                revision_of=source_quote,
                number=source_quote.number if source_quote else "",
                revision=source_quote.revision + 1 if source_quote else 1,
                issue_date=form.cleaned_data["issue_date"],
                valid_until=form.cleaned_data["valid_until"],
                tax_rate_percent=form.cleaned_data["tax_rate_percent"],
                payment_terms=form.cleaned_data["payment_terms"],
                delivery_terms=form.cleaned_data["delivery_terms"],
                target_margin_percent=pricing_settings.target_margin_percent,
                minimum_margin_percent=pricing_settings.minimum_margin_percent,
                maximum_discount_percent=pricing_settings.maximum_discount_percent,
                status=(
                    Quote.Status.NEEDS_REVIEW
                    if any(row["needs_review"] for row in form.pricing_rows)
                    else Quote.Status.READY
                ),
            )
            quote.full_clean()
            quote.save()
            if not quote.number:
                quote.number = f"QT-{quote.issue_date.year}-{quote.pk:06d}"
                quote.save(update_fields=["number", "updated_at"])
            for row in form.pricing_rows:
                quote_line = QuoteLine(
                    owner=owner,
                    quote=quote,
                    rfq_line=row["rfq_line"],
                    supplier_offer=row["supplier_offer"],
                    quantity=row["rfq_line"].quantity,
                    unit=row["rfq_line"].unit,
                    landed_cost_per_unit=row["landed_cost_per_unit"],
                    discount_percent=row["discount_percent"],
                    selling_price_per_unit=row["selling_price_per_unit"],
                )
                quote_line.full_clean()
                quote_line.save()
        messages.success(request, "Quotation saved.")
        return redirect("dashboard:quote_detail", pk=quote.pk)
    return render(request, "dashboard/quote_create.html", {
        "rfq": rfq,
        "form": form,
        "lines": lines,
        "line_rows": line_rows,
        "preview": preview,
        "can_create": can_create,
        "has_foreign_product_line": has_foreign_product_line,
        "pricing_settings": pricing_settings,
        "source_quote": source_quote,
    })


@login_required
def quote_detail(request, pk):
    owner = account_owner(request.user)
    visible_lines = QuoteLine.objects.filter(
        owner=owner,
        rfq_line__owner=owner,
        rfq_line__rfq__owner=owner, rfq_line__rfq_id=F("quote__rfq_id"),
        supplier_offer__rfq_line_id=F("rfq_line_id"), supplier_offer__owner=owner,
        supplier_offer__supplier__owner=owner,
    ).filter(
        Q(rfq_line__product__isnull=True) | Q(rfq_line__product__owner=owner),
    ).select_related(
        "rfq_line", "rfq_line__product", "supplier_offer", "supplier_offer__supplier",
    )
    quote = get_object_or_404(
        Quote.objects.filter(
            owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
        )
        .select_related("rfq", "rfq__customer", "approved_by")
        .prefetch_related(Prefetch("lines", queryset=visible_lines)),
        pk=pk,
    )
    quote.revision_history = Quote.objects.filter(owner=owner, number=quote.number).order_by("revision")
    status_form = QuoteStatusForm(quote=quote)
    return render(request, "dashboard/quote_detail.html", {
        "quote": quote, "status_form": status_form,
        "can_approve": can_manage_account(request.user),
        "can_update_status": bool(status_form.fields["status"].choices),
    })


@login_required
def quote_list(request):
    owner = account_owner(request.user)
    quotes = Quote.objects.filter(
        owner=owner, rfq__owner=owner, rfq__customer__owner=owner,
    ).select_related("rfq", "rfq__customer").order_by("-created_at", "-id")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        quotes = quotes.filter(
            Q(number__icontains=query) | Q(rfq__reference__icontains=query)
            | Q(rfq__customer__name__icontains=query) | Q(rfq__customer__company_name__icontains=query),
        )
    if status not in Quote.Status.values:
        status = ""
    if status:
        quotes = quotes.filter(status=status)
    return render(request, "dashboard/quote_list.html", {
        "quotes": Paginator(quotes, 25).get_page(request.GET.get("page")),
        "query": query, "status": status, "status_choices": Quote.Status.choices,
        "today": timezone.localdate(),
    })


@login_required
@require_POST
def quote_update_status(request, pk):
    owner = account_owner(request.user)
    quote = get_object_or_404(
        Quote.objects.filter(owner=owner, rfq__owner=owner, rfq__customer__owner=owner),
        pk=pk,
    )
    form = QuoteStatusForm(request.POST, quote=quote)
    if not form.is_valid():
        return HttpResponseBadRequest("Choose a valid quotation status.")
    target = form.cleaned_data["status"]
    # Keep the pipeline manual: each user action must match one of these transitions.
    transitions = {
        Quote.Status.READY: {Quote.Status.SENT},
        Quote.Status.APPROVED: {Quote.Status.SENT},
        Quote.Status.SENT: {Quote.Status.ACCEPTED, Quote.Status.LOST, Quote.Status.EXPIRED},
    }
    if target not in transitions.get(quote.status, set()):
        return HttpResponseBadRequest("That quotation status transition is not allowed.")
    now = timezone.now()
    today = timezone.localdate()
    if target == Quote.Status.SENT:
        if quote.valid_until < today:
            return HttpResponseBadRequest("An expired quotation cannot be marked as sent.")
        quote.sent_at = now
    elif target == Quote.Status.EXPIRED:
        if quote.valid_until >= today:
            return HttpResponseBadRequest("A quotation can be marked expired after its validity date.")
        quote.closed_at = now
    else:
        quote.closed_at = now
    quote.status = target
    with transaction.atomic():
        quote.full_clean()
        quote.save(update_fields=["status", "sent_at", "closed_at", "updated_at"])
        AuditEvent.objects.create(
            owner=owner, actor=request.user,
            action=AuditEvent.Action.QUOTE_STATUS_CHANGED,
            object_type="quote", object_id=str(quote.pk),
        )
    return redirect("dashboard:quote_detail", pk=quote.pk)


@login_required
@require_http_methods(["GET"])
def quote_pdf(request, pk, preview=False):
    owner = account_owner(request.user)
    visible_lines = QuoteLine.objects.filter(
        owner=owner,
        rfq_line__owner=owner,
        rfq_line__rfq__owner=owner, rfq_line__rfq_id=F("quote__rfq_id"),
        supplier_offer__rfq_line_id=F("rfq_line_id"), supplier_offer__owner=owner,
        supplier_offer__supplier__owner=owner,
    ).filter(
        Q(rfq_line__product__isnull=True) | Q(rfq_line__product__owner=owner),
    ).select_related("rfq_line", "rfq_line__product")
    quote = get_object_or_404(
        Quote.objects.filter(owner=owner, rfq__owner=owner, rfq__customer__owner=owner)
        .select_related("rfq__customer")
        .prefetch_related(Prefetch("lines", queryset=visible_lines)),
        pk=pk,
    )
    visible = list(quote.lines.all())
    if len(visible) != QuoteLine.objects.filter(quote=quote).count():
        raise PermissionDenied("The quotation contains records outside this account boundary.")
    if not visible:
        return HttpResponseBadRequest("A quotation must contain at least one item.")
    if quote.needs_review or (
        not (quote.approved_by_id and quote.approved_at) and any(line.needs_review for line in visible)
    ):
        raise PermissionDenied("A quotation awaiting manager review cannot be issued to a customer.")
    from .documents import build_quote_pdf
    response = HttpResponse(build_quote_pdf(quote), content_type="application/pdf")
    response["Cache-Control"] = "private, no-store"
    disposition = "inline" if preview else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{quote.number}-R{quote.revision}.pdf"'
    return response


@login_required
@require_POST
def quote_approve(request, pk):
    owner = account_owner(request.user)
    quote = get_object_or_404(
        Quote.objects.filter(
            owner=owner,
            rfq__owner=owner,
            rfq__customer__owner=owner,
            status=Quote.Status.NEEDS_REVIEW,
        ),
        pk=pk,
    )
    if not can_manage_account(request.user):
        raise PermissionDenied("Only the owner or a manager can approve quotations that need review.")
    quote.status = Quote.Status.APPROVED
    quote.approved_by = request.user
    quote.approved_at = timezone.now()
    with transaction.atomic():
        quote.full_clean()
        quote.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        AuditEvent.objects.create(
            owner=owner, actor=request.user,
            action=AuditEvent.Action.QUOTE_APPROVED,
            object_type="quote", object_id=str(quote.pk),
        )
    return redirect("dashboard:quote_detail", pk=quote.pk)


class OwnedListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/catalogue_list.html"
    context_object_name = "records"
    paginate_by = 25
    search_fields = ()
    title = "Catalogue"
    singular = "record"

    def get_queryset(self):
        records = self.model.objects.filter(owner=account_owner(self.request.user))
        query = self.request.GET.get("q", "").strip()
        if query and self.search_fields:
            matches = Q()
            for field in self.search_fields:
                matches |= Q(**{f"{field}__icontains": query})
            records = records.filter(matches)
        return records

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            title=self.title, singular=self.singular,
            create_url=f"dashboard:{self.singular}_create",
            query=self.request.GET.get("q", "").strip(),
        )
        return data


class OwnedCreateView(LoginRequiredMixin, CreateView):
    template_name = "dashboard/catalogue_form.html"
    success_message = "Saved"
    title = "Add record"
    singular = "record"

    def form_valid(self, form):
        form.instance.owner = account_owner(self.request.user)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(f"dashboard:{self.singular}_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(title=self.title, singular=self.singular)
        return data


class OwnedUpdateView(LoginRequiredMixin, UpdateView):
    def get_queryset(self):
        return self.model.objects.filter(owner=account_owner(self.request.user))

    def get_success_url(self):
        return reverse(f"dashboard:{self.singular}_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(title=self.title, singular=self.singular)
        return data


class OwnedDeleteView(LoginRequiredMixin, DeleteView):
    template_name = "dashboard/catalogue_confirm_delete.html"

    def get_queryset(self):
        return self.model.objects.filter(owner=account_owner(self.request.user))

    def get_success_url(self):
        return reverse(f"dashboard:{self.singular}_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(title=f"Delete {self.singular}", singular=self.singular)
        return data


class CustomerListView(OwnedListView):
    model, title, singular = Customer, "Customers", "customer"
    search_fields = ("name", "company_name", "email", "phone")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["export_url"] = "dashboard:customer_csv_export"
        return data


class CustomerCreateView(OwnedCreateView):
    model, form_class, title, singular = Customer, CustomerForm, "Add customer", "customer"


class CustomerUpdateView(OwnedUpdateView):
    model, form_class, title, singular = Customer, CustomerForm, "Edit customer", "customer"


class CustomerDeleteView(OwnedDeleteView):
    model, singular = Customer, "customer"


class SupplierListView(OwnedListView):
    model, title, singular = Supplier, "Suppliers", "supplier"
    search_fields = ("name", "company_name", "email", "phone")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["export_url"] = "dashboard:supplier_csv_export"
        return data


class SupplierCreateView(OwnedCreateView):
    model, form_class, title, singular = Supplier, SupplierForm, "Add supplier", "supplier"


class SupplierUpdateView(OwnedUpdateView):
    model, form_class, title, singular = Supplier, SupplierForm, "Edit supplier", "supplier"


class SupplierDeleteView(OwnedDeleteView):
    model, singular = Supplier, "supplier"


class ProductListView(OwnedListView):
    model, title, singular = Product, "Products", "product"
    search_fields = ("name", "grade", "dimensions", "shape")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update(
            import_url="dashboard:product_csv_import",
            export_url="dashboard:product_csv_export",
        )
        return data


class ProductCreateView(OwnedCreateView):
    model, form_class, title, singular = Product, ProductForm, "Add product", "product"


class ProductUpdateView(OwnedUpdateView):
    model, form_class, title, singular = Product, ProductForm, "Edit product", "product"


class ProductDeleteView(OwnedDeleteView):
    model, singular = Product, "product"
