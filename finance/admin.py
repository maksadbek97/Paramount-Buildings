from django.contrib import admin

from .models import Estimate, EstimateItem, Transaction


class EstimateItemInline(admin.TabularInline):
    model = EstimateItem
    extra = 1


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ("title", "construction_object", "total", "created_at")
    inlines = [EstimateItemInline]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "amount", "construction_object", "category")
    list_filter = ("kind", "date")
