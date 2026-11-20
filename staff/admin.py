from django.contrib import admin

from .models import Employee, Position, Task

admin.site.register(Position)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "phone", "is_active")
    list_filter = ("position", "is_active")
    search_fields = ("full_name", "phone")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "construction_object", "assignee", "status", "priority", "due_date")
    list_filter = ("status", "priority")
    search_fields = ("title",)
