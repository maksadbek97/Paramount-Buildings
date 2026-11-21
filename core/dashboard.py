"""Данные для раздела «Главная» (ТЗ модуля «Главная / Dashboard»).

Главная ничего не ведёт сама: всё считается из общей базы (объекты, договоры,
платежи, закупки, склад, задачи, журнал) и каждая цифра ведёт в свой раздел.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.urls import NoReverseMatch, reverse

ZERO = Decimal(0)

PERIODS = [
    ("today", "Сегодня"), ("yesterday", "Вчера"), ("week", "Текущая неделя"), ("last_week", "Прошлая неделя"),
    ("month", "Текущий месяц"), ("last_month", "Прошлый месяц"), ("quarter", "Текущий квартал"),
    ("year", "Текущий год"), ("all", "Всё время"),
]
PERIOD_NAMES = dict(PERIODS)
DEFAULT_PERIOD = "month"


def period_range(key, date_from=None, date_to=None, today=None):
    """(начало, конец, ключ, подпись). Конец включительно. None — без границы («Всё время»)."""
    t = today or date.today()
    if key == "custom":
        try:
            a, b = date.fromisoformat(date_from), date.fromisoformat(date_to)
        except (TypeError, ValueError):
            a = b = None
        if a and b and a <= b:
            return a, b, "custom", f"{a:%d.%m.%Y} – {b:%d.%m.%Y}"
        key = DEFAULT_PERIOD  # некорректный период — не считаем, берём по умолчанию
    if key not in PERIOD_NAMES:
        key = DEFAULT_PERIOD
    if key == "today":
        a = b = t
    elif key == "yesterday":
        a = b = t - timedelta(days=1)
    elif key == "week":
        a, b = t - timedelta(days=t.weekday()), t
    elif key == "last_week":
        b = t - timedelta(days=t.weekday() + 1)
        a = b - timedelta(days=6)
    elif key == "month":
        a, b = t.replace(day=1), t
    elif key == "last_month":
        b = t.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
    elif key == "quarter":
        a, b = date(t.year, 3 * ((t.month - 1) // 3) + 1, 1), t
    elif key == "year":
        a, b = date(t.year, 1, 1), t
    else:
        a = b = None
    return a, b, key, PERIOD_NAMES[key]


def _in(d, a, b):
    return (a is None or d >= a) and (b is None or d <= b)


def operations(objects=None, a=None, b=None):
    """Все денежные операции: платежи по объёмам + прочие доходы/расходы. Только сохранённые (подтверждённые)."""
    from contracts.models import Payment
    from finance.models import Transaction
    pays = Payment.objects.select_related("contract__construction_object", "assignment__crew",
                                          "assignment__employee")
    txs = Transaction.objects.select_related("construction_object")
    if objects is not None:
        pays = pays.filter(contract__construction_object__in=objects)
        txs = txs.filter(construction_object__in=objects)
    if a:
        pays, txs = pays.filter(date__gte=a), txs.filter(date__gte=a)
    if b:
        pays, txs = pays.filter(date__lte=b), txs.filter(date__lte=b)
    ops = []
    for p in pays:
        obj = p.contract.construction_object
        ops.append({"date": p.date, "income": p.is_income, "amount": p.amount, "object": obj,
                    "title": p.get_kind_display() + (f": {p.assignment.performer}" if p.assignment else ""),
                    "meta": p.contract.work_type + (f" · {p.note}" if p.note else ""),
                    "url": reverse("object_tab", args=[obj.pk, "money"])})
    for t in txs:
        obj = t.construction_object
        ops.append({"date": t.date, "income": t.kind == "income", "amount": t.amount, "object": obj,
                    "title": t.category or t.get_kind_display(), "meta": t.description,
                    "url": reverse("object_tab", args=[obj.pk, "money"]) if obj else reverse("finance_list")})
    ops.sort(key=lambda o: o["date"], reverse=True)
    return ops


def debts(contracts):
    """Дебиторка (нам должны генподрядчики) и кредиторка (мы должны рабочим) на сегодня."""
    receivable = sum((max(c.client_due, ZERO) for c in contracts), ZERO)
    payable_rows = []
    for c in contracts:
        for a in c.assignments.all():
            if a.due > 0:
                payable_rows.append(a)
    payable = sum((a.due for a in payable_rows), ZERO)
    receivable_rows = [c for c in contracts if c.client_due > 0]
    return receivable, payable, receivable_rows, payable_rows


def chart(ops, a, b):
    """Столбики «поступления / расходы» по дням, неделям или месяцам — в зависимости от периода."""
    if not ops and (a is None or b is None):
        return None
    dates = [o["date"] for o in ops]
    a = a or min(dates)
    b = b or max(dates)
    days = (b - a).days + 1
    if days <= 31:
        step, fmt = "day", "%d.%m"
    elif days <= 120:
        step, fmt = "week", "%d.%m"
    else:
        step, fmt = "month", "%m.%Y"

    def bucket(d):
        if step == "day":
            return d
        if step == "week":
            return d - timedelta(days=d.weekday())
        return d.replace(day=1)

    keys, cur = [], bucket(a)
    while cur <= b:
        keys.append(cur)
        if step == "day":
            cur += timedelta(days=1)
        elif step == "week":
            cur += timedelta(days=7)
        else:
            cur = (cur.replace(day=monthrange(cur.year, cur.month)[1]) + timedelta(days=1))
    data = {k: [ZERO, ZERO] for k in keys}
    for o in ops:
        k = bucket(o["date"])
        if k in data:
            data[k][0 if o["income"] else 1] += o["amount"]
    if not any(v[0] or v[1] for v in data.values()):
        return None
    top = max(max(v) for v in data.values()) or 1
    W, H, pad = 720, 200, 26
    n = len(keys)
    slot = (W - 10) / n
    bw = max(min(slot * 0.36, 26), 2)
    bars = []
    for i, k in enumerate(keys):
        inc, exp = data[k]
        x = 5 + i * slot + slot / 2
        end = {"day": k, "week": k + timedelta(days=6)}.get(
            step, k.replace(day=monthrange(k.year, k.month)[1]))
        label = k.strftime(fmt) if step != "week" else f"{k:%d.%m}–{end:%d.%m}"
        hi = float(inc) / float(top) * (H - pad - 6)
        he = float(exp) / float(top) * (H - pad - 6)
        bars.append({
            "x1": round(x - bw - 1, 1), "x2": round(x + 1, 1), "w": round(bw, 1),
            "yi": round(H - pad - hi, 1), "hi": round(hi, 1), "ye": round(H - pad - he, 1), "he": round(he, 1),
            "inc": inc, "exp": exp, "label": label,
            "show_label": n <= 12 or i % max(n // 8, 1) == 0, "lx": round(x, 1),
        })
    return {"bars": bars, "W": W, "H": H, "base": H - pad, "step": step}


def purchase_counts(requests, today=None):
    t = today or date.today()
    rs = list(requests)
    late = [r for r in rs if r.status in ("approved", "ordered") and r.needed_by and r.needed_by < t]
    return {
        "new": sum(r.status == "new" for r in rs),
        "approved": sum(r.status == "approved" for r in rs),
        "ordered": sum(r.status == "ordered" for r in rs),
        "overdue": len(late), "late": late[:5],
    }


def work_progress(objects, by_obj, today=None):
    """План/факт в деньгах по объектам. Разные единицы (м², м³, шт) не складываем — только суммы."""
    t = today or date.today()
    rows = []
    for o in objects:
        cs = by_obj.get(o.pk, [])
        plan = sum((c.total for c in cs), ZERO)
        done = sum((c.earned for c in cs), ZERO)
        lag = [c for c in cs if c.status == "active" and (c.is_overdue or c.delay_risk_days)]
        if not cs or o.is_closed:
            continue
        rows.append({"o": o, "plan": plan, "done": done, "left": plan - done,
                     "pct": int(done * 100 / plan) if plan else None, "lag": lag})
    plan = sum((r["plan"] for r in rows), ZERO)
    done = sum((r["done"] for r in rows), ZERO)
    from quality.models import DailyReport
    seen = set(DailyReport.objects.filter(date__gte=t - timedelta(days=1)).values_list(
        "construction_object_id", flat=True))
    no_report = [o for o in objects if o.is_working and o.pk not in seen]
    return {"rows": rows, "plan": plan, "done": done, "left": plan - done,
            "pct": int(done * 100 / plan) if plan else None,
            "lagging": [r for r in rows if r["lag"]], "no_report": no_report}


def materials_block(objects):
    from warehouse.models import Material, PurchaseRequest, StockMovement, Warehouse
    low = [m for m in Material.objects.all() if m.is_low]
    expected = list(StockMovement.objects.filter(kind="transfer", received=False).select_related(
        "material", "to_warehouse__construction_object"))
    ordered = list(PurchaseRequest.objects.filter(status="ordered", construction_object__in=objects).select_related(
        "material", "construction_object"))
    negative = []
    for w in Warehouse.objects.all():
        for r in w.balances():
            if r["balance"] < 0:
                negative.append((w, r))
    return {"low": low, "expected": expected, "ordered": ordered, "negative": negative}


TASK_DONE_STATUSES = ("done",)


def tasks_block(user, objects, a, b, today=None):
    from staff.models import Task
    t = today or date.today()
    qs = Task.objects.select_related("assignee", "construction_object").filter(
        construction_object__in=objects) | Task.objects.select_related("assignee", "construction_object").filter(
        construction_object__isnull=True)
    employee = getattr(user, "employee", None)
    mine = qs.filter(assignee=employee) if employee else qs.none()
    scope = mine if employee and mine.exists() else qs
    open_ = scope.exclude(status="done")
    done = scope.filter(status="done")
    if a:
        done = done.filter(done_at__date__gte=a)
    if b:
        done = done.filter(done_at__date__lte=b)
    return {
        "personal": bool(employee and mine.exists()),
        "today": list(open_.filter(due_date=t)),
        "overdue": list(open_.filter(due_date__lt=t).order_by("due_date")),
        "week": list(open_.filter(due_date__gt=t, due_date__lte=t + timedelta(days=7)).order_by("due_date")),
        "open_count": open_.count(),
        "done_count": done.count(),
    }


SOURCE_URLS = {
    "Объекты": "object_detail", "Договоры (объёмы работ)": "contract_detail", "Замечания": "remark_detail",
    "Ежедневные отчёты": "report_detail", "Заявки и закупки": "purchase_detail",
    "Инвентаризации": "inventory_detail", "Склады": "warehouse_detail",
}


def activity(objects, limit=10):
    from .models import AuditLog
    qs = AuditLog.objects.select_related("user", "construction_object").order_by("-created_at")
    ids = {o.pk for o in objects}
    rows = []
    for e in qs[:limit * 3]:
        if e.construction_object_id and e.construction_object_id not in ids:
            continue
        url = None
        name = SOURCE_URLS.get(e.module)
        if name and e.object_id.isdigit():
            try:
                url = reverse(name, args=[int(e.object_id)])
            except NoReverseMatch:
                url = None
        if url is None and e.construction_object_id:
            url = reverse("object_tab", args=[e.construction_object_id, "docs"])
        rows.append((e, url or reverse("history")))
        if len(rows) >= limit:
            break
    return rows
