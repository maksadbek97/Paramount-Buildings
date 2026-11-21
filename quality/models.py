"""Обходы и замечания (ТЗ п. 11) и ежедневные отчёты прораба (ТЗ п. 7.2–7.3)."""
from datetime import date, timedelta

from django.conf import settings
from django.db import models, transaction


class Remark(models.Model):
    class Priority(models.IntegerChoices):
        LOW = 1, "Низкий"
        NORMAL = 2, "Обычный"
        HIGH = 3, "Высокий"
        CRITICAL = 4, "Критичный"

    class Status(models.TextChoices):
        OPEN = "open", "Открыто"
        IN_WORK = "in_work", "В работе"
        REVIEW = "review", "На проверке"
        RETURNED = "returned", "Возвращено на доработку"
        CLOSED = "closed", "Принято и закрыто"

    number = models.CharField("Номер", max_length=20, unique=True, editable=False)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект",
                                            on_delete=models.CASCADE, related_name="remarks")
    section = models.CharField("Секция", max_length=50, blank=True)
    floor = models.CharField("Этаж", max_length=50, blank=True)
    place = models.CharField("Место", max_length=200, blank=True, help_text="Например: кв. 45, лестничная клетка")
    description = models.TextField("Описание замечания")
    photo = models.ImageField("Фото", upload_to="remarks/%Y/%m/", blank=True)
    priority = models.IntegerField("Приоритет", choices=Priority.choices, default=Priority.NORMAL)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный (прораб)",
                                    on_delete=models.PROTECT, related_name="remarks_responsible")
    executor = models.ForeignKey("staff.Employee", verbose_name="Исполнитель", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="remarks_executor")
    deadline = models.DateField("Срок устранения")
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    fix_photo = models.ImageField("Фото выполнения", upload_to="remarks/%Y/%m/", blank=True)
    fix_comment = models.CharField("Что сделано", max_length=300, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Проверяющий", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    accepted_at = models.DateTimeField("Дата приёмки", null=True, blank=True)
    task = models.OneToOneField("staff.Task", verbose_name="Задача прорабу", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="remark")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Замечание"
        verbose_name_plural = "Замечания"
        ordering = ["-priority", "deadline"]
        permissions = [("review_remark", "Может принимать или возвращать замечания")]

    def __str__(self):
        return f"{self.number}: {self.description[:60]}"

    def save(self, *args, **kwargs):
        if not self.number:
            with transaction.atomic():
                year = date.today().year
                prefix = f"ЗМ-{year}-"
                last = Remark.objects.filter(number__startswith=prefix).order_by("-number").first()
                n = int(last.number.rsplit("-", 1)[1]) + 1 if last else 1
                self.number = f"{prefix}{n:05d}"
                super().save(*args, **kwargs)
                return
        super().save(*args, **kwargs)

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED

    @property
    def is_overdue(self):
        return not self.is_closed and self.deadline < date.today()

    @property
    def due_soon(self):
        return not self.is_closed and date.today() <= self.deadline <= date.today() + timedelta(days=2)

    @property
    def location(self):
        parts = [f"секция {self.section}" if self.section else "", f"этаж {self.floor}" if self.floor else "",
                 self.place]
        return ", ".join(p for p in parts if p)

    def repeats(self):
        """Повторные замечания: то же место на том же объекте (ТЗ п. 11.3)."""
        if not (self.place or self.floor):
            return []
        same = Remark.objects.filter(construction_object=self.construction_object, section=self.section,
                                     floor=self.floor).exclude(pk=self.pk)
        # Сравнение без учёта регистра в Python: SQLite не умеет это для кириллицы.
        return [r for r in same if r.place.strip().casefold() == self.place.strip().casefold()]

    # Какие действия доступны в каждом статусе: (новый статус, кнопка, нужно право проверяющего)
    ACTIONS = {
        "open": [("in_work", "Взять в работу", False)],
        "returned": [("in_work", "Взять в работу", False)],
        "in_work": [("review", "Выполнено — на проверку", False)],
        "review": [("closed", "Принять и закрыть", True), ("returned", "Вернуть на доработку", True)],
    }


class DailyReport(models.Model):
    class Weather(models.TextChoices):
        SUN = "sun", "Ясно"
        CLOUD = "cloud", "Облачно"
        RAIN = "rain", "Дождь"
        SNOW = "snow", "Снег"
        WIND = "wind", "Сильный ветер"
        FROST = "frost", "Мороз"

    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект",
                                            on_delete=models.CASCADE, related_name="daily_reports")
    date = models.DateField("Дата")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    weather = models.CharField("Погода", max_length=10, choices=Weather.choices, default=Weather.SUN)
    temperature = models.SmallIntegerField("Температура, °C", null=True, blank=True)
    workers_count = models.PositiveSmallIntegerField("Рабочих на объекте", default=0)
    crews = models.ManyToManyField("contracts.Crew", verbose_name="Бригады", blank=True)
    works = models.TextField("Какие работы выполнены и где", blank=True,
                             help_text="Объёмы из «Выработки» за этот день подтянутся сами")
    materials = models.TextField("Использованные материалы", blank=True)
    equipment = models.TextField("Техника", blank=True)
    problems = models.TextField("Проблемы", blank=True)
    plan_next = models.TextField("План на завтра", blank=True)
    photo = models.ImageField("Фото", upload_to="reports/%Y/%m/", blank=True)
    confirmed = models.BooleanField("Подтверждён прорабом", default=False)
    confirmed_at = models.DateTimeField("Подтверждён", null=True, blank=True)

    class Meta:
        verbose_name = "Ежедневный отчёт"
        verbose_name_plural = "Ежедневные отчёты"
        ordering = ["-date"]
        unique_together = [("construction_object", "date")]

    def __str__(self):
        return f"Отчёт {self.date:%d.%m.%Y} · {self.construction_object}"

    def worklogs(self):
        from contracts.models import WorkLog
        return WorkLog.objects.filter(assignment__contract__construction_object=self.construction_object,
                                      date=self.date).select_related("assignment__contract", "assignment__crew",
                                                                     "assignment__employee")

    def material_out(self):
        from warehouse.models import StockMovement
        return StockMovement.objects.filter(construction_object=self.construction_object, date=self.date,
                                            kind="out").select_related("material")
