from datetime import date, timedelta
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import AuditLog
from objects.models import ConstructionObject

from . import services
from .models import PlanLine

S = PlanLine.Section


class FinPlanTests(TestCase):
    """Финплан по шаблону «Фин план до 2026 года»: план / факт / остаток, сводная, долги, календарь."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("boss", password="pass12345")
        cls.a = ConstructionObject.objects.create(name="Daryn", status="in_progress")
        cls.b = ConstructionObject.objects.create(name="Arna", status="in_progress")
        cls.free = ConstructionObject.objects.create(name="Zerde", status="in_progress")
        mk = PlanLine.objects.create
        cls.inc = mk(construction_object=cls.a, section=S.INCOME, name="Поступление от заказчика",
                     plan_amount=D("35000000"), fact_amount=D("10000000"), plan_date=date.today() + timedelta(30))
        cls.brig = mk(construction_object=cls.a, section=S.LABOR, name="Бригада — оплата за работу",
                      plan_amount=D("1500000"), plan_date=date.today() - timedelta(3))
        mk(construction_object=cls.a, section=S.MATERIAL, name="Материальные расходы", plan_amount=D("400000"),
           fact_amount=D("400000"))
        mk(construction_object=cls.a, section=S.OVERHEAD, name="Накладные расходы", plan_amount=D("100000"))
        mk(construction_object=cls.b, section=S.INCOME, name="Поступление от заказчика", plan_amount=D("32000000"))
        mk(construction_object=cls.b, section=S.LABOR, name="Гулом — оплата за работу", plan_amount=D("2000000"),
           note="Вид работ уточнить")
        cls.debt = mk(section=S.DEBT, name="Хару KZ", plan_amount=D("4000000"), fact_amount=D("1000000"))

    def setUp(self):
        self.client.force_login(self.user)

    def test_object_plan_totals(self):
        p = services.object_plan(self.a, list(self.a.plan_lines.all()))
        self.assertEqual(p["income"]["plan"], D("35000000"))
        self.assertEqual(p["income"]["fact"], D("10000000"))
        self.assertEqual(p["expense"]["plan"], D("2000000"))  # 1 500 000 + 400 000 + 100 000
        self.assertEqual(p["expense"]["fact"], D("400000"))
        self.assertEqual(p["balance"], {"plan": D("33000000"), "fact": D("9600000")})
        self.assertEqual(p["late"], 1)

    def test_summary_includes_company_debt(self):
        s = services.summary()
        self.assertEqual([r["o"] for r in s["rows"]], [self.a, self.b])  # объекты в порядке добавления, без пустых
        self.assertEqual(s["income"]["plan"], D("67000000"))
        self.assertEqual(s["expense"]["plan"], D("4000000"))
        self.assertEqual(s["debt"]["left"], D("3000000"))
        # как в таблице: итого расходы по компании = расходы объектов + общий долг
        self.assertEqual(s["expense_all"]["plan"], D("8000000"))
        self.assertEqual(s["balance"]["plan"], D("59000000"))
        self.assertEqual(s["balance"]["fact"], D("10000000") - D("400000") - D("1000000"))

    def test_line_states(self):
        self.assertEqual(self.brig.state[0], "late")
        self.assertEqual(self.inc.state, ("part", "Частично"))
        self.assertEqual(PlanLine.objects.get(name="Материальные расходы").state, ("done", "Оплачено"))

    def test_pages_render(self):
        for url in (reverse("finance_home"), reverse("finance_object", args=[self.a.pk]),
                    reverse("finance_object", args=[self.free.pk]), reverse("finance_debts"),
                    reverse("finance_calendar"), reverse("finance_list"), reverse("finance_line_new"),
                    reverse("finance_line_edit", args=[self.inc.pk])):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        home = self.client.get(reverse("finance_home")).content.decode()
        self.assertIn("Сводная по объектам", home)
        self.assertIn("Общий долг компании", home)
        self.assertIn(reverse("finance_object", args=[self.free.pk]), home)  # «+ Объект» в финплан
        page = self.client.get(reverse("finance_object", args=[self.a.pk])).content.decode()
        for label in ("Поступления", "Оплата работ", "Материальные расходы", "Накладные расходы"):
            self.assertIn(label, page)
        self.assertIn("Просрочено", page)

    def test_add_edit_delete_line(self):
        r = self.client.post(reverse("finance_line_new"), {
            "construction_object": self.b.pk, "section": "material", "name": "Гипсокартон",
            "plan_amount": "2 000 000", "note": "", "next": reverse("finance_object", args=[self.b.pk])})
        self.assertRedirects(r, reverse("finance_object", args=[self.b.pk]))
        line = PlanLine.objects.get(name="Гипсокартон")
        self.assertEqual(line.plan_amount, D("2000000"))
        self.assertEqual(line.fact_amount, 0)
        r = self.client.post(reverse("finance_line_edit", args=[line.pk]), {
            "construction_object": self.b.pk, "section": "material", "name": "Гипсокартон 12,5 мм",
            "plan_amount": "2100000", "fact_amount": "500 000", "note": "Аванс"})
        line.refresh_from_db()
        self.assertEqual((line.name, line.plan_amount, line.fact_amount), ("Гипсокартон 12,5 мм", D("2100000"),
                                                                             D("500000")))
        self.assertEqual(line.fact_date, date.today())  # факт без даты — сегодня
        self.assertTrue(AuditLog.objects.filter(object_id=str(line.pk)).exists())
        self.client.post(reverse("finance_line_delete", args=[line.pk]))
        self.assertFalse(PlanLine.objects.filter(pk=line.pk).exists())

    def test_object_required_except_debt(self):
        r = self.client.post(reverse("finance_line_new"), {"section": "labor", "name": "Без объекта",
                                                            "plan_amount": "100"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PlanLine.objects.filter(name="Без объекта").exists())
        self.client.post(reverse("finance_line_new"), {"section": "debt", "name": "Казгер", "plan_amount": "3000000",
                                                       "construction_object": self.a.pk})
        self.assertIsNone(PlanLine.objects.get(name="Казгер").construction_object)  # долг — не по объекту

    def test_pay_partial_and_full(self):
        url = reverse("finance_line_pay", args=[self.brig.pk])
        self.client.post(url, {"amount": "500 000", "date": "2026-11-20"})
        self.brig.refresh_from_db()
        self.assertEqual(self.brig.fact_amount, D("500000"))
        self.assertEqual(self.brig.fact_date, date(2026, 11, 20))
        self.assertEqual(self.brig.left, D("1000000"))
        self.client.post(url, {})  # без суммы — весь остаток
        self.brig.refresh_from_db()
        self.assertEqual(self.brig.left, 0)
        self.assertTrue(self.brig.is_done)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_calendar_groups(self):
        cal = services.calendar(list(PlanLine.objects.select_related("construction_object")))
        titles = [g["title"] for g in cal["groups"]]
        self.assertEqual(titles[0], "Просрочено")
        self.assertEqual(titles[-1], "Без даты")
        self.assertEqual(cal["in"], D("25000000") + D("32000000"))
        self.assertNotIn("Материальные расходы", [ln.name for g in cal["groups"] for ln in g["lines"]])  # оплачено

    def test_attention_lists_overdue_and_notes(self):
        items = services.attention(list(PlanLine.objects.select_related("construction_object")))
        self.assertIn(("bad", self.brig.pk), [(lvl, ln.pk) for lvl, _, ln, _ in items])
        self.assertTrue(any(lvl == "info" and "уточнить" in why for lvl, why, _, _ in items))

    def test_header_picker_opens_object_plan(self):
        r = self.client.get(reverse("finance_home"))
        self.assertContains(r, f'href="{reverse("finance_object", args=[self.a.pk])}" data-obj="{self.a.pk}"')
