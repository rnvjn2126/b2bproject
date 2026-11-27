from django.urls import path

from . import views


app_name = "inventory"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("actions/<slug:kind>/", views.action, name="action"),
    path("reservations/<int:pk>/", views.reservation_action, name="reservation_action"),
    path("lots/<int:pk>/certificate/upload/", views.certificate_upload, name="certificate_upload"),
    path("lots/<int:pk>/certificate/", views.certificate_download, name="certificate_download"),
]
