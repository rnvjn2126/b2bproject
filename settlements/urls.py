from django.urls import path

from . import views

app_name = "settlements"
urlpatterns = [
    path("", views.statement, name="statement"),
    path("invoices/<int:pk>/reminder/", views.reminder, name="reminder"),
]
