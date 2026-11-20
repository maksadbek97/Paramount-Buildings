from django.db import models


class Client(models.Model):
    name = models.CharField("Заказчик", max_length=200)
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
        IN_PROGRESS = "in_progress", "В работе"
        PAUSED = "paused", "Приостановлен"
        DONE = "done", "Завершён"

    name = models.CharField("Название объекта", max_length=200)
    address = models.CharField("Адрес", max_length=300, blank=True)
    client = models.ForeignKey(
        Client, verbose_name="Заказчик", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="construction_objects",
    )
    manager = models.ForeignKey(
        "staff.Employee", verbose_name="Ответственный", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="managed_objects",
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
        return self.name


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
