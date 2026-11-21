from django.contrib import admin

from .models import Material, StockMovement, Supplier

admin.site.register(Supplier)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "price", "stock", "min_stock")
    search_fields = ("name",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "material", "quantity", "supplier", "construction_object")
    list_filter = ("kind", "date")


from .models import Inventory, InventoryLine, PurchaseRequest, Warehouse  # noqa: E402

admin.site.register(Warehouse)


class InventoryLineInline(admin.TabularInline):
    model = InventoryLine
    extra = 0


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("number", "warehouse", "date", "status")
    inlines = [InventoryLineInline]


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("number", "material", "quantity", "construction_object", "status", "supplier")
    list_filter = ("status",)
