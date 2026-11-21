from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import audit
from core.models import AuditLog
from core.views import form_page
from staff.models import Employee, Task

from .forms import DailyReportForm, RemarkForm
from .models import DailyReport, Remark

TASK_STATUS = {"in_work": "in_progress", "returned": "in_progress", "review": "review", "closed": "done"}


def _remark_saved(request):
    def done(remark):
        # Замечание сразу создаёт задачу прорабу (ТЗ п. 33).
        if remark.task_id is None:
            remark.author = request.user
            remark.task = Task.objects.create(
                title=f"Устранить замечание {remark.number}", description=remark.description,
                construction_object=remark.construction_object, assignee=remark.responsible,
                due_date=remark.deadline, priority=min(remark.priority, 3), source=Task.Source.INSPECTION)
            remark.save(update_fields=["author", "task"])
        return reverse("remark_detail", args=[remark.pk])
    return done


@login_required
def remark_list(request):
    qs = Remark.objects.select_related("construction_object", "responsible", "executor")
    f = request.GET.get("status", "open")
    if f == "open":
        qs = qs.exclude(status=Remark.Status.CLOSED)
    elif f == "overdue":
        qs = qs.exclude(status=Remark.Status.CLOSED).filter(deadline__lt=date.today())
    elif f == "review":
        qs = qs.filter(status=Remark.Status.REVIEW)
    elif f == "closed":
        qs = qs.filter(status=Remark.Status.CLOSED)
    all_open = Remark.objects.exclude(status=Remark.Status.CLOSED)
    return render(request, "quality/remark_list.html", {
        "remarks": qs, "current": f,
        "counts": {"open": all_open.count(), "overdue": all_open.filter(deadline__lt=date.today()).count(),
                   "review": all_open.filter(status=Remark.Status.REVIEW).count()},
    })


@login_required
def remark_create(request):
    return form_page(request, RemarkForm, "Новое замечание", _remark_saved(request),
                     subtitle="Зафиксируйте замечание на обходе. Прорабу сразу придёт задача.",
                     back=reverse("remark_list"))


@login_required
def remark_detail(request, pk):
    r = get_object_or_404(Remark.objects.select_related("construction_object", "responsible", "executor",
                                                        "author", "reviewer", "task"), pk=pk)
    history = AuditLog.objects.filter(module=Remark._meta.verbose_name_plural, object_id=str(r.pk))
    can_review = request.user.has_perm("quality.review_remark")
    actions = [(to, label) for to, label, needs in Remark.ACTIONS.get(r.status, []) if can_review or not needs]
    return render(request, "quality/remark_detail.html", {
        "r": r, "history": history, "actions": actions, "repeats": r.repeats()[:5],
        "workers": Employee.objects.filter(is_active=True),
    })


@login_required
@require_POST
def remark_act(request, pk):
    r = get_object_or_404(Remark, pk=pk)
    to = request.POST.get("to")
    allowed = {t: needs for t, _, needs in Remark.ACTIONS.get(r.status, [])}
    if to not in allowed:
        messages.error(request, "Это действие сейчас недоступно.")
        return redirect("remark_detail", pk)
    if allowed[to] and not request.user.has_perm("quality.review_remark"):
        raise PermissionDenied
    before = audit.snapshot(r)
    comment = request.POST.get("comment", "")[:300]
    if to == "in_work" and request.POST.get("executor", "").isdigit():
        r.executor = Employee.objects.filter(pk=request.POST["executor"]).first() or r.executor
    if to == "review":
        r.fix_comment = comment
        if request.FILES.get("fix_photo"):
            r.fix_photo = request.FILES["fix_photo"]
    if to == "returned" and not comment:
        messages.error(request, "Напишите, что нужно переделать.")
        return redirect("remark_detail", pk)
    if to == "closed":
        r.reviewer = request.user
        r.accepted_at = timezone.now()
    r.status = to
    r.save()
    if r.task_id:
        Task.objects.filter(pk=r.task_id).update(status=TASK_STATUS[to])
    action = {"closed": AuditLog.Action.ACCEPT, "returned": AuditLog.Action.REJECT}.get(to, AuditLog.Action.UPDATE)
    audit.log(request, r, action, before=before, reason=comment)
    messages.success(request, r.get_status_display())
    return redirect("remark_detail", pk)


@login_required
def task_list(request):
    qs = Task.objects.select_related("assignee", "construction_object")
    f = request.GET.get("status", "active")
    if f == "active":
        qs = qs.exclude(status=Task.Status.DONE)
    elif f == "overdue":
        qs = qs.exclude(status=Task.Status.DONE).filter(due_date__lt=date.today())
    elif f == "review":
        qs = qs.filter(status=Task.Status.REVIEW)
    elif f == "done":
        qs = qs.filter(status=Task.Status.DONE)
    return render(request, "quality/task_list.html", {"tasks": qs, "current": f})


@login_required
@require_POST
def task_next(request, pk):
    t = get_object_or_404(Task, pk=pk)
    step = t.next_step
    if not step:
        return redirect("task_list")
    if step[0] == Task.Status.DONE and not request.user.has_perm("staff.close_task"):
        raise PermissionDenied  # закрытие требует подтверждения руководителя (ТЗ п. 30.4)
    if step[0] == Task.Status.DONE and hasattr(t, "remark") and not t.remark.is_closed:
        messages.error(request, "Сначала примите замечание, к которому относится задача.")
        return redirect("remark_detail", t.remark.pk)
    before = audit.snapshot(t)
    t.status = step[0]
    t.save(update_fields=["status"])
    audit.log(request, t, AuditLog.Action.UPDATE, before=before)
    messages.success(request, f"«{t.title}»: {t.get_status_display()}")
    return redirect(request.POST.get("next") or "task_list")


@login_required
def report_list(request):
    return render(request, "quality/report_list.html", {
        "reports": DailyReport.objects.select_related("construction_object").prefetch_related("crews")[:60]})


@login_required
def report_create(request):
    def saved(rep):
        if rep.author_id is None:
            rep.author = request.user
            rep.save(update_fields=["author"])
        return reverse("report_detail", args=[rep.pk])
    return form_page(request, DailyReportForm, "Ежедневный отчёт", saved,
                     subtitle="Короткий отчёт прораба за день. Выработка и расход материалов подтянутся сами.",
                     back=reverse("report_list"))


@login_required
def report_detail(request, pk):
    rep = get_object_or_404(DailyReport.objects.select_related("construction_object", "author"), pk=pk)
    remarks = Remark.objects.filter(construction_object=rep.construction_object, created_at__date=rep.date)
    return render(request, "quality/report_detail.html", {
        "rep": rep, "logs": rep.worklogs(), "materials_out": rep.material_out(), "remarks": remarks})


@login_required
@require_POST
def report_confirm(request, pk):
    rep = get_object_or_404(DailyReport, pk=pk)
    if not rep.confirmed:
        before = audit.snapshot(rep)
        rep.confirmed, rep.confirmed_at = True, timezone.now()
        rep.save(update_fields=["confirmed", "confirmed_at"])
        audit.log(request, rep, AuditLog.Action.ACCEPT, before=before)
        messages.success(request, "Отчёт подтверждён")
    return redirect("report_detail", pk)
