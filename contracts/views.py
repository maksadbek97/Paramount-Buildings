from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core import audit
from core.models import AuditLog
from core.views import form_page

from . import forms
from .models import Crew, WorkContract, WorkLog, pending_logs, summary


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
        "c": c, "cur_obj": c.construction_object, "assignments": assignments, "materials": c.material_plan_fact(),
        "pending": [log for log in pending_logs() if log.assignment.contract_id == c.pk],
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
                     extra={"cur_obj": c.construction_object},
                     back=reverse("contract_detail", args=[pk]))


@login_required
def assignment_create(request, pk):
    c = get_object_or_404(WorkContract, pk=pk)
    return form_page(request, forms.AssignmentForm, "Назначить исполнителя",
                     reverse("object_tab", args=[c.construction_object_id, "people"]), form_kwargs={"contract": c},
                     extra={"cur_obj": c.construction_object},
                     subtitle=f"{c.work_type} · {c.construction_object}. Цена для нас: {c.price:,.0f} ₸ за {c.unit}"
                     .replace(",", " "),
                     back=reverse("contract_detail", args=[pk]))


@login_required
def worklog_create(request):
    contract = _contract_from_get(request)
    return form_page(request, forms.WorkLogForm, "Записать выработку",
                     lambda log: reverse("contract_detail", args=[log.assignment.contract_id]),
                     form_kwargs={"contract": contract, "user": request.user},
                     subtitle="Сколько сделали за день. После проверки ПТО объём попадёт в учёт, "
                              "а деньги рабочим начислятся сами.",
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




@login_required
def pto(request):
    """ПТО: объёмы на проверке и план-факт по всем видам работ."""
    contracts = list(WorkContract.objects.select_related("construction_object").exclude(
        status=WorkContract.Status.DONE))
    return render(request, "contracts/pto.html", {"pending": pending_logs(), "contracts": contracts})


@login_required
@permission_required("contracts.review_worklog", raise_exception=True)
def worklog_review(request, pk):
    log = get_object_or_404(WorkLog.objects.select_related("assignment__contract__construction_object"), pk=pk)
    if log.status != WorkLog.Status.SUBMITTED:
        messages.info(request, "Этот объём уже проверен.")
        return redirect("contract_detail", log.contract.pk)
    if request.method == "POST":
        form = forms.ReviewForm(request.POST, log=log)
        if request.POST.get("all"):
            form = forms.ReviewForm({"accepted_volume": log.volume, "review_note": ""}, log=log)
        if form.is_valid():
            before = audit.snapshot(log)
            try:
                log.review(request.user, form.cleaned_data["accepted_volume"], form.cleaned_data["review_note"])
            except ValidationError as e:
                form.add_error(None, e)
            else:
                action = AuditLog.Action.ACCEPT if log.status == WorkLog.Status.ACCEPTED else AuditLog.Action.REJECT
                audit.log(request, log, action, before=before, reason=log.review_note)
                messages.success(request, f"{log.get_status_display()}: {log.accepted_volume.normalize():f} "
                                          f"{log.contract.unit}")
                return redirect(request.POST.get("next") or reverse("pto"))
    else:
        form = forms.ReviewForm(log=log)
    return render(request, "contracts/review.html", {"log": log, "form": form, "c": log.contract,
                                                     "cur_obj": log.contract.construction_object})


@login_required
def norm_create(request, pk):
    c = get_object_or_404(WorkContract, pk=pk)
    return form_page(request, forms.NormForm, "Норматив материала", reverse("contract_detail", args=[pk]),
                     form_kwargs={"contract": c},
                     subtitle=f"{c.work_type}: сколько материала уходит на 1 {c.unit}. "
                              "Система посчитает потребность и перерасход.",
                     back=reverse("contract_detail", args=[pk]))
