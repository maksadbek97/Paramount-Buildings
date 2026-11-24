from datetime import date

from django import forms

from core.forms import StyledMixin
from objects.models import ConstructionObject

from .models import PlanLine


class PlanLineForm(StyledMixin, forms.ModelForm):
    fieldsets = [
        ("Строка финплана", "Объект и блок, как лист и раздел в таблице «Фин план»",
         ["construction_object", "section", "name", "note"]),
        ("План", "Сколько и когда должны получить или оплатить", ["plan_amount", "plan_date"]),
        ("Факт", "Сколько уже получено или оплачено. Остаток посчитается сам", ["fact_amount", "fact_date"]),
    ]
    wide = {"name", "note"}

    class Meta:
        model = PlanLine
        fields = ["construction_object", "section", "name", "plan_amount", "plan_date", "fact_amount", "fact_date",
                  "note"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Например: Бригада — оплата за работу"}),
                   "note": forms.TextInput(attrs={"placeholder": "Например: аванс, объём не подтверждён"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["construction_object"].queryset = ConstructionObject.objects.exclude(status="archive")
        self.fields["plan_amount"].required = False
        self.fields["fact_amount"].required = False
        for f in ("plan_amount", "fact_amount"):
            self.fields[f].widget.attrs.pop("required", None)

    def clean(self):
        data = super().clean()
        for f in ("plan_amount", "fact_amount"):
            if data.get(f) is None:
                data[f] = 0
        if data.get("fact_amount") and not data.get("fact_date"):
            data["fact_date"] = date.today()
        if data.get("section") == PlanLine.Section.DEBT:
            data["construction_object"] = None
        elif data.get("section") and not data.get("construction_object"):
            self.add_error("construction_object", "Укажите объект.")
        return data


class PayForm(forms.Form):
    amount = forms.DecimalField(label="Сумма", required=False, min_value=0, max_digits=16, decimal_places=2)
    date = forms.DateField(label="Дата", required=False)

    def clean_amount(self):
        return self.cleaned_data.get("amount")

    def full_clean(self):
        if self.is_bound:
            data = self.data.copy()
            if isinstance(data.get("amount"), str):
                data["amount"] = "".join(data["amount"].split()).replace(",", ".")
            self.data = data
        super().full_clean()
