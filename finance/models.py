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
