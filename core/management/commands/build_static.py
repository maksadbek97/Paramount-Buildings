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

from objects.models import ConstructionObject


def page_list():
    """Адрес файла -> адрес в Django.

    Сейчас в демо только раздел «Главная» (остальные разделы подключаются по очереди):
    главная по умолчанию, каждый период и каждый объект в фильтре.
    """
    from core.dashboard import DEFAULT_PERIOD, PERIODS
    pages = {"/": "/"}
    objs = [""] + list(ConstructionObject.objects.values_list("pk", flat=True))
    for key, _ in PERIODS:
        for pk in objs:
            if key == DEFAULT_PERIOD and not pk:
                continue
            path = (f"period/{key}/" if key != DEFAULT_PERIOD else "") + (f"object/{pk}/" if pk else "")
            query = "&".join(x for x in (f"period={key}" if key != DEFAULT_PERIOD else "",
                                         f"object={pk}" if pk else "") if x)
            pages["/" + path] = "/?" + query
    return pages


def dashboard_path(query):
    """?period=year&object=2 -> /period/year/object/2/ (так страницы лежат в статике)."""
    params = dict(p.split("=", 1) for p in query.replace("&amp;", "&").split("&") if "=" in p)
    path = "/"
    if params.get("period"):
        path += f"period/{params['period']}/"
    if params.get("object"):
        path += f"object/{params['object']}/"
    return path


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
        if Path(settings.MEDIA_ROOT).exists():  # загруженные фото объектов и документы
            shutil.copytree(settings.MEDIA_ROOT, out / "media", dirs_exist_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Готово: {len(pages)} страниц в {out}"))

    @staticmethod
    def make_static(html, target, base):
        # Фильтры главной: ?period=x&object=y -> отдельная страница.
        html = re.sub(r'href="/?\?([^"#]*)"', lambda m: f'href="{dashboard_path(m.group(1))}"', html)
        # Прочие параметры (?contract=3) в статике не работают: ведём на общую форму.
        html = re.sub(r'href="(/[^"?#]*)\?[^"#]*"', r'href="\1"', html)
        # Абсолютные ссылки -> относительные, чтобы сайт работал в подпапке GitHub Pages.
        prefix = "../" * target.strip("/").count("/") + ("../" if target.strip("/") else "")
        html = re.sub(r"url\('/(?!/)([^']*)'\)", lambda m: f"url('{prefix + m.group(1)}')", html)
        return re.sub(r'(href|src|action)="/(?!/)([^"]*)"',
                      lambda m: f'{m.group(1)}="{prefix + m.group(2) or "./"}"', html)
