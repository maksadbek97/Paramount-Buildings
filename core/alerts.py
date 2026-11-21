"""Автоматические предупреждения для руководителя (ТЗ п. 4, 34)."""
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse

from contracts.models import Payment, WorkContract, pending_logs
from finance.models import Transaction
from objects.models import ConstructionObject
from staff.models import Task
from warehouse.models import Material


def _money(v):
    return f"{int(v):,}".replace(",", " ") + " ₸"


def object_expenses(obj):
    tx = Transaction.objects.filter(construction_object=obj, kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    pays = Payment.objects.filter(contract__construction_object=obj).exclude(
        kind=Payment.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or 0
    return Decimal(tx) + Decimal(pays)


def collect(contracts=None):
    """Список предупреждений: level (bad/warn/info), текст, ссылка."""
    items = []
    contracts = contracts if contracts is not None else list(
        WorkContract.objects.select_related("construction_object"))

    low = [m for m in Material.objects.all() if m.is_low]
    for m in low:
        items.append(("bad", f"Не хватает материала: {m.name} — осталось {m.stock.normalize():f} {m.unit}, "
                             f"минимум {m.min_stock.normalize():f}", reverse("warehouse_list")))

    for c in contracts:
        if c.status != WorkContract.Status.ACTIVE:
            continue
        risk = c.delay_risk_days
        if c.is_overdue:
            items.append(("bad", f"Просрочен срок: {c.work_type} ({c.construction_object.name}), "
                                 f"выполнено {c.progress}%", reverse("contract_detail", args=[c.pk])))
        elif risk:
            items.append(("warn", f"Риск задержки ~{risk} дн.: {c.work_type} ({c.construction_object.name}) — "
                                  "при текущем темпе не успеваем к сроку", reverse("contract_detail", args=[c.pk])))
        for row in c.material_plan_fact():
            if row["need"] and row["pct"] > 5:
                items.append(("warn", f"Перерасход {row['material'].name} на {row['pct']}% сверх нормы: "
                                      f"{c.work_type} ({c.construction_object.name})",
                              reverse("contract_detail", args=[c.pk])))

    pending = pending_logs()
    if pending:
        items.append(("info", f"Ждут проверки ПТО записи выработки: {len(pending)}", reverse("pto")))

    for obj in ConstructionObject.objects.exclude(budget=0):
        spent = object_expenses(obj)
        if spent > obj.budget:
            items.append(("bad", f"Превышен бюджет: {obj.name} — потрачено {_money(spent)} "
                                 f"при бюджете {_money(obj.budget)}", reverse("object_detail", args=[obj.pk])))

    overdue = Task.objects.exclude(status="done").filter(due_date__lt=date.today()).count()
    if overdue:
        items.append(("bad", f"Просроченные задачи: {overdue}", reverse("staff_list") + "#tasks"))

    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(items, key=lambda i: order[i[0]])
