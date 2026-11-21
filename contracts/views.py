from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.views import form_page

from . import forms
from .models import Crew, WorkContract, WorkLog, summary


def _contract_from_get(request):
    pk = request.GET.get("contract")
    return get_object_or_404(WorkContract, pk=pk) if pk and pk.isdigit() else None


@login_required
def contract_list(request):
    contracts = list(WorkContract.objects.select_related("construction_object").prefetch_related("assignments"))
    status = request.GET.get("status")
    shown = [c for c in contracts if not status or c.status == status]
    return render(request, "contracts/contract_list.html", {
        "contracts": shown, "s": summary(contracts), "statuses": WorkContract.Status.choices, "current": status,
    })


@login_required
def contract_detail(request, pk):
    c = get_object_or_404(WorkContract.objects.select_related("construction_object__client"), pk=pk)
    assignments = list(c.assignments.select_related("crew", "employee"))
    return render(request, "contracts/contract_detail.html", {
        "c": c, "assignments": assignments,
        "logs": WorkLog.objects.filter(assignment__contract=c).select_related(
            "assignment__crew", "assignment__employee", "assignment__contract")[:14],
        "payments": c.payments.select_related("assignment__crew", "assignment__employee")[:14],
    })


@login_required
def contract_create(request):
    return form_page(request, forms.ContractForm, "Новый объём работ",
                     lambda c: reverse("contract_detail", args=[c.pk]),
                     subtitle="Что взяли у генподрядчика: вид работ, объём и цену за единицу.",
                     back=reverse("contract_list"))


@login_required
def contract_edit(request, pk):
    c = get_object_or_404(WorkContract, pk=pk)
    return form_page(request, forms.ContractForm, "Изменить договор",
                     lambda c: reverse("contract_detail", args=[c.pk]), instance=c,
                     back=reverse("contract_detail", args=[pk]))


@login_required
def assignment_create(request, pk):
    c = get_object_or_404(WorkContract, pk=pk)
    return form_page(request, forms.AssignmentForm, "Назначить исполнителя",
                     reverse("contract_detail", args=[pk]), form_kwargs={"contract": c},
                     subtitle=f"{c.work_type} · {c.construction_object}. Цена для нас: {c.price:,.0f} за {c.unit}"
                     .replace(",", " "),
                     back=reverse("contract_detail", args=[pk]))


@login_required
def worklog_create(request):
    contract = _contract_from_get(request)
    return form_page(request, forms.WorkLogForm, "Записать выработку",
                     lambda log: reverse("contract_detail", args=[log.assignment.contract_id]),
                     form_kwargs={"contract": contract},
                     subtitle="Сколько сделали за день. Деньги рабочим начислятся сами.",
                     submit="Записать", back=reverse("contract_detail", args=[contract.pk]) if contract else None)


@login_required
def payment_create(request):
    contract = _contract_from_get(request)
    return form_page(request, forms.PaymentForm, "Добавить платёж",
                     lambda p: reverse("contract_detail", args=[p.contract_id]),
                     form_kwargs={"contract": contract},
                     subtitle="Деньги от генподрядчика, выплата рабочим или расход на материалы.",
                     back=reverse("contract_detail", args=[contract.pk]) if contract else None)


@login_required
def crew_create(request):
    return form_page(request, forms.CrewForm, "Новая бригада", reverse("staff_list"), back=reverse("staff_list"))


@login_required
def crew_edit(request, pk):
    return form_page(request, forms.CrewForm, "Изменить бригаду", reverse("staff_list"),
                     instance=get_object_or_404(Crew, pk=pk), back=reverse("staff_list"))


