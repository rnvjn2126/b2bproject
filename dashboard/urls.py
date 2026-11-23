from django.urls import path

from . import views
from . import billing_views

app_name = "dashboard"
urlpatterns = [
    path("plans/", billing_views.plans, name="plans"),
    path("signup/", billing_views.signup, name="signup"),
    path("billing/", billing_views.billing_overview, name="billing"),
    path("billing/checkout/", billing_views.checkout_create, name="checkout_create"),
    path("billing/checkout/<uuid:pk>/", billing_views.checkout, name="checkout"),
    path("billing/checkout/<uuid:pk>/cancel/", billing_views.cancel_checkout, name="cancel_checkout"),
    path("billing/webhooks/test/", billing_views.test_webhook, name="billing_test_webhook"),
    path("", views.home, name="home"),
    path("preferences/", views.preferences, name="preferences"),
    path("company-defaults/", views.company_defaults, name="company_defaults"),
    path("team/", views.team_list, name="team_list"),
    path("team/activity/", views.activity_log, name="activity_log"),
    path("reports/", views.reports, name="reports"),
    path("team/invitations/<slug:token>/accept/", views.team_invite_accept, name="team_invite_accept"),
    path("team/members/<int:pk>/role/", views.team_member_role, name="team_member_role"),
    path("team/members/<int:pk>/remove/", views.team_member_remove, name="team_member_remove"),
    path("team/invitations/<int:pk>/revoke/", views.team_invitation_revoke, name="team_invitation_revoke"),
    path("comparisons/", views.comparisons, name="comparisons"),
    path("customers/<int:pk>/", views.contact_detail, {"kind": "customer"}, name="customer_detail"),
    path("suppliers/<int:pk>/", views.contact_detail, {"kind": "supplier"}, name="supplier_detail"),
    path("rfqs/", views.rfq_list, name="rfq_list"),
    path("rfqs/new/", views.rfq_create, name="rfq_create"),
    path("rfqs/<int:pk>/", views.rfq_detail, name="rfq_detail"),
    path("rfqs/<int:pk>/status/", views.rfq_update_status, name="rfq_update_status"),
    path("rfqs/<int:pk>/follow-ups/new/", views.followup_create, name="followup_create"),
    path("rfqs/<int:pk>/lines/<int:line_pk>/offers/new/", views.supplier_offer_create, name="supplier_offer_create"),
    path("follow-ups/", views.followup_list, name="followup_list"),
    path("follow-ups/<int:pk>/complete/", views.followup_complete, name="followup_complete"),
    path("rfqs/<int:pk>/quote/", views.quote_create, name="quote_create"),
    path("quotes/", views.quote_list, name="quote_list"),
    path("quotes/<int:pk>/revisions/new/", views.quote_revision_create, name="quote_revision_create"),
    path("quotes/settings/", views.quote_pricing_settings, name="quote_pricing_settings"),
    path("quotes/<int:pk>/", views.quote_detail, name="quote_detail"),
    path("quotes/<int:pk>/status/", views.quote_update_status, name="quote_update_status"),
    path("quotes/<int:pk>/preview/", views.quote_pdf, {"preview": True}, name="quote_preview"),
    path("quotes/<int:pk>/pdf/", views.quote_pdf, name="quote_pdf"),
    path("quotes/<int:pk>/approve/", views.quote_approve, name="quote_approve"),
    path("products/import/", views.product_csv_import, name="product_csv_import"),
    path("products/export.csv", views.product_csv_export, name="product_csv_export"),
    path("customers/export.csv", views.customer_csv_export, name="customer_csv_export"),
    path("suppliers/export.csv", views.supplier_csv_export, name="supplier_csv_export"),
]
for slug, label in (("customer", "customers"), ("supplier", "suppliers"), ("product", "products")):
    urlpatterns += [
        path(f"{label}/", getattr(views, f"{label.title()[:-1]}ListView").as_view(), name=f"{slug}_list"),
        path(f"{label}/new/", getattr(views, f"{label.title()[:-1]}CreateView").as_view(), name=f"{slug}_create"),
        path(f"{label}/<int:pk>/edit/", getattr(views, f"{label.title()[:-1]}UpdateView").as_view(), name=f"{slug}_update"),
        path(f"{label}/<int:pk>/delete/", getattr(views, f"{label.title()[:-1]}DeleteView").as_view(), name=f"{slug}_delete"),
    ]
