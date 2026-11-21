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
              submit="Сохранить", back=None, extra=None):
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
        **(extra or {}),
    })


@login_required
def dashboard(request):
    """Главная: мои объекты и что требует внимания. Всё остальное — внутри объекта."""
    contracts = list(WorkContract.objects.select_related("construction_object").prefetch_related(
        "assignments__crew", "assignments__employee"))
    by_obj = {}
    for c in contracts:
        by_obj.setdefault(c.construction_object_id, []).append(c)
    open_remarks = dict(Remark.objects.exclude(status=Remark.Status.CLOSED).values_list(
        "construction_object").annotate(n=Count("id")))
    pending = {}
    for log in WorkLog.objects.filter(status=WorkLog.Status.SUBMITTED).select_related("assignment__contract"):
        oid = log.assignment.contract.construction_object_id
        pending[oid] = pending.get(oid, 0) + 1
    cards = []
    for o in ConstructionObject.objects.select_related("client", "foreman"):
        cs = by_obj.get(o.pk, [])
        cards.append({"o": o, "s": summary(cs), "remarks": open_remarks.get(o.pk, 0),
                      "pending": pending.get(o.pk, 0),
                      "active": sum(c.status == WorkContract.Status.ACTIVE for c in cs)})
    view = "done" if request.GET.get("status") == "done" else "active"
    active = sorted((c for c in cards if not c["o"].is_closed), key=lambda c: (not c["o"].is_working, -c["s"]["total"]))
    done = [c for c in cards if c["o"].is_closed]
    return render(request, "dashboard.html", {
        "s": summary([c for c in contracts if not c.construction_object.is_closed]),
        "alerts": alerts.collect(contracts) if view == "active" else [],
        "view": view, "cards": done if view == "done" else active,
        "active_count": len(active), "done_count": len(done),
        "working_count": sum(c["o"].is_working for c in cards),
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
def object_create(request):
    return form_page(request, forms.ObjectForm, "Новый объект",
                     lambda o: reverse("object_detail", args=[o.pk]), back=reverse("dashboard"),
                     subtitle="Взяли объект — создайте его здесь. Дальше объёмы, рабочие, материалы, деньги "
                              "и документы ведутся внутри объекта.", submit="Создать объект")


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
    from warehouse.models import PurchaseRequest, Warehouse
    materials = list(Material.objects.all())
    return render(request, "warehouse_list.html", {
        "warehouses": Warehouse.objects.select_related("construction_object", "keeper"),
        "materials": materials, "total_value": sum((m.stock_value for m in materials), 0),
        "in_transit": StockMovement.objects.filter(kind="transfer", received=False).select_related(
            "material", "warehouse", "to_warehouse"),
        "open_requests": PurchaseRequest.objects.filter(status__in=PurchaseRequest.OPEN).count(),
        "movements": StockMovement.objects.select_related("material", "supplier", "construction_object",
                                                          "warehouse", "to_warehouse")[:30],
    })


@login_required
def material_create(request):
    return form_page(request, forms.MaterialForm, "Новый материал", reverse("warehouse_list"),
                     back=reverse("warehouse_list"))


@login_required
def movement_create(request):
    return form_page(request, forms.StockMovementForm, "Складская операция", reverse("warehouse_list"),
                     form_kwargs={"user": request.user},
                     subtitle="Приход, расход в работу, перемещение, возврат, списание.",
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
