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
        ACCEPTED = "accepted", "Принята"
        IN_PROGRESS = "in_progress", "В работе"
        REVIEW = "review", "На проверке"
        DONE = "done", "Выполнена"

    class Source(models.TextChoices):
        MANAGEMENT = "management", "Руководство"
        INSPECTION = "inspection", "Обход"
        FOREMAN = "foreman", "Прораб"
        PTO = "pto", "ПТО"
        HR = "hr", "HR"
        FINANCE = "finance", "Финансы"
        DOCS = "docs", "Документы"
        SUPPLY = "supply", "Снабжение"

    # Какой статус следующий и как называется кнопка (ТЗ п. 12).
    FLOW = {
        "new": ("accepted", "Принять задачу"),
        "accepted": ("in_progress", "Начать работу"),
        "in_progress": ("review", "Готово — на проверку"),
        "review": ("done", "Подтвердить выполнение"),
    }

    class Priority(models.IntegerChoices):
        LOW = 1, "Низкий"
        NORMAL = 2, "Обычный"
        HIGH = 3, "Высокий"

    title = models.CharField("Задача", max_length=200)
    description = models.TextField("Описание", blank=True)
    source = models.CharField("Откуда задача", max_length=12, choices=Source.choices, default=Source.MANAGEMENT)
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
    file = models.FileField("Файл", upload_to="tasks/%Y/%m/", blank=True)
    comment = models.TextField("Комментарий", blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    done_at = models.DateTimeField("Выполнена", null=True, blank=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["due_date", "-priority"]
        permissions = [("close_task", "Может подтверждать выполнение задач")]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        from datetime import date
        return bool(self.due_date and self.due_date < date.today() and self.status != self.Status.DONE)

    @property
    def next_step(self):
        return self.FLOW.get(self.status)
