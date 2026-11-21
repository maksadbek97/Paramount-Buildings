"""Раздел «Моя компания»: профиль и реквизиты, банковские счета, документы,
структура (отделы) и штатное расписание. Сотрудники — staff.Employee."""
from datetime import date, timedelta

from django.core.validators import RegexValidator
from django.db import models

EXPIRING_DAYS = 30


class Company(models.Model):
    """Профиль своей компании. В системе одна запись (Company.get())."""

    class Form(models.TextChoices):
        TOO = "too", "ТОО"
        IP = "ip", "ИП"
        AO = "ao", "АО"

    legal_form = models.CharField("Форма", max_length=4, choices=Form.choices, default=Form.TOO)
    name = models.CharField("Полное название", max_length=255)
    short_name = models.CharField("Краткое название", max_length=120, blank=True)
    bin = models.CharField("БИН", max_length=12, blank=True,
                           validators=[RegexValidator(r"^\d{12}$", "БИН — 12 цифр.")])
    registered_at = models.DateField("Дата регистрации", null=True, blank=True)
    activity = models.CharField("Основной вид деятельности (ОКЭД)", max_length=255, blank=True)
    kbe = models.CharField("КБе", max_length=2, blank=True)
    vat_payer = models.BooleanField("Плательщик НДС", default=False)
    vat_certificate = models.CharField("Свидетельство НДС", max_length=100, blank=True)
    director = models.ForeignKey("staff.Employee", verbose_name="Руководитель", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    accountant = models.ForeignKey("staff.Employee", verbose_name="Главный бухгалтер", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    legal_address = models.CharField("Юридический адрес", max_length=255, blank=True)
    actual_address = models.CharField("Фактический адрес", max_length=255, blank=True)
    phone = models.CharField("Телефон", max_length=50, blank=True)
    email = models.EmailField("Эл. почта", blank=True)
    website = models.CharField("Сайт", max_length=120, blank=True)
    description = models.TextField("О компании", blank=True)

    class Meta:
        verbose_name = "Профиль компании"
        verbose_name_plural = "Профиль компании"

    def __str__(self):
        return self.short_name or self.name

    @classmethod
    def get(cls):
        return cls.objects.select_related("director__position", "accountant").first() or cls.objects.create(
            name="Моя компания")


class BankAccount(models.Model):
    class Currency(models.TextChoices):
        KZT = "KZT", "KZT — тенге"
        USD = "USD", "USD — доллар"
        EUR = "EUR", "EUR — евро"
        RUB = "RUB", "RUB — рубль"

    bank = models.CharField("Банк", max_length=150)
    bik = models.CharField("БИК", max_length=11, blank=True)
    iban = models.CharField("Номер счёта (IBAN)", max_length=34,
                            validators=[RegexValidator(r"^KZ[0-9A-Z]{18}$", "Счёт: KZ и 18 знаков, без пробелов.")])
    currency = models.CharField("Валюта", max_length=3, choices=Currency.choices, default=Currency.KZT)
    is_main = models.BooleanField("Основной счёт", default=False)
    note = models.CharField("Назначение", max_length=150, blank=True,
                            help_text="Например: расчёты с поставщиками, зарплатный")

    class Meta:
        verbose_name = "Банковский счёт"
        verbose_name_plural = "Банковские счета"
        ordering = ["-is_main", "bank"]

    def __str__(self):
        return f"{self.bank} · {self.iban}"

    @property
    def iban_pretty(self):
        return " ".join(self.iban[i:i + 4] for i in range(0, len(self.iban), 4))


class Department(models.Model):
    name = models.CharField("Отдел", max_length=150)
    parent = models.ForeignKey("self", verbose_name="Входит в", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="children")
    head = models.ForeignKey("staff.Employee", verbose_name="Руководитель отдела", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="headed_departments")
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Отдел"
        verbose_name_plural = "Структура: отделы"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class StaffUnit(models.Model):
    """Строка штатного расписания: сколько единиц должности в отделе и какой оклад."""
    department = models.ForeignKey(Department, verbose_name="Отдел", on_delete=models.CASCADE, related_name="units")
    position = models.ForeignKey("staff.Position", verbose_name="Должность", on_delete=models.PROTECT)
    count = models.DecimalField("Штатных единиц", max_digits=5, decimal_places=1, default=1)
    salary = models.DecimalField("Оклад по штату, ₸", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Штатная единица"
        verbose_name_plural = "Штатное расписание"
        ordering = ["department__order", "department__name", "-salary"]
        unique_together = [("department", "position")]

    def __str__(self):
        return f"{self.department}: {self.position} × {self.count}"


class CompanyDocument(models.Model):
    class Kind(models.TextChoices):
        CHARTER = "charter", "Учредительные"
        DECISION = "decision", "Решения"
        ORDER = "order", "Приказы"
        CERTIFICATE = "certificate", "Справки"
        LICENSE = "license", "Лицензии и допуски"
        OTHER = "other", "Прочие"

    kind = models.CharField("Вид", max_length=12, choices=Kind.choices, default=Kind.ORDER)
    number = models.CharField("Номер", max_length=50, blank=True)
    date = models.DateField("Дата документа", default=date.today)
    title = models.CharField("Название", max_length=255)
    valid_until = models.DateField("Действует до", null=True, blank=True,
                                   help_text="Для справок и лицензий: система напомнит заранее")
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    file = models.FileField("Файл", upload_to="company/%Y/", blank=True)
    note = models.CharField("Примечание", max_length=255, blank=True)

    class Meta:
        verbose_name = "Документ компании"
        verbose_name_plural = "Документы компании"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.number} {self.title}".strip()

    @property
    def state(self):
        """('expired'|'expiring'|'valid'|'', подпись)."""
        if not self.valid_until:
            return "", "бессрочно"
        left = (self.valid_until - date.today()).days
        if left < 0:
            return "expired", "истёк"
        if left <= EXPIRING_DAYS:
            return "expiring", f"осталось {left} дн."
        return "valid", "действует"

    @classmethod
    def attention(cls):
        return cls.objects.filter(valid_until__isnull=False,
                                  valid_until__lte=date.today() + timedelta(days=EXPIRING_DAYS)).order_by("valid_until")
