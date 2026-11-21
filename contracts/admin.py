from django.contrib import admin

from .models import Assignment, Crew, Payment, WorkContract, WorkLog


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0


@admin.register(WorkContract)
class WorkContractAdmin(admin.ModelAdmin):
    list_display = ("work_type", "construction_object", "volume", "unit", "price", "status", "end_date")
    list_filter = ("status", "unit")
    search_fields = ("work_type",)
    inlines = [AssignmentInline]


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ("name", "leader", "phone")
    filter_horizontal = ("members",)


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("date", "assignment", "volume", "people")
    list_filter = ("date",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "amount", "contract", "assignment")
    list_filter = ("kind", "date")
