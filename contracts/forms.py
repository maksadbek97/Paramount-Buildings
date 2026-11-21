from datetime import date

from django import forms

from core.forms import StyledMixin

from .models import Assignment, Crew, Payment, WorkContract, WorkLog


class ContractForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = WorkContract
        fields = ["construction_object", "work_type", "volume", "unit", "price", "start_date", "end_date",
                  "status", "note"]


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
        fields = ["assignment", "date", "volume", "people", "note"]
        labels = {"people": "Сколько человек вышло"}
        help_texts = {"people": "Нужно для оплаты подённо"}

    def __init__(self, *args, contract=None, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
        qs = Assignment.objects.select_related("contract__construction_object", "crew", "employee").filter(
            contract__status=WorkContract.Status.ACTIVE)
        if contract is not None:
            qs = qs.filter(contract=contract)
        self.fields["assignment"].queryset = qs
        self.fields["assignment"].label_from_instance = _assignment_label
        if qs.count() == 1:
            self.fields["assignment"].initial = qs.first()


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
