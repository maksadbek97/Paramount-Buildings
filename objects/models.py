from django.conf import settings
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
        PLANNED = "planned", "Черновик"
        PREPARING = "preparing", "Подготовка"
        IN_PROGRESS = "in_progress", "Активный"
        PAUSED = "paused", "Приостановлен"
        FINISHING = "finishing", "Завершение"
        ACCEPTANCE = "acceptance", "Приёмка"
        DONE = "done", "Закрыт"
        ARCHIVE = "archive", "Архив"

    class Kind(models.TextChoices):
        RESIDENTIAL = "residential", "Жилой дом"
        COMMERCIAL = "commercial", "Коммерческий объект"
        SOCIAL = "social", "Социальный объект"
        INDUSTRIAL = "industrial", "Промышленный / склад"
        INFRA = "infra", "Инфраструктура"
        OTHER = "other", "Другое"

    code = models.CharField("Код объекта", max_length=30, blank=True)
    name = models.CharField("Название объекта", max_length=200)
    kind = models.CharField("Тип объекта", max_length=20, choices=Kind.choices, blank=True)
    coordinates = models.CharField("Координаты", max_length=60, blank=True,
                                   help_text="Широта, долгота — например: 51.1282, 71.4304")
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
    responsible = models.ForeignKey(
        "staff.Employee", verbose_name="Ответственный менеджер", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="responsible_objects",
    )
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PREPARING)
    status_before_pause = models.CharField("Статус до приостановки", max_length=20, blank=True, editable=False)
    start_date = models.DateField("Дата начала", null=True, blank=True)
    end_date = models.DateField("Плановое завершение", null=True, blank=True)
    description = models.TextField("Описание", blank=True)
    photo = models.ImageField("Фото объекта", upload_to="objects/", blank=True,
                              help_text="Фото или визуализация. Если не загрузить — будет картинка по умолчанию.")
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"
        ordering = ["-created_at"]
        permissions = [("close_object", "Может закрывать и архивировать объекты")]

    def __str__(self):
        return f"{self.code} · {self.name}" if self.code else self.name

    @property
    def is_paused(self):
        return self.status == self.Status.PAUSED

    @property
    def days_left(self):
        """Сколько дней до плановой даты завершения (отрицательное — просрочено)."""
        from datetime import date
        if not self.end_date or self.is_closed:
            return None
        return (self.end_date - date.today()).days

    @property
    def cover(self):
        """Картинка для плитки: своё фото или красивая заглушка."""
        from django.templatetags.static import static
        if self.photo:
            return self.photo.url
        name = self.name.lower()
        if "склад" in name or "завод" in name or "цех" in name:
            n = 4
        elif "школ" in name or "сад" in name or "больниц" in name:
            n = 3
        elif "центр" in name or "офис" in name or "бц" in name:
            n = 2
        else:
            n = 1
        return static(f"img/objects/{n}.svg")

    @property
    def is_closed(self):
        return self.status in (self.Status.DONE, self.Status.ARCHIVE)

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


def _next(model, prefix):
    from warehouse.models import next_number
    return next_number(model, prefix)


class TransportRequest(models.Model):
    """Заявка на транспорт или технику для объекта."""

    class Kind(models.TextChoices):
        DUMP = "dump", "Самосвал"
        CRANE = "crane", "Автокран"
        EXCAVATOR = "excavator", "Экскаватор"
        PUMP = "pump", "Бетононасос"
        MANIPULATOR = "manipulator", "Манипулятор"
        LOADER = "loader", "Погрузчик"
        CAR = "car", "Легковой / доставка людей"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        APPROVED = "approved", "Согласована"
        ASSIGNED = "assigned", "Назначена"
        IN_WORK = "in_work", "В работе"
        DONE = "done", "Завершена"
        CANCELLED = "cancelled", "Отменена"

    OPEN = ("new", "approved", "assigned", "in_work")

    number = models.CharField("Номер", max_length=20, unique=True, editable=False)
    construction_object = models.ForeignKey(ConstructionObject, verbose_name="Объект", on_delete=models.CASCADE,
                                            related_name="transport")
    kind = models.CharField("Тип транспорта / техники", max_length=12, choices=Kind.choices)
    task = models.CharField("Задача", max_length=200, help_text="Например: вывоз грунта, подача газоблока на 5 этаж")
    route = models.CharField("Маршрут", max_length=200, blank=True)
    date = models.DateField("Дата подачи")
    time = models.TimeField("Время подачи", null=True, blank=True)
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    driver = models.CharField("Водитель / машинист", max_length=120, blank=True)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.NEW)
    mileage = models.DecimalField("Пробег, км", max_digits=10, decimal_places=1, null=True, blank=True)
    hours = models.DecimalField("Моточасы", max_digits=8, decimal_places=1, null=True, blank=True)
    cost = models.DecimalField("Стоимость (аренда, топливо), ₸", max_digits=14, decimal_places=2, default=0)
    note = models.CharField("Примечание", max_length=300, blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка на транспорт"
        verbose_name_plural = "Транспорт и техника"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number}: {self.get_kind_display()} — {self.task}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = _next(TransportRequest, "ТР")
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN


class SafetyRecord(models.Model):
    """Охрана труда: инструктажи, допуски и удостоверения, происшествия."""

    class Kind(models.TextChoices):
        BRIEFING = "briefing", "Инструктаж"
        PERMIT = "permit", "Допуск / удостоверение"
        INCIDENT = "incident", "Происшествие"

    construction_object = models.ForeignKey(ConstructionObject, verbose_name="Объект", on_delete=models.CASCADE,
                                            related_name="safety")
    kind = models.CharField("Что", max_length=10, choices=Kind.choices, default=Kind.BRIEFING)
    title = models.CharField("Название", max_length=200,
                             help_text="Например: повторный инструктаж, допуск к работам на высоте, падение инструмента")
    date = models.DateField("Дата")
    participants = models.TextField("Участники", blank=True, help_text="Кто прошёл инструктаж или кого касается")
    instructor = models.ForeignKey("staff.Employee", verbose_name="Инструктирующий / ответственный", null=True,
                                   blank=True, on_delete=models.SET_NULL, related_name="+")
    valid_until = models.DateField("Действует до", null=True, blank=True, help_text="Для допусков и удостоверений")
    measures = models.TextField("Меры устранения", blank=True, help_text="Для происшествий")
    confirmed = models.BooleanField("Прохождение подтверждено / закрыто", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Запись по охране труда"
        verbose_name_plural = "Охрана труда"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    @property
    def expired(self):
        from datetime import date
        return bool(self.valid_until and self.valid_until < date.today())

    @property
    def expiring(self):
        from datetime import date
        return bool(self.valid_until and not self.expired and (self.valid_until - date.today()).days <= 14)

    @property
    def is_open(self):
        """Требует действия: незакрытое происшествие, неподтверждённый инструктаж, просроченный допуск."""
        return (not self.confirmed and self.kind != self.Kind.PERMIT) or self.expired


class ObjectMedia(models.Model):
    """Фото и видео с объекта."""

    class Category(models.TextChoices):
        PROGRESS = "progress", "Ход работ"
        BEFORE_AFTER = "before_after", "До / после"
        DEFECT = "defect", "Дефект"
        DELIVERY = "delivery", "Поставка"
        SAFETY = "safety", "Безопасность"
        OTHER = "other", "Прочее"

    construction_object = models.ForeignKey(ConstructionObject, verbose_name="Объект", on_delete=models.CASCADE,
                                            related_name="media")
    file = models.FileField("Фото или видео", upload_to="media/%Y/%m/",
                            help_text="JPG, PNG, HEIC или MP4, до 50 МБ")
    category = models.CharField("Категория", max_length=12, choices=Category.choices, default=Category.PROGRESS)
    caption = models.CharField("Описание", max_length=300, blank=True)
    stage = models.CharField("Этап / место", max_length=120, blank=True, help_text="Например: секция 2, 5 этаж")
    date = models.DateField("Дата съёмки")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", editable=False)
    created_at = models.DateTimeField("Загружено", auto_now_add=True)

    class Meta:
        verbose_name = "Фото / видео"
        verbose_name_plural = "Фото и видео"
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.caption or f"Фото {self.date:%d.%m.%Y}"

    @property
    def is_video(self):
        return self.file.name.lower().rsplit(".", 1)[-1] in ("mp4", "mov", "webm")
