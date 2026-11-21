from django import forms

from core.forms import StyledMixin
from staff.models import Employee

from .models import BankAccount, Company, CompanyDocument, Department, StaffUnit


class CompanyForm(StyledMixin, forms.ModelForm):
    fieldsets = [
        ("Основные данные", "Как компания записана в документах.",
         ["legal_form", "bin", "name", "short_name", "registered_at", "kbe"]),
        ("Деятельность и налоги", "", ["activity", "vat_certificate", "vat_payer"]),
        ("Руководство", "Подставляется в реквизиты и подписи документов.", ["director", "accountant"]),
        ("Адреса и контакты", "", ["legal_address", "actual_address", "phone", "email", "website", "description"]),
    ]
    wide = {"name", "short_name", "activity", "legal_address", "actual_address", "website"}
    class Meta:
        model = Company
        fields = ["legal_form", "name", "short_name", "bin", "registered_at", "activity", "kbe", "vat_payer",
                  "vat_certificate", "director", "accountant", "legal_address", "actual_address", "phone",
                  "email", "website", "description"]
        widgets = {"bin": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 12}),
                   "description": forms.Textarea(attrs={"rows": 3})}


class BankAccountForm(StyledMixin, forms.ModelForm):
    fieldsets = [("Банк", "", ["bank", "bik"]), ("Счёт", "IBAN можно вводить с пробелами — система уберёт их сама.",
                                                 ["iban", "currency", "note", "is_main"])]
    wide = {"bank"}
    class Meta:
        model = BankAccount
        fields = ["bank", "bik", "iban", "currency", "is_main", "note"]
        widgets = {"iban": forms.TextInput(attrs={"placeholder": "KZ00 0000 0000 0000 0000", "autocomplete": "off"})}

    def clean_iban(self):
        return self.cleaned_data["iban"].replace(" ", "").upper()

    def save(self, commit=True):
        acc = super().save(commit)
        if commit and acc.is_main:  # основной счёт может быть только один
            BankAccount.objects.exclude(pk=acc.pk).filter(currency=acc.currency).update(is_main=False)
        return acc


class DocumentForm(StyledMixin, forms.ModelForm):
    fieldsets = [
        ("Документ", "Решение, приказ, справка, лицензия или другой документ компании.",
         ["kind", "number", "title", "date"]),
        ("Срок и ответственный", "Для справок и лицензий укажите срок — система напомнит за 30 дней.",
         ["valid_until", "responsible"]),
        ("Файл", "Скан или PDF документа.", ["file", "note"]),
    ]
    wide = {"title", "note"}
    class Meta:
        model = CompanyDocument
        fields = ["kind", "number", "date", "title", "valid_until", "responsible", "file", "note"]
        help_texts = {"valid_until": ""}


class DepartmentForm(StyledMixin, forms.ModelForm):
    fieldsets = [("Отдел", "Подразделение компании. Его можно вложить в другой отдел.",
                  ["name", "parent", "head", "order"])]
    wide = {"name"}
    class Meta:
        model = Department
        fields = ["name", "parent", "head", "order"]


class StaffUnitForm(StyledMixin, forms.ModelForm):
    fieldsets = [("Должность в штате", "Сколько единиц этой должности в отделе и оклад по штату. "
                  "Занятость и вакансии система посчитает сама по сотрудникам.",
                  ["department", "position", "count", "salary"])]
    class Meta:
        model = StaffUnit
        fields = ["department", "position", "count", "salary"]


class CompanyEmployeeForm(StyledMixin, forms.ModelForm):
    fieldsets = [
        ("Сотрудник", "Данные из трудового договора.", ["full_name", "iin", "position", "department"]),
        ("Контакты", "", ["phone", "email"]),
        ("Работа", "Оклад видят только руководитель и бухгалтерия.", ["hired_at", "salary", "is_active", "in_staff"]),
    ]
    wide = {"full_name"}
    class Meta:
        model = Employee
        fields = ["full_name", "iin", "position", "department", "phone", "email", "hired_at", "salary", "is_active", "in_staff"]
        widgets = {"iin": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 12}),
                   "phone": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+7 7__ ___ __ __"})}
