"""Карточка объекта (ТЗ модуля «Объект», пп. 6–25): верхняя панель, вкладки и формы внутри объекта.

Объект — центр системы: всё, что создаётся во вкладках, хранится один раз и сразу видно
в общих разделах. Вкладки «Документы», «Фото», «Согласования» и «История» ничего не дублируют —
они собирают записи из основных сущностей.
"""
from datetime import date, timedelta
from decimal import Decimal

from django import forms as djforms
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from contracts.forms import ContractForm, PaymentForm, WorkLogForm
from contracts.models import Assignment, Payment, WorkContract, WorkLog, summary
from objects.forms import MediaForm, SafetyForm, TransportForm
from objects.models import ConstructionObject, ObjectDocument, SafetyRecord, TransportRequest
from quality.forms import DailyReportForm, RemarkForm
from quality.models import Remark
from staff.models import Task
from warehouse.forms import PurchaseRequestForm
from warehouse.models import PurchaseRequest, StockMovement

from . import alerts
from .forms import StockMovementForm, StyledMixin, TaskForm, TransactionForm
from .models import AuditLog
from .views import form_page

ZERO = Decimal(0)

# ключ, название, иконка, показывать в основной строке на ПК
TABS = [
    ("overview", "Общая информация", "home", True),
    ("work", "Работы и объёмы", "contract", True),
    ("budget", "Бюджет", "wallet", True),
    ("purchases", "Закупки", "cash", True),
    ("materials", "Материалы и склад", "box", True),
    ("money", "Финансы", "wallet", True),
    ("tasks", "Задачи", "task", True),
    ("docs", "Документы", "file", True),
    ("people", "Сотрудники и бригады", "users", False),
    ("transport", "Транспорт и техника", "truck", False),
    ("reports", "Ежедневные отчёты", "clipboard", False),
    ("photos", "Фото и видео", "camera", False),
    ("remarks", "Качество и дефекты", "flag", False),
    ("safety", "Охрана труда", "shield", False),
    ("approvals", "Согласования", "check", False),
    ("history", "История", "history", False),
    ("closing", "Закрытие объекта", "lock", False),
]
SHORT = {"work": "Работы", "materials": "Склад", "overview": "Обзор"}  # короткие подписи в строке вкладок на ПК
TAB_NAMES = {t[0] for t in TABS} | {"output"}  # «output» — старый адрес выработки, открывает «Работы и объёмы»


def tab_url(obj, tab="overview"):
    if tab == "overview":
        return reverse("object_detail", args=[obj.pk])
    return reverse("object_tab", args=[obj.pk, tab])


def _perms(user):
    from objects.views import can_close, can_edit
    return {"can_edit": can_edit(user), "can_close": can_close(user)}


@login_required
def object_detail(request, pk, tab="overview"):
    if tab not in TAB_NAMES:
        raise Http404
    if tab == "output":
        tab = "work"
    obj = get_object_or_404(ConstructionObject.objects.select_related(
        "client", "manager", "foreman", "pto", "responsible", "general_contractor"), pk=pk)
    contracts = list(obj.contracts.prefetch_related("assignments__crew", "assignments__employee"))
    tabs = [{"key": k, "label": label, "short": SHORT.get(k, label), "icon": ic, "main": main, "url": tab_url(obj, k)}
            for k, label, ic, main in TABS]
    ctx = {"obj": obj, "cur_obj": obj, "tab": tab, "tabs": tabs, "contracts": contracts, "s": summary(contracts),
           "today": date.today(), **_perms(request.user)}
    ctx.update(_counts(obj, contracts))
    ctx["tab_label"] = next(t["label"] for t in tabs if t["key"] == tab)
    ctx["more_hot"] = any(ctx["counts"].get(t["key"]) and t["key"] in ctx["hot"] for t in tabs if not t["main"])
    ctx["more_active"] = any(t["key"] == tab for t in tabs if not t["main"])
    ctx.update(globals()[f"_tab_{tab}"](request, obj, contracts))
    return render(request, f"object/{tab}.html", ctx)


def _approvals(obj):
    """Что ждёт решения по объекту (ТЗ п. 23): собирается из основных сущностей, ничего не дублирует."""
    items = []
    for p in PurchaseRequest.objects.filter(construction_object=obj, status="new").select_related("material", "author"):
        items.append({"kind": "Закупка", "title": f"Заявка {p.number}: {p.material} — {p.quantity.normalize():f} "
                                                   f"{p.material.unit}", "who": p.author, "since": p.created_at.date(),
                      "amount": p.amount, "url": reverse("purchase_detail", args=[p.pk]), "act": "Рассмотреть"})
    for log in WorkLog.objects.filter(assignment__contract__construction_object=obj,
                                      status=WorkLog.Status.SUBMITTED).select_related("assignment__contract",
                                                                                      "assignment__crew",
                                                                                      "assignment__employee",
                                                                                      "created_by"):
        c = log.assignment.contract
        items.append({"kind": "Объём ПТО", "title": f"{c.work_type}: {log.volume.normalize():f} {c.unit} · "
                                                     f"{log.assignment.performer}",
                      "who": log.created_by, "since": log.date, "amount": log.volume * c.price,
                      "url": reverse("worklog_review", args=[log.pk]), "act": "Проверить"})
    for rep in obj.daily_reports.filter(confirmed=False).select_related("author"):
        items.append({"kind": "Отчёт", "title": f"Ежедневный отчёт за {rep.date:%d.%m.%Y}", "who": rep.author,
                      "since": rep.date, "amount": None, "url": reverse("report_detail", args=[rep.pk]),
                      "act": "Подтвердить"})
    for r in obj.remarks.filter(status=Remark.Status.REVIEW).select_related("responsible"):
        items.append({"kind": "Дефект", "title": f"{r.number}: устранение на проверке", "who": r.responsible,
                      "since": r.created_at.date(), "amount": None, "url": reverse("remark_detail", args=[r.pk]),
                      "act": "Принять работу"})
    for t in obj.transport.filter(status=TransportRequest.Status.NEW).select_related("responsible"):
        items.append({"kind": "Транспорт", "title": f"{t.number}: {t.get_kind_display()} на {t.date:%d.%m}",
                      "who": t.responsible, "since": t.created_at.date(), "amount": t.cost or None,
                      "url": tab_url(obj, "transport"), "act": "Открыть"})
    today = date.today()
    for i in items:
        i["age"] = (today - i["since"]).days if i["since"] else 0
    items.sort(key=lambda i: -i["age"])
    return items


def _counts(obj, contracts):
    """Счётчики на вкладках. В hot — то, что ждёт действия (красный)."""
    today = date.today()
    pending = WorkLog.objects.filter(assignment__contract__construction_object=obj,
                                     status=WorkLog.Status.SUBMITTED).count()
    arriving = StockMovement.objects.filter(kind="transfer", received=False, to_warehouse__construction_object=obj).count()
    open_req = PurchaseRequest.objects.filter(construction_object=obj, status__in=PurchaseRequest.OPEN).count()
    late_tasks = obj.tasks.exclude(status="done").filter(due_date__lt=today).count()
    approvals = len(_approvals(obj))
    safety_bad = sum(r.is_open for r in obj.safety.all())
    counts = {
        "work": len(contracts), "purchases": open_req, "materials": arriving,
        "tasks": obj.tasks.exclude(status="done").count(),
        "people": Assignment.objects.filter(contract__construction_object=obj).count(),
        "transport": obj.transport.filter(status__in=TransportRequest.OPEN).count(),
        "remarks": obj.remarks.exclude(status="closed").count(),
        "reports": obj.daily_reports.filter(confirmed=False).count(),
        "docs": obj.documents.count(), "approvals": approvals, "safety": safety_bad,
        "photos": obj.media.count(),
    }
    hot = {k for k, v in (("work", pending), ("materials", arriving), ("remarks", counts["remarks"]),
                          ("tasks", late_tasks), ("approvals", approvals), ("safety", safety_bad)) if v}
    return {"counts": counts, "hot": hot, "late_tasks": late_tasks, "pending_logs": pending}


def _money(obj, s):
    """Деньги объекта без двойного учёта (ТЗ п. 7.1, 13):
    оплачено — фактическое движение денег; начислено — оплачено + долг рабочим за принятый объём;
    обязательства — согласованные и заказанные, но ещё не полученные закупки."""
    paid = alerts.object_expenses(obj)
    commitments = sum((p.amount for p in PurchaseRequest.objects.filter(
        construction_object=obj, status__in=("approved", "ordered")) if p.amount), ZERO)
    debt = max(s["workers_due"], ZERO)
    fact = paid + debt
    left = obj.budget - fact - commitments if obj.budget else None
    used = int((fact + commitments) * 100 / obj.budget) if obj.budget else None
    return {"paid": paid, "fact": fact, "debt": debt, "commitments": commitments, "left": left, "used": used,
            "over": bool(obj.budget and fact + commitments > obj.budget)}


def _tab_overview(request, obj, contracts):
    s = summary(contracts)
    m = _money(obj, s)
    payments = list(Payment.objects.filter(contract__construction_object=obj).select_related("contract")[:6])
    tx = list(obj.transactions.all()[:6])
    fin = sorted([{"date": p.date, "title": p.get_kind_display(), "note": p.note or p.contract.work_type,
                   "amount": p.amount, "income": p.is_income} for p in payments] +
                 [{"date": t.date, "title": t.category or t.get_kind_display(), "note": t.description,
                   "amount": t.amount, "income": t.kind == "income"} for t in tx],
                 key=lambda x: x["date"], reverse=True)[:5]
    stages = sorted(contracts, key=lambda c: (c.start_date or date.max))
    total_days = (obj.end_date - obj.start_date).days if obj.start_date and obj.end_date else None
    passed = (date.today() - obj.start_date).days if obj.start_date else None
    return {
        "m": m, "alerts": alerts.for_object(obj, contracts),
        "fin": fin, "stages": stages,
        "time_pct": max(0, min(100, int(passed * 100 / total_days))) if total_days and passed is not None else None,
        "purchases": PurchaseRequest.objects.filter(construction_object=obj).select_related("material")[:5],
        "docs_recent": _documents(obj)[:5],
        "tasks_open": obj.tasks.exclude(status="done").select_related("assignee").order_by("due_date")[:5],
        "history": obj.history.select_related("user")[:6],
    }


def _tab_work(request, obj, contracts):
    all_logs = WorkLog.objects.filter(assignment__contract__construction_object=obj).select_related(
        "assignment__crew", "assignment__employee", "assignment__contract")
    pending = list(all_logs.filter(status=WorkLog.Status.SUBMITTED))
    logs = pending + list(all_logs.exclude(status=WorkLog.Status.SUBMITTED)[:12])
    rows = []
    for c in contracts:
        rows.append({"c": c, "performers": [a.performer for a in c.assignments.all()]})
    return {"rows": rows, "logs": logs, "pending": pending, "logs_total": all_logs.count()}


def _tab_budget(request, obj, contracts):
    s = summary(contracts)
    m = _money(obj, s)
    pays = {k: v or ZERO for k, v in Payment.objects.filter(contract__construction_object=obj).exclude(
        kind=Payment.Kind.INCOME).values_list("kind").annotate(x=Sum("amount"))}
    labor = sum((c.labor_accrued for c in contracts), ZERO)
    open_mat = sum((p.amount for p in PurchaseRequest.objects.filter(
        construction_object=obj, status__in=("approved", "ordered")) if p.amount), ZERO)
    rows = [
        {"name": "Работы (оплата бригадам)", "fact": labor, "paid": pays.get("worker", ZERO), "commit": ZERO},
        {"name": "Материалы", "fact": pays.get("material", ZERO), "paid": pays.get("material", ZERO),
         "commit": open_mat},
        {"name": "Прочие расходы по договорам", "fact": pays.get("other", ZERO), "paid": pays.get("other", ZERO),
         "commit": ZERO},
    ]
    for cat, amount in obj.transactions.filter(kind="expense").values_list("category").annotate(x=Sum("amount")):
        rows.append({"name": cat or "Прочие расходы", "fact": amount, "paid": amount, "commit": ZERO})
    rows = [r for r in rows if r["fact"] or r["paid"] or r["commit"]]
    total = {k: sum((r[k] for r in rows), ZERO) for k in ("fact", "paid", "commit")}
    for r in rows:
        r["share"] = int((r["fact"] + r["commit"]) * 100 / obj.budget) if obj.budget else None
    history = [e for e in obj.history.filter(module=ConstructionObject._meta.verbose_name_plural).select_related("user")
               if "Бюджет" in (e.changes or "")][:10]
    estimates = list(obj.estimates.prefetch_related("items"))
    return {"m": m, "rows": rows, "total": total, "estimates": estimates,
            "estimates_total": sum((e.total for e in estimates), ZERO), "budget_history": history}


def _tab_purchases(request, obj, contracts):
    reqs = list(PurchaseRequest.objects.filter(construction_object=obj).select_related("material", "supplier",
                                                                                         "author"))
    by_status = {k: 0 for k, _ in PurchaseRequest.Status.choices}
    for p in reqs:
        by_status[p.status] += 1
    suppliers = {}
    for p in reqs:
        if p.supplier:
            row = suppliers.setdefault(p.supplier.pk, {"s": p.supplier, "n": 0, "amount": ZERO, "last": None})
            row["n"] += 1
            row["amount"] += p.amount or ZERO
            row["last"] = max(filter(None, [row["last"], p.created_at.date()]))
    whs = list(obj.warehouses.all())
    for mv in StockMovement.objects.filter(kind="in", supplier__isnull=False).filter(
            Q(construction_object=obj) | Q(warehouse__in=whs)).select_related("supplier"):
        row = suppliers.setdefault(mv.supplier.pk, {"s": mv.supplier, "n": 0, "amount": ZERO, "last": None})
        row["n"] += 1
        row["amount"] += (mv.price or ZERO) * mv.quantity
        row["last"] = max(filter(None, [row["last"], mv.date]))
    return {
        "requests": reqs, "by_status": by_status, "statuses": PurchaseRequest.Status.choices,
        "suppliers": sorted(suppliers.values(), key=lambda r: -r["amount"]),
        "expected": (expected := [p for p in reqs if p.status == "ordered"]),
        "expected_count": len(expected) + StockMovement.objects.filter(kind="transfer", received=False,
                                                                       to_warehouse__in=whs).count(),
        "transit": list(StockMovement.objects.filter(kind="transfer", received=False, to_warehouse__in=whs)
                        .select_related("material", "warehouse")),
    }


def _tab_materials(request, obj, contracts):
    whs = list(obj.warehouses.all())
    return {
        "warehouses": [{"w": w, "rows": w.balances(), "pending": list(w.pending_transfers())} for w in whs],
        "plan_fact": [(c, c.material_plan_fact()) for c in contracts if c.material_plan_fact()],
        "movements": StockMovement.objects.filter(
            Q(construction_object=obj) | Q(warehouse__in=whs) | Q(to_warehouse__in=whs)).distinct().select_related(
            "material", "supplier", "construction_object", "warehouse", "to_warehouse")[:30],
    }


def _tab_money(request, obj, contracts):
    s = summary(contracts)
    tx = list(obj.transactions.all())
    payments = list(Payment.objects.filter(contract__construction_object=obj).select_related(
        "contract", "assignment__crew", "assignment__employee"))
    ops = sorted([{"date": p.date, "kind": p.get_kind_display(), "who": p.assignment.performer if p.assignment else "",
                   "base": p.contract.work_type, "note": p.note, "amount": p.amount, "income": p.is_income}
                  for p in payments] +
                 [{"date": t.date, "kind": "Прочий " + ("доход" if t.kind == "income" else "расход"), "who": "",
                   "base": t.category, "note": t.description, "amount": t.amount, "income": t.kind == "income"}
                  for t in tx], key=lambda x: x["date"], reverse=True)
    other_in = sum((t.amount for t in tx if t.kind == "income"), ZERO)
    m = _money(obj, s)
    return {"ops": ops[:60], "m": m, "income": s["received"] + other_in,
            "result": s["received"] + other_in - m["paid"]}


def _tab_people(request, obj, contracts):
    assignments = list(Assignment.objects.filter(contract__construction_object=obj).select_related(
        "crew__leader", "employee", "contract").prefetch_related("crew__members"))
    days = []
    reports = {r.date: r.workers_count for r in obj.daily_reports.filter(date__gte=date.today() - timedelta(days=13))}
    logs = {}
    for log in WorkLog.objects.filter(assignment__contract__construction_object=obj,
                                      date__gte=date.today() - timedelta(days=13)):
        logs[log.date] = logs.get(log.date, 0) + log.people
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        days.append({"d": d, "n": reports.get(d) or logs.get(d) or 0})
    peak = max([x["n"] for x in days] + [1])
    for x in days:
        x["h"] = int(x["n"] * 100 / peak)
    roles = [("Руководитель объекта", obj.manager), ("Ответственный менеджер", obj.responsible),
             ("Прораб", obj.foreman), ("Инженер ПТО", obj.pto)]
    return {
        "assignments": assignments, "days": days, "roles": roles,
        "earned": sum((a.earned for a in assignments), ZERO),
        "paid": sum((a.paid for a in assignments), ZERO),
        "due": sum((a.due for a in assignments), ZERO),
        "active_contracts": [c for c in contracts if c.status == WorkContract.Status.ACTIVE],
        "people_days": sum(x["n"] for x in days),
    }


def _tab_transport(request, obj, contracts):
    items = list(obj.transport.select_related("responsible"))
    open_ = [t for t in items if t.is_open]
    upcoming = sorted((t for t in open_ if t.date >= date.today()), key=lambda t: (t.date, t.time or ""))
    return {"items": items, "open": open_, "next_t": upcoming[0] if upcoming else None,
            "cost": sum((t.cost for t in items if t.status != "cancelled"), ZERO),
            "hours": sum((t.hours or 0 for t in items), 0)}


def _documents(obj):
    """Единый реестр документов объекта (ТЗ п. 17): загруженные файлы + документы, созданные в операциях."""
    docs = []
    for d in obj.documents.all():
        docs.append({"cat": "files", "type": "Файл", "title": d.title, "number": "", "date": d.uploaded_at.date(),
                     "url": d.file.url if d.file else "", "status": "Загружен", "download": True})
    for e in obj.estimates.all():
        docs.append({"cat": "estimates", "type": "Смета", "title": e.title, "number": "", "date": e.created_at.date(),
                     "url": "", "status": f"{e.total:,.0f} ₸".replace(",", " ")})
    for p in PurchaseRequest.objects.filter(construction_object=obj).select_related("material"):
        docs.append({"cat": "purchases", "type": "Заявка на закупку", "title": f"{p.material}", "number": p.number,
                     "date": p.created_at.date(), "url": reverse("purchase_detail", args=[p.pk]),
                     "status": p.get_status_display()})
    for r in obj.daily_reports.all():
        docs.append({"cat": "reports", "type": "Ежедневный отчёт", "title": f"Отчёт за {r.date:%d.%m.%Y}",
                     "number": "", "date": r.date, "url": reverse("report_detail", args=[r.pk]),
                     "status": "Подтверждён" if r.confirmed else "На проверке"})
    for r in obj.remarks.all():
        docs.append({"cat": "quality", "type": "Замечание", "title": r.description[:70], "number": r.number,
                     "date": r.created_at.date(), "url": reverse("remark_detail", args=[r.pk]),
                     "status": r.get_status_display()})
    for t in obj.transport.all():
        docs.append({"cat": "transport", "type": "Заявка на транспорт", "title": t.task, "number": t.number,
                     "date": t.date, "url": "", "status": t.get_status_display()})
    for d in obj.docflow.all():
        docs.append({"cat": "docflow", "type": d.get_kind_display(), "title": d.title, "number": d.number,
                     "date": d.doc_date, "url": reverse("docflow_detail", args=[d.pk]),
                     "status": d.get_status_display(), "file": d.file.url if d.file else ""})
    docs.sort(key=lambda d: d["date"], reverse=True)
    return docs


DOC_CATS = [("docflow", "Документооборот"), ("files", "Файлы"), ("purchases", "Закупки"), ("estimates", "Сметы"), ("reports", "Отчёты"),
            ("quality", "Качество"), ("transport", "Транспорт")]


def _tab_docs(request, obj, contracts):
    docs = _documents(obj)
    return {"documents": docs, "cats": [(k, v, sum(d["cat"] == k for d in docs)) for k, v in DOC_CATS]}


def _tab_tasks(request, obj, contracts):
    tasks = list(obj.tasks.select_related("assignee").order_by("status", "due_date"))
    open_ = [t for t in tasks if t.status != "done"]
    return {"tasks_open": sorted(open_, key=lambda t: (not t.is_overdue, t.due_date or date.max)),
            "tasks_done": [t for t in tasks if t.status == "done"][:15],
            "late": sum(t.is_overdue for t in open_),
            "by_status": [(k, v, sum(t.status == k for t in open_)) for k, v in Task.Status.choices if k != "done"]}


def _tab_reports(request, obj, contracts):
    return {"reports": obj.daily_reports.select_related("author")[:40]}


def _tab_photos(request, obj, contracts):
    items = []
    for m in obj.media.select_related("author"):
        items.append({"url": m.file.url, "video": m.is_video, "cat": m.category, "cat_label": m.get_category_display(),
                      "title": str(m), "date": m.date, "who": m.author, "src": m.stage})
    for r in obj.remarks.exclude(photo=""):
        items.append({"url": r.photo.url, "cat": "defect", "cat_label": "Дефект", "title": r.description[:60],
                      "date": r.created_at.date(), "who": r.author, "src": r.number})
    for rep in obj.daily_reports.exclude(photo=""):
        items.append({"url": rep.photo.url, "cat": "progress", "cat_label": "Ход работ",
                      "title": f"Отчёт за {rep.date:%d.%m}", "date": rep.date, "who": rep.author, "src": "отчёт"})
    for log in WorkLog.objects.filter(assignment__contract__construction_object=obj).exclude(photo="").select_related(
            "assignment__contract"):
        items.append({"url": log.photo.url, "cat": "progress", "cat_label": "Ход работ",
                      "title": log.assignment.contract.work_type, "date": log.date, "who": log.created_by,
                      "src": "выработка"})
    items.sort(key=lambda x: x["date"], reverse=True)
    from objects.models import ObjectMedia
    return {"items": items, "cats": [(k, v, sum(i["cat"] == k for i in items))
                                     for k, v in ObjectMedia.Category.choices]}


def _tab_remarks(request, obj, contracts):
    remarks = list(obj.remarks.select_related("responsible", "construction_object"))
    open_ = [r for r in remarks if r.status != "closed"]
    return {"open": open_, "closed": [r for r in remarks if r.status == "closed"][:15],
            "late": sum(r.is_overdue for r in open_), "critical": sum(r.priority >= 4 for r in open_),
            "review": sum(r.status == "review" for r in open_)}


def _tab_safety(request, obj, contracts):
    items = list(obj.safety.select_related("instructor"))
    return {"briefings": [i for i in items if i.kind == "briefing"],
            "permits": [i for i in items if i.kind == "permit"],
            "incidents": [i for i in items if i.kind == "incident"],
            "expired": sum(i.expired for i in items), "expiring": sum(i.expiring for i in items)}


def _tab_approvals(request, obj, contracts):
    decided = obj.history.filter(action__in=(AuditLog.Action.ACCEPT, AuditLog.Action.REJECT)).select_related("user")[:20]
    return {"approvals": _approvals(obj), "decided": decided}


HISTORY_GROUPS = [
    ("object", "Объект", ("Объекты",)),
    ("work", "Работы", ("Договоры (объёмы работ)", "Выработка по дням", "Исполнители на объёмах",
                         "Нормативы материалов")),
    ("purchase", "Закупки и склад", ("Заявки и закупки", "Движения материалов", "Инвентаризации")),
    ("money", "Финансы", ("Платежи по договорам", "Финансовые операции", "Сметы")),
    ("quality", "Качество и задачи", ("Замечания", "Задачи")),
    ("reports", "Отчёты и документы", ("Ежедневные отчёты", "Документы", "Фото и видео")),
    ("site", "Транспорт и охрана труда", ("Транспорт и техника", "Охрана труда")),
]


def _tab_history(request, obj, contracts):
    entries = list(obj.history.select_related("user")[:200])
    group_of = {m: key for key, _, mods in HISTORY_GROUPS for m in mods}
    for e in entries:
        e.group = group_of.get(e.module, "other")
    return {"entries": entries,
            "groups": [(k, label, sum(e.group == k for e in entries)) for k, label, _ in HISTORY_GROUPS
                       if any(e.group == k for e in entries)] +
                      ([("other", "Прочее", sum(e.group == "other" for e in entries))]
                       if any(e.group == "other" for e in entries) else [])}


def _tab_closing(request, obj, contracts):
    from objects.views import closing_checklist
    items = closing_checklist(obj)
    blocking = [i for i in items if i["blocking"] and not i["ok"]]
    return {"items": items, "blocking": blocking, "done_count": sum(i["ok"] for i in items)}


# ---------- формы внутри объекта ----------

class DocumentForm(StyledMixin, djforms.ModelForm):
    class Meta:
        model = ObjectDocument
        fields = ["construction_object", "title", "file"]


def _scope(form, obj):
    """Привязывает форму к объекту: объект подставлен и скрыт, в списках — только своё."""
    f = form.fields
    if "construction_object" in f:
        f["construction_object"].initial = obj
        f["construction_object"].widget = djforms.HiddenInput()
        if not form.is_bound:
            form.initial["construction_object"] = obj.pk
    if "contract" in f:
        f["contract"].queryset = f["contract"].queryset.filter(construction_object=obj)
        if f["contract"].queryset.count() == 1:
            form.initial.setdefault("contract", f["contract"].queryset.first().pk)
    if "assignment" in f:
        qs = f["assignment"].queryset.filter(contract__construction_object=obj)
        f["assignment"].queryset = qs
        if not form.initial.get("assignment") and qs.count() == 1:
            form.initial["assignment"] = qs.first().pk
    if "warehouse" in f and not form.initial.get("warehouse"):
        own = obj.warehouses.first()
        if own:
            form.initial["warehouse"] = own.pk


def _scoped(form_class, obj):
    class Scoped(form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            _scope(self, obj)
    Scoped.__name__ = form_class.__name__
    return Scoped


def _remark_done(request, obj):
    from quality.views import _remark_saved
    done = _remark_saved(request)

    def finish(remark):
        done(remark)
        return tab_url(obj, "remarks")
    return finish


def _report_done(request, obj):
    def finish(rep):
        if rep.author_id is None:
            rep.author = request.user
            rep.save(update_fields=["author"])
        return reverse("report_detail", args=[rep.pk])
    return finish


def _media_done(request, obj):
    def finish(m):
        if m.author_id is None:
            m.author = request.user
            m.save(update_fields=["author"])
        return tab_url(obj, "photos")
    return finish


# что: (форма, заголовок, подсказка, вкладка, доп. аргументы формы, кнопка)
NEW = {
    "work": (ContractForm, "Новый вид работ",
             "Что взяли у генподрядчика на этом объекте: вид работ, объём и цену за единицу.", "work", {}, "Сохранить"),
    "output": (WorkLogForm, "Записать выработку",
               "Сколько сделали за день. После проверки ПТО объём попадёт в учёт, а деньги рабочим начислятся сами.",
               "work", {"user": True}, "Записать"),
    "payment": (PaymentForm, "Платёж по объекту",
                "Деньги от генподрядчика, выплата рабочим или расход на материалы. Платёж не подтверждает поставку.",
                "money", {}, "Сохранить"),
    "expense": (TransactionForm, "Прочий доход или расход",
                "Например: аренда техники, доставка, питание.", "money", {}, "Сохранить"),
    "purchase": (PurchaseRequestForm, "Заявка на закупку",
                 "Система проверит бюджет, остатки на складах и последнюю цену. Дальше — согласование руководителем.",
                 "purchases", {"user": True}, "Отправить на согласование"),
    "movement": (StockMovementForm, "Материал: поступление или выдача",
                 "Поступление на склад объекта, выдача в работу, возврат, списание. При нехватке остатка выдача "
                 "не проводится.", "materials", {"user": True}, "Провести"),
    "remark": (RemarkForm, "Новый дефект / замечание", "Ответственному сразу создастся задача на устранение.",
               "remarks", {}, "Сохранить"),
    "task": (TaskForm, "Новая задача", "Исполнитель увидит задачу у себя. Срок и приоритет — по желанию.", "tasks", {},
             "Создать задачу"),
    "report": (DailyReportForm, "Ежедневный отчёт",
               "Короткий отчёт прораба. Выработка и расход материалов за день подтянутся сами. После отправки — "
               "статус «На проверке».", "reports", {}, "Отправить"),
    "doc": (DocumentForm, "Загрузить документ", "Договор, акт, смета, чертёж, исполнительная документация.", "docs", {},
            "Загрузить"),
    "photo": (MediaForm, "Добавить фото или видео", "Можно снять прямо с телефона. JPG, PNG, HEIC, MP4 — до 50 МБ.",
              "photos", {}, "Загрузить"),
    "transport": (TransportForm, "Заявка на транспорт / технику", "Что, куда и когда подать. Статус меняется по мере "
                                                                   "выполнения.", "transport", {}, "Отправить заявку"),
    "safety": (SafetyForm, "Охрана труда", "Инструктаж, допуск или удостоверение, происшествие.", "safety", {},
               "Сохранить"),
}


@login_required
def object_new(request, pk, what):
    if what not in NEW:
        raise Http404
    obj = get_object_or_404(ConstructionObject, pk=pk)
    form_class, title, subtitle, tab, kw, submit = NEW[what]
    kwargs = {k: request.user for k in kw}
    if what == "remark":
        success = _remark_done(request, obj)
    elif what == "report":
        success = _report_done(request, obj)
    elif what == "photo":
        success = _media_done(request, obj)
    else:
        success = tab_url(obj, tab)
    return form_page(request, _scoped(form_class, obj), title, success, form_kwargs=kwargs,
                     subtitle=subtitle, submit=submit, back=tab_url(obj, tab),
                     extra={"cur_obj": obj, "form_obj": obj})


@login_required
def object_add(request, pk):
    """Экран «+» внутри объекта: все действия по объекту."""
    obj = get_object_or_404(ConstructionObject, pk=pk)
    return render(request, "object/add.html", {"obj": obj, "cur_obj": obj})


CHOOSE_TITLES = {
    "purchase": "Заявка на закупку", "payment": "Финансовая операция", "report": "Ежедневный отчёт",
    "doc": "Документ", "task": "Задача по объекту", "output": "Выработка", "remark": "Замечание",
}


@login_required
def add_choose(request, what=None):
    """Экран «+» вне объекта: сначала выбрать объект (объектные операции без объекта не создаются)."""
    if what is not None and what not in NEW:
        raise Http404
    objects = [o for o in ConstructionObject.objects.all() if o.is_working] or list(ConstructionObject.objects.all())
    return render(request, "object/choose.html", {
        "objects": objects, "what": what, "what_title": CHOOSE_TITLES.get(what, NEW[what][1] if what else "")})
