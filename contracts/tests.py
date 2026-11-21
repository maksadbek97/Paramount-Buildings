import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from objects.models import Client, ConstructionObject
from staff.models import Employee

from .models import Assignment, Crew, Payment, WorkContract, WorkLog, summary

D = Decimal


class SubcontractMathTests(TestCase):
    """Расчёт объёмов, денег рабочим и прибыли."""

    @classmethod
    def setUpTestData(cls):
        obj = ConstructionObject.objects.create(name="ЖК Тест", client=Client.objects.create(name="Генподрядчик"))
        cls.worker = Employee.objects.create(full_name="Каримов Б.")
        cls.crew = Crew.objects.create(name="Бригада 1")
        # Взяли 100 м³ кладки по 300 000 за м³.
        cls.c = WorkContract.objects.create(construction_object=obj, work_type="Кладка", unit="м³",
                                            volume=D("100"), price=D("300000"))
        # Бригаде платим 180 000 за м³, рабочему — 250 000 за человеко-день.
        cls.a_unit = Assignment.objects.create(contract=cls.c, crew=cls.crew, pay_type="unit", rate=D("180000"))
        cls.a_day = Assignment.objects.create(contract=cls.c, employee=cls.worker, pay_type="day", rate=D("250000"))
        WorkLog.objects.create(assignment=cls.a_unit, date=date.today(), volume=D("20"), people=3)
        WorkLog.objects.create(assignment=cls.a_unit, date=date.today(), volume=D("15"), people=3)
        WorkLog.objects.create(assignment=cls.a_day, date=date.today(), volume=D("5"), people=2)
        Payment.objects.create(contract=cls.c, kind="income", amount=D("9000000"), date=date.today())
        Payment.objects.create(contract=cls.c, kind="worker", assignment=cls.a_unit, amount=D("5000000"),
                               date=date.today())
        Payment.objects.create(contract=cls.c, kind="material", amount=D("700000"), date=date.today())

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
        WorkLog.objects.create(assignment=self.a_unit, date=date.today(), volume=D("100"))
        c = WorkContract.objects.get(pk=self.c.pk)
        self.assertEqual(c.remaining_volume, 0)
        self.assertEqual(c.progress, 100)


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

        r = self.client.post(reverse("assignment_create", args=[c.pk]), {
            "employee": self.emp.pk, "pay_type": "unit", "rate": "200000"})
        a = Assignment.objects.get()
        self.assertEqual(a.contract, c)

        r = self.client.post(reverse("worklog_create"), {
            "assignment": a.pk, "date": "2026-11-20", "volume": "12,5", "people": "2"})
        self.assertRedirects(r, reverse("contract_detail", args=[c.pk]))
        self.assertEqual(WorkContract.objects.get().done_volume, D("12.5"))

        r = self.client.post(reverse("payment_create"), {
            "kind": "worker", "contract": c.pk, "assignment": a.pk, "amount": "1000000", "date": "2026-11-20"})
        self.assertEqual(Payment.objects.get().assignment, a)

        r = self.client.get(reverse("contract_detail", args=[c.pk]))
        self.assertContains(r, "12,5")
        self.assertContains(r, "к выплате 1 500 000")

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
        self.client.post(reverse("employee_create"), {"full_name": "Новый Н.", "new_position": "Каменщик",
                                                      "salary": "0", "is_active": "on"})
        self.assertEqual(Employee.objects.get(full_name="Новый Н.").position.name, "Каменщик")
        self.client.post(reverse("crew_create"), {"name": "Бригада А", "members": [self.emp.pk]})
        self.assertEqual(Crew.objects.get().members.count(), 1)
        self.client.post(reverse("object_create"), {"name": "Школа", "status": "planned", "new_client": "ООО Ген"})
        self.assertEqual(ConstructionObject.objects.get(name="Школа").client.name, "ООО Ген")


class DemoBuildTests(TestCase):
    def test_seed_and_build_static(self):
        call_command("seed_demo", stdout=open("/dev/null", "w"))
        with tempfile.TemporaryDirectory() as tmp:
            call_command("build_static", out=tmp, stdout=open("/dev/null", "w"))
            home = (Path(tmp) / "index.html").read_text()
            self.assertIn("Взяли работ на сумму", home)
            self.assertIn("static/img/logo-white.png", home)
            self.assertNotIn('href="/', home)
            self.assertTrue((Path(tmp) / "contracts" / "status" / "done" / "index.html").exists())
            self.assertTrue((Path(tmp) / "worklog" / "new" / "index.html").exists())
