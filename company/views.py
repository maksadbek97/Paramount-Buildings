from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.views import form_page
from staff.models import Employee

from . import forms
from .models import BankAccount, Company, CompanyDocument, Department, StaffUnit

TABS = [("profile", "Профиль", "company_profile"), ("docs", "Документы", "company_docs"),
        ("structure", "Структура", "company_structure"), ("staff", "Сотрудники", "company_staff"),
        ("schedule", "Штатное расписание", "company_schedule")]


def can_salary(user):
    """Оклады и фонд оплаты труда видят руководитель и кадры/бухгалтерия."""
    return user.is_superuser or user.has_perm("staff.change_employee")


def _page(request, tab, template, ctx):
    company = Company.get()
    return render(request, template, {"company": company, "tab": tab, "tabs": TABS,
                                      "can_salary": can_salary(request.user), **ctx})


def _schedule_rows():
    """Штатное расписание с фактом: сколько людей реально сидит на каждой строке."""
    fact = {(r["department"], r["position"]): r["n"] for r in Employee.objects.filter(is_active=True).values(
        "department", "position").annotate(n=Count("id"))}
    groups = []
    for d in Department.objects.prefetch_related("units__position"):
        rows = []
        for u in d.units.all():
            filled = fact.get((d.pk, u.position_id), 0)
            rows.append({"u": u, "filled": filled, "vacant": max(u.count - filled, 0), "fund": u.count * u.salary})
        if rows:
            groups.append({"d": d, "rows": rows, "count": sum(r["u"].count for r in rows),
                           "filled": sum(r["filled"] for r in rows), "vacant": sum(r["vacant"] for r in rows),
                           "fund": sum((r["fund"] for r in rows), Decimal(0))})
    total = {k: sum((g[k] for g in groups), Decimal(0) if k == "fund" else 0)
             for k in ("count", "filled", "vacant", "fund")}
    return groups, total


@login_required
def profile(request):
    company = Company.get()
    groups, total = _schedule_rows()
    active = Employee.objects.filter(is_active=True)
    req = [("Наименование", company.name), ("БИН", company.bin), ("КБе", company.kbe),
           ("Юридический адрес", company.legal_address)]
    main = BankAccount.objects.filter(is_main=True, currency="KZT").first() or BankAccount.objects.first()
    if main:
        req += [("Банк", main.bank), ("БИК", main.bik), ("ИИК (IBAN)", main.iban)]
    if company.director:
        req.append(("Руководитель", f"{company.director.position or 'Директор'} {company.director.full_name}"))
    return _page(request, "profile", "company/profile.html", {
        "accounts": BankAccount.objects.all(),
        "requisites": [(k, v) for k, v in req if v],
        "requisites_text": "\n".join(f"{k}: {v}" for k, v in req if v),
        "stats": {"employees": active.count(), "departments": Department.objects.count(),
                  "vacant": total["vacant"], "docs": CompanyDocument.objects.count()},
        "attention": CompanyDocument.attention()[:6],
        "recent_docs": CompanyDocument.objects.select_related("responsible")[:5],
        "years": (date.today() - company.registered_at).days // 365 if company.registered_at else None,
    })


@login_required
def docs(request):
    kind = request.GET.get("kind", "")
    kinds = dict(CompanyDocument.Kind.choices)
    if kind not in kinds and kind != "expiring":
        kind = ""
    qs = CompanyDocument.objects.select_related("responsible")
    counts = dict(qs.values_list("kind").annotate(n=Count("id")))
    if kind == "expiring":
        qs = CompanyDocument.attention().select_related("responsible")
    elif kind:
        qs = qs.filter(kind=kind)
    filters = [("", "Все", sum(counts.values()))] + [(k, v, counts.get(k, 0)) for k, v in kinds.items()]
    filters.append(("expiring", "Истекают", CompanyDocument.attention().count()))
    return _page(request, "docs", "company/docs.html", {"docs": qs, "kind": kind, "filters": filters,
                                                        "kind_label": dict((k, v) for k, v, _ in filters)[kind]})


def _tree():
    """Отделы деревом: [(отдел, глубина)], с числом людей и вакансиями."""
    deps = list(Department.objects.select_related("head__position").annotate(
        n=Count("employees", filter=Q(employees__is_active=True))))
    groups, _ = _schedule_rows()
    vacant = {g["d"].pk: g["vacant"] for g in groups}
    kids = {}
    for d in deps:
        d.vacant = vacant.get(d.pk, 0)
        kids.setdefault(d.parent_id, []).append(d)
    out = []

    def walk(parent, depth):
        for d in kids.get(parent, []):
            d.depth = depth
            d.kids = kids.get(d.pk, [])
            out.append(d)
            walk(d.pk, depth + 1)
    walk(None, 0)
    return out


@login_required
def structure(request):
    deps = _tree()
    top = [d for d in deps if d.depth == 0]
    return _page(request, "structure", "company/structure.html", {
        "top": top, "deps": deps,
        "no_dept": Employee.objects.filter(is_active=True, department__isnull=True).count()})


@login_required
def staff(request):
    dept = request.GET.get("dept", "")
    qs = Employee.objects.select_related("position", "department").order_by("department__order", "full_name")
    show_fired = dept == "fired"
    qs = qs.filter(is_active=not show_fired)
    selected = None
    if dept.isdigit():
        selected = get_object_or_404(Department, pk=int(dept))
        qs = qs.filter(department=selected)
    counts = dict(Employee.objects.filter(is_active=True).values_list("department").annotate(n=Count("id")))
    filters = [("", "Все", sum(counts.values()))] + [
        (str(d.pk), d.name, counts.get(d.pk, 0)) for d in Department.objects.all()]
    fired = Employee.objects.filter(is_active=False).count()
    if fired:
        filters.append(("fired", "Уволенные", fired))
    today = date.today()
    rows = []
    for e in qs:
        months = ((today - e.hired_at).days // 30) if e.hired_at else None
        rows.append({"e": e, "tenure": (f"{months // 12} г. {months % 12} мес." if months >= 12 else
                                        f"{months} мес.") if months is not None else ""})
    return _page(request, "staff", "company/staff.html", {"rows": rows, "dept": dept, "filters": filters,
                                                          "selected": selected})


@login_required
def schedule(request):
    groups, total = _schedule_rows()
    fact_fund = sum((e.salary for e in Employee.objects.filter(is_active=True)), Decimal(0))
    return _page(request, "schedule", "company/schedule.html", {"groups": groups, "total": total,
                                                                "fact_fund": fact_fund})


# ---------- формы ----------

def _form(request, form_class, title, back, instance=None, subtitle="", submit="Сохранить"):
    return form_page(request, form_class, title, back, instance=instance, subtitle=subtitle, submit=submit,
                     back=back, extra={"section": "company"})


@login_required
def edit(request):
    return _form(request, forms.CompanyForm, "Профиль компании", reverse("company_profile"), Company.get(),
                 "Эти данные попадают в реквизиты, документы и счета.")


@login_required
def account_new(request):
    return _form(request, forms.BankAccountForm, "Новый банковский счёт", reverse("company_profile"))


@login_required
def account_edit(request, pk):
    return _form(request, forms.BankAccountForm, "Банковский счёт", reverse("company_profile"),
                 get_object_or_404(BankAccount, pk=pk))


@login_required
def doc_new(request):
    return _form(request, forms.DocumentForm, "Новый документ компании", reverse("company_docs"),
                 subtitle="Решение, приказ, справка, лицензия. Для справок укажите срок — система напомнит.",
                 submit="Добавить")


@login_required
def doc_edit(request, pk):
    return _form(request, forms.DocumentForm, "Документ компании", reverse("company_docs"),
                 get_object_or_404(CompanyDocument, pk=pk))


@login_required
def department_new(request):
    return _form(request, forms.DepartmentForm, "Новый отдел", reverse("company_structure"))


@login_required
def department_edit(request, pk):
    return _form(request, forms.DepartmentForm, "Отдел", reverse("company_structure"),
                 get_object_or_404(Department, pk=pk))


@login_required
def employee_new(request):
    return _form(request, forms.CompanyEmployeeForm, "Новый сотрудник", reverse("company_staff"), submit="Добавить")


@login_required
def employee_edit(request, pk):
    return _form(request, forms.CompanyEmployeeForm, "Сотрудник", reverse("company_staff"),
                 get_object_or_404(Employee, pk=pk))


@login_required
def unit_new(request):
    return _form(request, forms.StaffUnitForm, "Строка штатного расписания", reverse("company_schedule"),
                 subtitle="Сколько единиц должности в отделе и оклад по штату.")


@login_required
def unit_edit(request, pk):
    return _form(request, forms.StaffUnitForm, "Строка штатного расписания", reverse("company_schedule"),
                 get_object_or_404(StaffUnit, pk=pk))
