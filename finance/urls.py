from django.urls import path

from core import views as core_views

from . import views as v

urlpatterns = [
    path("", v.home, name="finance_home"),
    path("object/<int:pk>/", v.object_plan, name="finance_object"),
    path("debts/", v.debts, name="finance_debts"),
    path("calendar/", v.calendar, name="finance_calendar"),
    path("lines/new/", v.line_new, name="finance_line_new"),
    path("lines/<int:pk>/", v.line_edit, name="finance_line_edit"),
    path("lines/<int:pk>/pay/", v.line_pay, name="finance_line_pay"),
    path("lines/<int:pk>/delete/", v.line_delete, name="finance_line_delete"),
    path("cash/", core_views.finance_list, name="finance_list"),
    path("cash/new/", core_views.transaction_create, name="transaction_create"),
]
