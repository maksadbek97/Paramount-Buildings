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


from .models import ObjectMedia, SafetyRecord, TransportRequest  # noqa: E402


@admin.register(TransportRequest)
class TransportRequestAdmin(admin.ModelAdmin):
    list_display = ("number", "construction_object", "kind", "task", "date", "status")
    list_filter = ("status", "kind")


@admin.register(SafetyRecord)
class SafetyRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "construction_object", "kind", "date", "valid_until", "confirmed")
    list_filter = ("kind",)


@admin.register(ObjectMedia)
class ObjectMediaAdmin(admin.ModelAdmin):
    list_display = ("__str__", "construction_object", "category", "date")
