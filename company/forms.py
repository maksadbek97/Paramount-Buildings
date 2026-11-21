from django import forms

from core.forms import StyledMixin
from staff.models import Employee

from .models import BankAccount, Company, CompanyDocument, Department, StaffUnit


class CompanyForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Company
        fields = ["legal_form", "name", "short_name", "bin", "registered_at", "activity", "kbe", "vat_payer",
                  "vat_certificate", "director", "accountant", "legal_address", "actual_address", "phone",
                  "email", "website", "description"]
        widgets = {"bin": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 12}),
                   "description": forms.Textarea(attrs={"rows": 3})}


class BankAccountForm(StyledMixin, forms.ModelForm):
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
    class Meta:
        model = CompanyDocument
        fields = ["kind", "number", "date", "title", "valid_until", "responsible", "file", "note"]


class DepartmentForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "parent", "head", "order"]


class StaffUnitForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = StaffUnit
        fields = ["department", "position", "count", "salary"]


class CompanyEmployeeForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "iin", "position", "department", "phone", "email", "hired_at", "salary", "is_active", "in_staff"]
        widgets = {"iin": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 12}),
                   "phone": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+7 7__ ___ __ __"})}
