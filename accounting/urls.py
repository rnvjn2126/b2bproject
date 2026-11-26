from django.urls import path

from . import views
from .models import Journal

app_name = "accounting"
urlpatterns = [
    path("", views.home, name="home"),
    path("periods/<int:pk>/lock/", views.close_period, name="close_period"),
    path("chart/", views.chart, name="chart"),
    path("chart/groups/new/", views.add_chart_record, {"kind": "group"}, name="add_group"),
    path("chart/ledgers/new/", views.add_chart_record, {"kind": "ledger"}, name="add_ledger"),
    path("chart/branches/new/", views.add_chart_record, {"kind": "branch"}, name="add_branch"),
    path("chart/cost-centres/new/", views.add_chart_record, {"kind": "cost-centre"}, name="add_centre"),
    path("journals/", views.journals, name="journals"),
    path("journals/new/", views.journal_create, name="journal_create"),
    path("vouchers/receipt/new/", views.cash_voucher_create, {"kind": Journal.Kind.RECEIPT}, name="receipt"),
    path("vouchers/payment/new/", views.cash_voucher_create, {"kind": Journal.Kind.PAYMENT}, name="payment"),
    path("vouchers/contra/new/", views.cash_voucher_create, {"kind": Journal.Kind.CONTRA}, name="contra"),
    path("journals/<int:pk>/", views.journal_detail, name="journal"),
    path("journals/<int:pk>/reverse/", views.reverse_journal, name="reverse"),
    path("trial-balance/", views.balances, name="trial_balance"),
    path("statements/", views.statements, name="statements"),
    path("ledgers/<int:pk>/", views.balances, name="ledger"),
]
