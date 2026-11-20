from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("objects/", views.object_list, name="object_list"),
    path("objects/<int:pk>/", views.object_detail, name="object_detail"),
    path("staff/", views.staff_list, name="staff_list"),
    path("warehouse/", views.warehouse_list, name="warehouse_list"),
    path("finance/", views.finance_list, name="finance_list"),
]
