"""Собирает статическую демо-версию интерфейса (для GitHub Pages).

Каждая страница системы рендерится через Django от имени демо-пользователя
(с DEMO_MODE=True) и сохраняется как обычный HTML-файл со относительными ссылками.
Формы показываются, но сохранение в статической версии не работает.
"""
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from contracts.models import Crew, WorkContract, WorkLog
from objects.models import ConstructionObject
from quality.models import DailyReport, Remark
from staff.models import Employee

STATIC_PAGES = [
    "/", "/menu/", "/objects/", "/objects/new/", "/contracts/", "/contracts/new/", "/worklog/new/",
    "/payments/new/", "/staff/", "/staff/new/", "/crews/new/", "/tasks/new/", "/warehouse/",
    "/warehouse/materials/new/", "/warehouse/movements/new/", "/finance/", "/finance/new/", "/pto/", "/history/",
    "/remarks/", "/remarks/new/", "/reports/", "/reports/new/", "/tasks/",
]
STATUS_FILTERS = {
    "/remarks/": ["open", "overdue", "review", "closed", "all"],
    "/tasks/": ["active", "overdue", "review", "done", "all"],
}


def page_list():
    """Адрес файла -> адрес в Django."""
    pages = {p: p for p in STATIC_PAGES}
    for value, _ in ConstructionObject.Status.choices:
        pages[f"/objects/status/{value}/"] = f"/objects/?status={value}"
    for value, _ in WorkContract.Status.choices:
        pages[f"/contracts/status/{value}/"] = f"/contracts/?status={value}"
    for base, values in STATUS_FILTERS.items():
        for value in values:
            pages[f"{base}status/{value}/"] = f"{base}?status={value}"
    for pk in Remark.objects.values_list("pk", flat=True):
        pages[f"/remarks/{pk}/"] = f"/remarks/{pk}/"
    for pk in DailyReport.objects.values_list("pk", flat=True):
        pages[f"/reports/{pk}/"] = f"/reports/{pk}/"
    for pk in ConstructionObject.objects.values_list("pk", flat=True):
        pages[f"/objects/{pk}/"] = f"/objects/{pk}/"
        pages[f"/objects/{pk}/edit/"] = f"/objects/{pk}/edit/"
    for pk in WorkContract.objects.values_list("pk", flat=True):
        for suffix in ("", "edit/", "assign/", "norm/"):
            pages[f"/contracts/{pk}/{suffix}"] = f"/contracts/{pk}/{suffix}"
    for pk in WorkLog.objects.filter(status=WorkLog.Status.SUBMITTED).values_list("pk", flat=True):
        pages[f"/worklog/{pk}/review/"] = f"/worklog/{pk}/review/"
    for pk in Employee.objects.values_list("pk", flat=True):
        pages[f"/staff/{pk}/edit/"] = f"/staff/{pk}/edit/"
    for pk in Crew.objects.values_list("pk", flat=True):
        pages[f"/crews/{pk}/edit/"] = f"/crews/{pk}/edit/"
    return pages


class Command(BaseCommand):
    help = "Собирает статическую демо-версию интерфейса в папку (по умолчанию _site/app)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="_site/app", help="Папка для готовых HTML-файлов.")

    def handle(self, *args, **options):
        out = Path(options["out"]).resolve()
        if not ConstructionObject.objects.exists():
            raise CommandError("База пуста. Сначала выполните: python manage.py seed_demo")

        user, _ = get_user_model().objects.get_or_create(username="Демо")
        user.is_superuser = True  # в демо видны все кнопки (проверка ПТО и т.п.)
        user.save()
        client = Client()
        client.force_login(user)

        pages = page_list()
        if out.exists():
            shutil.rmtree(out)
        with override_settings(ALLOWED_HOSTS=["testserver"], DEMO_MODE=True):
            for target, url in pages.items():
                response = client.get(url)
                if response.status_code != 200:
                    raise CommandError(f"{url}: код ответа {response.status_code}")
                html = self.make_static(response.content.decode(), target, url.split("?")[0])
                path = out / target.lstrip("/") / "index.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(html, encoding="utf-8")
                self.stdout.write(f"  {url} -> {path.relative_to(out.parent)}")

        for static_dir in settings.STATICFILES_DIRS:
            shutil.copytree(static_dir, out / "static", dirs_exist_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Готово: {len(pages)} страниц в {out}"))

    @staticmethod
    def make_static(html, target, base):
        # Фильтр по статусу: ?status=x -> отдельная страница раздела.
        html = re.sub(r'href="\?status=([\w-]+)"', lambda m: f'href="{base}status/{m.group(1)}/"', html)
        # Прочие параметры (?contract=3) в статике не работают: ведём на общую форму.
        html = re.sub(r'href="(/[^"?#]*)\?[^"#]*"', r'href="\1"', html)
        # Абсолютные ссылки -> относительные, чтобы сайт работал в подпапке GitHub Pages.
        prefix = "../" * target.strip("/").count("/") + ("../" if target.strip("/") else "")
        return re.sub(r'(href|src|action)="/(?!/)([^"]*)"',
                      lambda m: f'{m.group(1)}="{prefix + m.group(2) or "./"}"', html)
