import json
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import AuditLog
from objects.models import ConstructionObject

from . import services, state
from .models import ObjectContract, PlanLine, WorkAct

S = PlanLine.Section


class FinPlanTests(TestCase):
    """Финплан по шаблону «Фин план до 2026 года»: таблица, сохранение правок, договоры, АВР, уведомления."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("boss", password="pass12345")
        cls.a = ConstructionObject.objects.create(name="Daryn", status="in_progress")
        cls.b = ConstructionObject.objects.create(name="Arna", status="in_progress")
        mk = PlanLine.objects.create
        cls.inc = mk(construction_object=cls.a, section=S.INCOME, name="Поступление от заказчика",
                     plan_amount=D("35000000"), fact_amount=D("10000000"))
        cls.brig = mk(construction_object=cls.a, section=S.LABOR, name="Бригада работа", plan_amount=D("1500000"))
        mk(construction_object=cls.a, section=S.MATERIAL, name="Материалы", plan_amount=D("400000"),
           fact_amount=D("650000"))
        cls.debt = mk(section=S.DEBT, name="TOO HARD KZ", plan_amount=D("4000000"), fact_amount=D("1000000"))

    def setUp(self):
        self.client.force_login(self.user)

    def api(self, **body):
        r = self.client.post(reverse("finance_api"), json.dumps(body), content_type="application/json")
        return r.status_code, r.json()

    def test_pages_render_with_table_data(self):
        for url in (reverse("finance_home"), reverse("finance_object", args=[self.a.pk]),
                    reverse("finance_object", args=[self.b.pk]), reverse("finance_debts"), reverse("finance_list"),
                    reverse("object_tab", args=[self.a.pk, "money"])):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, 'id="finState"')
            self.assertContains(r, "fingrid.js")
            self.assertContains(r, "Доход / Расход")
        home = self.client.get(reverse("finance_home")).content.decode()
        self.assertNotIn("+ Объект", home)
        self.assertNotIn("Демо", home)
        self.assertIn(reverse("finance_object", args=[self.b.pk]), home)  # все объекты компании — во вкладках

    def test_state_has_objects_lines(self):
        s = state.state()
        self.assertEqual([o["name"] for o in s["objects"]], ["Daryn", "Arna"])
        line = next(x for x in s["lines"] if x["id"] == self.inc.pk)
        self.assertEqual((line["plan"], line["fact"], line["object"]), (35000000, 10000000, self.a.pk))

    def test_edit_cell_saves(self):
        code, res = self.api(kind="line", op="save", id=self.brig.pk, data={"fact": "500 000", "note": "Аванс"})
        self.assertEqual(code, 200)
        self.brig.refresh_from_db()
        self.assertEqual((self.brig.fact_amount, self.brig.note), (D("500000"), "Аванс"))
        self.assertEqual(self.brig.fact_date, date.today())  # факт без даты — сегодня
        self.assertEqual(res["row"]["fact"], 500000)
        self.assertTrue(AuditLog.objects.filter(object_id=str(self.brig.pk)).exists())

    def test_new_line_and_delete(self):
        code, res = self.api(kind="line", op="save", id=-1, data={"object": self.b.pk, "section": "material",
                                                                   "name": "Гипс белый", "plan": 1140000})
        self.assertEqual(code, 200)
        line = PlanLine.objects.get(pk=res["row"]["id"])
        self.assertEqual((line.construction_object, line.plan_amount), (self.b, D("1140000")))
        self.api(kind="line", op="delete", id=line.pk)
        self.assertFalse(PlanLine.objects.filter(pk=line.pk).exists())

    def test_validation(self):
        code, res = self.api(kind="line", op="save", data={"section": "labor", "name": "Без объекта", "plan": 1})
        self.assertEqual(code, 400)
        self.assertFalse(res["ok"])
        code, _ = self.api(kind="line", op="save", id=self.brig.pk, data={"plan": "abc"})
        self.assertEqual(code, 400)
        code, _ = self.api(kind="nope", op="save", data={})
        self.assertEqual(code, 400)
        self.assertEqual(self.client.get(reverse("finance_api")).status_code, 405)

    def test_contracts_and_acts(self):
        code, res = self.api(kind="contract", op="save", data={"object": self.a.pk, "kind": "main", "number": "12",
                                                                "date": "2026-03-01", "amount": "60 000 000"})
        self.assertEqual(code, 200)
        self.api(kind="contract", op="save", data={"object": self.a.pk, "kind": "extra", "number": "12/1",
                                                    "amount": "5000000"})
        self.assertEqual(ObjectContract.objects.filter(construction_object=self.a).count(), 2)
        self.assertEqual(ObjectContract.objects.get(number="12/1").get_kind_display(), "Доп. договор")
        code, res = self.api(kind="act", op="save", data={"object": self.a.pk, "work": "кладка", "amount": 35890462})
        self.assertEqual(code, 200)
        self.assertEqual(WorkAct.objects.get(pk=res["row"]["id"]).amount, D("35890462"))
        code, _ = self.api(kind="contract", op="save", data={"number": "без объекта"})
        self.assertEqual(code, 400)

    def test_overruns_fact_more_than_plan(self):
        items = services.overruns(list(PlanLine.objects.select_related("construction_object")))
        texts = [(lvl, where, text) for lvl, where, text, _ in items]
        self.assertTrue(any(lvl == "bad" and where == "Daryn" and text.startswith("Материальные") for lvl, where, text in texts))
        self.assertTrue(any(lvl == "warn" and "Материалы" in text for lvl, _, text in texts))
        self.assertFalse(any("Поступление" in text for _, _, text in texts))  # поступления сверх плана — не тревога
        r = self.client.get(reverse("notifications"))
        self.assertContains(r, "Финансы: факт больше плана")

    def test_summary_includes_company_debt(self):
        s = services.summary()
        self.assertEqual(s["debt"]["left"], D("3000000"))
        self.assertEqual(s["expense_all"]["plan"], D("1900000") + D("4000000"))


class SeedTests(TestCase):
    def test_only_six_objects_from_table(self):
        call_command("seed_demo", verbosity=0)
        names = sorted(ConstructionObject.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(["Atlant", "Daryn", "Arna", "Nexpo Global", "NAK", "Zerde"]))
        daryn = ConstructionObject.objects.get(name="Daryn")
        inc = PlanLine.objects.filter(construction_object=daryn, section=S.INCOME)
        self.assertEqual(sum(x.fact_amount for x in inc), D("6018000"))  # 4 194 000 + 1 824 000
        self.assertEqual(PlanLine.objects.filter(section=S.DEBT).count(), 18)
        self.assertEqual(WorkAct.objects.count(), 18)
        self.assertEqual(WorkAct.objects.filter(construction_object__isnull=True).count(), 1)  # «Арт кладка»
