"""Всё по объекту в одном месте: вкладки объекта и формы, открытые изнутри объекта.

Логика работы: взяли объект → создали его в системе → всё остальное (объёмы, рабочие,
выработка, материалы, деньги, замечания, отчёты, документы) живёт внутри объекта.
"""
from django import forms as djforms
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from contracts.forms import ContractForm, PaymentForm, WorkLogForm
from contracts.models import Assignment, Payment, WorkContract, WorkLog, summary
from objects.models import ConstructionObject, ObjectDocument
from quality.forms import DailyReportForm, RemarkForm
from staff.models import Task
from warehouse.forms import PurchaseRequestForm
from warehouse.models import PurchaseRequest, StockMovement, Warehouse

from . import alerts
from .forms import StockMovementForm, StyledMixin, TaskForm, TransactionForm
from .views import form_page

TABS = [
    ("overview", "Обзор", "home"),
    ("work", "Объёмы работ", "contract"),
    ("people", "Рабочие", "users"),
    ("output", "Выработка", "brick"),
    ("materials", "Материалы", "box"),
    ("money", "Деньги", "wallet"),
    ("remarks", "Замечания", "flag"),
    ("reports", "Отчёты", "clipboard"),
    ("docs", "Документы", "history"),
]
TAB_NAMES = {t[0] for t in TABS}


def tab_url(obj, tab="overview"):
    if tab == "overview":
        return reverse("object_detail", args=[obj.pk])
    return reverse("object_tab", args=[obj.pk, tab])


@login_required
def object_detail(request, pk, tab="overview"):
    if tab not in TAB_NAMES:
        raise Http404
    obj = get_object_or_404(ConstructionObject.objects.select_related(
        "client", "manager", "foreman", "pto"), pk=pk)
    contracts = list(obj.contracts.prefetch_related("assignments__crew", "assignments__employee"))
    ctx = {"obj": obj, "cur_obj": obj, "tab": tab, "tabs": TABS, "contracts": contracts,
           "s": summary(contracts)}
    ctx.update(_counts(obj, contracts))
    ctx.update(globals()[f"_tab_{tab}"](request, obj, contracts))
    return render(request, f"object/{tab}.html", ctx)


def _counts(obj, contracts):
    """Счётчики на вкладках, как «Договора проекта (4)». Красным — то, что ждёт действия."""
    pending = WorkLog.objects.filter(assignment__contract__construction_object=obj,
                                     status=WorkLog.Status.SUBMITTED).count()
    arriving = StockMovement.objects.filter(kind="transfer", received=False, to_warehouse__construction_object=obj).count()
    counts = {
        "work": len(contracts),
        "people": Assignment.objects.filter(contract__construction_object=obj).count(),
        "output": pending,
        "materials": arriving + PurchaseRequest.objects.filter(construction_object=obj,
                                                                status__in=PurchaseRequest.OPEN).count(),
        "remarks": obj.remarks.exclude(status="closed").count(),
        "reports": obj.daily_reports.filter(confirmed=False).count(),
        "docs": obj.documents.count(),
    }
    hot = {k for k, v in (("output", pending), ("materials", arriving), ("remarks", counts["remarks"])) if v}
    return {"counts": counts, "hot": hot}


def _tab_overview(request, obj, contracts):
    spent = alerts.object_expenses(obj)
    return {
        "alerts": alerts.for_object(obj, contracts),
        "spent": spent, "budget_left": obj.budget - spent if obj.budget else None,
        "history": obj.history.select_related("user")[:8],
        "open_remarks": obj.remarks.exclude(status="closed").count(),
        "people_today": obj.daily_reports.order_by("-date").values_list("workers_count", flat=True).first(),
    }


def _tab_work(request, obj, contracts):
    return {}


def _tab_people(request, obj, contracts):
    assignments = list(Assignment.objects.filter(contract__construction_object=obj).select_related(
        "crew__leader", "employee", "contract"))
    return {
        "assignments": assignments,
        "earned": sum((a.earned for a in assignments), 0),
        "paid": sum((a.paid for a in assignments), 0),
        "due": sum((a.due for a in assignments), 0),
        "active_contracts": [c for c in contracts if c.status == WorkContract.Status.ACTIVE],
    }


def _tab_output(request, obj, contracts):
    logs = WorkLog.objects.filter(assignment__contract__construction_object=obj).select_related(
        "assignment__crew", "assignment__employee", "assignment__contract")
    return {"logs": logs[:60], "pending": [l for l in logs if l.status == WorkLog.Status.SUBMITTED]}


def _tab_materials(request, obj, contracts):
    whs = list(obj.warehouses.all())
    return {
        "warehouses": [{"w": w, "rows": w.balances(), "pending": list(w.pending_transfers())} for w in whs],
        "plan_fact": [(c, c.material_plan_fact()) for c in contracts if c.material_plan_fact()],
        "requests": PurchaseRequest.objects.filter(construction_object=obj).select_related("material", "supplier"),
        "movements": StockMovement.objects.filter(
            Q(construction_object=obj) | Q(warehouse__in=whs) | Q(to_warehouse__in=whs)).distinct().select_related(
            "material", "supplier", "construction_object", "warehouse", "to_warehouse")[:20],
    }


def _tab_money(request, obj, contracts):
    tx = obj.transactions.all()
    income = tx.filter(kind="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = tx.filter(kind="expense").aggregate(s=Sum("amount"))["s"] or 0
    spent = alerts.object_expenses(obj)
    return {
        "payments": Payment.objects.filter(contract__construction_object=obj).select_related(
            "contract", "assignment__crew", "assignment__employee")[:40],
        "transactions": tx[:30], "income": income, "expense": expense,
        "estimates": obj.estimates.prefetch_related("items"),
        "spent": spent,
    }


def _tab_remarks(request, obj, contracts):
    remarks = obj.remarks.select_related("responsible", "construction_object")
    return {
        "open": [r for r in remarks if r.status != "closed"],
        "closed": [r for r in remarks if r.status == "closed"][:10],
        "tasks": obj.tasks.select_related("assignee").exclude(status="done"),
    }


def _tab_reports(request, obj, contracts):
    return {"reports": obj.daily_reports.select_related("author")[:30]}


def _tab_docs(request, obj, contracts):
    return {"documents": obj.documents.all(), "estimates": obj.estimates.all(),
            "history": obj.history.select_related("user")[:40]}


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


# что: (форма, заголовок, подсказка, вкладка, доп. аргументы формы, кнопка)
NEW = {
    "work": (ContractForm, "Новый объём работ",
             "Что взяли у генподрядчика на этом объекте: вид работ, объём и цену за единицу.", "work", {}, "Сохранить"),
    "output": (WorkLogForm, "Записать выработку",
               "Сколько сделали за день. После проверки ПТО объём попадёт в учёт, а деньги рабочим начислятся сами.",
               "output", {"user": True}, "Записать"),
    "payment": (PaymentForm, "Платёж по объекту",
                "Деньги от генподрядчика, выплата рабочим или расход на материалы.", "money", {}, "Сохранить"),
    "expense": (TransactionForm, "Прочий доход или расход",
                "Например: аренда техники, доставка, питание.", "money", {}, "Сохранить"),
    "purchase": (PurchaseRequestForm, "Заявка на материал",
                 "Система проверит остатки на складах и последнюю цену.", "materials", {"user": True}, "Отправить"),
    "movement": (StockMovementForm, "Материал: приход или расход",
                 "Приход на склад объекта, выдача в работу, возврат, списание.", "materials", {"user": True},
                 "Сохранить"),
    "remark": (RemarkForm, "Новое замечание", "Прорабу сразу создастся задача на исправление.", "remarks", {},
               "Сохранить"),
    "task": (TaskForm, "Новая задача", "", "remarks", {}, "Сохранить"),
    "report": (DailyReportForm, "Отчёт за день",
               "Короткий отчёт прораба. Выработка и расход материалов подтянутся сами.", "reports", {}, "Сохранить"),
    "doc": (DocumentForm, "Загрузить документ", "Договор, акт, смета, чертёж, фото.", "docs", {}, "Загрузить"),
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


@login_required
def add_choose(request):
    """Экран «+» вне объекта: выбрать объект или создать новый."""
    objects = [o for o in ConstructionObject.objects.all() if o.is_working] or list(ConstructionObject.objects.all())
    return render(request, "object/choose.html", {"objects": objects})
