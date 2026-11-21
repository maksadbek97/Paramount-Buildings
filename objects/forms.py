"""Формы раздела «Объекты»: создание и редактирование карточки, транспорт, охрана труда, фото."""
import re
from datetime import date

from django import forms

from core.forms import StyledMixin

from .models import Client, ConstructionObject, ObjectMedia, SafetyRecord, TransportRequest

CITY_PREFIX = {
    "Астана": "AST", "Алматы": "ALA", "Шымкент": "SHM", "Караганда": "KRG", "Актобе": "AKT", "Атырау": "ATR",
    "Актау": "AKU", "Павлодар": "PVL", "Усть-Каменогорск": "UKG", "Семей": "SEM", "Костанай": "KST",
    "Кызылорда": "KZO", "Уральск": "URA", "Петропавловск": "PPK", "Тараз": "TRZ", "Туркестан": "TRK",
    "Талдыкорган": "TDK", "Кокшетау": "KOK", "Жезказган": "ZHZ", "Экибастуз": "EKB", "Конаев": "KON",
}
CODE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-/._]{1,29}$")


def next_code(city):
    """Следующий свободный код объекта: AST-01, AST-02… (префикс по городу, OBJ — если город не указан)."""
    prefix = CITY_PREFIX.get(city or "", "OBJ")
    used = set(ConstructionObject.objects.filter(code__istartswith=prefix + "-").values_list("code", flat=True))
    used = {c.upper() for c in used}
    n = 1
    while f"{prefix}-{n:02d}" in used:
        n += 1
    return f"{prefix}-{n:02d}"


class ObjectCardForm(StyledMixin, forms.ModelForm):
    """Форма карточки объекта по ТЗ п. 5.1."""

    new_client = forms.CharField(label="Или новый заказчик", required=False,
                                 widget=forms.TextInput(attrs={"placeholder": "Название компании, если её нет в списке"}))
    REQUIRED = ("name", "kind", "client", "manager", "start_date", "end_date")

    class Meta:
        model = ConstructionObject
        fields = ["name", "code", "kind", "client", "new_client", "general_contractor", "city", "address",
                  "coordinates", "contract_number", "contract_amount", "budget", "manager", "responsible",
                  "foreman", "pto", "start_date", "end_date", "status", "photo", "description"]
        labels = {"manager": "Руководитель объекта", "budget": "Плановый бюджет, ₸", "city": "Регион / город",
                  "contract_number": "Основной договор №", "description": "Описание / комментарий"}
        help_texts = {"contract_number": "Можно добавить позже.",
                      "budget": "План расходов по объекту. Превышение система подсветит."}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, draft=False, can_status=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.draft = draft
        creating = not self.instance.pk
        f = self.fields
        for name in self.REQUIRED:
            f[name].required = not draft
            if draft:
                f[name].widget.attrs.pop("required", None)
            else:
                f[name].widget.attrs["required"] = True
        for name in ("kind", "city"):
            f[name].choices = [("", "— выберите —")] + [c for c in f[name].choices if c[0]]
        for name in ("contract_amount", "budget"):
            f[name].required = False
            f[name].widget.attrs.pop("required", None)
            f[name].widget.attrs["placeholder"] = "0"
        f["name"].required = True
        f["name"].widget.attrs["required"] = True
        if draft:
            f["status"].required = False
        f["client"].required = False  # можно выбрать из списка или ввести нового — проверим в clean()
        f["code"].widget.attrs.update({"placeholder": "Например: AST-03", "autocomplete": "off"})
        f["coordinates"].widget.attrs["placeholder"] = "51.1282, 71.4304"
        f["status"].choices = [c for c in ConstructionObject.Status.choices
                               if creating and c[0] in ("planned", "preparing", "in_progress")
                               or not creating and c[0] not in ("done", "archive", "paused")]
        if not creating and self.instance.status in ("done", "archive", "paused"):
            # Закрыть, приостановить и архивировать — только кнопками в карточке (с проверками).
            f["status"].choices = [(self.instance.status, self.instance.get_status_display())]
            f["status"].disabled = True
            f["status"].help_text = "Меняется кнопками в карточке объекта: «Возобновить», «Закрыть», «В архив»."
        if not can_status:
            f["status"].disabled = True
        if creating:
            f["status"].initial = ConstructionObject.Status.PREPARING
            f["status"].help_text = "По умолчанию — «Подготовка»."

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            return ""
        if not CODE_RE.match(code):
            raise forms.ValidationError("Код — от 2 до 30 символов: буквы, цифры, дефис. Например: AST-03.")
        dup = ConstructionObject.objects.filter(code__iexact=code).exclude(pk=self.instance.pk).first()
        if dup:
            raise forms.ValidationError(f"Код {code} уже занят объектом «{dup.name}». Оставьте поле пустым — "
                                        f"система предложит свободный.")
        return code

    def clean_contract_amount(self):
        return self.cleaned_data.get("contract_amount") or 0

    def clean_budget(self):
        value = self.cleaned_data.get("budget") or 0
        if value < 0:
            raise forms.ValidationError("Бюджет не может быть отрицательным.")
        return value

    def clean_coordinates(self):
        value = (self.cleaned_data.get("coordinates") or "").strip()
        if value:
            m = re.match(r"^(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)$", value)
            if not m or abs(float(m[1].replace(",", "."))) > 90 or abs(float(m[2].replace(",", "."))) > 180:
                raise forms.ValidationError("Укажите широту и долготу через запятую, например: 51.1282, 71.4304")
            value = f"{m[1].replace(',', '.')}, {m[2].replace(',', '.')}"
        return value

    def clean(self):
        data = super().clean()
        if not self.draft and not data.get("client") and not data.get("new_client"):
            self.add_error("client", "Выберите заказчика из списка или впишите нового ниже.")
        a, b = data.get("start_date"), data.get("end_date")
        if a and b and b < a:
            self.add_error("end_date", "Плановая дата завершения раньше даты начала.")
        if a and a.year < 2000:
            self.add_error("start_date", "Проверьте год в дате начала.")
        if self.draft:
            data["status"] = ConstructionObject.Status.PLANNED
        return data

    def save(self, commit=True):
        obj = self.instance
        name = (self.cleaned_data.get("new_client") or "").strip()
        if name:
            obj.client = Client.objects.filter(name__iexact=name).first() or Client.objects.create(name=name)
        if self.draft:
            obj.status = ConstructionObject.Status.PLANNED
        if not obj.code:
            obj.code = next_code(obj.city)
        return super().save(commit)


class TransportForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = TransportRequest
        fields = ["construction_object", "kind", "task", "route", "date", "time", "responsible", "driver",
                  "status", "mileage", "hours", "cost", "note"]
        widgets = {"time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].initial = date.today()


class SafetyForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = SafetyRecord
        fields = ["construction_object", "kind", "title", "date", "participants", "instructor", "valid_until",
                  "measures", "confirmed"]
        widgets = {"kind": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].initial = date.today()

    def clean(self):
        data = super().clean()
        if data.get("kind") == SafetyRecord.Kind.PERMIT and not data.get("valid_until"):
            self.add_error("valid_until", "Для допуска или удостоверения укажите срок действия.")
        return data


MAX_MEDIA = 50 * 1024 * 1024
MEDIA_EXT = ("jpg", "jpeg", "png", "heic", "webp", "mp4", "mov", "webm")


class MediaForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = ObjectMedia
        fields = ["construction_object", "file", "category", "caption", "stage", "date"]
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": "image/*,video/*", "capture": "environment"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].initial = date.today()

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f and getattr(f, "size", 0) > MAX_MEDIA:
            raise forms.ValidationError("Файл больше 50 МБ. Сожмите видео или загрузите фото.")
        if f and f.name.lower().rsplit(".", 1)[-1] not in MEDIA_EXT:
            raise forms.ValidationError("Поддерживаются JPG, PNG, HEIC, WEBP, MP4, MOV.")
        return f
