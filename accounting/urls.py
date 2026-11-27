from django.urls import include, path

from banking import views as bank_views
from invoicing import views as invoice_views

from . import views, voucher_views
from .models import Journal

app_name = "accounting"
urlpatterns = [
    path("", views.home, name="home"),
    path("bank-reconciliation/upload/", bank_views.statement_upload, name="bank_statement_upload"),
    path("bank-reconciliation/", bank_views.reconciliation_report, name="bank_reconciliation"),
    path("bank-reconciliation/<int:pk>/confirm/", bank_views.reconciliation_confirm, name="bank_reconciliation_confirm"),
    path("settlements/", include("settlements.urls")),
    path("invoice-drafts/", invoice_views.invoice_movements, name="invoice_movements"),
    path("invoice-drafts/movements/<int:pk>/", invoice_views.invoice_prepare, name="invoice_prepare"),
    path("invoice-drafts/<int:pk>/", invoice_views.invoice_draft, name="invoice_draft"),
    path("invoice-drafts/movements/<int:pk>/actuals/", invoice_views.invoice_prepare, {"replace_estimate": True},
         name="invoice_actuals"),
    path("invoice-drafts/<int:pk>/issue/", invoice_views.invoice_issue, name="invoice_issue"),
    path("invoice-drafts/issued/<int:pk>/cancel/", invoice_views.invoice_adjust, {"action": "cancel"}, name="invoice_cancel"),
    path("invoice-drafts/issued/<int:pk>/return/", invoice_views.invoice_adjust, {"action": "return"}, name="invoice_return"),
    path("invoice-drafts/issued/<int:pk>/print/", invoice_views.invoice_print, name="invoice_print"),
    path("gst-settings/", invoice_views.gst_settings, name="gst_settings"),
    path("gst-settings/registrations/<int:pk>/branding/", invoice_views.registration_branding, name="registration_branding"),
    path("periods/<int:pk>/lock/", views.close_period, name="close_period"),
    path("chart/", views.chart, name="chart"),
    path("chart/groups/new/", views.add_chart_record, {"kind": "group"}, name="add_group"),
    path("chart/ledgers/new/", views.add_chart_record, {"kind": "ledger"}, name="add_ledger"),
    path("chart/branches/new/", views.add_chart_record, {"kind": "branch"}, name="add_branch"),
    path("chart/cost-centres/new/", views.add_chart_record, {"kind": "cost-centre"}, name="add_centre"),
    path("journals/", views.journals, name="journals"),
    path("journals/new/", views.journal_create, name="journal_create"),
    path("vouchers/", voucher_views.vouchers, name="vouchers"),
    path("vouchers/new/", voucher_views.voucher_edit, name="voucher_create"),
    path("vouchers/<int:pk>/", voucher_views.voucher_detail, name="voucher"),
    path("vouchers/<int:pk>/edit/", voucher_views.voucher_edit, name="voucher_edit"),
    path("vouchers/<int:pk>/approve/", voucher_views.voucher_approve, name="voucher_approve"),
    path("day-book/", voucher_views.day_book, name="day_book"),
    path("vouchers/receipt/new/", views.cash_voucher_create, {"kind": Journal.Kind.RECEIPT}, name="receipt"),
    path("vouchers/payment/new/", views.cash_voucher_create, {"kind": Journal.Kind.PAYMENT}, name="payment"),
    path("vouchers/contra/new/", views.cash_voucher_create, {"kind": Journal.Kind.CONTRA}, name="contra"),
    path("journals/<int:pk>/", views.journal_detail, name="journal"),
    path("journals/<int:pk>/reverse/", views.reverse_journal, name="reverse"),
    path("trial-balance/", views.balances, name="trial_balance"),
    path("statements/", views.statements, name="statements"),
    path("audit/", views.audit_history, name="audit_history"),
    path("ledgers/<int:pk>/", views.balances, name="ledger"),
]
