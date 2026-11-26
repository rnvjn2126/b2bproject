from django.urls import path

from . import procurement_views, views
from .models import SalesOrder

app_name = "orders"
urlpatterns = [
    path("", views.sales_orders, name="sales_list"),
    path("pending/", procurement_views.pending, name="pending"),
    path("requirements/<int:pk>/purchase/", procurement_views.purchase_create, name="purchase_create"),
    path("requirements/<int:pk>/dispatch/", procurement_views.movement, {"receipt": False}, name="dispatch"),
    path("purchases/<int:pk>/", procurement_views.purchase_detail, name="purchase_detail"),
    path("purchases/<int:pk>/approve/", procurement_views.purchase_status, {"target": SalesOrder.Status.APPROVED}, name="purchase_approve"),
    path("purchases/<int:pk>/cancel/", procurement_views.purchase_status, {"target": SalesOrder.Status.CANCELLED}, name="purchase_cancel"),
    path("purchases/<int:pk>/receipt/", procurement_views.movement, {"receipt": True}, name="receipt"),
    path("purchases/<int:pk>/document.pdf", procurement_views.purchase_pdf, name="purchase_pdf"),
    path("from-quotation/<int:pk>/", views.convert, name="convert"),
    path("<int:pk>/", views.sales_detail, name="sales_detail"),
    path("<int:pk>/approve/", views.sales_status, {"target": SalesOrder.Status.APPROVED}, name="sales_approve"),
    path("<int:pk>/cancel/", views.sales_status, {"target": SalesOrder.Status.CANCELLED}, name="sales_cancel"),
    path("<int:pk>/document.pdf", views.sales_pdf, name="sales_pdf"),
]
