"""Раздел «Объекты» (ТЗ модуля «Объект»): общий список, создание, редактирование, смена статуса, закрытие.

Карточка объекта и её вкладки — в core/object_views.py.
"""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from contracts.models import Payment, WorkContract, WorkLog, summary
from core import audit
from core.models import AuditLog
from finance.models import Transaction
from quality.models import DailyReport, Remark
from staff.models import Task
from warehouse.models import PurchaseRequest, StockMovement

from .forms import CITY_PREFIX, ObjectCardForm
from .models import ConstructionObject, SafetyRecord, TransportRequest

ZERO = Decimal(0)
S = ConstructionObject.Status
# Фильтр статусов в списке (ТЗ п. 4.2)
STATUS_FILTER = [("working", "В работе"), ("preparing", "Подготовка"), ("in_progress", "Активные"),
                 ("paused", "Приостановлены"), ("finishing", "Завершение"), ("done", "Закрытые"),
                 ("archive", "Архив"), ("planned", "Черновики"), ("all", "Все")]


def can_edit(user):
    return user.is_superuser or user.has_perm("objects.change_constructionobject")


def can_create(user):
    return user.is_superuser or user.has_perm("objects.add_constructionobject")


def can_close(user):
    return user.is_superuser or user.has_perm("objects.close_object")


def _by_object(qs, field="construction_object"):
    return dict(qs.values_list(field).annotate(n=Count("id")))


def _sum_by(qs, field, value):
    return {k: v or ZERO for k, v in qs.values_list(field).annotate(s=Sum(value))}


def expenses_by_object():
    """Оплаченные расходы по объектам: платежи (кроме поступлений) + прочие расходы."""
    pays = _sum_by(Payment.objects.exclude(kind=Payment.Kind.INCOME), "contract__construction_object", "amount")
    tx = _sum_by(Transaction.objects.filter(kind="expense", construction_object__isnull=False),
                 "construction_object", "amount")
    return {k: pays.get(k, ZERO) + tx.get(k, ZERO) for k in set(pays) | set(tx)}


def object_rows():
    """Строки общего списка (ТЗ п. 4.1): деньги, прогресс, задачи по каждому объекту."""
    contracts = list(WorkContract.objects.prefetch_related("assignments__crew", "assignments__employee"))
    by_obj = {}
    for c in contracts:
        by_obj.setdefault(c.construction_object_id, []).append(c)
    today = date.today()
    open_tasks = _by_object(Task.objects.exclude(status="done"))
    late_tasks = _by_object(Task.objects.exclude(status="done").filter(due_date__lt=today))
    open_remarks = _by_object(Remark.objects.exclude(status=Remark.Status.CLOSED))
    spent = expenses_by_object()
    rows = []
    for o in ConstructionObject.objects.select_related("client", "manager", "responsible", "general_contractor"):
        s = summary(by_obj.get(o.pk, []))
        fact = spent.get(o.pk, ZERO)
        rows.append({
            "o": o, "s": s, "fact": fact,
            "deviation": (o.budget - fact) if o.budget else None,
            "over": bool(o.budget and fact > o.budget),
            "tasks": open_tasks.get(o.pk, 0), "late": late_tasks.get(o.pk, 0),
            "remarks": open_remarks.get(o.pk, 0),
            "overdue": bool(o.end_date and o.end_date < today and not o.is_closed),
            "group": "working" if o.is_working or o.is_paused else o.status,
        })
    order = {S.IN_PROGRESS: 0, S.FINISHING: 1, S.ACCEPTANCE: 2, S.PREPARING: 3, S.PAUSED: 4, S.PLANNED: 5,
             S.DONE: 6, S.ARCHIVE: 7}
    rows.sort(key=lambda r: (order.get(r["o"].status, 9), not (r["late"] or r["overdue"]), r["o"].name))
    return rows


@login_required
def object_list(request):
    rows = object_rows()
    status = request.GET.get("status", "working")
    if status == "active":
        status = "working"
    if status not in dict(STATUS_FILTER):
        status = "working"
    counts = {"all": len(rows), "working": sum(r["o"].is_working or r["o"].is_paused for r in rows)}
    for r in rows:
        counts[r["o"].status] = counts.get(r["o"].status, 0) + 1
    working = [r for r in rows if r["o"].is_working or r["o"].is_paused]
    budget = sum((r["o"].budget for r in working), ZERO)
    fact = sum((r["fact"] for r in working), ZERO)

    def options(attr):
        seen = {}
        for r in rows:
            v = getattr(r["o"], attr)
            if v:
                seen[str(getattr(v, "pk", v))] = str(v)
        return sorted(seen.items(), key=lambda x: x[1])

    export = [{
        "id": r["o"].pk, "Название объекта": r["o"].name, "Код": r["o"].code, "Заказчик": str(r["o"].client or ""),
        "Адрес / регион": ", ".join(x for x in (r["o"].city, r["o"].address) if x),
        "Руководитель объекта": str(r["o"].manager or ""), "Ответственный менеджер": str(r["o"].responsible or ""),
        "Дата начала": f"{r['o'].start_date:%d.%m.%Y}" if r["o"].start_date else "",
        "Плановое завершение": f"{r['o'].end_date:%d.%m.%Y}" if r["o"].end_date else "",
        "Статус": r["o"].get_status_display(), "Готовность, %": r["s"]["progress"],
        "Плановый бюджет, ₸": int(r["o"].budget), "Фактические расходы, ₸": int(r["fact"]),
        "Отклонение бюджета, ₸": int(r["deviation"]) if r["deviation"] is not None else "",
        "Активные задачи": r["tasks"], "Просроченные задачи": r["late"],
    } for r in rows]
    return render(request, "objects/list.html", {
        "rows": rows, "export": export, "status": status, "counts": counts,
        "statuses": [(k, label, counts.get(k, 0)) for k, label in STATUS_FILTER],
        "kpi": {"working": counts["working"], "budget": budget, "fact": fact,
                "over": sum(r["over"] for r in working), "late": sum(r["late"] for r in working),
                "tasks": sum(r["tasks"] for r in working),
                "progress": int(sum(r["s"]["earned"] for r in working) * 100 / t)
                if (t := sum(r["s"]["total"] for r in working)) else 0},
        "managers": options("manager"), "clients": options("client"), "cities": options("city"),
        "kinds": [(k, v) for k, v in ConstructionObject.Kind.choices if any(r["o"].kind == k for r in rows)],
        "can_create": can_create(request.user), "can_edit": can_edit(request.user),
        "can_close": can_close(request.user), "today": date.today(),
    })


def _form_page(request, title, instance=None):
    creating = instance is None
    if creating and not can_create(request.user) or not creating and not can_edit(request.user):
        return render(request, "objects/denied.html", {"title": title, "obj": instance}, status=403)
    action = request.POST.get("action", "create")
    draft = request.method == "POST" and action == "draft" and creating
    if request.method == "POST":
        before = audit.snapshot(instance) if instance else None
        form = ObjectCardForm(request.POST, request.FILES, instance=instance, draft=draft)
        if form.is_valid():
            obj = form.save()
            audit.log(request, obj, AuditLog.Action.CREATE if creating else AuditLog.Action.UPDATE, before=before,
                      reason=request.POST.get("change_reason", "")[:300])
            if creating:
                messages.success(request, f"Объект «{obj.name}» создан, код {obj.code}." if not draft else
                                 f"Черновик «{obj.name}» сохранён. Заполните остальные поля, когда будут данные.")
                if action == "create_open":
                    return redirect("object_detail", obj.pk)
                return redirect(reverse("object_list") + ("?status=planned" if draft else ""))
            messages.success(request, "Изменения сохранены")
            return redirect("object_detail", obj.pk)
    else:
        form = ObjectCardForm(instance=instance)
    return render(request, "objects/form.html", {
        "form": form, "title": title, "obj": instance, "creating": creating,
        "city_prefix": CITY_PREFIX, "cur_obj": instance,
        "back": reverse("object_detail", args=[instance.pk]) if instance else reverse("object_list"),
        "sections": [
            ("Основное", ["name", "code", "kind", "status"]),
            ("Заказчик и договор", ["client", "new_client", "general_contractor", "contract_number",
                                    "contract_amount", "budget"]),
            ("Где", ["city", "address", "coordinates"]),
            ("Ответственные", ["manager", "responsible", "foreman", "pto"]),
            ("Сроки", ["start_date", "end_date"]),
            ("Дополнительно", ["photo", "description"]),
        ],
    })


@login_required
def object_create(request):
    return _form_page(request, "Новый объект")


@login_required
def object_edit(request, pk):
    return _form_page(request, "Редактировать объект", get_object_or_404(ConstructionObject, pk=pk))


# ---------- закрытие объекта (ТЗ п. 25) ----------

def closing_checklist(obj):
    """Чек-лист закрытия: (ключ, пункт, выполнен?, блокирует?, подробность, ссылка)."""
    from core.object_views import tab_url
    contracts = list(obj.contracts.prefetch_related("assignments"))
    s = summary(contracts)
    whs = list(obj.warehouses.all())
    unfinished = [c for c in contracts if c.status != WorkContract.Status.DONE]
    pending_logs = WorkLog.objects.filter(assignment__contract__construction_object=obj,
                                          status=WorkLog.Status.SUBMITTED).count()
    transit = StockMovement.objects.filter(kind="transfer", received=False, to_warehouse__in=whs).count()
    open_req = PurchaseRequest.objects.filter(construction_object=obj, status__in=PurchaseRequest.OPEN).count()
    open_remarks = obj.remarks.exclude(status=Remark.Status.CLOSED).count()
    open_tasks = obj.tasks.exclude(status="done").count()
    unconfirmed = obj.daily_reports.filter(confirmed=False).count()
    open_transport = obj.transport.filter(status__in=TransportRequest.OPEN).count()
    open_safety = obj.safety.filter(kind=SafetyRecord.Kind.INCIDENT, confirmed=False).count()
    docs = obj.documents.count()

    def n(x, one, few, many):
        x10, x100 = x % 10, x % 100
        word = one if x10 == 1 and x100 != 11 else few if 2 <= x10 <= 4 and not 12 <= x100 <= 14 else many
        return f"{x} {word}"

    items = [
        ("works", "Работы завершены и подтверждены", not unfinished, True,
         "Все виды работ сданы" if not unfinished else f"Не сданы: {', '.join(c.work_type for c in unfinished[:3])}"
         + ("…" if len(unfinished) > 3 else ""), tab_url(obj, "work")),
        ("acts", "Выработка проверена ПТО, акты оформлены", not pending_logs, True,
         "Всё проверено" if not pending_logs else n(pending_logs, "запись ждёт", "записи ждут", "записей ждут")
         + " проверки ПТО", tab_url(obj, "work")),
        ("stock", "Материалы и складские остатки сверены", not transit, True,
         "Нет непринятых перемещений" if not transit else n(transit, "перемещение не принято",
                                                             "перемещения не приняты", "перемещений не принято"),
         tab_url(obj, "materials")),
        ("purchases", "Незакрытые закупки проверены", not open_req, True,
         "Открытых заявок нет" if not open_req else n(open_req, "заявка в работе", "заявки в работе",
                                                      "заявок в работе"), tab_url(obj, "purchases")),
        ("workers", "Расчёт с бригадами выполнен", s["workers_due"] <= 0, True,
         "Долгов перед рабочими нет" if s["workers_due"] <= 0 else f"Должны рабочим {s['workers_due']:,.0f} ₸"
         .replace(",", " "), tab_url(obj, "people")),
        ("debts", "Задолженности отображены", True, False,
         f"Нам должны {s['client_due']:,.0f} ₸".replace(",", " ") if s["client_due"] > 0
         else "Генподрядчик рассчитался полностью", tab_url(obj, "money")),
        ("defects", "Дефекты устранены", not open_remarks, True,
         "Открытых замечаний нет" if not open_remarks else n(open_remarks, "замечание открыто",
                                                             "замечания открыты", "замечаний открыто"),
         tab_url(obj, "remarks")),
        ("tasks", "Задачи закрыты", not open_tasks, True,
         "Открытых задач нет" if not open_tasks else n(open_tasks, "задача не закрыта", "задачи не закрыты",
                                                       "задач не закрыто"), tab_url(obj, "tasks")),
        ("reports", "Ежедневные отчёты подтверждены", not unconfirmed, True,
         "Все отчёты подтверждены" if not unconfirmed else n(unconfirmed, "отчёт ждёт", "отчёта ждут",
                                                              "отчётов ждут") + " подтверждения",
         tab_url(obj, "reports")),
        ("transport", "Заявки на транспорт закрыты", not open_transport, True,
         "Открытых заявок нет" if not open_transport else n(open_transport, "заявка открыта", "заявки открыты",
                                                            "заявок открыто"), tab_url(obj, "transport")),
        ("safety", "Происшествия по охране труда закрыты", not open_safety, True,
         "Открытых происшествий нет" if not open_safety else n(open_safety, "происшествие не закрыто",
                                                               "происшествия не закрыты", "происшествий не закрыто"),
         tab_url(obj, "safety")),
        ("docs", "Документы собраны", docs > 0, False,
         n(docs, "документ", "документа", "документов") + " в реестре" if docs else "В реестре нет документов",
         tab_url(obj, "docs")),
    ]
    return [dict(zip(("key", "title", "ok", "blocking", "detail", "url"), i)) for i in items]


TRANSITIONS = {
    # действие: (из каких статусов, подпись для журнала)
    "pause": ({S.PREPARING, S.IN_PROGRESS, S.FINISHING, S.ACCEPTANCE}, "Приостановлен"),
    "resume": ({S.PAUSED}, "Возобновлён"),
    "close": ({S.PREPARING, S.IN_PROGRESS, S.FINISHING, S.ACCEPTANCE, S.PAUSED}, "Закрыт"),
    "archive": ({S.DONE}, "Отправлен в архив"),
    "reopen": ({S.DONE, S.ARCHIVE}, "Открыт повторно"),
    "activate": ({S.PLANNED, S.PREPARING}, "Переведён в работу"),
}


@login_required
@require_POST
def object_status(request, pk):
    """Приостановить / возобновить / закрыть / архивировать — с проверкой прав и чек-листа."""
    obj = get_object_or_404(ConstructionObject, pk=pk)
    action = request.POST.get("action", "")
    reason = request.POST.get("reason", "").strip()[:300]
    back = reverse("object_detail", args=[pk])
    if action not in TRANSITIONS:
        messages.error(request, "Неизвестное действие")
        return redirect(back)
    allowed, label = TRANSITIONS[action]
    need_close_perm = action in ("close", "archive", "reopen")
    if not (can_close(request.user) if need_close_perm else can_edit(request.user)):
        return HttpResponseForbidden("Недостаточно прав для этого действия.")
    if obj.status not in allowed:
        messages.error(request, f"Сейчас объект в статусе «{obj.get_status_display()}» — это действие недоступно.")
        return redirect(back)
    if action in ("pause", "reopen") and not reason:
        messages.error(request, "Укажите причину — она попадёт в журнал.")
        return redirect(back)
    if action == "close":
        blocking = [i for i in closing_checklist(obj) if i["blocking"] and not i["ok"]]
        if blocking:
            messages.error(request, "Закрыть нельзя: остались незавершённые пункты чек-листа.")
            return redirect("object_tab", pk, "closing")
    before = audit.snapshot(obj)
    if action == "pause":
        obj.status_before_pause, obj.status = obj.status, S.PAUSED
    elif action == "resume":
        obj.status = obj.status_before_pause or S.IN_PROGRESS
        obj.status_before_pause = ""
    elif action == "close":
        obj.status = S.DONE
    elif action == "archive":
        obj.status = S.ARCHIVE
    elif action == "reopen":
        obj.status = S.FINISHING
    elif action == "activate":
        obj.status = S.IN_PROGRESS
    obj.save()
    audit.log(request, obj, AuditLog.Action.UPDATE, before=before, reason=reason or label)
    messages.success(request, f"Объект «{obj.name}»: {label.lower()}.")
    return redirect(back)
