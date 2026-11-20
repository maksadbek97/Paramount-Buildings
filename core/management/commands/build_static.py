"""Собирает статическую демо-версию интерфейса (для GitHub Pages).

Каждая страница системы рендерится через Django от имени демо-пользователя
и сохраняется как обычный HTML-файл со относительными ссылками.
Формы, вход/выход и админка в статической версии не работают.
"""
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from objects.models import ConstructionObject

BANNER = (
    '<div style="background:#fff4e5;border:1px solid #f3c58f;color:#7a4a12;'
    'padding:10px 14px;border-radius:8px;margin-bottom:20px;font-size:14px">'
    "Демо-версия с примерными данными: только просмотр. Добавление и редактирование "
    "данных работает в полной версии системы (Django-сервер).</div>"
)


class Command(BaseCommand):
    help = "Собирает статическую демо-версию интерфейса в папку (по умолчанию _site/app)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="_site/app", help="Папка для готовых HTML-файлов.")

    def handle(self, *args, **options):
        out = Path(options["out"]).resolve()
        if not ConstructionObject.objects.exists():
            raise CommandError("База пуста. Сначала выполните: python manage.py seed_demo")

        user, _ = get_user_model().objects.get_or_create(username="Демо")
        client = Client()
        client.force_login(user)

        pages = {"/": "/", "/objects/": "/objects/", "/staff/": "/staff/",
                 "/warehouse/": "/warehouse/", "/finance/": "/finance/"}
        for value, _label in ConstructionObject.Status.choices:
            pages[f"/objects/status/{value}/"] = f"/objects/?status={value}"
        for pk in ConstructionObject.objects.values_list("pk", flat=True):
            pages[f"/objects/{pk}/"] = f"/objects/{pk}/"

        if out.exists():
            shutil.rmtree(out)
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            for target, url in pages.items():
                response = client.get(url)
                if response.status_code != 200:
                    raise CommandError(f"{url}: код ответа {response.status_code}")
                html = self.make_static(response.content.decode(), target)
                path = out / target.lstrip("/") / "index.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(html, encoding="utf-8")
                self.stdout.write(f"  {url} -> {path.relative_to(out.parent)}")

        for static_dir in settings.STATICFILES_DIRS:
            shutil.copytree(static_dir, out / "static", dirs_exist_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Готово: {len(pages)} страниц в {out}"))

    @staticmethod
    def make_static(html, target):
        # Выход и админка без сервера не работают: убираем форму, ссылки делаем текстом.
        html = re.sub(r'<form method="post" action="/logout/".*?</form>', "", html, flags=re.S)
        html = re.sub(r'<a href="/admin/[^"]*">([^<]*)</a>', r"\1", html)
        # Фильтр по статусу: ?status=x -> отдельная страница.
        html = re.sub(r'href="\?status=([\w-]+)"', r'href="/objects/status/\1/"', html)
        # Абсолютные ссылки -> относительные, чтобы сайт работал в подпапке GitHub Pages.
        prefix = "../" * target.strip("/").count("/") + ("../" if target.strip("/") else "")
        html = re.sub(r'(href|src)="/(?!/)([^"]*)"',
                      lambda m: f'{m.group(1)}="{prefix + m.group(2) or "./"}"', html)
        return html.replace("<main>", "<main>" + BANNER, 1)
