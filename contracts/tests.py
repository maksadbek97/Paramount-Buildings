import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import AuditLog
from objects.models import Client, ConstructionObject
from staff.models import Employee
from warehouse.models import Material, StockMovement, Warehouse

from .models import Assignment, Crew, MaterialNorm, Payment, WorkContract, WorkLog, summary

D = Decimal
TODAY = date.today()


def accepted_log(a, volume, people=1):
    return WorkLog.objects.create(assignment=a, date=TODAY, volume=D(volume), people=people,
                                  status=WorkLog.Status.ACCEPTED, accepted_volume=D(volume))


class SubcontractMathTests(TestCase):
    """Расчёт объёмов, денег рабочим и прибыли (по принятому объёму)."""

    @classmethod
    def setUpTestData(cls):
        obj = ConstructionObject.objects.create(name="ЖК Тест", client=Client.objects.create(name="Генподрядчик"))
        cls.worker = Employee.objects.create(full_name="Каримов Б.")
        cls.crew = Crew.objects.create(name="Бригада 1")
        # Взяли 100 м³ кладки по 300 000 ₸ за м³.
        cls.c = WorkContract.objects.create(construction_object=obj, work_type="Кладка", unit="м³",
                                            volume=D("100"), price=D("300000"))
        # Бригаде платим 180 000 за м³, рабочему — 250 000 за человеко-день.
        cls.a_unit = Assignment.objects.create(contract=cls.c, crew=cls.crew, pay_type="unit", rate=D("180000"))
        cls.a_day = Assignment.objects.create(contract=cls.c, employee=cls.worker, pay_type="day", rate=D("250000"))
        accepted_log(cls.a_unit, "20", 3)
        accepted_log(cls.a_unit, "15", 3)
        accepted_log(cls.a_day, "5", 2)
        Payment.objects.create(contract=cls.c, kind="income", amount=D("9000000"), date=TODAY)
        Payment.objects.create(contract=cls.c, kind="worker", assignment=cls.a_unit, amount=D("5000000"), date=TODAY)
        Payment.objects.create(contract=cls.c, kind="material", amount=D("700000"), date=TODAY)

    def test_volume(self):
        c = WorkContract.objects.get(pk=self.c.pk)
        self.assertEqual(c.done_volume, D("40"))
        self.assertEqual(c.remaining_volume, D("60"))
        self.assertEqual(c.progress, 40)
        self.assertEqual(c.total, D("30000000"))
        self.assertEqual(c.earned, D("12000000"))

    def test_worker_pay(self):
        unit = Assignment.objects.get(pk=self.a_unit.pk)
        day = Assignment.objects.get(pk=self.a_day.pk)
        self.assertEqual(unit.earned, D("6300000"))  # 35 м³ × 180 000
        self.assertEqual(unit.due, D("1300000"))
        self.assertEqual(day.earned, D("500000"))  # 2 чел.-дня × 250 000
        self.assertEqual(day.due, D("500000"))

    def test_profit(self):
        c = WorkContract.objects.get(pk=self.c.pk)
        self.assertEqual(c.labor_accrued, D("6800000"))
        self.assertEqual(c.workers_due, D("1800000"))
        self.assertEqual(c.client_due, D("3000000"))
        self.assertEqual(c.profit, D("12000000") - D("6800000") - D("700000"))
        self.assertEqual(c.cash, D("9000000") - D("5000000") - D("700000"))
        s = summary(WorkContract.objects.all())
        self.assertEqual(s["progress"], 40)
        self.assertEqual(s["received"], D("9000000"))

    def test_overdone_volume_does_not_go_negative(self):
        accepted_log(self.a_unit, "100")
        c = WorkContract.objects.get(pk=self.c.pk)
        self.assertEqual(c.remaining_volume, 0)
        self.assertEqual(c.progress, 100)


class AcceptanceTests(TestCase):
    """ТЗ п. 32.2: план 1000 м², внесено 300, принято 280, отклонено 20."""

    def test_tz_32_2(self):
        user = get_user_model().objects.create_superuser("tech", password="x")
        obj = ConstructionObject.objects.create(name="ЖК Атлант")
        c = WorkContract.objects.create(construction_object=obj, work_type="Штукатурка", unit="м²",
                                        volume=D("1000"), price=D("2500"))
        a = Assignment.objects.create(contract=c, crew=Crew.objects.create(name="Б"), pay_type="unit", rate=D("1000"))
        mat = Material.objects.create(name="Смесь", unit="кг")
        MaterialNorm.objects.create(contract=c, material=mat, per_unit=D("10"))
        log = WorkLog.objects.create(assignment=a, date=TODAY, volume=D("300"))

        c = WorkContract.objects.get(pk=c.pk)
        self.assertEqual(c.accepted_volume, 0)  # до проверки в учёт не идёт
        self.assertEqual(c.pending_volume, D("300"))

        self.client.force_login(user)
        self.client.post(reverse("worklog_review", args=[log.pk]), {"accepted_volume": "280", "review_note": "брак"})
        c = WorkContract.objects.get(pk=c.pk)
        self.assertEqual(c.accepted_volume, D("280"))
        self.assertEqual(c.rejected_volume, D("20"))
        self.assertEqual(c.remaining_volume, D("720"))
        self.assertEqual(c.progress, 28)
        self.assertEqual(c.earned, D("700000"))  # 280 × 2 500
        self.assertEqual(c.material_plan_fact()[0]["need"], D("2800"))  # норма на 280 м²
        self.assertEqual(Assignment.objects.get(pk=a.pk).earned, D("280000"))
        self.assertTrue(AuditLog.objects.filter(action="accept", reason="брак").exists())

        # повторно принять нельзя
        r = self.client.post(reverse("worklog_review", args=[log.pk]), {"accepted_volume": "300"})
        self.assertEqual(WorkLog.objects.get(pk=log.pk).accepted_volume, D("280"))
        self.assertEqual(r.status_code, 302)

    def test_review_needs_permission(self):
        user = get_user_model().objects.create_user("foreman", password="x")
        obj = ConstructionObject.objects.create(name="О")
        c = WorkContract.objects.create(construction_object=obj, work_type="К", volume=10, price=1)
        a = Assignment.objects.create(contract=c, crew=Crew.objects.create(name="Б"), rate=1)
        log = WorkLog.objects.create(assignment=a, date=TODAY, volume=D("5"))
        self.client.force_login(user)
        r = self.client.post(reverse("worklog_review", args=[log.pk]), {"accepted_volume": "5"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(WorkLog.objects.get(pk=log.pk).status, WorkLog.Status.SUBMITTED)


class SubcontractFormTests(TestCase):
    """Ввод данных прямо в интерфейсе, без админки."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("boss", password="pass12345")
        cls.obj = ConstructionObject.objects.create(name="Дом")
        cls.emp = Employee.objects.create(full_name="Рабочий Р.")

    def setUp(self):
        self.client.login(username="boss", password="pass12345")

    def test_full_flow(self):
        r = self.client.post(reverse("contract_create"), {
            "construction_object": self.obj.pk, "work_type": "Кладка", "volume": "50", "unit": "м³",
            "price": "300000", "status": "active"})
        c = WorkContract.objects.get()
        self.assertRedirects(r, reverse("contract_detail", args=[c.pk]))
        self.assertTrue(AuditLog.objects.filter(action="create", object_repr__startswith="Кладка").exists())

        self.client.post(reverse("assignment_create", args=[c.pk]), {
            "employee": self.emp.pk, "pay_type": "unit", "rate": "200000"})
        a = Assignment.objects.get()
        self.assertEqual(a.contract, c)

        r = self.client.post(reverse("worklog_create"), {
            "assignment": a.pk, "date": "2026-11-20", "volume": "12,5", "people": "2", "floor": "3"})
        self.assertRedirects(r, reverse("contract_detail", args=[c.pk]))
        log = WorkLog.objects.get()
        self.assertEqual(log.created_by, self.user)
        self.assertEqual(WorkContract.objects.get().pending_volume, D("12.5"))
        log.review(self.user, D("12.5"))

        self.client.post(reverse("payment_create"), {
            "kind": "worker", "contract": c.pk, "assignment": a.pk, "amount": "1000000", "date": "2026-11-20"})
        self.assertEqual(Payment.objects.get().assignment, a)

        r = self.client.get(reverse("contract_detail", args=[c.pk]))
        self.assertContains(r, "12,5")
        self.assertContains(r, "к выплате 1 500 000")

    def test_over_plan_needs_permission(self):
        c = WorkContract.objects.create(construction_object=self.obj, work_type="Х", volume=10, price=1)
        a = Assignment.objects.create(contract=c, employee=self.emp, rate=1)
        data = {"assignment": a.pk, "date": "2026-11-20", "volume": "11", "people": "1", "over_plan": "on"}
        r = self.client.post(reverse("worklog_create"), data)
        self.assertContains(r, "больше плана")
        self.assertFalse(WorkLog.objects.exists())
        self.user.user_permissions.add(Permission.objects.get(codename="allow_over_plan"))
        self.client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self.client.post(reverse("worklog_create"), data)
        self.assertTrue(WorkLog.objects.get().over_plan)

    def test_edit_logs_old_and_new_value(self):
        c = WorkContract.objects.create(construction_object=self.obj, work_type="Кладка", volume=10, price=1)
        self.client.post(reverse("contract_edit", args=[c.pk]), {
            "construction_object": self.obj.pk, "work_type": "Кладка", "volume": "12", "unit": "м³", "price": "1",
            "status": "active", "change_reason": "уточнили по проекту"})
        e = AuditLog.objects.get(action="update")
        self.assertEqual(e.reason, "уточнили по проекту")
        self.assertIn(["Объём по договору", "10", "12"], e.change_list)
        self.assertEqual(e.construction_object, self.obj)
        r = self.client.get(reverse("object_detail", args=[self.obj.pk]))
        self.assertContains(r, "уточнили по проекту")

    def test_assignment_needs_exactly_one_performer(self):
        c = WorkContract.objects.create(construction_object=self.obj, work_type="Х", volume=1, price=1)
        r = self.client.post(reverse("assignment_create", args=[c.pk]), {"pay_type": "unit", "rate": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "либо рабочего, либо бригаду")
        self.assertFalse(Assignment.objects.exists())

    def test_worker_payment_needs_performer(self):
        c = WorkContract.objects.create(construction_object=self.obj, work_type="Х", volume=1, price=1)
        r = self.client.post(reverse("payment_create"), {
            "kind": "worker", "contract": c.pk, "amount": "10", "date": "2026-11-20"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Payment.objects.exists())

    def test_create_crew_employee_object(self):
        r = self.client.post(reverse("employee_create"), {"full_name": "Новый Н.", "new_position": "Каменщик",
                                                          "iin": "900101300123", "salary": "0", "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Employee.objects.get(full_name="Новый Н.").position.name, "Каменщик")
        r = self.client.post(reverse("employee_create"), {"full_name": "Плохой ИИН", "iin": "123", "salary": "0"})
        self.assertContains(r, "12 цифр")
        self.client.post(reverse("crew_create"), {"name": "Бригада А", "members": [self.emp.pk]})
        self.assertEqual(Crew.objects.get().members.count(), 1)
        self.client.post(reverse("object_create"), {"name": "Школа", "status": "planned", "new_client": "ТОО Ген",
                                                    "city": "Астана", "contract_amount": "0", "budget": "0"})
        self.assertEqual(ConstructionObject.objects.get(name="Школа").client.name, "ТОО Ген")


class StockRulesTests(TestCase):
    """ТЗ п. 30.1: нельзя выдать больше, чем есть, и отрицательные количества."""

    def test_cannot_issue_more_than_stock(self):
        user = get_user_model().objects.create_user("k", password="x")
        self.client.force_login(user)
        m = Material.objects.create(name="Цемент", unit="т")
        w = Warehouse.objects.create(name="Центральный")
        StockMovement.objects.create(material=m, kind="in", quantity=D("100"), date=TODAY, warehouse=w)
        base = {"material": m.pk, "date": "2026-11-20", "warehouse": w.pk}
        r = self.client.post(reverse("movement_create"), {**base, "kind": "out", "quantity": "120"})
        self.assertContains(r, "Нельзя выдать больше")
        r = self.client.post(reverse("movement_create"), {**base, "kind": "in", "quantity": "-5"})
        self.assertContains(r, "больше нуля")
        self.client.post(reverse("movement_create"), {**base, "kind": "out", "quantity": "20"})
        self.assertEqual(Material.objects.get().stock, D("80"))


class DemoBuildTests(TestCase):
    def test_seed_and_build_static(self):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        with tempfile.TemporaryDirectory() as tmp:
            call_command("build_static", out=tmp, stdout=open("/dev/null", "w"))
            home = (Path(tmp) / "index.html").read_text()
            self.assertIn("Главная", home)
            self.assertIn("Сумма договоров", home)
            self.assertIn("₸", home)
            self.assertIn("static/img/logo-white.png", home)
            self.assertNotIn('href="/', home)
            self.assertNotIn("url('/", home)
            for page in ("objects/status/done", "period/year", "finance/kind/debtors", "add/purchase",
                         "notifications", "search"):
                self.assertTrue((Path(tmp) / page / "index.html").exists(), page)
            for page in ("contracts/status/done", "worklog/new", "pto", "history", "objects/1/money",
                         "objects/1/new/output", "purchases/status/open", "add"):
                self.assertTrue((Path(tmp) / page / "index.html").exists(), page)
