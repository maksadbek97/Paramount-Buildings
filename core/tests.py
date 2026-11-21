from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from finance.models import Estimate, EstimateItem, Transaction
from objects.models import Client, ConstructionObject
from staff.models import Employee, Position, Task
from warehouse.models import Material, StockMovement, Warehouse


class SystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("admin", password="pass12345")
        from django.contrib.auth.models import Permission
        cls.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="objects", codename__in=["add_constructionobject", "change_constructionobject"]))
        cls.client_obj = Client.objects.create(name="ООО Заказчик")
        pos = Position.objects.create(name="Прораб")
        cls.emp = Employee.objects.create(full_name="Иванов И.И.", position=pos)
        cls.obj = ConstructionObject.objects.create(
            name="ЖК Парамаунт", client=cls.client_obj, manager=cls.emp, status="in_progress")
        Task.objects.create(title="Залить фундамент", construction_object=cls.obj, assignee=cls.emp)
        cls.mat = Material.objects.create(name="Цемент", unit="мешок", min_stock=50)
        cls.wh = Warehouse.objects.create(name="Центральный")
        StockMovement.objects.create(material=cls.mat, kind="in", quantity=100, date=date.today(), warehouse=cls.wh)
        StockMovement.objects.create(material=cls.mat, kind="out", quantity=70, date=date.today(),
                                     construction_object=cls.obj, warehouse=cls.wh)
        est = Estimate.objects.create(construction_object=cls.obj, title="Смета №1")
        EstimateItem.objects.create(estimate=est, name="Бетон", quantity=10, unit_price=500)
        Transaction.objects.create(construction_object=cls.obj, kind="income", amount=1000, date=date.today())
        Transaction.objects.create(construction_object=cls.obj, kind="expense", amount=400, date=date.today())

    def test_stock_and_low(self):
        self.assertEqual(self.mat.stock, 30)
        self.assertTrue(self.mat.is_low)

    def test_estimate_total(self):
        self.assertEqual(Estimate.objects.get().total, 5000)

    def test_login_required(self):
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 302)

    def test_pages_render(self):
        self.client.login(username="admin", password="pass12345")
        for name, args in [("dashboard", []), ("object_list", []), ("object_detail", [self.obj.pk]),
                           ("staff_list", []), ("warehouse_list", []), ("finance_list", []), ("menu", []),
                           ("contract_list", []), ("object_create", []), ("object_edit", [self.obj.pk]),
                           ("employee_create", []), ("task_create", []), ("material_create", []),
                           ("movement_create", []), ("transaction_create", []), ("worklog_create", []),
                           ("payment_create", []), ("contract_create", []), ("crew_create", []),
                           ("pto", []), ("history", []), ("remark_list", []), ("remark_create", []),
                           ("report_list", []), ("report_create", []), ("task_list", [])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 200, name)
        r = self.client.get(reverse("object_list") + "?status=done")
        self.assertEqual(r.status_code, 200)

    def test_quick_forms_save(self):
        self.client.login(username="admin", password="pass12345")
        r = self.client.post(reverse("movement_create"), {
            "kind": "out", "material": self.mat.pk, "quantity": "5", "date": "2026-11-20",
            "warehouse": self.wh.pk})
        self.assertRedirects(r, reverse("warehouse_list"))
        self.assertEqual(self.mat.stock, 25)
        self.client.post(reverse("transaction_create"), {"kind": "income", "amount": "50", "date": "2026-11-20"})
        self.assertEqual(Transaction.objects.count(), 3)

    def test_money_filters(self):
        from core.templatetags.ui import money, num, short
        self.assertEqual(num("1234567.50"), "1\u00a0234\u00a0567,5")
        self.assertEqual(money(-2500), "−2\u00a0500")
        self.assertEqual(short(3700000000), "3,7\u00a0млрд\u00a0₸")
        self.assertEqual(short(250000000), "250\u00a0млн\u00a0₸")

    def test_login_page_has_brand(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, "img/logo-white.png")
        self.assertContains(r, "Manrope")


class ObjectHubTests(TestCase):
    """Всё по объекту — внутри объекта: вкладки и формы, привязанные к объекту."""

    @classmethod
    def setUpTestData(cls):
        from contracts.models import Assignment, WorkContract
        from staff.models import Employee
        cls.user = get_user_model().objects.create_superuser("boss", password="x")
        cls.obj = ConstructionObject.objects.create(name="ЖК Атлант", status="in_progress")
        cls.other = ConstructionObject.objects.create(name="Другой", status="in_progress")
        cls.c = WorkContract.objects.create(construction_object=cls.obj, work_type="Кладка", volume=100,
                                            unit="м³", price=9500)
        cls.c2 = WorkContract.objects.create(construction_object=cls.other, work_type="Штукатурка", volume=50,
                                             unit="м²", price=2000)
        w = Employee.objects.create(full_name="Ерлан")
        cls.a = Assignment.objects.create(contract=cls.c, employee=w, pay_type="per_volume", rate=4000)
        Assignment.objects.create(contract=cls.c2, employee=w, pay_type="per_volume", rate=1000)

    def setUp(self):
        self.client.force_login(self.user)

    def test_home_lists_objects_and_all_tabs_open(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Объекты")
        self.assertContains(r, "ЖК Атлант")
        self.assertEqual(self.client.get(reverse("object_detail", args=[self.obj.pk])).status_code, 200)
        from core.object_views import NEW, TABS
        for tab, *_ in TABS[1:]:
            self.assertEqual(self.client.get(reverse("object_tab", args=[self.obj.pk, tab])).status_code, 200, tab)
        for what in NEW:
            self.assertEqual(self.client.get(reverse("object_new", args=[self.obj.pk, what])).status_code, 200, what)
        self.assertEqual(self.client.get(reverse("object_tab", args=[self.obj.pk, "nope"])).status_code, 404)

    def test_form_inside_object_is_scoped_and_returns_to_object(self):
        url = reverse("object_new", args=[self.obj.pk, "output"])
        r = self.client.get(url)
        form = r.context["form"]
        self.assertEqual(list(form.fields["assignment"].queryset), [self.a])  # только исполнители этого объекта
        r = self.client.post(url, {"assignment": self.a.pk, "date": "2026-11-20", "volume": "5", "people": "2"})
        self.assertRedirects(r, reverse("object_tab", args=[self.obj.pk, "work"]))

    def test_contract_created_inside_object_belongs_to_it(self):
        from contracts.models import WorkContract
        r = self.client.post(reverse("object_new", args=[self.obj.pk, "work"]), {
            "construction_object": self.obj.pk, "work_type": "Монолит", "volume": "10", "unit": "м³",
            "price": "50000", "status": "active"})
        self.assertRedirects(r, reverse("object_tab", args=[self.obj.pk, "work"]))
        self.assertEqual(WorkContract.objects.get(work_type="Монолит").construction_object, self.obj)

    def test_object_list_has_all_objects_with_status_groups(self):
        done = ConstructionObject.objects.create(name="Логистический склад", status="done")
        r = self.client.get(reverse("object_list"))
        rows = {x["o"].name: x for x in r.context["rows"]}
        self.assertEqual(rows["ЖК Атлант"]["group"], "working")
        self.assertEqual(rows[done.name]["group"], "done")
        self.assertContains(r, "img/objects/1.svg")  # заглушка, пока нет своего фото
        self.assertContains(r, "img/objects/4.svg")
        r = self.client.get(reverse("object_list") + "?status=done")
        self.assertEqual(r.context["status"], "done")


class DashboardTests(TestCase):
    """ТЗ модуля «Главная»: период, фильтр объекта, KPI, задачи, быстрые действия."""

    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta

        from contracts.models import Payment, WorkContract
        cls.user = get_user_model().objects.create_superuser("dir", password="x")
        cls.a = ConstructionObject.objects.create(name="Атлант", status="in_progress")
        cls.b = ConstructionObject.objects.create(name="Алатау", status="in_progress")
        ca = WorkContract.objects.create(construction_object=cls.a, work_type="Кладка", volume=10, unit="м³", price=1000)
        cb = WorkContract.objects.create(construction_object=cls.b, work_type="Штукатурка", volume=10, unit="м²", price=500)
        today = date.today()
        Payment.objects.create(contract=ca, kind="income", amount=7000, date=today)
        Payment.objects.create(contract=cb, kind="income", amount=3000, date=today)
        Payment.objects.create(contract=ca, kind="material", amount=2000, date=today - timedelta(days=400))
        Transaction.objects.create(kind="expense", amount=500, date=today, construction_object=cls.b)
        cls.emp = Employee.objects.create(full_name="Ерлан", user=cls.user)
        cls.late = Task.objects.create(title="Сдать акт", assignee=cls.emp, construction_object=cls.a,
                                       due_date=today - timedelta(days=2))

    def setUp(self):
        self.client.force_login(self.user)

    def test_period_and_object_filters_change_flow_numbers(self):
        r = self.client.get(reverse("dashboard"))
        k = r.context["kpi"]
        self.assertEqual((k["income"], k["expense"], k["result"]), (10000, 500, 9500))  # старый расход не в месяце
        self.assertEqual(k["active"], 2)
        self.assertEqual(k["contracts"], 15000)
        k = self.client.get(reverse("dashboard") + "?period=all").context["kpi"]
        self.assertEqual(k["expense"], 2500)
        k = self.client.get(reverse("dashboard") + f"?period=all&object={self.a.pk}").context["kpi"]
        self.assertEqual((k["income"], k["expense"], k["active"]), (7000, 2000, 1))

    def test_bad_custom_period_is_rejected(self):
        r = self.client.get(reverse("dashboard") + "?period=custom&from=2026-05-10&to=2026-05-01")
        self.assertTrue(r.context["bad_period"])
        self.assertContains(r, "не может быть позже")

    def test_period_ranges(self):
        from core.dashboard import period_range
        t = date(2026, 11, 21)  # суббота
        self.assertEqual(period_range("week", today=t)[:2], (date(2026, 11, 16), t))
        self.assertEqual(period_range("last_week", today=t)[:2], (date(2026, 11, 9), date(2026, 11, 15)))
        self.assertEqual(period_range("last_month", today=t)[:2], (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(period_range("quarter", today=t)[:2], (date(2026, 10, 1), t))
        self.assertEqual(period_range("all", today=t)[:2], (None, None))

    def test_task_done_and_postpone(self):
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["kpi"]["tasks_overdue"], 1)
        self.assertContains(r, "Сдать акт")
        r = self.client.post(reverse("task_postpone", args=[self.late.pk]), {"due_date": "2026-12-01", "reason": ""})
        self.assertContains(r, "Обязательное поле")
        self.client.post(reverse("task_postpone", args=[self.late.pk]),
                         {"due_date": "2026-12-01", "reason": "Ждём подпись"})
        self.late.refresh_from_db()
        self.assertEqual(self.late.due_date, date(2026, 12, 1))
        self.client.post(reverse("task_done", args=[self.late.pk]), {"next": reverse("dashboard")})
        self.late.refresh_from_db()
        self.assertEqual(self.late.status, "done")
        self.assertIsNotNone(self.late.done_at)
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["tasks"]["done_count"], 1)

    def test_quick_actions_require_object_and_links_work(self):
        r = self.client.get(reverse("add_for", args=["purchase"]))
        self.assertContains(r, reverse("object_new", args=[self.a.pk, "purchase"]))
        for url in (reverse("finance_list") + "?kind=income", reverse("finance_list") + "?kind=debtors",
                    reverse("finance_list") + "?kind=creditors", reverse("notifications"),
                    reverse("search") + "?q=Атл", reverse("task_list") + "?status=today",
                    reverse("purchase_list") + "?status=overdue"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse("search") + "?q=Атл"), "Атлант")
        self.assertContains(self.client.get(reverse("search") + "?q=zzzz"), "Ничего не найдено")

    def test_money_hidden_without_permission(self):
        u = get_user_model().objects.create_user("worker", password="x")
        self.client.force_login(u)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "Сумма договоров")
        self.assertContains(r, "Просроченные задачи")
