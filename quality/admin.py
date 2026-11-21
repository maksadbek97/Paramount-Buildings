from django.contrib import admin

from .models import DailyReport, Remark


@admin.register(Remark)
class RemarkAdmin(admin.ModelAdmin):
    list_display = ("number", "construction_object", "priority", "status", "responsible", "deadline")
    list_filter = ("status", "priority")
    search_fields = ("number", "description")


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ("date", "construction_object", "workers_count", "confirmed")
    list_filter = ("confirmed",)
