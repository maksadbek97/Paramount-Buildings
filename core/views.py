from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, render

from finance.models import Estimate, Transaction
from objects.models import ConstructionObject
from staff.models import Employee, Task
from warehouse.models import Material, StockMovement


@login_required
def dashboard(request):
    income = Transaction.objects.filter(kind="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = Transaction.objects.filter(kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    context = {
        "objects_active": ConstructionObject.objects.filter(status="in_progress").count(),
        "objects_total": ConstructionObject.objects.count(),
        "employees": Employee.objects.filter(is_active=True).count(),
        "tasks_open": Task.objects.exclude(status="done").count(),
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "low_materials": [m for m in Material.objects.all() if m.is_low],
        "recent_tasks": Task.objects.exclude(status="done").select_related("assignee", "construction_object")[:8],
    }
    return render(request, "dashboard.html", context)


@login_required
def object_list(request):
    qs = ConstructionObject.objects.select_related("client", "manager").annotate(task_count=Count("tasks"))
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return render(request, "object_list.html", {
        "objects": qs, "statuses": ConstructionObject.Status.choices, "current": status,
    })


@login_required
def object_detail(request, pk):
    obj = get_object_or_404(ConstructionObject.objects.select_related("client", "manager"), pk=pk)
    income = obj.transactions.filter(kind="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = obj.transactions.filter(kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    return render(request, "object_detail.html", {
        "obj": obj, "tasks": obj.tasks.select_related("assignee"),
        "estimates": obj.estimates.all(), "documents": obj.documents.all(),
        "income": income, "expense": expense, "balance": income - expense,
    })


@login_required
def staff_list(request):
    return render(request, "staff_list.html", {
        "employees": Employee.objects.select_related("position"),
        "tasks": Task.objects.select_related("assignee", "construction_object"),
    })


@login_required
def warehouse_list(request):
    return render(request, "warehouse_list.html", {
        "materials": Material.objects.all(),
        "movements": StockMovement.objects.select_related("material", "supplier", "construction_object")[:30],
    })


@login_required
def finance_list(request):
    return render(request, "finance_list.html", {
        "estimates": Estimate.objects.select_related("construction_object"),
        "transactions": Transaction.objects.select_related("construction_object")[:50],
    })
