from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from contracts.models import Crew, WorkContract, WorkLog, summary
from finance.models import Estimate, Transaction
from objects.models import ConstructionObject
from quality.models import Remark
from staff.models import Employee, Task
from warehouse.models import Material, StockMovement

from . import alerts, audit, forms
from .models import AuditLog


def form_page(request, form_class, title, success_url, instance=None, form_kwargs=None, subtitle="",
              submit="Сохранить", back=None):
    """Общая страница с формой: показывает, проверяет, сохраняет и пишет в журнал действий."""
    form_kwargs = form_kwargs or {}
    editing = instance is not None and instance.pk is not None
    if request.method == "POST":
        before = audit.snapshot(instance) if editing else None
        form = form_class(request.POST, request.FILES, instance=instance, **form_kwargs)
        if form.is_valid():
            obj = form.save()
            audit.log(request, obj, AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE,
                      before=before, reason=request.POST.get("change_reason", "")[:300])
            messages.success(request, "Сохранено")
            return redirect(success_url(obj) if callable(success_url) else success_url)
    else:
        form = form_class(instance=instance, initial=dict(request.GET.items()), **form_kwargs)
    return render(request, "form.html", {
        "form": form, "title": title, "subtitle": subtitle, "submit": submit, "editing": editing,
        "back": back or request.META.get("HTTP_REFERER") or reverse("dashboard"),
    })


@login_required
def dashboard(request):
    contracts = list(WorkContract.objects.select_related("construction_object").prefetch_related(
        "assignments__crew", "assignments__employee"))
    obj_id = request.GET.get("object")
    if obj_id and obj_id.isdigit():
        contracts = [c for c in contracts if c.construction_object_id == int(obj_id)]
    active = [c for c in contracts if c.status == WorkContract.Status.ACTIVE]
    objects = ConstructionObject.objects.all()
    working = [o for o in objects if o.is_working]
    open_remarks = Remark.objects.exclude(status=Remark.Status.CLOSED)
    return render(request, "dashboard.html", {
        "s": summary(contracts),
        "alerts": alerts.collect(contracts),
        "active_contracts": active,
        "objects_count": {"working": len(working), "paused": sum(o.status == "paused" for o in objects),
                          "done": sum(o.status in ("done", "archive") for o in objects), "total": len(objects)},
        "stock_value": sum((m.stock_value for m in Material.objects.all()), 0),
        "tasks_overdue": Task.objects.exclude(status="done").filter(due_date__lt=date.today()).count(),
        "remarks_open": open_remarks.count(),
        "remarks_overdue": open_remarks.filter(deadline__lt=date.today()).count(),
        "remarks_review": open_remarks.filter(status="review").count(),
        "objects_active": len(working),
        "workers": Employee.objects.filter(is_active=True).count(),
        "crews": Crew.objects.count(),
        "recent_logs": WorkLog.objects.select_related(
            "assignment__contract__construction_object", "assignment__crew", "assignment__employee")[:6],
        "low_materials": [m for m in Material.objects.all() if m.is_low],
        "tasks_open": Task.objects.exclude(status="done").count(),
    })


@login_required
def menu(request):
    return render(request, "menu.html")


@login_required
def object_list(request):
    qs = ConstructionObject.objects.select_related("client", "manager").annotate(
        task_count=Count("tasks", distinct=True), contract_count=Count("contracts", distinct=True))
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return render(request, "object_list.html", {
        "objects": qs, "statuses": ConstructionObject.Status.choices, "current": status,
    })


@login_required
def object_detail(request, pk):
    obj = get_object_or_404(ConstructionObject.objects.select_related("client", "manager"), pk=pk)
    contracts = list(obj.contracts.prefetch_related("assignments"))
    income = obj.transactions.filter(kind="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = obj.transactions.filter(kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    spent = alerts.object_expenses(obj)
    return render(request, "object_detail.html", {
        "obj": obj, "contracts": contracts, "s": summary(contracts),
        "spent": spent, "budget_left": obj.budget - spent if obj.budget else None,
        "history": obj.history.select_related("user")[:15],
        "remarks": obj.remarks.exclude(status="closed").select_related("responsible", "construction_object"),
        "reports": obj.daily_reports.all()[:5],
        "tasks": obj.tasks.select_related("assignee"),
        "estimates": obj.estimates.all(), "documents": obj.documents.all(),
        "income": income, "expense": expense, "balance": income - expense,
    })


@login_required
def object_create(request):
    return form_page(request, forms.ObjectForm, "Новый объект",
                     lambda o: reverse("object_detail", args=[o.pk]), back=reverse("object_list"))


@login_required
def object_edit(request, pk):
    obj = get_object_or_404(ConstructionObject, pk=pk)
    return form_page(request, forms.ObjectForm, "Изменить объект",
                     lambda o: reverse("object_detail", args=[o.pk]), instance=obj,
                     back=reverse("object_detail", args=[pk]))


@login_required
def staff_list(request):
    employees = Employee.objects.select_related("position").prefetch_related("crews")
    return render(request, "staff_list.html", {
        "crews": Crew.objects.select_related("leader").prefetch_related("members"),
        "employees": employees,
        "tasks": Task.objects.select_related("assignee", "construction_object").exclude(status="done"),
    })


@login_required
def employee_create(request):
    return form_page(request, forms.EmployeeForm, "Новый рабочий", reverse("staff_list"),
                     back=reverse("staff_list"))


@login_required
def employee_edit(request, pk):
    return form_page(request, forms.EmployeeForm, "Изменить данные рабочего", reverse("staff_list"),
                     instance=get_object_or_404(Employee, pk=pk), back=reverse("staff_list"))


@login_required
def task_create(request):
    return form_page(request, forms.TaskForm, "Новая задача", reverse("task_list"), back=reverse("task_list"))


@login_required
def warehouse_list(request):
    return render(request, "warehouse_list.html", {
        "materials": Material.objects.all(),
        "movements": StockMovement.objects.select_related("material", "supplier", "construction_object")[:30],
    })


@login_required
def material_create(request):
    return form_page(request, forms.MaterialForm, "Новый материал", reverse("warehouse_list"),
                     back=reverse("warehouse_list"))


@login_required
def movement_create(request):
    return form_page(request, forms.StockMovementForm, "Приход / расход материала", reverse("warehouse_list"),
                     back=reverse("warehouse_list"))


@login_required
def finance_list(request):
    income = Transaction.objects.filter(kind="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = Transaction.objects.filter(kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    return render(request, "finance_list.html", {
        "estimates": Estimate.objects.select_related("construction_object").prefetch_related("items"),
        "transactions": Transaction.objects.select_related("construction_object")[:50],
        "income": income, "expense": expense, "balance": income - expense,
    })


@login_required
def transaction_create(request):
    return form_page(request, forms.TransactionForm, "Доход / расход компании", reverse("finance_list"),
                     back=reverse("finance_list"))


@login_required
def history(request):
    qs = AuditLog.objects.select_related("user", "construction_object")
    obj = request.GET.get("object")
    if obj and obj.isdigit():
        qs = qs.filter(construction_object_id=obj)
    return render(request, "history.html", {"entries": qs[:200]})
