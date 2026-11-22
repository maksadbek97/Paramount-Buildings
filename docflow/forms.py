from django import forms

from staff.models import Employee

from .models import CaseFile, DocTask, Document, Journal, Seal, Template

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def staff_qs():
    return Employee.objects.filter(is_active=True, in_staff=True).order_by("full_name")


class StaffMixin:
    staff_fields = ("author", "responsible", "signer", "assignee", "controller", "owner", "issued_to")

    def _setup(self):
        for name in self.staff_fields:
            if name in self.fields:
                self.fields[name].queryset = staff_qs()
        for f in self.fields.values():
            if isinstance(f.widget, forms.DateInput):
                f.widget = DATE


class DocumentForm(StaffMixin, forms.ModelForm):
    """Общая форма документа. Набор полей зависит от типа (KIND_SETS)."""

    COMMON = ["title", "subtype", "doc_date", "construction_object", "department", "author", "responsible",
              "due_date", "priority", "confidential", "case", "summary", "keywords", "file"]
    KIND_SETS = {
        "order": [
            ("Приказ", "Только административные и организационные приказы, без кадровых.",
             ["subtype", "title", "doc_date", "construction_object", "summary"]),
            ("Исполнение", "Пункты приказа превращаются в поручения после регистрации.",
             ["responsible", "due_date", "priority", "signer"]),
            ("Регистрация", "", ["case", "keywords", "file", "confidential"]),
        ],
        "incoming": [
            ("Отправитель", "Входящий номер присвоится при регистрации.",
             ["counterparty", "sender_number", "doc_date", "channel"]),
            ("Содержание", "", ["title", "summary", "construction_object", "contract"]),
            ("Резолюция и срок", "Кому поручено и до какого числа ответить или исполнить.",
             ["responsible", "due_date", "priority", "resolution"]),
            ("Файлы и дело", "Скан или PDF письма обязателен для регистрации.", ["file", "case", "confidential"]),
        ],
        "outgoing": [
            ("Адресат", "", ["counterparty", "channel", "doc_date", "parent"]),
            ("Письмо", "Для письма на фирменном бланке удобнее генератор.",
             ["title", "summary", "construction_object", "contract"]),
            ("Подписание", "", ["author", "signer", "due_date", "priority"]),
            ("Файлы и дело", "", ["file", "case", "confidential"]),
        ],
        "internal": [
            ("Документ", "Служебная записка, протокол, распоряжение и т. п.",
             ["subtype", "title", "doc_date", "department", "summary"]),
            ("Исполнение", "", ["author", "responsible", "due_date", "priority", "construction_object"]),
            ("Файлы и дело", "", ["file", "case", "confidential"]),
        ],
        "contract": [
            ("Стороны и предмет", "", ["contract_type", "counterparty", "title", "construction_object",
                                       "doc_date", "summary"]),
            ("Сумма", "", ["amount", "currency", "vat", "paid"]),
            ("Сроки", "Система напомнит об окончании договора и гарантии.",
             ["valid_from", "valid_until", "guarantee_until", "due_date"]),
            ("Ответственные", "", ["responsible", "signer", "case", "file"]),
        ],
    }
    WIDE = {"title", "summary", "resolution"}

    class Meta:
        model = Document
        fields = ["title", "subtype", "doc_date", "counterparty", "construction_object", "contract", "parent",
                  "department", "author", "responsible", "signer", "due_date", "priority", "confidential", "case",
                  "summary", "keywords", "file", "sender_number", "channel", "resolution", "contract_type",
                  "amount", "currency", "vat", "paid", "valid_from", "valid_until", "guarantee_until"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 4}), "resolution": forms.Textarea(attrs={"rows": 2})}
        labels = {"counterparty": "Контрагент"}

    def __init__(self, *args, kind="other", **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        sets = self.KIND_SETS.get(kind) or [("Документ", "", self.COMMON)]
        used = {n for _, _, names in sets for n in names}
        for name in list(self.fields):
            if name not in used:
                del self.fields[name]
        self.fieldsets = sets
        self.wide = self.WIDE
        self._setup()
        if "contract" in self.fields:
            self.fields["contract"].queryset = Document.objects.filter(kind="contract").order_by("-doc_date")
        if "parent" in self.fields:
            self.fields["parent"].queryset = Document.objects.filter(kind="incoming").order_by("-doc_date")
            self.fields["parent"].label = "В ответ на входящее"
        if "case" in self.fields:
            self.fields["case"].queryset = CaseFile.objects.exclude(status="archived")
        labels = {"incoming": {"counterparty": "Отправитель", "title": "Тема", "doc_date": "Дата письма",
                               "responsible": "Исполнитель"},
                  "outgoing": {"counterparty": "Адресат", "title": "Тема"},
                  "order": {"subtype": "Вид приказа", "summary": "Основание и текст", "responsible": "Контролирует"},
                  "contract": {"title": "Предмет договора (кратко)", "summary": "Предмет и условия"}}
        for name, label in labels.get(kind, {}).items():
            if name in self.fields:
                self.fields[name].label = label
        if kind == "incoming":
            self.fields["counterparty"].required = True
        if kind == "outgoing":
            self.fields["counterparty"].required = True
        if kind == "contract":
            self.fields["counterparty"].required = True
            self.fields["amount"].required = True
            self.fields["contract_type"].required = True

    def save(self, commit=True):
        doc = super().save(commit=False)
        doc.kind = self.kind
        doc.direction = {"incoming": "in", "outgoing": "out"}.get(self.kind, "internal")
        if not doc.pk:
            doc.status = "registering" if self.kind == "incoming" else "draft"
        if commit:
            doc.save()
            self.save_m2m()
        return doc


class TaskForm(StaffMixin, forms.ModelForm):
    fieldsets = [("Поручение", "", ["title", "description", "document", "construction_object"]),
                 ("Кто и когда", "Перенос срока потом — только с причиной.",
                  ["assignee", "co_assignees", "controller", "due", "priority"])]
    wide = {"title", "description"}

    class Meta:
        model = DocTask
        fields = ["title", "description", "document", "construction_object", "assignee", "co_assignees",
                  "controller", "due", "priority"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._setup()
        self.fields["controller"].queryset = staff_qs()


class CaseForm(StaffMixin, forms.ModelForm):
    fieldsets = [("Дело", "Индекс вида 02-03: раздел подразделения и номер дела.",
                  ["index", "title", "department", "year", "doc_types"]),
                 ("Хранение", "", ["retention", "retention_years", "basis", "responsible", "location", "status"])]
    wide = {"title"}

    class Meta:
        model = CaseFile
        fields = ["index", "title", "department", "year", "doc_types", "retention", "retention_years", "basis",
                  "responsible", "location", "status"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._setup()


class JournalForm(forms.ModelForm):
    fieldsets = [("Журнал", "", ["name", "kind", "is_active"]),
                 ("Нумерация", "Номер собирается так: префикс – год – номер – суффикс.",
                  ["prefix", "suffix", "separator", "use_year", "digits", "reset_yearly"])]

    class Meta:
        model = Journal
        fields = ["name", "kind", "is_active", "prefix", "suffix", "separator", "use_year", "digits", "reset_yearly"]


class TemplateForm(StaffMixin, forms.ModelForm):
    fieldsets = [("Шаблон", "", ["name", "code", "category", "is_letterhead", "version", "active_from"]),
                 ("Доступ и подпись", "", ["access", "sign_rule", "author", "is_active"]),
                 ("Содержимое", "Старые документы сохраняют версию шаблона, по которой созданы.", ["body", "file", "preview"])]
    wide = {"body"}

    class Meta:
        model = Template
        fields = ["name", "code", "category", "is_letterhead", "version", "active_from", "access", "sign_rule",
                  "author", "is_active", "body", "file", "preview"]
        widgets = {"body": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._setup()


class SealForm(StaffMixin, forms.ModelForm):
    fieldsets = [("Печать или подпись", "", ["name", "kind", "owner", "location", "access", "is_active"])]
    wide = {"access"}

    class Meta:
        model = Seal
        fields = ["name", "kind", "owner", "location", "access", "is_active"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._setup()
