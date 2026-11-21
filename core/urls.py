from django.urls import path

from contracts import views as cv

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("menu/", views.menu, name="menu"),
    path("objects/", views.object_list, name="object_list"),
    path("objects/new/", views.object_create, name="object_create"),
    path("objects/<int:pk>/", views.object_detail, name="object_detail"),
    path("objects/<int:pk>/edit/", views.object_edit, name="object_edit"),
    path("contracts/", cv.contract_list, name="contract_list"),
    path("contracts/new/", cv.contract_create, name="contract_create"),
    path("contracts/<int:pk>/", cv.contract_detail, name="contract_detail"),
    path("contracts/<int:pk>/edit/", cv.contract_edit, name="contract_edit"),
    path("contracts/<int:pk>/assign/", cv.assignment_create, name="assignment_create"),
    path("worklog/new/", cv.worklog_create, name="worklog_create"),
    path("worklog/<int:pk>/review/", cv.worklog_review, name="worklog_review"),
    path("pto/", cv.pto, name="pto"),
    path("contracts/<int:pk>/norm/", cv.norm_create, name="norm_create"),
    path("history/", views.history, name="history"),
    path("payments/new/", cv.payment_create, name="payment_create"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.employee_create, name="employee_create"),
    path("staff/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("crews/new/", cv.crew_create, name="crew_create"),
    path("crews/<int:pk>/edit/", cv.crew_edit, name="crew_edit"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("warehouse/", views.warehouse_list, name="warehouse_list"),
    path("warehouse/materials/new/", views.material_create, name="material_create"),
    path("warehouse/movements/new/", views.movement_create, name="movement_create"),
    path("finance/", views.finance_list, name="finance_list"),
    path("finance/new/", views.transaction_create, name="transaction_create"),
]
