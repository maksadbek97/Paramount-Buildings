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
