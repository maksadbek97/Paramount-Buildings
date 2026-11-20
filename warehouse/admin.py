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
