from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.profile, name="company_profile"),
    path("edit/", v.edit, name="company_edit"),
    path("accounts/new/", v.account_new, name="company_account_new"),
    path("accounts/<int:pk>/", v.account_edit, name="company_account_edit"),
    path("docs/", v.docs, name="company_docs"),
    path("docs/new/", v.doc_new, name="company_doc_new"),
    path("docs/<int:pk>/", v.doc_edit, name="company_doc_edit"),
    path("structure/", v.structure, name="company_structure"),
    path("structure/new/", v.department_new, name="company_department_new"),
    path("structure/<int:pk>/", v.department_edit, name="company_department_edit"),
    path("staff/", v.staff, name="company_staff"),
    path("staff/new/", v.employee_new, name="company_employee_new"),
    path("staff/<int:pk>/", v.employee_edit, name="company_employee_edit"),
    path("schedule/", v.schedule, name="company_schedule"),
    path("schedule/new/", v.unit_new, name="company_unit_new"),
    path("schedule/<int:pk>/", v.unit_edit, name="company_unit_edit"),
]
