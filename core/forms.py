from datetime import date

from django import forms

from finance.models import Transaction
from objects.models import Client, ConstructionObject
from staff.models import Employee, Position, Task
from warehouse.models import Material, StockMovement, Warehouse


class StyledMixin:
    """Удобные поля для телефона: календарь для дат, цифровая клавиатура для чисел."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            elif isinstance(field, forms.DecimalField):
                # Принимаем и «12,5», и «12.5»; на телефоне — цифровая клавиатура.
                field.localize = True
                field.widget = forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"})
                field.widget.is_localized = True
            elif isinstance(field, forms.IntegerField):
                w.attrs.setdefault("inputmode", "numeric")
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 3)
            if isinstance(field, forms.ModelChoiceField) and not isinstance(field, forms.ModelMultipleChoiceField):
                field.empty_label = "— выберите —"
            if field.required:
                field.widget.attrs.setdefault("required", True)


    def full_clean(self):
        # «48 000 000» -> «48000000»: суммы часто вводят с пробелами.
        if self.is_bound:
            data = self.data.copy()
            for name, field in self.fields.items():
                key = self.add_prefix(name)
                if isinstance(field, forms.DecimalField) and isinstance(data.get(key), str):
                    data[key] = "".join(data[key].split()).replace("\u00a0", "")
            self.data = data
        super().full_clean()


class ObjectForm(StyledMixin, forms.ModelForm):
    new_client = forms.CharField(label="Или новый заказчик / генподрядчик", required=False,
                                 widget=forms.TextInput(attrs={"placeholder": "Название компании"}))

    class Meta:
        model = ConstructionObject
        fields = ["code", "name", "status", "city", "address", "client", "new_client", "general_contractor",
                  "contract_number", "contract_amount", "budget", "start_date", "end_date", "photo",
                  "manager", "foreman", "pto", "description"]
        labels = {"client": "Заказчик"}

    def save(self, commit=True):
        name = self.cleaned_data.get("new_client")
        if name:
            self.instance.client, _ = Client.objects.get_or_create(name=name.strip())
        return super().save(commit)


class EmployeeForm(StyledMixin, forms.ModelForm):
    new_position = forms.CharField(label="Или новая специальность", required=False,
                                   widget=forms.TextInput(attrs={"placeholder": "Например: арматурщик"}))

    class Meta:
        model = Employee
        fields = ["full_name", "iin", "phone", "position", "new_position", "hired_at", "salary", "is_active"]
        widgets = {"iin": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 12}),
                   "phone": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+7 7__ ___ __ __"})}
        labels = {"position": "Специальность", "salary": "Оклад (если есть)"}

    def save(self, commit=True):
        name = self.cleaned_data.get("new_position")
        if name:
            self.instance.position, _ = Position.objects.get_or_create(name=name.strip())
        return super().save(commit)


class TaskForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "construction_object", "assignee", "source", "priority", "due_date", "description",
                  "file", "comment"]
        labels = {"assignee": "Ответственный / исполнитель"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].required = True  # ТЗ п. 30.4: у задачи должен быть ответственный
        self.fields["assignee"].widget.attrs["required"] = True


class MaterialForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Material
        fields = ["name", "code", "category", "brand", "unit", "price", "min_stock", "max_stock"]


class StockMovementForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ["kind", "warehouse", "to_warehouse", "material", "quantity", "date", "construction_object",
                  "contract", "supplier", "price", "note"]
        widgets = {"kind": forms.RadioSelect}
        help_texts = {"to_warehouse": "Только для перемещения. Получатель подтвердит приёмку.",
                      "contract": "Для расхода: на какой вид работ — для сравнения с нормой",
                      "price": "Для прихода"}

    def __init__(self, *args, user=None, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["kind"].choices = StockMovement.Kind.choices
        self.fields["warehouse"].required = True
        if not self.initial.get("warehouse") and Warehouse.objects.count():
            self.initial["warehouse"] = Warehouse.objects.first().pk

    def save(self, commit=True):
        if self.user and self.user.is_authenticated and not self.instance.pk:
            self.instance.created_by = self.user
        return super().save(commit)


class TransactionForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["kind", "amount", "date", "construction_object", "category", "description"]
        widgets = {"kind": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("initial", {}).setdefault("date", date.today())
        super().__init__(*args, **kwargs)
