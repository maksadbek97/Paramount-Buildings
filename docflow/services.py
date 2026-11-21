"""Действия с документами: переходы по статусам, регистрация, архив, история."""
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from staff.models import Employee

from .models import Approval, ArchiveRecord, DocEvent, Document, Journal

JOURNAL_FOR = {"incoming": "incoming", "outgoing": "outgoing", "order": "order", "contract": "contract",
               "internal": "internal"}


class ActionError(Exception):
    pass


def employee_of(user):
    """Сотрудник, связанный с учётной записью (или руководитель — для администратора)."""
    if not user or not user.is_authenticated:
        return None
    emp = Employee.objects.filter(user=user).first()
    if emp:
        return emp
    if user.last_name:
        emp = Employee.objects.filter(full_name__startswith=user.last_name, in_staff=True).first()
    return emp


def who(user):
    emp = employee_of(user)
    if emp:
        return emp.full_name
    return (user.get_full_name() or user.get_username()) if user else "система"


def log(doc, kind, text, user=None, old="", new="", reason="", by=None):
    return DocEvent.objects.create(document=doc, kind=kind, text=text[:300], old=old[:200], new=new[:200],
                                   reason=reason[:300], who=by or (who(user) if user else "система"))


def register(doc, user=None):
    """Присвоить номер по журналу и дату регистрации. Номер уже был — не меняем."""
    if doc.number:
        if not doc.reg_date:
            doc.reg_date = date.today()
        return doc.number
    journal = doc.journal or Journal.objects.filter(kind=JOURNAL_FOR.get(doc.kind, "custom"), is_active=True).first()
    if not journal:
        raise ActionError("Нет журнала регистрации для этого типа документа.")
    with transaction.atomic():
        doc.journal = journal
        doc.number = journal.next_number()
        doc.reg_date = date.today()
        doc.save(update_fields=["journal", "number", "reg_date"])
    log(doc, "register", f"Зарегистрирован в журнале «{journal}» под № {doc.number}", user, new=doc.number)
    return doc.number


def set_status(doc, status, user=None, reason="", text=""):
    old = doc.get_status_display()
    doc.status = status
    doc.save(update_fields=["status"])
    log(doc, "status", text or f"Статус: {doc.get_status_display()}", user, old=old,
        new=doc.get_status_display(), reason=reason)


def can_sign(user):
    return bool(user and (user.is_superuser or user.has_perm("docflow.sign_document")))


def apply_action(doc, code, user, reason=""):
    """Выполняет действие из Document.actions(). Возвращает текст для сообщения пользователю."""
    allowed = {a[0]: a for a in doc.actions()}
    if code not in allowed:
        raise ActionError("Это действие сейчас недоступно для документа.")
    if allowed[code][3] and not reason.strip():
        raise ActionError("Укажите причину — без неё действие не выполняется.")
    me = employee_of(user)
    now = timezone.now()

    if code == "to_approval":
        steps = doc.approvals.all()
        if not steps.exists():
            raise ActionError("Добавьте хотя бы одного согласующего или подписанта.")
        first = min(s.step for s in steps)
        steps.exclude(decision__in=["approved", "signed"]).update(decision="waiting", comment="", decided_at=None)
        steps.filter(step=first).exclude(decision__in=["approved", "signed"]).update(decision="pending")
        set_status(doc, "approval", user, text="Отправлен на согласование")
        return "Документ отправлен на согласование."

    if code == "approve":
        pending = doc.approvals.filter(decision="pending", role="approver")
        mine = pending.filter(employee=me).first() if me else None
        step = mine or pending.first()
        if step:
            step.decision, step.decided_at, step.comment = "approved", now, reason[:300]
            step.save()
            log(doc, "approve", f"Согласовал: {step.employee}", user, reason=reason)
        rest = doc.approvals.filter(role="approver", decision__in=["pending", "waiting"])
        if not rest.filter(decision="pending").exists() and rest.exists():
            nxt = min(s.step for s in rest)
            rest.filter(step=nxt).update(decision="pending")
        if not rest.exists():
            doc.approvals.filter(role="signer").update(decision="pending")
            set_status(doc, "signing" if doc.approvals.filter(role="signer").exists() else "approved", user,
                       text="Согласование завершено")
            return "Все согласовали. Документ передан на подпись."
        return "Ваше согласование учтено."

    if code in {"return", "reject"}:
        step = doc.approvals.filter(decision="pending").filter(employee=me).first() if me else None
        step = step or doc.approvals.filter(decision="pending").first()
        if step:
            step.decision = "returned" if code == "return" else "rejected"
            step.decided_at, step.comment = now, reason[:300]
            step.save()
        if code == "return":
            set_status(doc, "rework", user, reason, "Возвращён на доработку")
            return "Документ возвращён автору на доработку."
        set_status(doc, "rejected", user, reason, "Отклонён")
        return "Документ отклонён."

    if code == "sign":
        if not can_sign(user):
            raise ActionError("У вас нет права подписи.")
        step = doc.approvals.filter(role="signer").exclude(decision="signed").first()
        if step:
            step.decision, step.decided_at = "signed", now
            step.method = step.method or "ЭЦП НУЦ РК"
            step.save()
        log(doc, "sign", f"Подписан: {step.employee if step else who(user)}", user)
        if doc.kind == "contract":
            set_status(doc, "signed", user, text="Договор подписан")
            if not doc.number:
                register(doc, user)
            return "Договор подписан и зарегистрирован."
        register(doc, user)
        set_status(doc, "registered", user, text="Подписан и зарегистрирован")
        return f"Документ подписан и зарегистрирован под № {doc.number}."

    if code == "register":
        missing = [m for m in doc.missing if m != "дело"]
        if missing:
            raise ActionError("Перед регистрацией заполните: " + ", ".join(missing) + ".")
        register(doc, user)
        set_status(doc, "registered", user, text="Зарегистрирован")
        return f"Зарегистрирован под № {doc.number}."

    if code == "send":
        doc.sent_at = date.today()
        doc.save(update_fields=["sent_at"])
        log(doc, "send", f"Отправлен адресату: {doc.counterparty}"
            + (f" ({doc.get_channel_display()})" if doc.channel else ""), user)
        set_status(doc, "sent", user)
        return "Отправка отмечена."

    if code == "confirm":
        doc.delivery_confirmed = True
        doc.save(update_fields=["delivery_confirmed"])
        log(doc, "receive", "Адресат подтвердил получение", user)
        set_status(doc, "closed", user)
        return "Получение подтверждено, письмо закрыто."

    if code == "execute":
        set_status(doc, "execution", user, text="Вступил в силу" if doc.kind == "contract" else "Передан в исполнение")
        return "Готово."

    if code == "done":
        doc.tasks.filter(status__in=["review"]).update(status="done", done_at=date.today())
        set_status(doc, "closed" if doc.kind == "contract" else "executed", user)
        return "Отмечено."

    if code == "archive":
        return archive(doc, user)

    if code == "cancel":
        set_status(doc, "cancelled", user, reason, "Отменён")
        return "Документ отменён. Номер и история сохранены."
    raise ActionError("Неизвестное действие.")


def archive(doc, user=None, archivist=None, when=None):
    if not doc.case:
        raise ActionError("Укажите дело по номенклатуре — без него документ нельзя передать в архив.")
    if doc.tasks.exclude(status__in=["done", "cancelled"]).exists():
        raise ActionError("Есть незакрытые поручения по документу — архивировать пока нельзя.")
    when = when or date.today()
    year = when.year
    n = ArchiveRecord.objects.filter(archive_id__startswith=f"АРХ-{year}-").count() + 1
    years = doc.case.retention_years
    rec = ArchiveRecord.objects.create(
        archive_id=f"АРХ-{year}-{n:04d}", document=doc, case=doc.case, archived_at=when,
        keep_until=date(doc.case.year + 1 + years, 1, 1) if years else None,
        location=doc.case.location, archivist=archivist or employee_of(user))
    old = doc.get_status_display()
    doc.status = "archived"
    doc.save(update_fields=["status"])
    log(doc, "archive", f"Передан в архив: {rec.archive_id}, дело {doc.case.index}", user, old=old,
        new="В архиве")
    return f"Документ передан в архив под № {rec.archive_id}."


def due_text(days):
    if days is None:
        return ""
    if days < 0:
        return f"просрочено на {-days} дн."
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"
    return f"через {days} дн."


def week_ago():
    return date.today() - timedelta(days=7)


__all__ = ["apply_action", "archive", "register", "log", "employee_of", "ActionError", "Approval", "Document"]
