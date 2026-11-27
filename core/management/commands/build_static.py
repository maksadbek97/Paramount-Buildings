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
    pages.update(company_pages())
    pages.update(object_pages())
    pages.update(docflow_pages())
    pages.update(finance_pages())
    pages["/profile/"] = "/profile/"
    return pages


def company_pages():
    """Раздел «Моя компания»: вкладки, фильтры и формы."""
    from company.models import BankAccount, CompanyDocument, Department, StaffUnit
    from staff.models import Employee
    pages = {u: u for u in ["/company/", "/company/edit/", "/company/accounts/new/", "/company/docs/",
                            "/company/docs/new/", "/company/structure/", "/company/structure/new/",
                            "/company/staff/", "/company/staff/new/", "/company/schedule/",
                            "/company/schedule/new/"]}
    for k in [*CompanyDocument.Kind.values, "expiring"]:
        pages[f"/company/docs/kind/{k}/"] = f"/company/docs/?kind={k}"
    for pk in Department.objects.values_list("pk", flat=True):
        pages[f"/company/staff/dept/{pk}/"] = f"/company/staff/?dept={pk}"
    if Employee.objects.filter(is_active=False).exists():
        pages["/company/staff/dept/fired/"] = "/company/staff/?dept=fired"
    for prefix, model in [("accounts", BankAccount), ("docs", CompanyDocument), ("structure", Department),
                          ("staff", Employee), ("schedule", StaffUnit)]:
        for pk in model.objects.values_list("pk", flat=True):
            pages[f"/company/{prefix}/{pk}/"] = f"/company/{prefix}/{pk}/"
    return pages


def object_pages():
    """Раздел «Объекты»: список, создание, карточка со всеми вкладками и формы внутри объекта,
    а также карточки записей, на которые ведут вкладки (заявки, отчёты, замечания, виды работ)."""
    from contracts.models import WorkContract, WorkLog
    from core.object_views import NEW, TABS
    from quality.models import DailyReport, Remark
    from warehouse.models import PurchaseRequest
    pages = {"/objects/": "/objects/", "/objects/new/": "/objects/new/"}
    for pk in ConstructionObject.objects.values_list("pk", flat=True):
        base = f"/objects/{pk}/"
        pages[base] = base
        pages[base + "edit/"] = base + "edit/"
        for key, *_ in TABS[1:]:
            pages[f"{base}{key}/"] = f"{base}{key}/"
        pages[f"{base}output/"] = f"{base}output/"
        for what in NEW:
            pages[f"{base}new/{what}/"] = f"{base}new/{what}/"
    for name, model in [("purchases", PurchaseRequest), ("reports", DailyReport), ("remarks", Remark),
                        ("contracts", WorkContract)]:
        for pk in model.objects.values_list("pk", flat=True):
            pages[f"/{name}/{pk}/"] = f"/{name}/{pk}/"
    for pk in WorkContract.objects.values_list("pk", flat=True):
        for sub in ("assign", "edit", "norm"):
            pages[f"/contracts/{pk}/{sub}/"] = f"/contracts/{pk}/{sub}/"
    for pk in PurchaseRequest.objects.values_list("pk", flat=True):
        pages[f"/purchases/{pk}/edit/"] = f"/purchases/{pk}/edit/"
    for pk in WorkLog.objects.filter(status="submitted").values_list("pk", flat=True):
        pages[f"/worklog/{pk}/review/"] = f"/worklog/{pk}/review/"
    return pages


def docflow_pages():
    """Раздел «Документы»: все вкладки, журналы, карточки документов и формы."""
    from docflow.models import CaseFile, Document, Journal, Seal, Template
    from docflow.views import KIND_TITLES
    base = "/documents/"
    pages = {base + u: base + u for u in ["", "all/", "orders/", "letters/", "letters/outgoing/",
                                          "letters/internal/", "contracts/", "tasks/", "tasks/new/", "cases/",
                                          "cases/new/", "journals/", "journals/new/", "templates/", "templates/new/",
                                          "seals/", "seals/new/", "archive/", "letter/"]}
    for pk in ConstructionObject.objects.values_list("pk", flat=True):  # обзор по объекту из шапки
        pages[f"{base}object/{pk}/"] = f"{base}?object={pk}"
    for kind in KIND_TITLES:
        pages[f"{base}new/{kind}/"] = f"{base}new/{kind}/"
    for d in Document.objects.all():
        pages[f"{base}{d.pk}/"] = f"{base}{d.pk}/"
        pages[f"{base}{d.pk}/edit/"] = f"{base}{d.pk}/edit/"
    for pk in Journal.objects.values_list("pk", flat=True):
        pages[f"{base}journals/{pk}/"] = f"{base}journals/{pk}/"
        pages[f"{base}journals/{pk}/edit/"] = f"{base}journals/{pk}/edit/"
    for prefix, model in [("cases", CaseFile), ("templates", Template), ("seals", Seal)]:
        for pk in model.objects.values_list("pk", flat=True):
            pages[f"{base}{prefix}/{pk}/"] = f"{base}{prefix}/{pk}/"
    return pages


def finance_pages():
    """Раздел «Финансы»: сводная, финплан каждого объекта, долги, движение денег."""
    base = "/finance/"
    pages = {base + u: base + u for u in ["", "debts/", "cash/", "cash/new/"]}
    for kind in ("income", "expense", "debtors", "creditors"):
        pages[f"{base}cash/kind/{kind}/"] = f"{base}cash/?kind={kind}"
    for pk in ConstructionObject.objects.exclude(status="archive").values_list("pk", flat=True):
        pages[f"{base}object/{pk}/"] = f"{base}object/{pk}/"
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

        user, _ = get_user_model().objects.get_or_create(username="n.baltaev")
        user.is_superuser = True  # в демо видны все кнопки (проверка ПТО и т.п.)
        user.first_name, user.last_name = "Нурбек", "Балтаев"  # в шапке: «Балтаев Нурбек»
        user.email = user.email or "n.baltaev@paramount-buildings.kz"
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
        # Фильтры главной: ?period=x&object=y -> отдельная страница; на других страницах ?kind=x -> base/kind/x/.
        def local(m):
            if base == "/" or m.group(1) == "/":
                return f'href="{dashboard_path(m.group(2))}"'
            k, _, v = m.group(2).partition("=")
            return f'href="{base}{k}/{v}/"'
        html = re.sub(r'href="(/?)\?([^"#]*)"', local, html)
        # Фильтры разделов: /company/docs/?kind=x или ?kind=x на самой странице -> /company/docs/kind/x/;
        # объект из шапки: /documents/?object=3 -> /documents/object/3/.
        html = re.sub(r'href="(/[^"?#]*)\?(kind|dept|object)=([\w-]+)"', r'href="\1\2/\3/"', html)
        # Прочие параметры (?contract=3) в статике не работают: ведём на общую форму.
        html = re.sub(r'href="(/(?!static/)[^"?#]*)\?[^"#]*"', r'href="\1"', html)
        # Абсолютные ссылки -> относительные, чтобы сайт работал в подпапке GitHub Pages.
        prefix = "../" * target.strip("/").count("/") + ("../" if target.strip("/") else "")
        html = re.sub(r"url\('/(?!/)([^']*)'\)", lambda m: f"url('{prefix + m.group(1)}')", html)
        return re.sub(r'(href|src|action)="/(?!/)([^"]*)"',
                      lambda m: f'{m.group(1)}="{prefix + m.group(2) or "./"}"', html)
