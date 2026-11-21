from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Position(models.Model):
    name = models.CharField("Должность", max_length=100, unique=True)

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="Учётная запись",
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    full_name = models.CharField("ФИО", max_length=200)
    iin = models.CharField("ИИН", max_length=12, blank=True,
                           validators=[RegexValidator(r"^\d{12}$", "ИИН — 12 цифр.")])
    position = models.ForeignKey(
        Position, verbose_name="Должность", null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    phone = models.CharField("Телефон", max_length=30, blank=True)
    hired_at = models.DateField("Дата приёма", null=True, blank=True)
    salary = models.DecimalField("Оклад", max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField("Работает", default=True)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Выполнена"

    class Priority(models.IntegerChoices):
        LOW = 1, "Низкий"
        NORMAL = 2, "Обычный"
        HIGH = 3, "Высокий"

    title = models.CharField("Задача", max_length=200)
    description = models.TextField("Описание", blank=True)
    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект",
        null=True, blank=True, on_delete=models.CASCADE, related_name="tasks",
    )
    assignee = models.ForeignKey(
        Employee, verbose_name="Исполнитель", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="tasks",
    )
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    priority = models.IntegerField("Приоритет", choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField("Срок", null=True, blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["status", "due_date"]

    def __str__(self):
        return self.title
