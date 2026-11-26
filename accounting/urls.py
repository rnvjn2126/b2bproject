from django.urls import path

from . import views

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
    path("journals/<int:pk>/", views.journal_detail, name="journal"),
    path("journals/<int:pk>/reverse/", views.reverse_journal, name="reverse"),
    path("trial-balance/", views.balances, name="trial_balance"),
    path("ledgers/<int:pk>/", views.balances, name="ledger"),
]
