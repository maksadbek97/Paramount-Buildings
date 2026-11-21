"""Склады и материалы (ТЗ п. 8–10, 30.1).

Остаток считается по движениям: приход, расход в работу, перемещение, возврат, списание, корректировка.
Перемещение уменьшает склад-отправитель сразу, а склад-получатель увеличивает только после приёмки.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum

ZERO = Decimal("0")


def next_number(model, prefix):
    year = date.today().year
    start = f"{prefix}-{year}-"
    last = model.objects.filter(number__startswith=start).order_by("-number").first()
    n = int(last.number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{start}{n:05d}"


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


class Warehouse(models.Model):
    class Kind(models.TextChoices):
        CENTRAL = "central", "Центральный склад"
        OBJECT = "object", "Склад объекта"
        TEMP = "temp", "Временный склад"
        EQUIPMENT = "equipment", "Склад техники"
        TOOLS = "tools", "Склад инструментов"

    name = models.CharField("Название", max_length=120)
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.CENTRAL)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект", null=True,
                                            blank=True, on_delete=models.SET_NULL, related_name="warehouses")
    keeper = models.ForeignKey("staff.Employee", verbose_name="Кладовщик / ответственный", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="warehouses")

    class Meta:
        verbose_name = "Склад"
        verbose_name_plural = "Склады"
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name

    def balances(self):
        """Остатки по всем материалам этого склада (карточка складского остатка, п. 9.3)."""
        rows = []
        for m in Material.objects.filter(Q(movements__warehouse=self) | Q(movements__to_warehouse=self)).distinct():
            card = m.card(self)
            if any(card[k] for k in ("in", "out", "transfer_in", "transfer_out", "pending")):
                rows.append({"material": m, **card})
        return rows

    @property
    def value(self):
        return sum((r["balance"] * r["material"].price for r in self.balances()), ZERO)

    def pending_transfers(self):
        return self.incoming.filter(kind=StockMovement.Kind.TRANSFER, received=False).select_related(
            "material", "warehouse")


class Material(models.Model):
    code = models.CharField("Код", max_length=30, blank=True)
    name = models.CharField("Материал", max_length=200)
    category = models.CharField("Категория", max_length=80, blank=True)
    brand = models.CharField("Бренд / марка", max_length=80, blank=True)
    unit = models.CharField("Ед. изм.", max_length=20, default="шт")
    price = models.DecimalField("Цена за единицу", max_digits=12, decimal_places=2, default=0)
    min_stock = models.DecimalField("Минимальный остаток", max_digits=12, decimal_places=2, default=0)
    max_stock = models.DecimalField("Максимальный остаток", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def _sum(self, **filters):
        return self.movements.filter(**filters).aggregate(s=Sum("quantity"))["s"] or ZERO

    def card(self, warehouse):
        K = StockMovement.Kind
        w = {"warehouse": warehouse}
        incoming = self._sum(kind=K.IN, **w)
        returned = self._sum(kind=K.RETURN, **w)
        out = self._sum(kind=K.OUT, **w)
        writeoff = self._sum(kind=K.WRITEOFF, **w)
        adj = self._sum(kind=K.ADJUST_PLUS, **w) - self._sum(kind=K.ADJUST_MINUS, **w)
        t_out = self._sum(kind=K.TRANSFER, **w)
        t_in = self.movements.filter(kind=K.TRANSFER, to_warehouse=warehouse, received=True).aggregate(
            s=Sum("quantity"))["s"] or ZERO
        pending = self.movements.filter(kind=K.TRANSFER, to_warehouse=warehouse, received=False).aggregate(
            s=Sum("quantity"))["s"] or ZERO
        balance = incoming + returned + t_in + adj - out - writeoff - t_out
        return {"in": incoming, "return": returned, "out": out, "writeoff": writeoff, "adjust": adj,
                "transfer_in": t_in, "transfer_out": t_out, "pending": pending, "balance": balance,
                "value": balance * self.price}

    def balance(self, warehouse):
        return self.card(warehouse)["balance"]

    @property
    def in_transit(self):
        return self._sum(kind=StockMovement.Kind.TRANSFER, received=False)

    @property
    def stock(self):
        """Всего у компании: на всех складах плюс в пути."""
        K = StockMovement.Kind
        plus = self._sum(kind__in=[K.IN, K.RETURN, K.ADJUST_PLUS])
        minus = self._sum(kind__in=[K.OUT, K.WRITEOFF, K.ADJUST_MINUS])
        return plus - minus

    @property
    def is_low(self):
        return self.stock < self.min_stock

    @property
    def stock_value(self):
        return self.stock * self.price

    def last_price(self, supplier=None):
        qs = self.movements.filter(kind=StockMovement.Kind.IN, price__isnull=False)
        if supplier is not None:
            qs = qs.filter(supplier=supplier)
        last = qs.order_by("-date", "-id").first()
        return last.price if last else None


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        IN = "in", "Приход"
        OUT = "out", "Расход в работу"
        TRANSFER = "transfer", "Перемещение"
        RETURN = "return", "Возврат"
        WRITEOFF = "writeoff", "Списание (потери, брак)"
        ADJUST_PLUS = "adj_plus", "Корректировка +"
        ADJUST_MINUS = "adj_minus", "Корректировка −"

    DECREASE = {"out", "transfer", "writeoff", "adj_minus"}

    material = models.ForeignKey(Material, verbose_name="Материал", on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField("Операция", max_length=10, choices=Kind.choices)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=2)
    date = models.DateField("Дата")
    warehouse = models.ForeignKey(Warehouse, verbose_name="Склад", null=True, on_delete=models.PROTECT,
                                  related_name="movements")
    to_warehouse = models.ForeignKey(Warehouse, verbose_name="На склад (для перемещения)", null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="incoming")
    received = models.BooleanField("Принято получателем", default=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Принял", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    received_at = models.DateTimeField("Когда принято", null=True, blank=True)
    supplier = models.ForeignKey(
        Supplier, verbose_name="Поставщик", null=True, blank=True, on_delete=models.SET_NULL,
    )
    price = models.DecimalField("Цена закупки за единицу", max_digits=12, decimal_places=2, null=True, blank=True)
    construction_object = models.ForeignKey(
        "objects.ConstructionObject", verbose_name="Объект (для расхода)",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="material_movements",
    )
    contract = models.ForeignKey(
        "contracts.WorkContract", verbose_name="На какой вид работ (для расхода)",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="material_movements",
    )
    request = models.ForeignKey("PurchaseRequest", verbose_name="По заявке", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="movements")
    note = models.CharField("Примечание / причина", max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Провёл", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "Движение материала"
        verbose_name_plural = "Движения материалов"
        ordering = ["-date", "-id"]
        permissions = [("approve_inventory", "Может утверждать инвентаризацию")]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.material} × {self.quantity}"

    @property
    def is_increase(self):
        return self.kind not in self.DECREASE

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Количество должно быть больше нуля."})
        if self.kind == self.Kind.TRANSFER:
            if not self.to_warehouse_id:
                raise ValidationError({"to_warehouse": "Укажите, на какой склад перемещаем."})
            if self.to_warehouse_id == self.warehouse_id:
                raise ValidationError({"to_warehouse": "Склад отправителя и получателя совпадают."})
        if self.kind in (self.Kind.WRITEOFF, self.Kind.ADJUST_MINUS, self.Kind.ADJUST_PLUS) and not self.note:
            raise ValidationError({"note": "Укажите причину списания или корректировки."})
        if self.kind in self.DECREASE and self.material_id and self.warehouse_id and self.quantity:
            available = self.material.balance(self.warehouse)
            if self.pk:
                old = StockMovement.objects.get(pk=self.pk)
                if old.kind in self.DECREASE and old.warehouse_id == self.warehouse_id:
                    available += old.quantity
            if self.quantity > available:
                raise ValidationError({"quantity": f"На складе «{self.warehouse}» только "
                                                   f"{available.normalize():f} {self.material.unit}. "
                                                   "Нельзя выдать больше, чем есть."})
        if self.contract_id and self.construction_object_id is None:
            self.construction_object = self.contract.construction_object
        if self.construction_object_id is None and self.warehouse_id and self.warehouse.construction_object_id:
            self.construction_object = self.warehouse.construction_object

    def save(self, *args, **kwargs):
        if self.kind == self.Kind.TRANSFER and self._state.adding:
            # Получатель должен подтвердить приёмку (ТЗ: «материал без приёмки не включается в приход»).
            self.received = False
        super().save(*args, **kwargs)

    def accept(self, user):
        from django.utils import timezone
        if self.kind != self.Kind.TRANSFER or self.received:
            raise ValidationError("Это перемещение уже принято.")
        self.received, self.received_by, self.received_at = True, user, timezone.now()
        self.save(update_fields=["received", "received_by", "received_at"])


class Inventory(models.Model):
    """Инвентаризация (п. 9.4): учётный остаток → фактический → разница → акт → утверждение → корректировка."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        APPROVED = "approved", "Утверждена"

    number = models.CharField("Номер акта", max_length=20, unique=True, editable=False)
    warehouse = models.ForeignKey(Warehouse, verbose_name="Склад", on_delete=models.PROTECT,
                                  related_name="inventories")
    date = models.DateField("Дата", default=date.today)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.DRAFT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Провёл", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Утвердил", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    note = models.CharField("Примечание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Инвентаризация"
        verbose_name_plural = "Инвентаризации"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} · {self.warehouse}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Inventory, "ИНВ")
        super().save(*args, **kwargs)

    @transaction.atomic
    def approve(self, user):
        if self.status == self.Status.APPROVED:
            raise ValidationError("Инвентаризация уже утверждена.")
        for line in self.lines.select_related("material"):
            diff = line.difference
            if diff:
                StockMovement.objects.create(
                    material=line.material, warehouse=self.warehouse, date=self.date, quantity=abs(diff),
                    kind=StockMovement.Kind.ADJUST_PLUS if diff > 0 else StockMovement.Kind.ADJUST_MINUS,
                    note=f"Инвентаризация {self.number}", created_by=user)
        self.status, self.approved_by = self.Status.APPROVED, user
        self.save(update_fields=["status", "approved_by"])


class InventoryLine(models.Model):
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, verbose_name="Материал", on_delete=models.PROTECT)
    book_qty = models.DecimalField("По учёту", max_digits=12, decimal_places=2)
    actual_qty = models.DecimalField("Фактически", max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [("inventory", "material")]

    @property
    def difference(self):
        return self.actual_qty - self.book_qty


class PurchaseRequest(models.Model):
    """Заявка на материал и закупка (п. 8.3, 10): заявка → согласование → заказ → приёмка."""

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        APPROVED = "approved", "Согласована"
        ORDERED = "ordered", "Заказана"
        RECEIVED = "received", "Принята на склад"
        REJECTED = "rejected", "Отклонена"

    FLOW = {"new": ("approved", "Согласовать"), "approved": ("ordered", "Заказать у поставщика")}
    OPEN = ("new", "approved", "ordered")

    number = models.CharField("Номер", max_length=20, unique=True, editable=False)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект",
                                            on_delete=models.CASCADE, related_name="purchase_requests")
    warehouse = models.ForeignKey(Warehouse, verbose_name="На какой склад", on_delete=models.PROTECT,
                                  related_name="requests")
    material = models.ForeignKey(Material, verbose_name="Материал", on_delete=models.PROTECT,
                                 related_name="requests")
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=2)
    needed_by = models.DateField("Нужно к дате", null=True, blank=True)
    supplier = models.ForeignKey(Supplier, verbose_name="Поставщик", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="requests")
    price = models.DecimalField("Цена за единицу", max_digits=12, decimal_places=2, null=True, blank=True)
    payment_terms = models.CharField("Условия оплаты", max_length=120, blank=True)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.NEW)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    note = models.CharField("Примечание", max_length=300, blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка на материал"
        verbose_name_plural = "Заявки и закупки"
        ordering = ["-created_at"]
        permissions = [("approve_purchase", "Может согласовывать заявки на материалы")]

    def __str__(self):
        return f"{self.number}: {self.material} × {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(PurchaseRequest, "ЗМТ")
        super().save(*args, **kwargs)

    @property
    def amount(self):
        return (self.price or ZERO) * self.quantity

    @property
    def is_late(self):
        return bool(self.needed_by and self.needed_by < date.today() and self.status in self.OPEN)

    def analysis(self):
        """Проверка заявки (п. 8.3): норма, остатки на объекте и других складах, уже заказано."""
        from contracts.models import WorkContract
        need = ZERO
        for c in WorkContract.objects.filter(construction_object=self.construction_object).exclude(
                status=WorkContract.Status.DONE):
            for row in c.material_plan_fact():
                if row["material"].pk == self.material_id:
                    need += row["remaining_need"]
        on_object = sum((self.material.balance(w) for w in Warehouse.objects.filter(
            construction_object=self.construction_object)), ZERO)
        if self.warehouse.construction_object_id != self.construction_object_id:
            on_object += self.material.balance(self.warehouse)
        elsewhere = sum((self.material.balance(w) for w in Warehouse.objects.exclude(
            construction_object=self.construction_object).exclude(pk=self.warehouse_id)), ZERO)
        ordered = PurchaseRequest.objects.filter(
            construction_object=self.construction_object, material=self.material, status__in=self.OPEN
        ).exclude(pk=self.pk).aggregate(s=Sum("quantity"))["s"] or ZERO
        to_buy = max(need - on_object - ordered, ZERO) if need else None
        warnings = []
        if need and self.quantity > max(need - on_object - ordered, ZERO) * Decimal("1.1"):
            warnings.append(f"Заявка больше, чем нужно по нормам: к закупке достаточно "
                            f"{to_buy.normalize():f} {self.material.unit}.")
        if elsewhere > 0:
            warnings.append(f"На других складах есть {elsewhere.normalize():f} {self.material.unit} — "
                            "можно переместить вместо закупки.")
        last = self.material.last_price(self.supplier) if self.supplier_id else self.material.last_price()
        if self.price and last and self.price > last * Decimal("1.1"):
            warnings.append(f"Цена выше прошлой закупки на {int((self.price / last - 1) * 100)}% "
                            f"(было {last.normalize():f} ₸).")
        return {"need": need, "on_object": on_object, "elsewhere": elsewhere, "ordered": ordered,
                "to_buy": to_buy, "last_price": last, "warnings": warnings}

    @transaction.atomic
    def receive(self, user, quantity=None):
        """Приёмка поставки кладовщиком: создаёт приход один раз (нельзя провести дважды)."""
        if self.status != self.Status.ORDERED:
            raise ValidationError("Принять можно только заказанную заявку, и только один раз.")
        StockMovement.objects.create(
            material=self.material, warehouse=self.warehouse, kind=StockMovement.Kind.IN, date=date.today(),
            quantity=quantity or self.quantity, supplier=self.supplier, price=self.price, request=self,
            note=f"Поставка по заявке {self.number}", created_by=user)
        if self.price:
            Material.objects.filter(pk=self.material_id).update(price=self.price)
        self.status = self.Status.RECEIVED
        self.save(update_fields=["status"])
