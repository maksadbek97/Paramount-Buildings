from django.core.validators import RegexValidator
from django.db import models

KZ_CITIES = [
    "Астана", "Алматы", "Шымкент", "Караганда", "Актобе", "Атырау", "Актау", "Павлодар",
    "Усть-Каменогорск", "Семей", "Костанай", "Кызылорда", "Уральск", "Петропавловск", "Тараз",
    "Туркестан", "Талдыкорган", "Кокшетау", "Жезказган", "Экибастуз", "Конаев",
]
bin_validator = RegexValidator(r"^\d{12}$", "БИН/ИИН — 12 цифр.")


class Client(models.Model):
    name = models.CharField("Заказчик", max_length=200)
    bin = models.CharField("БИН/ИИН", max_length=12, blank=True, validators=[bin_validator])
    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    note = models.TextField("Примечание", blank=True)

    class Meta:
        verbose_name = "Заказчик"
        verbose_name_plural = "Заказчики"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ConstructionObject(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Планируется"
        PREPARING = "preparing", "Подготовка"
        IN_PROGRESS = "in_progress", "Активный"
        PAUSED = "paused", "Приостановлен"
        FINISHING = "finishing", "Завершение"
        ACCEPTANCE = "acceptance", "Приёмка"
        DONE = "done", "Завершён"
        ARCHIVE = "archive", "Архив"

    code = models.CharField("Код объекта", max_length=30, blank=True)
    name = models.CharField("Название объекта", max_length=200)
    city = models.CharField("Город", max_length=40, blank=True, choices=[(c, c) for c in KZ_CITIES])
    address = models.CharField("Адрес", max_length=300, blank=True)
    client = models.ForeignKey(
        Client, verbose_name="Заказчик", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="construction_objects",
    )
    general_contractor = models.ForeignKey(
        Client, verbose_name="Генподрядчик", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="gc_objects",
    )
    contract_number = models.CharField("Договор №", max_length=60, blank=True)
    contract_amount = models.DecimalField("Сумма договора, ₸", max_digits=16, decimal_places=2, default=0)
    budget = models.DecimalField("Бюджет (план расходов), ₸", max_digits=16, decimal_places=2, default=0)
    manager = models.ForeignKey(
        "staff.Employee", verbose_name="Руководитель проекта", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="managed_objects",
    )
    foreman = models.ForeignKey(
        "staff.Employee", verbose_name="Прораб", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="foreman_objects",
    )
    pto = models.ForeignKey(
        "staff.Employee", verbose_name="Инженер ПТО", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pto_objects",
    )
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField("Дата начала", null=True, blank=True)
    end_date = models.DateField("Плановое завершение", null=True, blank=True)
    description = models.TextField("Описание", blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} · {self.name}" if self.code else self.name

    @property
    def is_working(self):
        return self.status in (self.Status.PREPARING, self.Status.IN_PROGRESS, self.Status.FINISHING,
                               self.Status.ACCEPTANCE)


class ObjectDocument(models.Model):
    construction_object = models.ForeignKey(
        ConstructionObject, verbose_name="Объект", on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField("Название", max_length=200)
    file = models.FileField("Файл", upload_to="documents/%Y/%m/")
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title
