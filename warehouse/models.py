from django.db import models


class Supplier(models.Model):
    name = models.CharField("Поставщик", max_length=200)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    address = models.CharField("Адрес", max_length=300, blank=True)

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Material(models.Model):
    name = models.CharField("Материал", max_length=200)
    unit = models.CharField("Ед. изм.", max_length=20, default="шт")
    price = models.DecimalField("Цена за единицу", max_digits=12, decimal_places=2, default=0)
    min_stock = models.DecimalField("Минимальный остаток", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def stock(self):
        incoming = self.movements.filter(kind=StockMovement.Kind.IN).aggregate(s=models.Sum("quantity"))["s"] or 0
        outgoing = self.movements.filter(kind=StockMovement.Kind.OUT).aggregate(s=models.Sum("quantity"))["s"] or 0
        return incoming - outgoing

    @property
    def is_low(self):
        return self.stock < self.min_stock

    @property
    def stock_value(self):
        return self.stock * self.price


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        IN = "in", "Приход"
        OUT = "out", "Расход"

    material = models.ForeignKey(Material, verbose_name="Материал", on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField("Тип", max_length=3, choices=Kind.choices)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=2)
    date = models.DateField("Дата")
    supplier = models.ForeignKey(
        Supplier, verbose_name="Поставщик", null=True, blank=True, on_delete=models.SET_NULL,
    )
    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект (для расхода)",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="material_movements",
    )
    contract = models.ForeignKey(
        "contracts.WorkContract", verbose_name="На какой вид работ (для расхода)",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="material_movements",
    )
    note = models.CharField("Примечание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Движение материала"
        verbose_name_plural = "Движения материалов"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.material} × {self.quantity}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Количество должно быть больше нуля."})
        if self.kind == self.Kind.OUT and self.material_id and self.quantity:
            available = self.material.stock
            if self.pk:
                old = StockMovement.objects.get(pk=self.pk)
                if old.kind == self.Kind.OUT:
                    available += old.quantity
            if self.quantity > available:
                raise ValidationError({"quantity": f"На складе только {available} {self.material.unit}. "
                                                   "Нельзя выдать больше, чем есть."})
        if self.contract_id and self.construction_object_id is None:
            self.construction_object = self.contract.construction_object
