from django.db import models


class Estimate(models.Model):
    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект",
        on_delete=models.CASCADE, related_name="estimates",
    )
    title = models.CharField("Название сметы", max_length=200)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Смета"
        verbose_name_plural = "Сметы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.construction_object})"

    @property
    def total(self):
        return sum((item.total for item in self.items.all()), 0)


class EstimateItem(models.Model):
    estimate = models.ForeignKey(Estimate, verbose_name="Смета", on_delete=models.CASCADE, related_name="items")
    name = models.CharField("Наименование работ / материалов", max_length=250)
    unit = models.CharField("Ед. изм.", max_length=20, default="шт")
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField("Цена за единицу", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Позиция сметы"
        verbose_name_plural = "Позиции сметы"

    def __str__(self):
        return self.name

    @property
    def total(self):
        return self.quantity * self.unit_price


class Transaction(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Доход"
        EXPENSE = "expense", "Расход"

    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions",
    )
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices)
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2)
    date = models.DateField("Дата")
    category = models.CharField("Категория", max_length=100, blank=True)
    description = models.CharField("Описание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Финансовая операция"
        verbose_name_plural = "Финансовые операции"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} ({self.date})"


class PlanLine(models.Model):
    """Строка финплана «план / факт» (по шаблону компании «Фин план до 2026 года»).

    У каждого объекта четыре блока: поступления, оплата работ, материальные и накладные расходы.
    Общие долги компании — отдельный блок без объекта. Остаток = план − факт, итоги считаются сами.
    """

    class Section(models.TextChoices):
        INCOME = "income", "Поступления"
        LABOR = "labor", "Оплата работ"
        MATERIAL = "material", "Материальные расходы"
        OVERHEAD = "overhead", "Накладные расходы"
        DEBT = "debt", "Общий долг компании"

    EXPENSES = (Section.LABOR, Section.MATERIAL, Section.OVERHEAD)

    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект", null=True, blank=True,
        on_delete=models.CASCADE, related_name="plan_lines",
        help_text="Не указывается для общих долгов компании",
    )
    section = models.CharField("Блок", max_length=10, choices=Section.choices)
    name = models.CharField("Наименование / получатель", max_length=250, blank=True)
    plan_amount = models.DecimalField("План, ₸", max_digits=16, decimal_places=2, default=0)
    plan_date = models.DateField("Плановая дата", null=True, blank=True)
    fact_amount = models.DecimalField("Факт, ₸", max_digits=16, decimal_places=2, default=0,
                                      help_text="Сколько уже оплачено или получено")
    fact_date = models.DateField("Дата факта", null=True, blank=True)
    note = models.CharField("Статус / примечание", max_length=300, blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        verbose_name = "Строка финплана"
        verbose_name_plural = "Финплан: план и факт"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.get_section_display()}: {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.section == self.Section.DEBT:
            self.construction_object = None
        elif not self.construction_object_id:
            raise ValidationError({"construction_object": "Укажите объект."})
        for f in ("plan_amount", "fact_amount"):
            if getattr(self, f) is not None and getattr(self, f) < 0:
                raise ValidationError({f: "Сумма не может быть отрицательной."})

    @property
    def is_income(self):
        return self.section == self.Section.INCOME

    @property
    def left(self):
        return (self.plan_amount or 0) - (self.fact_amount or 0)

    @property
    def pct(self):
        if not self.plan_amount:
            return 100 if self.fact_amount else 0
        return min(int(self.fact_amount * 100 / self.plan_amount), 100)

    @property
    def is_done(self):
        return bool(self.fact_amount) and self.left <= 0

    @property
    def overdue(self):
        from datetime import date
        return bool(self.plan_date and self.plan_date < date.today() and self.left > 0)

    @property
    def state(self):
        """(код, подпись) для бейджа статуса."""
        if self.is_done:
            return "done", "Получено" if self.is_income else "Оплачено"
        if self.overdue:
            return "late", "Просрочено"
        if self.fact_amount:
            return "part", "Частично"
        return "wait", "Ожидается" if self.is_income else "К оплате"


class ObjectContract(models.Model):
    """Договор с заказчиком по объекту и доп. договоры (доп. соглашения) к нему."""

    class Kind(models.TextChoices):
        MAIN = "main", "Договор"
        EXTRA = "extra", "Доп. договор"

    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект",
                                            on_delete=models.CASCADE, related_name="fin_contracts")
    kind = models.CharField("Вид", max_length=10, choices=Kind.choices, default=Kind.MAIN)
    number = models.CharField("Номер", max_length=60, blank=True)
    date = models.DateField("Дата", null=True, blank=True)
    subject = models.CharField("Предмет / вид работ", max_length=250, blank=True)
    amount = models.DecimalField("Сумма, ₸", max_digits=16, decimal_places=2, default=0)
    note = models.CharField("Примечание", max_length=300, blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Договор по объекту"
        verbose_name_plural = "Договоры и доп. договоры по объектам"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.number or ''} {self.subject}".strip()


class WorkAct(models.Model):
    """АВР — акт выполненных работ: сколько работ сдали заказчику (основание для оплаты)."""

    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект", null=True,
                                            blank=True, on_delete=models.CASCADE, related_name="work_acts")
    work = models.CharField("Вид работ / договор", max_length=250, blank=True)
    amount = models.DecimalField("Сумма, ₸", max_digits=16, decimal_places=2, default=0)
    date = models.DateField("Дата", null=True, blank=True)
    note = models.CharField("Примечание", max_length=300, blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "АВР"
        verbose_name_plural = "АВР — акты выполненных работ"
        ordering = ["position", "id"]

    def __str__(self):
        return f"АВР {self.work} {self.amount}"
