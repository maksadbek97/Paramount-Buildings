from django.contrib import admin

from .models import BankAccount, Company, CompanyDocument, Department, StaffUnit

admin.site.register(Company)
admin.site.register(BankAccount)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "head", "order")


@admin.register(StaffUnit)
class StaffUnitAdmin(admin.ModelAdmin):
    list_display = ("department", "position", "count", "salary")
    list_filter = ("department",)


@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ("kind", "number", "date", "title", "valid_until")
    list_filter = ("kind",)
    search_fields = ("title", "number")
