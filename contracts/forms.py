from datetime import date

from django import forms

from core.forms import StyledMixin

from .models import Assignment, Crew, MaterialNorm, Payment, WorkContract, WorkLog


class ContractForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = WorkContract
        fields = ["construction_object", "work_type", "section", "floor", "volume", "unit", "price",
                  "start_date", "end_date", "responsible", "status", "note"]


class CrewForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Crew
        fields = ["name", "leader", "phone", "members", "note"]
        widgets = {"members": forms.CheckboxSelectMultiple}


class AssignmentForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["crew", "employee", "pay_type", "rate", "planned_volume"]
        widgets = {"pay_type": forms.RadioSelect}
        help_texts = {"crew": "Выберите бригаду или одного рабочего ниже"}

    def __init__(self, *args, contract=None, **kwargs):
        super().__init__(*args, **kwargs)
        if contract is not None:
            self.instance.contract = contract
        self.fields["pay_type"].choices = Assignment.PayType.choices  # без пустого варианта


def _assignment_label(a):
    return f"{a.performer} · {a.contract.work_type}, {a.contract.construction_object}"


class WorkLogForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = WorkLog
        fields = ["assignment", "date", "section", "floor", "volume", "people", "photo", "note", "over_plan"]
        labels = {"people": "Сколько человек вышло", "over_plan": "Разрешаю внести объём сверх плана"}
        help_texts = {"people": "Нужно для оплаты подённо",
                      "photo": "Фото выполненной работы (по желанию)"}

    def __init__(self, *args, contract=None, user=None, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
        self.user = user
        if not (user and user.has_perm("contracts.allow_over_plan")):
            del self.fields["over_plan"]
        qs = Assignment.objects.select_related("contract__construction_object", "crew", "employee").filter(
            contract__status=WorkContract.Status.ACTIVE)
        if contract is not None:
            qs = qs.filter(contract=contract)
        self.fields["assignment"].queryset = qs
        self.fields["assignment"].label_from_instance = _assignment_label
        if qs.count() == 1:
            self.fields["assignment"].initial = qs.first()

    def clean(self):
        data = super().clean()
        a, volume = data.get("assignment"), data.get("volume")
        if a and volume is not None:
            if volume < 0:
                self.add_error("volume", "Объём не может быть отрицательным.")
            c = a.contract
            left = c.volume - c.accepted_volume - c.pending_volume
            if volume > left and not data.get("over_plan"):
                self.add_error("volume", f"Это больше плана: по договору осталось {left.normalize():f} {c.unit}. "
                                         "Сверх плана может внести только тот, у кого есть разрешение.")
        return data

    def save(self, commit=True):
        if self.user and self.user.is_authenticated and not self.instance.pk:
            self.instance.created_by = self.user
        if not self.instance.section and self.cleaned_data.get("assignment"):
            self.instance.section = self.cleaned_data["assignment"].contract.section
        return super().save(commit)


class ReviewForm(StyledMixin, forms.Form):
    accepted_volume = forms.DecimalField(label="Принять объём", min_value=0, decimal_places=2)
    review_note = forms.CharField(label="Комментарий", required=False,
                                  widget=forms.TextInput(attrs={"placeholder": "Что не принято и почему"}))

    def __init__(self, *args, log=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = log
        self.fields["accepted_volume"].initial = log.volume
        self.fields["accepted_volume"].help_text = f"Внесено {log.volume.normalize():f} {log.contract.unit}. " \
                                                   "Поставьте 0, чтобы отклонить полностью."

    def clean_accepted_volume(self):
        v = self.cleaned_data["accepted_volume"]
        if v > self.log.volume:
            raise forms.ValidationError("Нельзя принять больше, чем внесено.")
        return v


class NormForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = MaterialNorm
        fields = ["material", "per_unit"]

    def __init__(self, *args, contract=None, **kwargs):
        super().__init__(*args, **kwargs)
        if contract is not None:
            self.instance.contract = contract
            self.fields["per_unit"].label = f"Расход на 1 {contract.unit}"


class PaymentForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["kind", "contract", "assignment", "amount", "date", "note"]
        widgets = {"kind": forms.RadioSelect}
        help_texts = {"assignment": "Только для выплаты рабочим"}

    def __init__(self, *args, contract=None, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = Payment.Kind.choices
        qs = Assignment.objects.select_related("contract__construction_object", "crew", "employee")
        if contract is not None:
            qs = qs.filter(contract=contract)
            self.fields["contract"].initial = contract
        self.fields["assignment"].queryset = qs
        self.fields["assignment"].label_from_instance = _assignment_label
