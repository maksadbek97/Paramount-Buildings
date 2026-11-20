from django.contrib import admin

from .models import Client, ConstructionObject, ObjectDocument


class DocumentInline(admin.TabularInline):
    model = ObjectDocument
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email")
    search_fields = ("name", "phone")


@admin.register(ConstructionObject)
class ConstructionObjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "manager", "status", "start_date", "end_date")
    list_filter = ("status",)
    search_fields = ("name", "address")
    inlines = [DocumentInline]
