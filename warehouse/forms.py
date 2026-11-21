from datetime import date, timedelta

from django import forms

from core.forms import StyledMixin

from .models import PurchaseRequest, Supplier, Warehouse


class WarehouseForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "kind", "construction_object", "keeper"]


class SupplierForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "address"]


class PurchaseRequestForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = PurchaseRequest
        fields = ["construction_object", "warehouse", "material", "quantity", "needed_by", "supplier", "price",
                  "payment_terms", "note"]
        help_texts = {"supplier": "Можно выбрать позже, при согласовании",
                      "price": "Система сравнит с прошлыми закупками"}

    def __init__(self, *args, user=None, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("needed_by", date.today() + timedelta(days=3))
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_quantity(self):
        q = self.cleaned_data["quantity"]
        if q <= 0:
            raise forms.ValidationError("Количество должно быть больше нуля.")
        return q

    def save(self, commit=True):
        if self.user and self.user.is_authenticated and not self.instance.pk:
            self.instance.author = self.user
        return super().save(commit)


class InventoryStartForm(StyledMixin, forms.Form):
    warehouse = forms.ModelChoiceField(Warehouse.objects.all(), label="Склад")
    note = forms.CharField(label="Примечание", required=False)
