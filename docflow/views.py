import re
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from company.models import Company, Department
from core.views import form_page
from objects.models import ConstructionObject
from staff.models import Employee

from . import blank_docx, forms, pdf, services
from .models import (Approval, ArchiveRecord, CaseFile, DocEvent, DocTask, Document, DocumentFile, Journal, Seal,
                     SealUsage, Template)

TABS = [("home", "Обзор", "docflow_home"), ("all", "Все документы", "docflow_all"),
        ("orders", "Приказы", "docflow_orders"), ("letters", "Письма", "docflow_letters"),
        ("contracts", "Договоры", "docflow_contracts"), ("tasks", "Поручения", "docflow_tasks"),
        ("cases", "Номенклатура дел", "docflow_cases"), ("journals", "Журналы", "docflow_journals"),
        ("templates", "Шаблоны", "docflow_templates"), ("seals", "Подпись и печать", "docflow_seals"),
        ("archive", "Архив", "docflow_archive")]

CREATE = [("letter", "Письмо на фирменном бланке", "Генератор: текст → PDF с номером", "mail"),
          ("incoming", "Зарегистрировать входящий", "Письмо от заказчика, поставщика, госоргана", "inbox"),
          ("order", "Приказ", "Организационный, по объекту, комиссия", "stamp"),
          ("outgoing", "Исходящее письмо", "Без бланка: загрузить готовый файл", "send"),
          ("contract", "Договор", "С заказчиком, поставщиком, субподрядчиком", "contract"),
          ("internal", "Внутренний документ", "Служебная записка, протокол", "file")]

GROUPS = [("work", "В работе"), ("approval", "На согласовании"), ("signing", "На подписи"), ("draft", "Черновики"),
          ("done", "Исполнены"), ("archived", "В архиве"), ("cancelled", "Отменены")]
GROUP_OF = {"draft": "draft", "rework": "approval", "approval": "approval", "approved": "signing",
            "signing": "signing", "executed": "done", "closed": "done", "archived": "archived",
            "cancelled": "cancelled", "rejected": "cancelled"}


def group_of(status):
    return GROUP_OF.get(status, "work")


def _page(request, tab, template, ctx=None):
    ctx = ctx or {}
    return render(request, template, {"tab": tab, "tabs": TABS, "create": CREATE,
                                      "today": date.today(), **ctx})


def _docs():
    return Document.objects.select_related("construction_object", "responsible", "author", "signer", "case",
                                           "journal", "department")


def _rows(qs):
    """Строки реестра с данными для фильтров на странице."""
    rows = []
    for d in qs:
        due = "overdue" if d.overdue else ("soon" if d.due_soon else ("has" if d.days_left is not None else ""))
        rows.append({"d": d, "group": group_of(d.status), "due": due, "due_text": services.due_text(d.days_left),
                     "missing": d.missing})
    return rows


def _filters(rows):
    def uniq(pairs):
        return sorted({p for p in pairs if p[0]}, key=lambda p: p[1])
    return {
        "f_resp": uniq((str(r["d"].responsible_id or ""), str(r["d"].responsible or "")) for r in rows),
        "f_obj": uniq((str(r["d"].construction_object_id or ""), str(r["d"].construction_object or "")) for r in rows),
        "f_cp": uniq((r["d"].counterparty, r["d"].counterparty) for r in rows),
        "f_dep": uniq((str(r["d"].department_id or ""), str(r["d"].department or "")) for r in rows),
        "f_case": uniq((str(r["d"].case_id or ""), str(r["d"].case.index if r["d"].case else "")) for r in rows),
        "f_status": [(k, v) for k, v in Document.Status.choices if any(r["d"].status == k for r in rows)],
        "overdue_n": sum(r["due"] == "overdue" for r in rows),
    }


# ---------------- Обзор ----------------

@login_required
def home(request):
    today = date.today()
    docs = list(_docs())
    month = [d for d in docs if d.doc_date.year == today.year and d.doc_date.month == today.month]
    by_kind = {}
    for d in docs:
        by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
    kpis = [
        ("Всего документов", len(docs), f"за этот месяц {len(month)}", reverse("docflow_all"), ""),
        ("Входящие", by_kind.get("incoming", 0),
         f"новых за 7 дней {sum(1 for d in docs if d.kind == 'incoming' and d.doc_date >= today - timedelta(7))}",
         reverse("docflow_letters"), ""),
        ("Исходящие", by_kind.get("outgoing", 0),
         f"отправлено {sum(1 for d in docs if d.kind == 'outgoing' and d.sent_at)}",
         reverse("docflow_letters_out"), ""),
        ("Приказы", by_kind.get("order", 0),
         f"в исполнении {sum(1 for d in docs if d.kind == 'order' and d.status == 'execution')}",
         reverse("docflow_orders"), ""),
        ("Договоры", by_kind.get("contract", 0),
         f"действуют {sum(1 for d in docs if d.kind == 'contract' and d.status in ('execution', 'signed'))}",
         reverse("docflow_contracts"), ""),
        ("На согласовании", sum(1 for d in docs if d.status in ("approval", "rework")), "ждут решения",
         reverse("docflow_all") + "#g=approval", "warn"),
        ("На подписи", sum(1 for d in docs if d.status in ("signing", "approved")), "у директора",
         reverse("docflow_all") + "#g=signing", "violet"),
        ("Черновики", sum(1 for d in docs if d.status == "draft"), "ещё не отправлены",
         reverse("docflow_all") + "#g=draft", ""),
    ]
    overdue = [d for d in docs if d.overdue]
    soon = [d for d in docs if d.due_soon]
    expiring = [d for d in docs if d.contract_left is not None and d.contract_left <= 30]
    tasks = list(DocTask.objects.select_related("assignee", "document", "construction_object").exclude(
        status__in=["done", "cancelled"]))
    late_tasks = [t for t in tasks if t.overdue]
    attention = ([("bad", "Просрочен ответ", d.title, d, services.due_text(d.days_left)) for d in overdue]
                 + [("bad", "Поручение просрочено", t.title, t.document, services.due_text(t.days_left))
                    for t in late_tasks]
                 + [("warn", "Срок скоро", d.title, d, services.due_text(d.days_left)) for d in soon]
                 + [("warn", "Договор истекает", d.title, d,
                     f"до {d.valid_until:%d.%m.%Y}" if d.contract_left >= 0 else "истёк") for d in expiring])
    waiting = []
    for d in docs:
        if d.status in ("approval", "signing", "approved", "rework"):
            step = next((a for a in d.approvals.all() if a.decision == "pending"), None)
            waiting.append({"d": d, "step": step})
    events = DocEvent.objects.select_related("document")[:9]
    return _page(request, "home", "docflow/home.html", {
        "kpis": kpis, "attention": attention, "waiting": waiting,
        "incoming": [d for d in docs if d.kind == "incoming"][:5],
        "outgoing": [d for d in docs if d.kind == "outgoing"][:5],
        "tasks": tasks[:6], "tasks_total": len(tasks), "late_tasks": len(late_tasks), "events": events,
    })


# ---------------- Списки ----------------

KIND_CHIPS = [("order", "Приказы"), ("incoming", "Входящие"), ("outgoing", "Исходящие"), ("internal", "Внутренние"),
              ("contract", "Договоры"), ("act", "Акты"), ("other", "Прочие")]


@login_required
def registry(request):
    rows = _rows(_docs())
    chips = [("", "Все", len(rows))] + [(k, v, sum(r["d"].kind == k for r in rows)) for k, v in KIND_CHIPS]
    return _page(request, "all", "docflow/registry.html", {
        "rows": rows, "chips": [c for c in chips if c[2] or not c[0]], "groups": GROUPS, **_filters(rows),
        "export_name": "reestr-dokumentov"})


@login_required
def orders(request):
    qs = _docs().filter(kind="order").prefetch_related("tasks")
    rows = _rows(qs)
    for r in rows:
        ts = list(r["d"].tasks.all())
        r["tasks"] = len(ts)
        r["tasks_done"] = sum(t.status == "done" for t in ts)
        r["pct"] = int(r["tasks_done"] * 100 / len(ts)) if ts else None
    return _list(request, "orders", rows, "Приказы",
                 "Административные и организационные приказы. Кадровые приказы ведутся в отдельном модуле.",
                 "order", "Создать приказ", sub=None)


LETTER_SUBS = [("incoming", "Входящие", "docflow_letters"), ("outgoing", "Исходящие", "docflow_letters_out"),
               ("internal", "Внутренние", "docflow_letters_internal")]


@login_required
def letters(request, kind="incoming"):
    rows = _rows(_docs().filter(kind=kind).prefetch_related("recipients"))
    counts = dict(Document.objects.values_list("kind").annotate(n=Count("id")))
    sub = [(k, label, url, counts.get(k, 0)) for k, label, url in LETTER_SUBS]
    titles = {"incoming": ("Входящие письма", "Поступление → регистрация → резолюция → исполнитель → ответ → архив.",
                           "incoming", "Зарегистрировать входящий"),
              "outgoing": ("Исходящие письма", "Черновик → согласование → подпись → регистрация → отправка → "
                           "подтверждение.", "letter", "Письмо на бланке"),
              "internal": ("Внутренние документы", "Служебные записки и протоколы. У каждого адресата свой статус "
                           "ознакомления.", "internal", "Внутренний документ")}
    t, s, new, label = titles[kind]
    return _list(request, "letters", rows, t, s, new, label, sub=sub, sub_on=kind)


@login_required
def contracts(request):
    rows = _rows(_docs().filter(kind="contract").prefetch_related("contract_docs"))
    for r in rows:
        r["left"] = r["d"].contract_left
    active = [r["d"] for r in rows if r["d"].status in ("execution", "signed")]
    total = sum((d.amount or 0) for d in active)
    paid = sum((d.paid or 0) for d in active)
    stats = [("Действующих", len(active), ""), ("Сумма действующих", total, "money"),
             ("Оплачено по ним", paid, "money"), ("Остаток к оплате", total - paid, "money")]
    return _list(request, "contracts", rows, "Договоры",
                 "Контроль сроков, сумм, оплат и гарантий. Допсоглашения, акты и переписка — в карточке договора.",
                 "contract", "Создать договор", stats=stats)


def _list(request, tab, rows, title, subtitle, new_kind, new_label, sub=None, sub_on="", stats=None):
    return _page(request, tab, "docflow/list.html", {
        "rows": rows, "title": title, "subtitle": subtitle, "new_kind": new_kind, "new_label": new_label,
        "sub": sub, "sub_on": sub_on, "groups": GROUPS, "stats": stats, **_filters(rows),
        "chips": [("", "Все", len(rows))] + [(k, v, sum(r["group"] == k for r in rows)) for k, v in GROUPS
                                              if any(r["group"] == k for r in rows)],
        "export_name": tab})


@login_required
def tasks(request):
    qs = list(DocTask.objects.select_related("assignee", "controller", "author", "document", "construction_object"))
    cols = [("new", "Новые"), ("in_work", "В работе"), ("review", "На проверке"), ("done", "Выполнены")]
    norm = {"accepted": "in_work", "rework": "in_work", "cancelled": "done"}
    board = [{"key": k, "label": v, "items": [t for t in qs if norm.get(t.status, t.status) == k]} for k, v in cols]
    for c in board:
        if c["key"] == "done":
            c["items"] = c["items"][:6]
    open_ = [t for t in qs if t.open]
    stats = [("Активных", len(open_), ""), ("Просрочено", sum(t.overdue for t in open_), "bad"),
             ("Срок сегодня–3 дня", sum(1 for t in open_ if 0 <= t.days_left <= 3), "warn"),
             ("Выполнено за 30 дней", sum(1 for t in qs if t.done_at and t.done_at >= date.today() - timedelta(30)),
              "ok")]
    people = sorted({(t.assignee_id, t.assignee.full_name) for t in qs}, key=lambda p: p[1])
    return _page(request, "tasks", "docflow/tasks.html", {"board": board, "stats": stats, "people": people,
                                                          "all_tasks": qs})


@login_required
def cases(request):
    cs = list(CaseFile.objects.select_related("department", "responsible").annotate(n=Count("documents")))
    groups = {}
    for c in cs:
        groups.setdefault(c.index.split("-")[0], {"dep": c.department, "items": []})["items"].append(c)
    return _page(request, "cases", "docflow/cases.html", {
        "groups": [{"code": k, **v} for k, v in sorted(groups.items())], "total": len(cs),
        "year": date.today().year, "docs_in": sum(c.n for c in cs),
        "no_case": Document.objects.filter(case__isnull=True).exclude(status__in=["draft", "cancelled"]).count()})


@login_required
def journals(request):
    js = list(Journal.objects.annotate(n=Count("documents")))
    year = date.today().year
    for j in js:
        j.last = j.documents.exclude(number="").order_by("-reg_date", "-id").first()
        j.this_year = j.documents.filter(reg_date__year=year).count()
    return _page(request, "journals", "docflow/journals.html", {"journals": js})


@login_required
def journal_detail(request, pk):
    j = get_object_or_404(Journal, pk=pk)
    entries = j.documents.exclude(number="").select_related("responsible", "author", "signer",
                                                            "construction_object").order_by("-reg_date", "-id")
    return _page(request, "journals", "docflow/journal_detail.html", {"j": j, "entries": entries,
                                                                      "journals": Journal.objects.all()})


@login_required
def templates(request):
    ts = list(Template.objects.select_related("author").annotate(n=Count("documents")))
    return _page(request, "templates", "docflow/templates.html", {
        "letterheads": [t for t in ts if t.is_letterhead], "others": [t for t in ts if not t.is_letterhead],
        "company": Company.get()})


@login_required
def seals(request):
    return _page(request, "seals", "docflow/seals.html", {
        "seals": Seal.objects.select_related("owner", "issued_to").annotate(n=Count("usages")),
        "usages": SealUsage.objects.select_related("seal", "document", "employee")[:25],
        "signers": Approval.objects.filter(role="signer", decision="signed").select_related(
            "document", "employee").order_by("-decided_at")[:10],
        "can_sign": services.can_sign(request.user)})


@login_required
def archive(request):
    recs = list(ArchiveRecord.objects.select_related("document", "case", "archivist"))
    return _page(request, "archive", "docflow/archive.html", {
        "recs": recs, "years": sorted({r.archived_at.year for r in recs}, reverse=True),
        "ready": _docs().filter(status__in=["executed", "closed"]).exclude(case__isnull=True)[:8]})


# ---------------- Карточка ----------------

@login_required
def detail(request, pk):
    d = get_object_or_404(_docs().select_related("contract", "parent", "template"), pk=pk)
    approvals = list(d.approvals.select_related("employee").all())
    related = []
    if d.parent:
        related.append(("Создан на основании", d.parent))
    for c in d.children.all():
        related.append(("Создан на его основании", c))
    if d.contract:
        related.append(("Договор", d.contract))
    for c in d.contract_docs.all():
        related.append(("По этому договору", c))
    for r in d.related.all():
        related.append(("Связанный документ", r))
    req = [("ID", d.uid), ("Тип", d.get_kind_display() + (f" · {d.subtype}" if d.subtype else "")),
           ("Рег. номер", d.number or "не зарегистрирован"),
           ("Дата документа", f"{d.doc_date:%d.%m.%Y}"),
           ("Дата регистрации", f"{d.reg_date:%d.%m.%Y}" if d.reg_date else "—"),
           ("Организация", Company.get().name)]
    if d.kind in ("incoming", "outgoing", "internal"):
        req.insert(5, ("Направление", d.get_direction_display()))
    if d.counterparty:
        req.append(({"incoming": "Отправитель", "outgoing": "Адресат"}.get(d.kind, "Контрагент"), d.counterparty))
    if d.sender_number:
        req.append(("Номер отправителя", d.sender_number))
    if d.channel:
        req.append(("Канал", d.get_channel_display()))
    req += [("Подразделение", str(d.department or "—")), ("Автор", str(d.author or "—")),
            ("Ответственный", str(d.responsible or "—"))]
    if d.signer:
        req.append(("Подписант", str(d.signer)))
    req += [("Приоритет", d.get_priority_display()),
            ("Конфиденциальность", "конфиденциально" if d.confidential else "общий доступ"),
            ("Дело", f"{d.case.index} {d.case.title}" if d.case else "не указано"),
            ("Журнал", str(d.journal or "—"))]
    if d.sent_at:
        req.append(("Отправлен", f"{d.sent_at:%d.%m.%Y}" + (" · получение подтверждено" if d.delivery_confirmed
                                                             else "")))
    money = []
    if d.kind == "contract":
        money = [("Тип договора", d.get_contract_type_display() or "—"),
                 ("Сумма", d.amount), ("Валюта", d.currency + (", с НДС" if d.vat else ", без НДС")),
                 ("Оплачено", d.paid),
                 ("Действует", f"{d.valid_from:%d.%m.%Y} – {d.valid_until:%d.%m.%Y}" if d.valid_from and d.valid_until
                  else "—"),
                 ("Гарантия до", f"{d.guarantee_until:%d.%m.%Y}" if d.guarantee_until else "—")]
    files = list(d.files.select_related("author"))
    return _page(request, "all", "docflow/detail.html", {
        "d": d, "steps": d.steps(), "actions": d.actions(), "approvals": approvals, "related": related,
        "req": req, "money": money, "files": files, "tasks": d.tasks.select_related("assignee"),
        "recipients": d.recipients.select_related("employee"), "events": d.events.all(),
        "seal_usages": d.seal_usages.select_related("seal", "employee"),
        "archive_rec": getattr(d, "archive", None), "due_text": services.due_text(d.days_left),
        "back_tab": {"order": "docflow_orders", "incoming": "docflow_letters", "outgoing": "docflow_letters_out",
                     "internal": "docflow_letters_internal", "contract": "docflow_contracts"}.get(d.kind, "docflow_all"),
        "wa_text": f"{d.get_kind_display()} № {d.number or d.uid} от {d.doc_date:%d.%m.%Y}: {d.title}",
    })


@login_required
@require_POST
def action(request, pk):
    d = get_object_or_404(Document, pk=pk)
    code = request.POST.get("action", "")
    try:
        if code == "comment":
            text = request.POST.get("reason", "").strip()
            if text:
                services.log(d, "comment", text, request.user)
                messages.success(request, "Комментарий добавлен")
        else:
            had_number = bool(d.number)
            messages.success(request, services.apply_action(d, code, request.user, request.POST.get("reason", "")))
            d.refresh_from_db()
            if d.kind == "order" and d.number and not had_number and d.template and d.template.is_letterhead \
                    and d.template.category == "order":
                build_order_files(d, d.template, services.employee_of(request.user), request.user)
    except services.ActionError as e:
        messages.error(request, str(e))
    return redirect("docflow_detail", pk=d.pk)


# ---------------- Формы ----------------

KIND_TITLES = {"order": ("Новый приказ", "Организационный или административный приказ. После подписи — регистрация "
                                          "и поручения по пунктам."),
               "incoming": ("Регистрация входящего", "Загрузите скан, укажите отправителя и срок ответа. Номер ВХ "
                                                    "присвоится автоматически."),
               "outgoing": ("Исходящее письмо", "Если нужен готовый PDF на фирменном бланке — воспользуйтесь "
                                               "генератором писем."),
               "internal": ("Внутренний документ", "Служебная записка, протокол совещания, распоряжение."),
               "contract": ("Новый договор", "После согласования и подписи договор получит номер и станет "
                                             "действующим.")}


def _form(request, form_class, title, back, instance=None, subtitle="", submit="Сохранить", kwargs=None,
          success=None, extra=None):
    return form_page(request, form_class, title, success or back, instance=instance, subtitle=subtitle,
                     submit=submit, back=back, form_kwargs=kwargs, extra={"section": "docflow", **(extra or {})})


@login_required
def new(request, kind):
    if kind not in KIND_TITLES:
        raise Http404
    title, sub = KIND_TITLES[kind]

    def done(doc):
        services.log(doc, "create", f"Создан: {doc.get_kind_display()}", request.user)
        blank = order_blank() if kind == "order" and not doc.file else None
        if blank:
            build_order_files(doc, blank, services.employee_of(request.user), request.user)
        elif doc.file:
            DocumentFile.objects.create(document=doc, file=doc.file.name, name=doc.file.name.rsplit("/", 1)[-1],
                                        role="original" if kind == "incoming" else "working",
                                        author=services.employee_of(request.user))
        if doc.signer and not doc.approvals.exists():
            Approval.objects.create(document=doc, step=9, role="signer", employee=doc.signer)
        return reverse("docflow_detail", args=[doc.pk])
    extra = {"blank_data": blank_data(Company.get(), "order", request.user)} if kind == "order" else None
    return _form(request, forms.DocumentForm, title, reverse("docflow_home"), subtitle=sub,
                 submit="Зарегистрировать" if kind == "incoming" else "Создать", kwargs={"kind": kind},
                 success=done, extra=extra)


@login_required
def edit(request, pk):
    d = get_object_or_404(Document, pk=pk)
    if d.is_locked and not request.user.is_superuser:
        messages.error(request, "Документ подписан или зарегистрирован — изменить можно только через новую версию.")
        return redirect("docflow_detail", pk=pk)
    return _form(request, forms.DocumentForm, f"{d.get_kind_display()}: изменение",
                 reverse("docflow_detail", args=[pk]), instance=d, kwargs={"kind": d.kind},
                 subtitle="Изменения попадут в историю документа.")


@login_required
def task_new(request):
    def done(t):
        if not t.number:
            t.number = f"П-{date.today():%Y}-{t.pk:04d}"
            t.author = t.author or services.employee_of(request.user)
            t.save(update_fields=["number", "author"])
        if t.document:
            services.log(t.document, "assign", f"Поручение {t.number}: {t.assignee}", request.user)
        return reverse("docflow_tasks")
    return _form(request, forms.TaskForm, "Новое поручение", reverse("docflow_tasks"), submit="Поручить",
                 subtitle="Исполнитель и срок обязательны. Напоминания придут до срока, в срок и при просрочке.",
                 success=done)


@login_required
@require_POST
def task_act(request, pk):
    t = get_object_or_404(DocTask, pk=pk)
    act = request.POST.get("act")
    if act == "postpone":
        reason, new_due = request.POST.get("reason", "").strip(), request.POST.get("due", "")
        if not reason or not new_due:
            messages.error(request, "Для переноса срока нужны новая дата и причина.")
        else:
            old = t.due
            t.due, t.postpone_reason = date.fromisoformat(new_due), reason[:255]
            t.save()
            if t.document:
                services.log(t.document, "deadline", f"Перенесён срок поручения {t.number}", request.user,
                             old=f"{old:%d.%m.%Y}", new=f"{t.due:%d.%m.%Y}", reason=reason)
            messages.success(request, "Срок перенесён")
    elif act == "rework" and t.status == "review":
        t.status = "rework"
        t.save()
        messages.success(request, "Возвращено на доработку")
    elif t.status in DocTask.NEXT:
        t.status = DocTask.NEXT[t.status][0]
        if t.status == "done":
            t.done_at = date.today()
        t.save()
        messages.success(request, f"Поручение: {t.get_status_display().lower()}")
    return redirect(request.POST.get("next") or "docflow_tasks")


def _simple(form_class, model, title_new, title_edit, back_name, subtitle=""):
    @login_required
    def view(request, pk=None):
        inst = get_object_or_404(model, pk=pk) if pk else None
        return _form(request, form_class, title_edit if inst else title_new, reverse(back_name), instance=inst,
                     subtitle=subtitle)
    return view


case_form = _simple(forms.CaseForm, CaseFile, "Новое дело", "Дело номенклатуры", "docflow_cases",
                    "Уничтожение дел — только по утверждённому акту и со специальными правами.")
journal_form = _simple(forms.JournalForm, Journal, "Новый журнал регистрации", "Журнал регистрации",
                       "docflow_journals", "Зарегистрированные записи нельзя удалить; исправления — с причиной.")
template_form = _simple(forms.TemplateForm, Template, "Новый шаблон", "Шаблон", "docflow_templates",
                        "Загрузите бланк DOCX или PDF и укажите, где подпись и печать.")
seal_form = _simple(forms.SealForm, Seal, "Новая печать или подпись", "Печать / подпись", "docflow_seals",
                    "Каждое использование фиксируется в журнале печатей.")


# ---------------- Генератор писем на бланке (ТЗ п. 35) ----------------

SIGN_CHOICES = [("both", "Да, подпись и печать"), ("sign", "Только подпись"), ("seal", "Только печать"),
                ("none", "Без подписи и печати")]


def _generator_ctx(request):
    company = Company.get()
    out_j = Journal.objects.filter(kind="outgoing", is_active=True).first()
    director = company.director
    signers = [e for e in Employee.objects.filter(is_active=True, in_staff=True, position__name__in=[
        "Директор", "Заместитель директора"]).select_related("position")]
    last = Document.objects.filter(kind="outgoing", template__isnull=False).exclude(file="").order_by("-id").first()
    return {
        "company": company, "letterheads": Template.objects.filter(is_letterhead=True, is_active=True, category="letter").order_by(
            "name", "-version"),
        "signers": signers, "director": director,
        "seals": Seal.objects.filter(kind="seal", is_active=True),
        "objects": ConstructionObject.objects.exclude(status="archive").order_by("name"),
        "contracts_list": Document.objects.filter(kind="contract").exclude(status="cancelled"),
        "incoming_list": Document.objects.filter(kind="incoming").order_by("-doc_date")[:20],
        "addressees": sorted(set(Document.objects.exclude(counterparty="").values_list("counterparty", flat=True))),
        "next_number": out_j.example if out_j else "",
        "sign_choices": SIGN_CHOICES, "can_sign": services.can_sign(request.user),
        "can_seal": request.user.is_superuser or request.user.has_perm("docflow.use_seal"),
        "sample": last, "me": services.employee_of(request.user),
        "today_text": f"{date.today():%d.%m.%Y}",
        "blank_data": blank_data(company, "letter", request.user),
    }


def short_name(emp):
    """Балтаев Н. Ш. — фамилия и инициалы."""
    if not emp:
        return ""
    parts = emp.full_name.split()
    return parts[0] + (" " + " ".join(p[0] + "." for p in parts[1:3]) if len(parts) > 1 else "")


def _blank_bytes(template):
    """Файл бланка DOCX (шапка, логотип, водяной знак) или None."""
    if not template or not template.file or not template.is_docx:
        return None
    try:
        with template.file.open("rb") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def _attach(doc, content, filename, name, author, comment, role="working"):
    f = DocumentFile(document=doc, name=name, role=role, author=author, comment=comment,
                     version=doc.files.filter(name=name).count() + 1, size_kb=max(1, len(content) // 1024))
    f.file.save(filename, ContentFile(content), save=False)
    f.save()
    return f


def order_text(summary):
    """Текст приказа из поля «Содержание»: преамбула (основание) и пункты «1. …»."""
    basis, points = [], []
    for line in (x.strip() for x in (summary or "").split("\n")):
        if not line or line.rstrip(":").upper() in ("ПРИКАЗЫВАЮ", "БҰЙЫРАМЫН"):
            continue
        m = re.match(r"^\d+[.)]\s*(.+)$", line)
        if m:
            points.append(m.group(1))
        elif points:
            points.append(line)
        else:
            basis.append(line)
    if not points:
        basis, points = [], basis
    return " ".join(basis), points


def order_blank():
    return Template.objects.filter(is_letterhead=True, is_active=True, category="order").order_by("-version").first()


def order_signer(signer):
    """Подпись под приказом: (должность, «Н.Балтаев»)."""
    position = signer.position.name if signer and signer.position else "Директор"
    initials = ""
    if signer:
        parts = signer.full_name.split()
        initials = " ".join(p[0] + "." for p in parts[1:2]) + parts[0] if len(parts) > 1 else parts[0]
    return position, initials


def blank_data(company, kind, user=None):
    """Данные для предпросмотра, PDF и DOCX в браузере (static/blank.js): шапка бланка, файл бланка,
    исполнитель и подписанты. Браузер собирает документ из того, что ввёл человек, — без сервера."""
    me = services.employee_of(user) if user else None
    data = {"kind": kind, "header": pdf.letterhead_columns(company), "company": company.name,
            "bin": company.bin or "", "executor": short_name(me), "executor_phone": (me.phone if me else "") or ""}
    if kind == "order":
        tpl = order_blank()
        data["docx"] = tpl.file.url if tpl and tpl.file and tpl.is_docx else ""
        data["director"] = order_signer(company.director)
        data["signers"] = {str(e.pk): order_signer(e) for e in Employee.objects.filter(is_active=True)
                           .select_related("position")}
    return data


def build_order_files(doc, template, author=None, user=None):
    """Приказ на фирменном бланке: PDF (основной файл) и DOCX для правки в Word."""
    company = Company.get()
    position, initials = order_signer(doc.signer or company.director)
    basis, points = order_text(doc.summary)
    dt = f"{doc.doc_date:%d.%m.%Y}" if doc.doc_date else ""
    content = pdf.order_pdf(company, doc.number, dt, doc.title, basis, points, position, initials, sign=False)
    doc.file.save(f"prikaz-{doc.pk}.pdf", ContentFile(content), save=False)
    doc.template = template
    doc.save(update_fields=["file", "template"])
    _attach(doc, content, f"prikaz-{doc.pk}-v.pdf", f"Приказ — {doc.title[:60]}.pdf", author,
            f"Сформирован на бланке «{template.name}»")
    blank = _blank_bytes(template)
    if blank:
        docx = blank_docx.order_docx(blank, number=doc.number, date_text=dt, title=doc.title, basis=basis,
                                     points=points, signer_pos=position, signer_name=initials)
        _attach(doc, docx, f"prikaz-{doc.pk}.docx", f"Приказ — {doc.title[:60]}.docx", author,
                "Тот же приказ в Word на бланке — для правки и печати")
    services.log(doc, "create", f"Приказ оформлен на бланке «{template.name}» v{template.version}", user)


def build_letter(company, *, template, addressee, subject, body, signer, sign_mode, seal, obj=None, contract=None,
                 parent=None, attachments=(), author=None, user=None, when=None, channel="email", status="registered"):
    """Создаёт исходящее письмо: номер по журналу, PDF на бланке, запись в журнале, история и журнал печатей."""
    when = when or date.today()
    if sign_mode in ("sign", "both") and template.sign_rule == "none":
        sign_mode = "none"
    doc = Document.objects.create(
        kind="outgoing", direction="out", title=subject, doc_date=when, counterparty=addressee,
        construction_object=obj, contract=contract, parent=parent, author=author, responsible=author, signer=signer,
        summary=body, template=template, channel=channel, status="draft",
        case=CaseFile.objects.filter(doc_types__icontains="исходящ").first(),
        department=author.department if author else None)
    services.log(doc, "create", f"Создано в генераторе на бланке «{template.name}» v{template.version}", user,
                 by=None if user else (author.full_name if author else "система"))
    services.register(doc, user)
    doc.reg_date = when
    use_sign, use_seal = sign_mode in ("sign", "both"), sign_mode in ("seal", "both")
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    position = signer.position.name if signer and signer.position else "Директор"
    short = ""
    if signer:
        parts = signer.full_name.split()
        short = parts[0] + (" " + " ".join(p[0] + "." for p in parts[1:3]) if len(parts) > 1 else "")
    executor, phone = (short_name(author), author.phone) if author else ("", "")
    content = pdf.letter_pdf(company, doc.number, f"{when:%d.%m.%Y}", addressee, subject, paras, position, short,
                             sign=use_sign, seal=use_seal and bool(seal), attachments=attachments,
                             executor=executor, executor_phone=phone)
    doc.file.save(f"ishod-{doc.pk}.pdf", ContentFile(content), save=False)
    doc.status = status
    doc.save()
    DocumentFile.objects.create(document=doc, file=doc.file.name, name=f"Письмо {doc.number}.pdf", role="original",
                                author=author, comment="Финальный PDF, сформирован на бланке", locked=True,
                                size_kb=len(content) // 1024)
    blank = _blank_bytes(template)
    if blank:
        docx = blank_docx.letter_docx(blank, number=doc.number, date_text=f"{when:%d.%m.%Y}", addressee=addressee,
                                      subject=subject, paragraphs=paras, signer_pos=position, signer_name=short,
                                      attachments=attachments, executor=executor, executor_phone=phone)
        _attach(doc, docx, f"ishod-{doc.pk}.docx", f"Письмо {doc.number}.docx", author,
                "Тот же текст в Word на бланке — для правки и печати", role="working")
    if signer:
        Approval.objects.create(document=doc, step=1, role="signer", employee=signer, decision="signed",
                                method="Изображение подписи на бланке" if use_sign else "Собственноручно",
                                decided_at=timezone.now())
    labels = dict(SIGN_CHOICES)
    services.log(doc, "sign", f"Подпись и печать: {labels.get(sign_mode, sign_mode).lower()}", user,
                 by=None if user else (author.full_name if author else ""))
    for s, used in ((seal, use_seal),):
        if s and used:
            SealUsage.objects.create(seal=s, document=doc, employee=author, action="use",
                                     purpose=f"Исходящее письмо {doc.number}")
            services.log(doc, "seal", f"Проставлена печать «{s.name}»", user,
                         by=None if user else (author.full_name if author else ""))
    return doc


@login_required
def letter(request):
    ctx = _generator_ctx(request)
    if request.method == "POST":
        p = request.POST
        errors = []
        tpl = Template.objects.filter(pk=p.get("template") or 0, is_letterhead=True, category="letter").first()
        if not tpl:
            errors.append("Выберите фирменный бланк.")
        for field, label in (("addressee", "адресата"), ("subject", "тему"), ("body", "текст письма")):
            if not p.get(field, "").strip():
                errors.append(f"Укажите {label}.")
        sign_mode = p.get("sign_mode", "")
        if sign_mode not in dict(SIGN_CHOICES):
            errors.append("Ответьте на вопрос «Добавить подпись и печать на документ?».")
        if sign_mode in ("sign", "both") and not ctx["can_sign"]:
            errors.append("У вас нет права ставить подпись.")
        if sign_mode in ("seal", "both") and not ctx["can_seal"]:
            errors.append("У вас нет права ставить печать.")
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "docflow/letter.html", {**ctx, "tab": "letters", "tabs": TABS, "post": p})
        signer = Employee.objects.filter(pk=p.get("signer") or 0).first() or ctx["director"]
        doc = build_letter(
            ctx["company"], template=tpl, addressee=p["addressee"].strip(), subject=p["subject"].strip(),
            body=p["body"], signer=signer, sign_mode=sign_mode,
            seal=Seal.objects.filter(pk=p.get("seal") or 0).first(),
            obj=ConstructionObject.objects.filter(pk=p.get("object") or 0).first(),
            contract=Document.objects.filter(pk=p.get("contract") or 0, kind="contract").first(),
            parent=Document.objects.filter(pk=p.get("parent") or 0).first(),
            attachments=[a.strip() for a in p.get("attachments", "").split("\n") if a.strip()],
            author=services.employee_of(request.user), user=request.user)
        messages.success(request, f"Письмо сформировано и зарегистрировано: № {doc.number} от {doc.reg_date:%d.%m.%Y}")
        return redirect(reverse("docflow_detail", args=[doc.pk]) + "?done=1")
    return render(request, "docflow/letter.html", {**ctx, "tab": "letters", "tabs": TABS})
