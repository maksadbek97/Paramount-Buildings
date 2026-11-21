from datetime import date, timedelta

from django import forms

from core.forms import StyledMixin

from .models import DailyReport, Remark


class RemarkForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Remark
        fields = ["construction_object", "section", "floor", "place", "description", "photo", "priority",
                  "responsible", "deadline"]
        help_texts = {"responsible": "Если не выбрать — назначится прораб объекта"}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("deadline", date.today() + timedelta(days=3))
        super().__init__(*args, **kwargs)
        self.fields["responsible"].required = False
        self.fields["responsible"].widget.attrs.pop("required", None)

    def clean(self):
        data = super().clean()
        obj = data.get("construction_object")
        if not data.get("responsible"):
            if obj and obj.foreman:
                data["responsible"] = obj.foreman
                self.instance.responsible = obj.foreman
            else:
                self.add_error("responsible", "У объекта не указан прораб — выберите ответственного.")
        return data


class DailyReportForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = DailyReport
        fields = ["construction_object", "date", "weather", "temperature", "workers_count", "crews", "works",
                  "materials", "equipment", "problems", "plan_next", "photo"]
        widgets = {"crews": forms.CheckboxSelectMultiple, "weather": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
        self.fields["weather"].choices = DailyReport.Weather.choices
