import json
from decimal import Decimal

from django.db import models

from .models import AuditLog

SKIP = {"id", "created_at", "uploaded_at"}


def snapshot(instance):
    """Значения полей записи в читаемом виде (для «было → стало»)."""
    data = {}
    if instance is None or instance.pk is None:
        return data
    for f in instance._meta.concrete_fields:
        if f.name in SKIP:
            continue
        value = getattr(instance, f.name)
        if isinstance(f, models.ForeignKey):
            value = str(value) if value is not None else ""
        elif f.choices:
            value = getattr(instance, f"get_{f.name}_display")()
        elif isinstance(f, models.FileField):
            value = value.name if value else ""
        if isinstance(value, Decimal):
            value = f"{value.normalize():f}"
        data[str(f.verbose_name)] = "" if value is None else str(value)
    return data


def object_of(instance):
    """Строительный объект, к которому относится запись."""
    from objects.models import ConstructionObject
    if isinstance(instance, ConstructionObject):
        return instance
    for path in ("construction_object", "contract.construction_object", "assignment.contract.construction_object"):
        obj = instance
        try:
            for part in path.split("."):
                obj = getattr(obj, part)
        except AttributeError:
            continue
        if isinstance(obj, ConstructionObject):
            return obj
    return None


def log(request, instance, action, before=None, reason=""):
    after = snapshot(instance)
    before = before or {}
    if action == AuditLog.Action.CREATE:
        changes = [[k, "", v] for k, v in after.items() if v not in ("", "0", "False")]
    else:
        changes = [[k, before.get(k, ""), v] for k, v in after.items() if before.get(k, "") != v]
        if action == AuditLog.Action.UPDATE and not changes:
            return None
    user = getattr(request, "user", None)
    return AuditLog.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        ip=(request.META.get("REMOTE_ADDR") or None) if request else None,
        action=action, module=instance._meta.verbose_name_plural, object_id=str(instance.pk),
        object_repr=str(instance)[:300], construction_object=object_of(instance),
        changes=json.dumps(changes, ensure_ascii=False), reason=reason,
    )
