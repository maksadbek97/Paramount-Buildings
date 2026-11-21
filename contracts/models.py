"""Субподряд: объёмы работ, взятые у генподрядчика, исполнители, выработка и расчёты.

Как это устроено:
    Договор (WorkContract) — вид работ на объекте: объём, единица, цена за единицу.
    Назначение (Assignment) — кто выполняет: рабочий или бригада, и как ему платим
        (за единицу объёма или за день).
    Выработка (WorkLog) — сколько сделано за день конкретным исполнителем.
    Платёж (Payment) — деньги от генподрядчика, выплаты рабочим, материалы, прочее.
"""
from decimal import Decimal
from functools import cached_property

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

ZERO = Decimal("0")


def _sum(qs, field):
    return qs.aggregate(s=Sum(field))["s"] or ZERO


class Crew(models.Model):
    name = models.CharField("Название бригады", max_length=120)
    leader = models.ForeignKey(
        "staff.Employee", verbose_name="Бригадир", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="led_crews",
    )
    members = models.ManyToManyField("staff.Employee", verbose_name="Состав", blank=True, related_name="crews")
    phone = models.CharField("Телефон", max_length=30, blank=True)
    note = models.CharField("Примечание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Бригада"
        verbose_name_plural = "Бригады"
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkContract(models.Model):
    class Unit(models.TextChoices):
        M3 = "м³", "м³ (кубометр)"
        M2 = "м²", "м² (квадратный метр)"
        M = "м.п.", "м.п. (погонный метр)"
        PCS = "шт", "шт (штука)"
        T = "т", "т (тонна)"

    class Status(models.TextChoices):
        ACTIVE = "active", "В работе"
        PAUSED = "paused", "Приостановлен"
        DONE = "done", "Сдан"

    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект",
        on_delete=models.CASCADE, related_name="contracts",
    )
    work_type = models.CharField("Вид работ", max_length=200, help_text="Например: кладка газоблока")
    section = models.CharField("Секция / блок", max_length=50, blank=True)
    floor = models.CharField("Этаж", max_length=50, blank=True, help_text="Например: 5 или 1–9")
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный (ПТО)", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="pto_contracts")
    unit = models.CharField("Единица", max_length=10, choices=Unit.choices, default=Unit.M3)
    volume = models.DecimalField("Объём по договору", max_digits=12, decimal_places=2)
    price = models.DecimalField("Цена за единицу (нам платят)", max_digits=14, decimal_places=2)
    start_date = models.DateField("Начало", null=True, blank=True)
    end_date = models.DateField("Срок сдачи", null=True, blank=True)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    note = models.TextField("Примечание", blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Договор (объём работ)"
        verbose_name_plural = "Договоры (объёмы работ)"
        ordering = ["status", "end_date", "-created_at"]
        permissions = [
            ("review_worklog", "Может принимать и отклонять объёмы"),
            ("allow_over_plan", "Может вносить объём сверх плана"),
        ]

    def __str__(self):
        return f"{self.work_type} — {self.construction_object}"

    @property
    def place(self):
        parts = []
        if self.section:
            parts.append(f"секция {self.section}")
        if self.floor:
            parts.append(f"этаж {self.floor}")
        return ", ".join(parts)

    # --- объёмы ---
    # Официальный учёт (ТЗ п. 6.2): только принятый объём.
    #   Остаток = План − Принято; Выполнение % = Принято / План × 100; Стоимость = Принято × Цена.
    def _logs(self):
        return WorkLog.objects.filter(assignment__contract=self)

    @cached_property
    def accepted_volume(self):
        return _sum(self._logs().filter(status=WorkLog.Status.ACCEPTED), "accepted_volume")

    @cached_property
    def pending_volume(self):
        """Внесено прорабом, ждёт проверки ПТО."""
        return _sum(self._logs().filter(status=WorkLog.Status.SUBMITTED), "volume")

    @cached_property
    def reported_volume(self):
        """Всё, что внесено (принятое, на проверке и отклонённое)."""
        return _sum(self._logs(), "volume")

    @property
    def rejected_volume(self):
        return self.reported_volume - self.accepted_volume - self.pending_volume

    @property
    def done_volume(self):
        return self.accepted_volume

    @property
    def is_overdue(self):
        from datetime import date
        return bool(self.end_date and self.end_date < date.today() and self.status == self.Status.ACTIVE
                    and self.progress < 100)

    @property
    def delay_risk_days(self):
        """Простая оценка: сколько дней не хватит при текущем темпе (за последние 14 дней)."""
        from datetime import date, timedelta
        if self.status != self.Status.ACTIVE or not self.end_date or self.remaining_volume <= 0:
            return 0
        since = date.today() - timedelta(days=14)
        pace = _sum(self._logs().filter(date__gte=since).exclude(status=WorkLog.Status.REJECTED), "volume") / 14
        if pace <= 0:
            return None
        days_needed = int(self.remaining_volume / pace) + 1
        days_left = (self.end_date - date.today()).days
        return max(days_needed - days_left, 0)

    # --- материалы ---
    def material_plan_fact(self):
        """Норматив против фактического списания по каждому материалу."""
        from warehouse.models import StockMovement
        rows = []
        for norm in self.norms.select_related("material"):
            need = self.accepted_volume * norm.per_unit
            actual = _sum(StockMovement.objects.filter(contract=self, material=norm.material,
                                                       kind=StockMovement.Kind.OUT), "quantity")
            diff = actual - need
            rows.append({
                "material": norm.material, "per_unit": norm.per_unit, "need": need, "actual": actual,
                "diff": diff, "pct": int(diff * 100 / need) if need else 0,
                "remaining_need": self.remaining_volume * norm.per_unit,
            })
        return rows

    @property
    def remaining_volume(self):
        return max(self.volume - self.done_volume, ZERO)

    @property
    def progress(self):
        if not self.volume:
            return 0
        return min(int(self.done_volume * 100 / self.volume), 100)

    # --- деньги ---
    @property
    def total(self):
        """Сколько получим за весь объём."""
        return self.volume * self.price

    @property
    def earned(self):
        """Сколько заработано по выполненному объёму."""
        return self.done_volume * self.price

    def _payments(self, kind):
        return _sum(self.payments.filter(kind=kind), "amount")

    @cached_property
    def received(self):
        return self._payments(Payment.Kind.INCOME)

    @cached_property
    def paid_workers(self):
        return self._payments(Payment.Kind.WORKER)

    @cached_property
    def materials(self):
        return self._payments(Payment.Kind.MATERIAL)

    @cached_property
    def other_expenses(self):
        return self._payments(Payment.Kind.OTHER)

    @cached_property
    def labor_accrued(self):
        """Сколько начислено рабочим за сделанное (по их ставкам)."""
        return sum((a.earned for a in self.assignments.all()), ZERO)

    @property
    def workers_due(self):
        return self.labor_accrued - self.paid_workers

    @property
    def client_due(self):
        """Генподрядчик должен нам за сделанное."""
        return self.earned - self.received

    @property
    def profit(self):
        """Прибыль по сделанному: заработали − начислено рабочим − материалы − прочее."""
        return self.earned - self.labor_accrued - self.materials - self.other_expenses

    @property
    def cash(self):
        """Деньги на руках: получили − выплатили рабочим − материалы − прочее."""
        return self.received - self.paid_workers - self.materials - self.other_expenses


class Assignment(models.Model):
    class PayType(models.TextChoices):
        PER_UNIT = "unit", "За объём (за единицу)"
        PER_DAY = "day", "За день (подённо)"

    contract = models.ForeignKey(WorkContract, verbose_name="Договор", on_delete=models.CASCADE,
                                 related_name="assignments")
    employee = models.ForeignKey("staff.Employee", verbose_name="Рабочий", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="assignments")
    crew = models.ForeignKey(Crew, verbose_name="Бригада", null=True, blank=True,
                             on_delete=models.PROTECT, related_name="assignments")
    pay_type = models.CharField("Как платим", max_length=5, choices=PayType.choices, default=PayType.PER_UNIT)
    rate = models.DecimalField("Ставка", max_digits=14, decimal_places=2,
                               help_text="Сумма за единицу объёма или за один человеко-день")
    planned_volume = models.DecimalField("Объём на исполнителя", max_digits=12, decimal_places=2,
                                         null=True, blank=True)

    class Meta:
        verbose_name = "Исполнитель на объёме"
        verbose_name_plural = "Исполнители на объёмах"
        ordering = ["contract", "id"]

    def __str__(self):
        return f"{self.performer} · {self.contract.work_type} ({self.contract.construction_object})"

    @property
    def performer(self):
        return self.crew or self.employee

    @property
    def is_crew(self):
        return self.crew_id is not None

    def clean(self):
        if bool(self.employee_id) == bool(self.crew_id):
            raise ValidationError("Выберите либо рабочего, либо бригаду.")

    @cached_property
    def done_volume(self):
        return _sum(self.logs.filter(status=WorkLog.Status.ACCEPTED), "accepted_volume")

    @cached_property
    def days(self):
        return _sum(self.logs.exclude(status=WorkLog.Status.REJECTED), "people")

    @cached_property
    def earned(self):
        if self.pay_type == self.PayType.PER_DAY:
            return Decimal(self.days) * self.rate
        return self.done_volume * self.rate

    @cached_property
    def paid(self):
        return _sum(self.payments.all(), "amount")

    @property
    def due(self):
        return self.earned - self.paid


class WorkLog(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "На проверке"
        ACCEPTED = "accepted", "Принято"
        REJECTED = "rejected", "Отклонено"

    assignment = models.ForeignKey(Assignment, verbose_name="Кто работал", on_delete=models.CASCADE,
                                   related_name="logs")
    date = models.DateField("Дата")
    section = models.CharField("Секция", max_length=50, blank=True)
    floor = models.CharField("Этаж", max_length=50, blank=True)
    volume = models.DecimalField("Сделано (объём)", max_digits=12, decimal_places=2, default=0)
    people = models.PositiveSmallIntegerField("Человек вышло", default=1)
    note = models.CharField("Примечание", max_length=300, blank=True)
    photo = models.ImageField("Фото", upload_to="worklogs/%Y/%m/", blank=True)
    over_plan = models.BooleanField("Сверх плана (разрешено)", default=False)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    accepted_volume = models.DecimalField("Принятый объём", max_digits=12, decimal_places=2, default=0)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Проверил", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField("Проверено", null=True, blank=True)
    review_note = models.CharField("Комментарий проверяющего", max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Внёс", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "Выработка за день"
        verbose_name_plural = "Выработка по дням"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date}: {self.volume} {self.assignment.contract.unit}"

    @property
    def contract(self):
        return self.assignment.contract

    @property
    def rejected_part(self):
        return self.volume - self.accepted_volume if self.status != self.Status.SUBMITTED else ZERO

    @property
    def pay(self):
        a = self.assignment
        if a.pay_type == Assignment.PayType.PER_DAY:
            return ZERO if self.status == self.Status.REJECTED else a.rate * self.people
        return a.rate * self.accepted_volume if self.status == self.Status.ACCEPTED else ZERO

    def review(self, user, accepted, note=""):
        """Приёмка ПТО: можно принять всё, часть или ничего (ТЗ п. 6.4, 32.2)."""
        from django.utils import timezone
        if self.status != self.Status.SUBMITTED:
            raise ValidationError("Этот объём уже проверен.")
        accepted = Decimal(accepted)
        if accepted < 0 or accepted > self.volume:
            raise ValidationError("Принятый объём должен быть от 0 до внесённого.")
        self.accepted_volume = accepted
        self.status = self.Status.ACCEPTED if accepted > 0 else self.Status.REJECTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save()


class MaterialNorm(models.Model):
    """Норматив расхода материала на единицу вида работ (ТЗ п. 8.2)."""
    contract = models.ForeignKey(WorkContract, verbose_name="Объём работ", on_delete=models.CASCADE,
                                 related_name="norms")
    material = models.ForeignKey("warehouse.Material", verbose_name="Материал", on_delete=models.PROTECT)
    per_unit = models.DecimalField("Расход на 1 единицу работ", max_digits=12, decimal_places=4)

    class Meta:
        verbose_name = "Норматив материала"
        verbose_name_plural = "Нормативы материалов"
        unique_together = [("contract", "material")]

    def __str__(self):
        return f"{self.material}: {self.per_unit} на {self.contract.unit}"


class Payment(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Получили от генподрядчика"
        WORKER = "worker", "Выплата рабочим"
        MATERIAL = "material", "Материалы"
        OTHER = "other", "Прочий расход"

    contract = models.ForeignKey(WorkContract, verbose_name="Договор", on_delete=models.CASCADE,
                                 related_name="payments")
    kind = models.CharField("Что за платёж", max_length=10, choices=Kind.choices)
    assignment = models.ForeignKey(Assignment, verbose_name="Кому (рабочий или бригада)", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="payments")
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2)
    date = models.DateField("Дата")
    note = models.CharField("Примечание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Платёж по договору"
        verbose_name_plural = "Платежи по договорам"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.amount}"

    @property
    def is_income(self):
        return self.kind == self.Kind.INCOME

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Сумма должна быть больше нуля."})
        if self.kind == self.Kind.WORKER and not self.assignment_id:
            raise ValidationError({"assignment": "Укажите, кому выплата."})
        if self.assignment_id and self.contract_id and self.assignment.contract_id != self.contract_id:
            raise ValidationError({"assignment": "Этот исполнитель работает на другом договоре."})
        if self.kind != self.Kind.WORKER:
            self.assignment = None


def pending_logs():
    return WorkLog.objects.filter(status=WorkLog.Status.SUBMITTED).select_related(
        "assignment__contract__construction_object", "assignment__crew", "assignment__employee")


def summary(contracts):
    """Сводка для карточек на главной по списку договоров."""
    contracts = list(contracts)
    total = sum((c.total for c in contracts), ZERO)
    earned = sum((c.earned for c in contracts), ZERO)
    return {
        "count": len(contracts),
        "total": total,
        "earned": earned,
        "remaining": max(total - earned, ZERO),
        "progress": int(earned * 100 / total) if total else 0,
        "received": sum((c.received for c in contracts), ZERO),
        "client_due": sum((c.client_due for c in contracts), ZERO),
        "paid_workers": sum((c.paid_workers for c in contracts), ZERO),
        "workers_due": sum((c.workers_due for c in contracts), ZERO),
        "materials": sum((c.materials + c.other_expenses for c in contracts), ZERO),
        "profit": sum((c.profit for c in contracts), ZERO),
        "pending": sum((c.pending_volume * c.price for c in contracts), ZERO),
        "cash": sum((c.cash for c in contracts), ZERO),
    }
