"""Журнал действий (Audit log, ТЗ п. 26): кто, что, когда, на каком объекте, было → стало."""
import json

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Создание"
        UPDATE = "update", "Изменение"
        DELETE = "delete", "Удаление"
        ACCEPT = "accept", "Приёмка"
        REJECT = "reject", "Отклонение"

    created_at = models.DateTimeField("Когда", auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Кто", null=True, blank=True,
                             on_delete=models.SET_NULL)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    action = models.CharField("Действие", max_length=10, choices=Action.choices)
    module = models.CharField("Раздел", max_length=60)
    object_id = models.CharField("ID записи", max_length=40)
    object_repr = models.CharField("Запись", max_length=300)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект", null=True,
                                            blank=True, on_delete=models.SET_NULL, related_name="history")
    changes = models.TextField("Было → стало", blank=True)
    reason = models.CharField("Причина", max_length=300, blank=True)

    class Meta:
        verbose_name = "Запись журнала"
        verbose_name_plural = "Журнал действий"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.created_at:%d.%m.%Y %H:%M} {self.get_action_display()}: {self.object_repr}"

    @property
    def change_list(self):
        try:
            return json.loads(self.changes) if self.changes else []
        except ValueError:
            return []
