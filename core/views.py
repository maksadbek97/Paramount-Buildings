from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

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


def _object_cards(contracts):
    """Карточки объектов: деньги, прогресс, просрочки, открытые задачи и заявки."""
    from warehouse.models import PurchaseRequest
    by_obj = {}
    for c in contracts:
        by_obj.setdefault(c.construction_object_id, []).append(c)
    open_remarks = dict(Remark.objects.exclude(status=Remark.Status.CLOSED).values_list(
        "construction_object").annotate(n=Count("id")))
    open_tasks = dict(Task.objects.exclude(status="done").values_list("construction_object").annotate(n=Count("id")))
    late_tasks = dict(Task.objects.exclude(status="done").filter(due_date__lt=date.today()).values_list(
        "construction_object").annotate(n=Count("id")))
    open_req = dict(PurchaseRequest.objects.filter(status__in=PurchaseRequest.OPEN).values_list(
        "construction_object").annotate(n=Count("id")))
    pending = {}
    for log in WorkLog.objects.filter(status=WorkLog.Status.SUBMITTED).select_related("assignment__contract"):
        oid = log.assignment.contract.construction_object_id
        pending[oid] = pending.get(oid, 0) + 1
    cards = []
    for o in ConstructionObject.objects.select_related("client", "foreman", "manager"):
        cs = by_obj.get(o.pk, [])
        late = late_tasks.get(o.pk, 0) + sum(c.status == "active" and c.is_overdue for c in cs)
        cards.append({"o": o, "s": summary(cs), "remarks": open_remarks.get(o.pk, 0),
                      "pending": pending.get(o.pk, 0), "tasks": open_tasks.get(o.pk, 0),
                      "requests": open_req.get(o.pk, 0), "late": late,
                      "overdue": bool(o.end_date and o.end_date < date.today() and not o.is_closed)})
    return cards, by_obj


def _can_money(user):
    return user.is_superuser or user.has_perm("finance.view_transaction")


@login_required
def dashboard(request):
    """Главная: обзор компании по ТЗ модуля «Главная / Dashboard»."""
    from objects.models import ObjectDocument
    from warehouse.models import PurchaseRequest

    from . import dashboard as dash
    a, b, period, period_label = dash.period_range(request.GET.get("period", dash.DEFAULT_PERIOD),
                                                   request.GET.get("from"), request.GET.get("to"))
    bad_period = request.GET.get("period") == "custom" and period != "custom"
    all_objects = list(ConstructionObject.objects.all())
    obj_id = request.GET.get("object", "")
    selected = next((o for o in all_objects if obj_id.isdigit() and o.pk == int(obj_id)), None)
    objects = [selected] if selected else all_objects

    contracts = [c for c in WorkContract.objects.select_related("construction_object").prefetch_related(
        "assignments__crew", "assignments__employee") if c.construction_object in objects]
    cards, by_obj = _object_cards(contracts)
    cards = [c for c in cards if c["o"] in objects]
    order = lambda c: (not (c["late"] or c["overdue"]), not c["o"].is_working,  # noqa: E731
                       c["o"].end_date or date.max)
    active_cards = sorted((c for c in cards if not c["o"].is_closed), key=order)

    ops = dash.operations(objects if selected else None, a, b)
    income = sum((o["amount"] for o in ops if o["income"]), 0)
    expense = sum((o["amount"] for o in ops if not o["income"]), 0)
    # Динамика к предыдущему периоду такой же длины (ТЗ п. 6)
    delta = {}
    if a and b:
        days = (b - a).days + 1
        pa, pb = a - timedelta(days=days), a - timedelta(days=1)
        prev = dash.operations(objects if selected else None, pa, pb)
        p_inc = sum((o["amount"] for o in prev if o["income"]), 0)
        p_exp = sum((o["amount"] for o in prev if not o["income"]), 0)

        def pct(cur, old):
            return None if not old else int(round((cur - old) * 100 / old))
        delta = {"income": pct(income, p_inc), "expense": pct(expense, p_exp),
                 "result": pct(income - expense, p_inc - p_exp) if (p_inc - p_exp) > 0 else None,
                 "label": f"{pa:%d.%m}–{pb:%d.%m}"}
    receivable, payable, _, _ = dash.debts(contracts)
    requests = PurchaseRequest.objects.filter(construction_object__in=objects)
    tasks = dash.tasks_block(request.user, objects, a, b)

    def q(**kw):  # ссылки фильтров: без значений по умолчанию, чтобы работали и в демо
        params = {"period": period if period != dash.DEFAULT_PERIOD else "", "object": obj_id}
        params.update(kw)
        if params.get("period") == "custom":
            params.update({"from": a.isoformat(), "to": b.isoformat()})
        if not any(params.values()):
            return reverse("dashboard")
        return "?" + "&".join(f"{k}={v}" for k, v in params.items() if v)

    return render(request, "dashboard.html", {
        "period": period, "period_label": period_label, "a": a, "b": b, "bad_period": bad_period,
        "periods": [(k, label, q(period=k if k != dash.DEFAULT_PERIOD else "")) for k, label in dash.PERIODS],
        "objects_all": all_objects, "selected": selected,
        "object_links": [(o, q(object=o.pk)) for o in all_objects], "all_objects_link": q(object=""),
        "filtered": bool(selected or period != dash.DEFAULT_PERIOD),
        "can_money": _can_money(request.user),
        "kpi": {
            "active": sum(o.is_working for o in objects),
            "contracts": sum((c.total for c in contracts if c.status == WorkContract.Status.ACTIVE), 0),
            "contracts_count": sum(c.status == WorkContract.Status.ACTIVE for c in contracts),
            "income": income, "expense": expense, "result": income - expense,
            "receivable": receivable, "payable": payable,
            "tasks_overdue": len(tasks["overdue"]),
        },
        "has_ops": bool(ops),
        "cards": active_cards[:6], "cards_total": len(active_cards),
        "chart": dash.chart(ops, a, b),
        "works": dash.work_progress(objects, by_obj),
        "purchases": dash.purchase_counts(requests),
        "materials": dash.materials_block(objects),
        "documents": ObjectDocument.objects.filter(construction_object__in=objects).select_related(
            "construction_object").order_by("-uploaded_at")[:5],
        "tasks": tasks,
        "activity": dash.activity(objects),
        "alerts": alerts.collect(contracts),
        "delta": delta,
        "rows": sorted(cards, key=order),
        "updated": timezone.localtime(),
    })


@login_required
def menu(request):
    return render(request, "menu.html")


@login_required
def object_list(request):
    """Мои объекты: плитки с фото; завершённые — на отдельной вкладке."""
    contracts = list(WorkContract.objects.select_related("construction_object").prefetch_related(
        "assignments__crew", "assignments__employee"))
    cards, _ = _object_cards(contracts)
    status = request.GET.get("status", "")
    view = "done" if status == "done" else "active"
    active = sorted((c for c in cards if not c["o"].is_closed), key=lambda c: (not c["o"].is_working,
                                                                               -c["s"]["total"]))
    done = [c for c in cards if c["o"].is_closed]
    shown = done if view == "done" else active
    if status and status not in ("done", "active"):
        shown = [c for c in cards if c["o"].status == status]
    return render(request, "object_list.html", {
        "view": view, "cards": shown, "active_count": len(active), "done_count": len(done),
    })


@login_required
def object_create(request):
    return form_page(request, forms.ObjectForm, "Новый объект",
                     lambda o: reverse("object_detail", args=[o.pk]), back=reverse("object_list"),
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


FIN_VIEWS = [("all", "Все операции"), ("income", "Поступления"), ("expense", "Расходы"),
             ("debtors", "Дебиторская задолженность"), ("creditors", "Кредиторская задолженность")]


@login_required
def finance_list(request):
    """Финансы компании: все поступления и расходы (по объёмам и прочие), задолженности."""
    from . import dashboard as dash
    kind = request.GET.get("kind", "all")
    a, b, period, period_label = dash.period_range(request.GET.get("period", "all"),
                                                   request.GET.get("from"), request.GET.get("to"))
    ops = dash.operations(None, a, b)
    income = sum((o["amount"] for o in ops if o["income"]), 0)
    expense = sum((o["amount"] for o in ops if not o["income"]), 0)
    contracts = list(WorkContract.objects.select_related("construction_object").prefetch_related(
        "assignments__crew", "assignments__employee"))
    receivable, payable, rec_rows, pay_rows = dash.debts(contracts)
    if kind == "income":
        ops = [o for o in ops if o["income"]]
    elif kind == "expense":
        ops = [o for o in ops if not o["income"]]
    return render(request, "finance_list.html", {
        "kind": kind, "views": FIN_VIEWS, "period_label": period_label, "period": period,
        "ops": ops[:100], "income": income, "expense": expense, "balance": income - expense,
        "receivable": receivable, "payable": payable, "rec_rows": rec_rows, "pay_rows": pay_rows,
        "estimates": Estimate.objects.select_related("construction_object").prefetch_related("items"),
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


@login_required
def search(request):
    """Глобальный поиск: объекты, сотрудники, контрагенты, документы, договоры, материалы."""
    from django.db.models import Q

    from objects.models import Client, ObjectDocument
    from warehouse.models import Material, Supplier
    q = request.GET.get("q", "").strip()
    groups = []
    if len(q) >= 2:
        def add(title, items):
            if items:
                groups.append((title, items))
        add("Объекты", [(o.name, f"{o.code} · {o.city} · {o.address}".strip(" ·"), reverse("object_detail", args=[o.pk]))
                        for o in ConstructionObject.objects.filter(Q(name__icontains=q) | Q(code__icontains=q) |
                                                                   Q(address__icontains=q) | Q(city__icontains=q))[:10]])
        add("Сотрудники", [(e.full_name, " · ".join(filter(None, [str(e.position or ""), e.phone])),
                            reverse("employee_edit", args=[e.pk]))
                           for e in Employee.objects.select_related("position").filter(
                               Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(position__name__icontains=q))[:10]])
        add("Контрагенты", [(c.name, f"БИН {c.bin}" if c.bin else "Заказчик", reverse("object_list"))
                            for c in Client.objects.filter(Q(name__icontains=q) | Q(bin__icontains=q))[:10]] +
            [(s.name, "Поставщик" + (f" · {s.phone}" if s.phone else ""), reverse("purchase_list"))
             for s in Supplier.objects.filter(Q(name__icontains=q) | Q(phone__icontains=q))[:10]])
        add("Договоры и объёмы", [(c.work_type, str(c.construction_object), reverse("contract_detail", args=[c.pk]))
                                  for c in WorkContract.objects.select_related("construction_object").filter(
                                      Q(work_type__icontains=q) | Q(construction_object__name__icontains=q) |
                                      Q(construction_object__contract_number__icontains=q))[:10]])
        add("Документы", [(d.title, str(d.construction_object), reverse("object_tab", args=[d.construction_object_id, "docs"]))
                          for d in ObjectDocument.objects.select_related("construction_object").filter(
                              Q(title__icontains=q) | Q(construction_object__name__icontains=q))[:10]])
        add("Материалы", [(m.name, " · ".join(filter(None, [m.code, m.unit])), reverse("warehouse_list"))
                          for m in Material.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))[:10]])
    return render(request, "search.html", {"q": q, "groups": groups})


def notifications_for(user):
    """Уведомления пользователя: назначенные и просроченные задачи, согласования, приёмки, контрольные события."""
    from warehouse.models import PurchaseRequest, StockMovement
    items = []
    employee = getattr(user, "employee", None)
    today = date.today()
    tasks = Task.objects.exclude(status="done").select_related("construction_object")
    if employee:
        for t in tasks.filter(assignee=employee):
            late = t.due_date and t.due_date < today
            items.append(("bad" if late else "info", "Задача просрочена" if late else "Вам назначена задача",
                          t.title + (f" · до {t.due_date:%d.%m}" if t.due_date else ""), reverse("task_list")))
    if user.has_perm("warehouse.approve_purchase"):
        for p in PurchaseRequest.objects.filter(status="new").select_related("material", "construction_object"):
            items.append(("warn", "Заявка ждёт согласования", f"{p.number}: {p.material} · {p.construction_object.name}",
                          reverse("purchase_detail", args=[p.pk])))
    for p in PurchaseRequest.objects.filter(status__in=["approved", "ordered"], needed_by__lt=today).select_related(
            "material", "construction_object"):
        items.append(("bad", "Поставка просрочена", f"{p.number}: {p.material} · {p.construction_object.name}",
                      reverse("purchase_detail", args=[p.pk])))
    for mv in StockMovement.objects.filter(kind="transfer", received=False).select_related("material", "to_warehouse"):
        items.append(("info", "Материал ждёт приёмки", f"{mv.material} {mv.quantity.normalize():f} → {mv.to_warehouse}",
                      reverse("warehouse_detail", args=[mv.to_warehouse_id])))
    if user.is_superuser:
        for level, text, url in alerts.collect():
            items.append((level, "Контроль", text, url))
    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(items, key=lambda i: order[i[0]])


@login_required
def notifications(request):
    return render(request, "notifications.html", {"items": notifications_for(request.user)})
