"""Раздел «Документы / Документооборот» (ТЗ, версия 1.0).

Один документ — одна запись: реестр, журналы, карточка объекта и архив показывают её же.
Кадровые (HR) процессы сюда не входят.
"""
from datetime import date, timedelta

from django.db import models, transaction
from django.utils import timezone

SOON_DAYS = 3  # «срок скоро» — за сколько дней подсвечивать


class Journal(models.Model):
    """Журнал регистрации с правилами нумерации (ТЗ п. 13). Номер выдаётся атомарно."""

    class Kind(models.TextChoices):
        INCOMING = "incoming", "Входящие"
        OUTGOING = "outgoing", "Исходящие"
        ORDER = "order", "Приказы"
        CONTRACT = "contract", "Договоры"
        INTERNAL = "internal", "Внутренние"
        CUSTOM = "custom", "Пользовательский"

    name = models.CharField("Название", max_length=150)
    kind = models.CharField("Вид", max_length=10, choices=Kind.choices, default=Kind.CUSTOM)
    prefix = models.CharField("Префикс", max_length=12, blank=True, help_text="Например: ВХ, ИСХ")
    suffix = models.CharField("Суффикс", max_length=12, blank=True, help_text="Например: ОД")
    separator = models.CharField("Разделитель", max_length=2, default="-")
    use_year = models.BooleanField("Год в номере", default=True)
    digits = models.PositiveSmallIntegerField("Цифр в номере", default=4)
    reset_yearly = models.BooleanField("Сбрасывать нумерацию каждый год", default=True)
    counter = models.PositiveIntegerField("Последний номер", default=0)
    counter_year = models.PositiveIntegerField("Год счётчика", default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Журнал регистрации"
        verbose_name_plural = "Журналы регистрации"
        ordering = ["pk"]

    def __str__(self):
        return self.name

    def format(self, n, year):
        parts = [self.prefix, str(year) if self.use_year else "", str(n).zfill(self.digits), self.suffix]
        return self.separator.join(p for p in parts if p)

    @property
    def example(self):
        return self.format(self.counter + 1, date.today().year)

    def next_number(self):
        """Следующий номер. Блокирует строку журнала, поэтому двух одинаковых номеров не бывает."""
        with transaction.atomic():
            j = Journal.objects.select_for_update().get(pk=self.pk)
            year = date.today().year
            if j.reset_yearly and j.counter_year != year:
                j.counter = 0
            j.counter += 1
            j.counter_year = year
            j.save(update_fields=["counter", "counter_year"])
            self.counter, self.counter_year = j.counter, j.counter_year
            return j.format(j.counter, year)


class CaseFile(models.Model):
    """Дело номенклатуры (ТЗ п. 12)."""

    class Status(models.TextChoices):
        OPEN = "open", "Открыто"
        CLOSED = "closed", "Закрыто"
        ARCHIVED = "archived", "Передано в архив"

    index = models.CharField("Индекс", max_length=20)
    title = models.CharField("Заголовок дела", max_length=255)
    department = models.ForeignKey("company.Department", verbose_name="Подразделение", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    doc_types = models.CharField("Типы документов", max_length=255, blank=True)
    year = models.PositiveIntegerField("Год", default=date.today().year)
    retention = models.CharField("Срок хранения", max_length=60, default="5 лет")
    retention_years = models.PositiveSmallIntegerField("Срок хранения, лет", default=5,
                                                       help_text="0 — постоянно")
    basis = models.CharField("Основание (статья перечня)", max_length=120, blank=True)
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    location = models.CharField("Место хранения", max_length=120, blank=True)

    class Meta:
        verbose_name = "Дело (номенклатура)"
        verbose_name_plural = "Номенклатура дел"
        ordering = ["index"]

    def __str__(self):
        return f"{self.index} {self.title}"


class Template(models.Model):
    """Шаблон документа или фирменный бланк (ТЗ п. 14, 35.1)."""

    class Category(models.TextChoices):
        LETTER = "letter", "Письма"
        ORDER = "order", "Приказы"
        CONTRACT = "contract", "Договоры"
        ACT = "act", "Акты"
        INTERNAL = "internal", "Внутренние"

    class SignRule(models.TextChoices):
        ASK = "ask", "Спрашивать каждый раз"
        SIGN = "sign", "Подпись обязательна"
        SEAL = "seal", "Печать обязательна"
        BOTH = "both", "Подпись и печать обязательны"
        NONE = "none", "Без подписи и печати"

    name = models.CharField("Название", max_length=150)
    code = models.CharField("Код", max_length=20)
    category = models.CharField("Категория", max_length=10, choices=Category.choices, default=Category.LETTER)
    is_letterhead = models.BooleanField("Фирменный бланк", default=False,
                                        help_text="Можно выбрать в генераторе писем")
    version = models.PositiveSmallIntegerField("Версия", default=1)
    author = models.ForeignKey("staff.Employee", verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    active_from = models.DateField("Действует с", default=date.today)
    access = models.CharField("Кому доступен", max_length=150, default="Все сотрудники")
    sign_rule = models.CharField("Подпись и печать", max_length=5, choices=SignRule.choices, default=SignRule.ASK)
    is_active = models.BooleanField("Активен", default=True)
    body = models.TextField("Текст шаблона", blank=True,
                            help_text="Переменные: {компания}, {адресат}, {объект}, {договор}, {дата}, {номер}")
    file = models.FileField("Файл бланка (DOCX или PDF)", upload_to="docflow/templates/", blank=True)

    class Meta:
        verbose_name = "Шаблон"
        verbose_name_plural = "Шаблоны"
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} · v{self.version}"


class Seal(models.Model):
    """Печать, штамп или утверждённое изображение подписи (ТЗ п. 16, 35.3)."""

    class Kind(models.TextChoices):
        SEAL = "seal", "Печать"
        STAMP = "stamp", "Штамп"
        SIGNATURE = "signature", "Образ подписи"

    name = models.CharField("Название", max_length=150)
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.SEAL)
    owner = models.ForeignKey("staff.Employee", verbose_name="Владелец / хранитель", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="+")
    location = models.CharField("Место хранения", max_length=150, blank=True)
    access = models.CharField("Кто может использовать", max_length=200, blank=True)
    is_active = models.BooleanField("Действует", default=True)
    issued_to = models.ForeignKey("staff.Employee", verbose_name="Сейчас выдана", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = "Печать / подпись"
        verbose_name_plural = "Печати и подписи"
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name


class Document(models.Model):
    class Kind(models.TextChoices):
        ORDER = "order", "Приказ"
        INCOMING = "incoming", "Входящее письмо"
        OUTGOING = "outgoing", "Исходящее письмо"
        INTERNAL = "internal", "Внутренний документ"
        CONTRACT = "contract", "Договор"
        ACT = "act", "Акт"
        OTHER = "other", "Прочий документ"

    class Direction(models.TextChoices):
        IN = "in", "Входящий"
        OUT = "out", "Исходящий"
        INTERNAL = "internal", "Внутренний"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        REGISTERING = "registering", "На регистрации"
        REGISTERED = "registered", "Зарегистрирован"
        APPROVAL = "approval", "На согласовании"
        REWORK = "rework", "На доработке"
        APPROVED = "approved", "Согласован"
        SIGNING = "signing", "На подписи"
        SIGNED = "signed", "Подписан"
        SENT = "sent", "Отправлен"
        RECEIVED = "received", "Получен"
        EXECUTION = "execution", "В исполнении"
        EXECUTED = "executed", "Исполнен"
        CLOSED = "closed", "Закрыт"
        ARCHIVED = "archived", "В архиве"
        CANCELLED = "cancelled", "Отменён"
        REJECTED = "rejected", "Отклонён"

    class Priority(models.TextChoices):
        LOW = "low", "Низкий"
        NORMAL = "normal", "Обычный"
        HIGH = "high", "Высокий"
        URGENT = "urgent", "Срочный"

    class Channel(models.TextChoices):
        EMAIL = "email", "Эл. почта"
        COURIER = "courier", "Курьер"
        POST = "post", "Почта"
        HAND = "hand", "Нарочно"
        EDO = "edo", "ЭДО"
        WHATSAPP = "whatsapp", "WhatsApp"

    class ContractType(models.TextChoices):
        CUSTOMER = "customer", "С заказчиком / генподрядчиком"
        SUPPLIER = "supplier", "С поставщиком"
        SUBCONTRACT = "subcontract", "Субподряд"
        RENT = "rent", "Аренда"
        SERVICES = "services", "Услуги"
        SUPPLY = "supply", "Поставка"
        OTHER = "other", "Прочие"

    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.OTHER)
    subtype = models.CharField("Вид / категория", max_length=100, blank=True,
                               help_text="Например: организационный, претензия, служебная записка")
    title = models.CharField("Название / тема", max_length=255)
    number = models.CharField("Рег. номер", max_length=40, blank=True)
    doc_date = models.DateField("Дата документа", default=date.today)
    reg_date = models.DateField("Дата регистрации", null=True, blank=True)
    direction = models.CharField("Направление", max_length=8, choices=Direction.choices, default=Direction.INTERNAL)
    counterparty = models.CharField("Контрагент", max_length=200, blank=True)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект", null=True,
                                            blank=True, on_delete=models.SET_NULL, related_name="docflow")
    contract = models.ForeignKey("self", verbose_name="Договор", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="contract_docs", limit_choices_to={"kind": "contract"})
    parent = models.ForeignKey("self", verbose_name="Создан на основании", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="children")
    related = models.ManyToManyField("self", verbose_name="Связанные документы", blank=True)
    department = models.ForeignKey("company.Department", verbose_name="Подразделение", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    author = models.ForeignKey("staff.Employee", verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    responsible = models.ForeignKey("staff.Employee", verbose_name="Ответственный", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    signer = models.ForeignKey("staff.Employee", verbose_name="Подписант", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.DRAFT)
    due_date = models.DateField("Срок исполнения / ответа", null=True, blank=True)
    priority = models.CharField("Приоритет", max_length=7, choices=Priority.choices, default=Priority.NORMAL)
    confidential = models.BooleanField("Конфиденциально", default=False)
    case = models.ForeignKey(CaseFile, verbose_name="Дело (номенклатура)", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="documents")
    journal = models.ForeignKey(Journal, verbose_name="Журнал регистрации", null=True, blank=True,
                                on_delete=models.PROTECT, related_name="documents")
    summary = models.TextField("Содержание", blank=True)
    keywords = models.CharField("Ключевые слова", max_length=255, blank=True)
    file = models.FileField("Основной файл", upload_to="docflow/%Y/", blank=True)
    template = models.ForeignKey(Template, verbose_name="Шаблон", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="documents")
    # Письма
    sender_number = models.CharField("Номер отправителя", max_length=50, blank=True)
    channel = models.CharField("Канал", max_length=9, choices=Channel.choices, blank=True)
    resolution = models.TextField("Резолюция руководителя", blank=True)
    sent_at = models.DateField("Дата отправки", null=True, blank=True)
    delivery_confirmed = models.BooleanField("Получение подтверждено", default=False)
    # Договоры
    contract_type = models.CharField("Тип договора", max_length=12, choices=ContractType.choices, blank=True)
    amount = models.DecimalField("Сумма", max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Валюта", max_length=3, default="KZT")
    vat = models.BooleanField("С НДС", default=True)
    paid = models.DecimalField("Оплачено", max_digits=15, decimal_places=2, default=0)
    valid_from = models.DateField("Действует с", null=True, blank=True)
    valid_until = models.DateField("Действует до", null=True, blank=True)
    guarantee_until = models.DateField("Гарантия до", null=True, blank=True)
    created_at = models.DateTimeField("Создан", default=timezone.now)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ["-doc_date", "-id"]
        permissions = [("sign_document", "Может подписывать документы"),
                       ("use_seal", "Может ставить печать"),
                       ("register_document", "Может регистрировать документы")]
        constraints = [models.UniqueConstraint(fields=["journal", "number"], name="docflow_unique_number",
                                               condition=~models.Q(number=""))]

    def __str__(self):
        return f"{self.number + ' ' if self.number else ''}{self.title}"

    @property
    def uid(self):
        return f"DOC-{self.pk:06d}"

    # --- статусы, сроки, этапы ---
    FINAL = {"executed", "closed", "archived", "cancelled", "rejected"}

    @property
    def is_final(self):
        return self.status in self.FINAL

    @property
    def is_locked(self):
        """Подписанный / зарегистрированный документ не редактируется обычным способом."""
        return self.status not in {"draft", "rework", "approval", "registering"}

    @property
    def tone(self):
        return {"draft": "gray", "registering": "warn", "registered": "blue", "approval": "warn", "rework": "bad",
                "approved": "blue", "signing": "violet", "signed": "ok", "sent": "blue", "received": "blue",
                "execution": "blue", "executed": "ok", "closed": "ok", "archived": "gray", "cancelled": "gray",
                "rejected": "bad"}.get(self.status, "gray")

    @property
    def days_left(self):
        if not self.due_date or self.is_final:
            return None
        return (self.due_date - date.today()).days

    @property
    def overdue(self):
        d = self.days_left
        return d is not None and d < 0

    @property
    def due_soon(self):
        d = self.days_left
        return d is not None and 0 <= d <= SOON_DAYS

    @property
    def contract_left(self):
        if self.kind != "contract" or not self.valid_until or self.status in {"archived", "cancelled", "closed"}:
            return None
        return (self.valid_until - date.today()).days

    @property
    def paid_pct(self):
        if not self.amount:
            return 0
        return min(100, int(self.paid * 100 / self.amount))

    @property
    def missing(self):
        """Чего не хватает до регистрации (ТЗ п. 27: обязательные поля)."""
        need = []
        if not self.file:
            need.append("файл")
        if self.kind == "incoming" and not self.counterparty:
            need.append("отправитель")
        if self.kind == "outgoing" and not self.counterparty:
            need.append("адресат")
        if self.kind == "contract" and (not self.counterparty or not self.amount):
            need.append("реквизиты договора")
        if not self.case_id and self.status not in {"draft", "cancelled"}:
            need.append("дело")
        return need

    STEPS = {
        "order": [("draft", "Черновик"), ("approval", "Согласование"), ("signing", "Подпись"),
                  ("registered", "Регистрация"), ("execution", "Исполнение"), ("executed", "Завершён"),
                  ("archived", "Архив")],
        "incoming": [("registering", "Получен"), ("registered", "Регистрация"), ("execution", "Резолюция и исполнение"),
                     ("executed", "Ответ / выполнено"), ("archived", "Архив")],
        "outgoing": [("draft", "Черновик"), ("approval", "Согласование"), ("signing", "Подпись"),
                     ("registered", "Регистрация"), ("sent", "Отправка"), ("closed", "Подтверждено"),
                     ("archived", "Архив")],
        "internal": [("draft", "Черновик"), ("approval", "Согласование"), ("registered", "Регистрация"),
                     ("execution", "Ознакомление / исполнение"), ("executed", "Исполнен"), ("archived", "Архив")],
        "contract": [("draft", "Черновик"), ("approval", "Согласование"), ("signing", "Подпись"),
                     ("execution", "Действует"), ("closed", "Обязательства выполнены"), ("archived", "Архив")],
    }
    ALIASES = {"rework": "approval", "approved": "signing", "signed": "registered", "received": "closed",
               "registering": "registered"}

    def steps(self):
        flow = self.STEPS.get(self.kind) or self.STEPS["internal"]
        keys = [k for k, _ in flow]
        cur = self.status
        if cur not in keys:
            cur = self.ALIASES.get(cur, cur)
            if self.kind == "contract" and self.status == "signed":
                cur = "execution"
            if self.kind == "incoming" and self.status == "closed":
                cur = "executed"
        idx = keys.index(cur) if cur in keys else -1
        if self.status in {"cancelled", "rejected"}:
            idx = -1
        return [{"key": k, "label": label, "state": "done" if i < idx else ("now" if i == idx else "next")}
                for i, (k, label) in enumerate(flow)]

    def actions(self):
        """Доступные действия: (код, подпись, вид кнопки, нужна причина)."""
        s, k = self.status, self.kind
        a = []
        if s in {"draft", "rework"}:
            if k == "incoming":
                a.append(("register", "Зарегистрировать", "primary", False))
            else:
                a.append(("to_approval", "Отправить на согласование", "primary", False))
        if s == "registering":
            a.append(("register", "Зарегистрировать", "primary", False))
        if s == "approval":
            a += [("approve", "Согласовать", "primary", False), ("return", "Вернуть на доработку", "ghost", True),
                  ("reject", "Отклонить", "danger", True)]
        if s in {"approved", "signing"}:
            a.append(("sign", "Подписать и зарегистрировать" if k != "contract" else "Подписать", "primary", False))
        if s in {"registered", "signed"}:
            if k == "outgoing":
                a.append(("send", "Отметить отправку", "primary", False))
            elif k == "contract":
                a.append(("execute", "Договор вступил в силу", "primary", False))
            else:
                a.append(("execute", "Передать в исполнение", "primary", False))
        if s == "sent":
            a.append(("confirm", "Получение подтверждено", "primary", False))
        if s == "execution":
            a.append(("done", "Закрыть договор" if k == "contract" else "Отметить исполненным", "primary", False))
        if s in {"executed", "closed", "signed"} or (s == "registered" and k == "act"):
            a.append(("archive", "Передать в архив", "ghost", False))
        if s not in self.FINAL:
            a.append(("cancel", "Отменить документ", "danger", True))
        return a


class DocumentFile(models.Model):
    """Файл и версия документа (ТЗ п. 23): оригинал, рабочая, подписанная, приложение."""

    class Role(models.TextChoices):
        ORIGINAL = "original", "Оригинал"
        WORKING = "working", "Рабочая версия"
        SIGNED = "signed", "Подписанная версия"
        SCAN = "scan", "Скан"
        ATTACHMENT = "attachment", "Приложение"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="files")
    file = models.FileField("Файл", upload_to="docflow/%Y/")
    name = models.CharField("Название", max_length=200)
    role = models.CharField("Вид", max_length=10, choices=Role.choices, default=Role.WORKING)
    version = models.PositiveSmallIntegerField("Версия", default=1)
    author = models.ForeignKey("staff.Employee", verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    comment = models.CharField("Комментарий", max_length=200, blank=True)
    size_kb = models.PositiveIntegerField("Размер, КБ", default=0)
    locked = models.BooleanField("Защищён от изменений", default=False)
    created_at = models.DateTimeField("Загружен", default=timezone.now)

    class Meta:
        verbose_name = "Файл документа"
        verbose_name_plural = "Файлы документов"
        ordering = ["-version", "-id"]

    @property
    def ext(self):
        return self.file.name.rsplit(".", 1)[-1].upper() if "." in self.file.name else ""


class Approval(models.Model):
    """Шаг маршрута согласования и подписи (ТЗ п. 15). Шаги с одним номером идут параллельно."""

    class Role(models.TextChoices):
        APPROVER = "approver", "Согласующий"
        SIGNER = "signer", "Подписант"
        OBSERVER = "observer", "Наблюдатель"

    class Decision(models.TextChoices):
        WAITING = "waiting", "Ожидает очереди"
        PENDING = "pending", "На рассмотрении"
        APPROVED = "approved", "Согласовано"
        SIGNED = "signed", "Подписано"
        RETURNED = "returned", "Возвращено на доработку"
        REJECTED = "rejected", "Отклонено"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="approvals")
    step = models.PositiveSmallIntegerField("Этап", default=1)
    role = models.CharField("Роль", max_length=8, choices=Role.choices, default=Role.APPROVER)
    employee = models.ForeignKey("staff.Employee", verbose_name="Сотрудник", on_delete=models.PROTECT,
                                 related_name="+")
    decision = models.CharField("Решение", max_length=8, choices=Decision.choices, default=Decision.WAITING)
    comment = models.CharField("Комментарий", max_length=300, blank=True)
    method = models.CharField("Способ подписи", max_length=60, blank=True,
                              help_text="ЭЦП (НУЦ РК) или собственноручно")
    decided_at = models.DateTimeField("Когда", null=True, blank=True)

    class Meta:
        verbose_name = "Шаг согласования"
        verbose_name_plural = "Согласование и подпись"
        ordering = ["step", "id"]


class Recipient(models.Model):
    """Адресат внутреннего документа со своим статусом ознакомления (ТЗ п. 10)."""

    class State(models.TextChoices):
        NEW = "new", "Не открыт"
        READ = "read", "Ознакомлен"
        DONE = "done", "Исполнил"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="recipients")
    employee = models.ForeignKey("staff.Employee", verbose_name="Сотрудник", on_delete=models.CASCADE,
                                 related_name="+")
    state = models.CharField("Статус", max_length=4, choices=State.choices, default=State.NEW)
    at = models.DateTimeField("Когда", null=True, blank=True)

    class Meta:
        ordering = ["id"]


class DocTask(models.Model):
    """Поручение (ТЗ п. 17). Может возникнуть из пункта приказа, резолюции или вручную."""

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        ACCEPTED = "accepted", "Принято"
        IN_WORK = "in_work", "В работе"
        REVIEW = "review", "На проверке"
        REWORK = "rework", "На доработке"
        DONE = "done", "Выполнено"
        CANCELLED = "cancelled", "Отменено"

    number = models.CharField("Номер", max_length=20, blank=True)
    title = models.CharField("Задача", max_length=255)
    description = models.TextField("Описание", blank=True)
    document = models.ForeignKey(Document, verbose_name="Документ-основание", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="tasks")
    assignee = models.ForeignKey("staff.Employee", verbose_name="Исполнитель", on_delete=models.PROTECT,
                                 related_name="+")
    co_assignees = models.CharField("Соисполнители", max_length=255, blank=True)
    author = models.ForeignKey("staff.Employee", verbose_name="Постановщик", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    controller = models.ForeignKey("staff.Employee", verbose_name="Контролёр", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    due = models.DateField("Срок")
    priority = models.CharField("Приоритет", max_length=7, choices=Document.Priority.choices,
                                default=Document.Priority.NORMAL)
    construction_object = models.ForeignKey("objects.ConstructionObject", verbose_name="Объект", null=True,
                                            blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField("Статус", max_length=9, choices=Status.choices, default=Status.NEW)
    postpone_reason = models.CharField("Причина переноса срока", max_length=255, blank=True)
    created_at = models.DateTimeField("Создано", default=timezone.now)
    done_at = models.DateField("Выполнено", null=True, blank=True)

    class Meta:
        verbose_name = "Поручение"
        verbose_name_plural = "Поручения"
        ordering = ["due", "id"]

    def __str__(self):
        return f"{self.number} {self.title}".strip()

    @property
    def open(self):
        return self.status not in {"done", "cancelled"}

    @property
    def days_left(self):
        return (self.due - date.today()).days if self.open else None

    @property
    def overdue(self):
        return self.open and self.due < date.today()

    NEXT = {"new": ("accepted", "Принять"), "accepted": ("in_work", "Взять в работу"),
            "in_work": ("review", "Сдать на проверку"), "rework": ("review", "Сдать повторно"),
            "review": ("done", "Принять работу")}


class ArchiveRecord(models.Model):
    """Документ в архиве (ТЗ п. 18)."""

    class Status(models.TextChoices):
        STORED = "stored", "На хранении"
        ISSUED = "issued", "Выдан"
        EXPERTISE = "expertise", "На экспертизе ценности"

    archive_id = models.CharField("Архивный номер", max_length=20)
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="archive")
    case = models.ForeignKey(CaseFile, verbose_name="Дело", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    archived_at = models.DateField("Дата передачи", default=date.today)
    keep_until = models.DateField("Хранить до", null=True, blank=True)
    location = models.CharField("Место", max_length=120, blank=True)
    archivist = models.ForeignKey("staff.Employee", verbose_name="Архивариус", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="+")
    status = models.CharField("Статус", max_length=9, choices=Status.choices, default=Status.STORED)
    issued_to = models.CharField("Кому выдан", max_length=150, blank=True)

    class Meta:
        verbose_name = "Архивная запись"
        verbose_name_plural = "Архив"
        ordering = ["-archived_at", "-id"]

    @property
    def keep_text(self):
        return f"до {self.keep_until:%Y}" if self.keep_until else "постоянно"


class SealUsage(models.Model):
    """Журнал выдачи и использования печатей и подписей (ТЗ п. 16, 35.8)."""

    class Action(models.TextChoices):
        USE = "use", "Проставлена на документ"
        ISSUE = "issue", "Выдана"
        RETURN = "return", "Возвращена"

    seal = models.ForeignKey(Seal, verbose_name="Печать / подпись", on_delete=models.CASCADE, related_name="usages")
    document = models.ForeignKey(Document, verbose_name="Документ", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="seal_usages")
    employee = models.ForeignKey("staff.Employee", verbose_name="Кто", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    action = models.CharField("Действие", max_length=6, choices=Action.choices, default=Action.USE)
    purpose = models.CharField("Цель", max_length=200, blank=True)
    at = models.DateTimeField("Когда", default=timezone.now)

    class Meta:
        verbose_name = "Использование печати"
        verbose_name_plural = "Журнал печатей"
        ordering = ["-at", "-id"]


class DocEvent(models.Model):
    """История и аудит документа (ТЗ п. 24). Записи не редактируются."""

    class Kind(models.TextChoices):
        CREATE = "create", "Создание"
        UPDATE = "update", "Изменение"
        REGISTER = "register", "Регистрация"
        APPROVE = "approve", "Согласование"
        RETURN = "return", "Возврат на доработку"
        REJECT = "reject", "Отклонение"
        SIGN = "sign", "Подпись"
        SEND = "send", "Отправка"
        RECEIVE = "receive", "Получение"
        ASSIGN = "assign", "Назначение исполнителя"
        DEADLINE = "deadline", "Изменение срока"
        COMMENT = "comment", "Комментарий"
        FILE = "file", "Файл"
        DOWNLOAD = "download", "Скачивание"
        SEAL = "seal", "Печать"
        ARCHIVE = "archive", "Архивирование"
        CANCEL = "cancel", "Отмена"
        STATUS = "status", "Смена статуса"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField("Действие", max_length=9, choices=Kind.choices)
    who = models.CharField("Кто", max_length=150, blank=True)
    text = models.CharField("Что", max_length=300)
    old = models.CharField("Было", max_length=200, blank=True)
    new = models.CharField("Стало", max_length=200, blank=True)
    reason = models.CharField("Причина", max_length=300, blank=True)
    at = models.DateTimeField("Когда", default=timezone.now)

    class Meta:
        verbose_name = "Событие документа"
        verbose_name_plural = "История документов"
        ordering = ["-at", "-id"]


def soon(days=7):
    return date.today() + timedelta(days=days)
