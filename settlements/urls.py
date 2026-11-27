from django.urls import path

from . import views

app_name = "settlements"
urlpatterns = [
    path("", views.statement, name="statement"),
    path("payments/new/", views.payment_create, name="payment_create"),
    path("payments/<int:pk>/", views.payment_detail, name="payment_detail"),
    path("payments/<int:pk>/allocate/", views.payment_allocate, name="payment_allocate"),
    path("payments/<int:pk>/allocations/<int:allocation_pk>/release/", views.payment_allocate, name="payment_release"),
    path("credit-terms/", views.credit_profile, name="credit_profile"),
    path("invoices/<int:pk>/due-date/", views.invoice_terms, {"mode": "due"}, name="invoice_due"),
    path("invoices/<int:pk>/mse/", views.invoice_terms, {"mode": "mse"}, name="invoice_mse"),
    path("invoices/<int:pk>/reminder/", views.reminder, name="reminder"),
]
