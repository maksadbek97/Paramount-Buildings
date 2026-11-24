"""Раздел «Финансы»: финплан «план / факт» по шаблону компании.

Сводная → объект (четыре блока) → долги компании → платёжный календарь.
Любую строку можно добавить, изменить, отметить оплаченной или удалить прямо в списке.
"""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core import audit
from core.models import AuditLog
from core.views import form_page
from objects.models import ConstructionObject

from . import services
from .forms import PayForm, PlanLineForm
from .models import PlanLine

S = PlanLine.Section


def base_ctx(tab, **extra):
    objs = services.plan_objects()
    others = [o for o in ConstructionObject.objects.exclude(status="archive") if o not in objs]
    return {"tab": tab, "plan_objs": objs, "other_objs": others, "sections": S.choices,
            "object_sections": [(k, S(k).label) for k in services.OBJECT_SECTIONS],
            "all_objs": objs + others, "today": date.today(), **extra}


def _next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default


def _back_url(line):
    if line.section == S.DEBT:
        return reverse("finance_debts")
    return reverse("finance_object", args=[line.construction_object_id]) + f"#s-{line.section}"


@login_required
def home(request):
    s = services.summary()
    cal = services.calendar(s["lines"])
    return render(request, "finance/home.html", base_ctx(
        "home", s=s, cal=cal, attention=services.attention(s["lines"])[:8]))


@login_required
def object_plan(request, pk):
    obj = get_object_or_404(ConstructionObject, pk=pk)
    lines = list(obj.plan_lines.all())
    return render(request, "finance/object.html", base_ctx(
        f"o{obj.pk}", p=services.object_plan(obj, lines), cur_obj=obj, obj=obj))


@login_required
def debts(request):
    lines = list(PlanLine.objects.filter(section=S.DEBT))
    total = services.sums(lines)
    return render(request, "finance/debts.html", base_ctx(
        "debts", lines=lines, total=total, late=[ln for ln in lines if ln.overdue],
        sec={"key": S.DEBT, "label": S.DEBT.label, "lines": lines, "is_debt": True, **total}))


@login_required
def calendar(request):
    lines = list(PlanLine.objects.select_related("construction_object"))
    return render(request, "finance/calendar.html", base_ctx("calendar", cal=services.calendar(lines)))


# ---------------- Изменения ----------------

@login_required
def line_new(request):
    initial_section = request.GET.get("section") or request.POST.get("section")
    obj_id = request.GET.get("construction_object") or request.POST.get("construction_object")

    def done(line):
        return _next(request, _back_url(line))
    back = reverse("finance_debts") if initial_section == S.DEBT else (
        reverse("finance_object", args=[obj_id]) if obj_id and str(obj_id).isdigit() else reverse("finance_home"))
    return form_page(request, PlanLineForm, "Новая строка финплана", done, back=back,
                     subtitle="План, факт и остаток по шаблону «Фин план»", submit="Добавить")


@login_required
def line_edit(request, pk):
    line = get_object_or_404(PlanLine, pk=pk)
    return form_page(request, PlanLineForm, "Изменить строку финплана", lambda ln: _next(request, _back_url(ln)),
                     instance=line, back=_back_url(line), subtitle=str(line))


@login_required
@require_POST
def line_pay(request, pk):
    """Внести оплату (поступление): факт увеличивается, остаток пересчитывается. Без суммы — весь остаток."""
    line = get_object_or_404(PlanLine, pk=pk)
    form = PayForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Проверьте сумму и дату.")
        return redirect(_next(request, _back_url(line)))
    before = audit.snapshot(line)
    amount = form.cleaned_data.get("amount")
    if amount is None:
        amount = max(line.left, Decimal(0))
    if amount <= 0:
        messages.error(request, "Сумма должна быть больше нуля.")
        return redirect(_next(request, _back_url(line)))
    line.fact_amount = (line.fact_amount or 0) + amount
    line.fact_date = form.cleaned_data.get("date") or date.today()
    line.save()
    audit.log(request, line, AuditLog.Action.UPDATE, before=before,
              reason=("Получено " if line.is_income else "Оплачено ") + f"{amount.normalize():f} ₸")
    messages.success(request, ("Поступление записано" if line.is_income else "Оплата записана") +
                     (" — строка закрыта" if line.is_done else f", остаток {line.left.normalize():f} ₸"))
    return redirect(_next(request, _back_url(line)))


@login_required
@require_POST
def line_delete(request, pk):
    line = get_object_or_404(PlanLine, pk=pk)
    back = _back_url(line).split("#")[0]
    audit.log(request, line, AuditLog.Action.DELETE, before=audit.snapshot(line), reason="Удалена строка финплана")
    line.delete()
    messages.success(request, "Строка удалена")
    return redirect(_next(request, back))
