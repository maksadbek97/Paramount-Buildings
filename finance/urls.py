from django.urls import path

from core import views as core_views

from . import views as v

urlpatterns = [
    path("", v.home, name="finance_home"),
    path("object/<int:pk>/", v.object_plan, name="finance_object"),
    path("debts/", v.debts, name="finance_debts"),
    path("api/", v.api, name="finance_api"),
    path("cash/", core_views.finance_list, name="finance_list"),
    path("cash/new/", core_views.transaction_create, name="transaction_create"),
]
