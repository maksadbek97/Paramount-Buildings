"""Раздел «Объекты» (ТЗ модуля «Объект»): создание, права, статусы, закрытие по чек-листу, вкладки."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from contracts.models import WorkContract
from core.models import AuditLog
from staff.models import Employee, Task

from .models import Client, ConstructionObject, SafetyRecord, TransportRequest


class ObjectModuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = get_user_model().objects.create_superuser("boss", password="x")
        cls.clerk = get_user_model().objects.create_user("clerk", password="x")
        cls.client_org = Client.objects.create(name="ТОО Заказчик")
        cls.manager = Employee.objects.create(full_name="Ким Сергей Викторович")
        cls.obj = ConstructionObject.objects.create(code="AST-01", name="ЖК Атлант", city="Астана",
                                                    status="in_progress", client=cls.client_org, budget=1000)

    def setUp(self):
        self.client.force_login(self.boss)

    def form(self, **kw):
        data = {"name": "Школа", "kind": "social", "client": self.client_org.pk, "manager": self.manager.pk,
                "city": "Астана", "start_date": "2026-12-01", "end_date": "2027-09-01", "status": "preparing",
                "action": "create_open"}
        data.update(kw)
        return data

    # --- создание (ТЗ п. 5) ---
    def test_create_generates_unique_code_audits_and_opens_card(self):
        r = self.client.post(reverse("object_create"), self.form())
        obj = ConstructionObject.objects.get(name="Школа")
        self.assertRedirects(r, reverse("object_detail", args=[obj.pk]))
        self.assertEqual(obj.code, "AST-02")  # AST-01 уже занят
        self.assertTrue(AuditLog.objects.filter(construction_object=obj, action="create").exists())

    def test_create_button_returns_to_list(self):
        r = self.client.post(reverse("object_create"), self.form(action="create"))
        self.assertRedirects(r, reverse("object_list"))

    def test_validation_errors_shown_next_to_fields_and_nothing_saved(self):
        r = self.client.post(reverse("object_create"), self.form(code="ast-01", end_date="2026-01-01",
                                                                 client="", coordinates="abc"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "уже занят")
        self.assertContains(r, "раньше даты начала")
        self.assertContains(r, "Выберите заказчика")
        self.assertContains(r, "широту и долготу")
        self.assertFalse(ConstructionObject.objects.filter(name="Школа").exists())

    def test_draft_needs_only_name(self):
        self.client.post(reverse("object_create"), {"name": "Черновик", "action": "draft"})
        d = ConstructionObject.objects.get(name="Черновик")
        self.assertEqual(d.status, "planned")
        self.assertEqual(d.code, "OBJ-01")

    def test_rights_are_checked_on_server(self):
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.get(reverse("object_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("object_edit", args=[self.obj.pk])).status_code, 403)
        r = self.client.post(reverse("object_status", args=[self.obj.pk]), {"action": "pause", "reason": "x"})
        self.assertEqual(r.status_code, 403)
        self.clerk.user_permissions.add(Permission.objects.get(codename="change_constructionobject"))
        self.assertEqual(self.client.get(reverse("object_edit", args=[self.obj.pk])).status_code, 200)
        r = self.client.post(reverse("object_status", args=[self.obj.pk]), {"action": "close"})
        self.assertEqual(r.status_code, 403)  # закрывать может только руководитель с правом close_object

    # --- статусы ---
    def test_pause_needs_reason_and_resume_restores_status(self):
        url = reverse("object_status", args=[self.obj.pk])
        self.client.post(url, {"action": "pause"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "in_progress")
        self.client.post(url, {"action": "pause", "reason": "нет финансирования"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "paused")
        self.assertTrue(AuditLog.objects.filter(construction_object=self.obj, reason="нет финансирования").exists())
        self.client.post(url, {"action": "resume"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "in_progress")

    def test_archive_only_after_close(self):
        self.client.post(reverse("object_status", args=[self.obj.pk]), {"action": "archive"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "in_progress")

    # --- закрытие (ТЗ п. 25) ---
    def test_close_blocked_by_open_items_then_allowed(self):
        task = Task.objects.create(title="Сдать акт", construction_object=self.obj, assignee=self.manager)
        contract = WorkContract.objects.create(construction_object=self.obj, work_type="Кладка", volume=1, price=1)
        TransportRequest.objects.create(construction_object=self.obj, kind="crane", task="Подача", date=date.today())
        SafetyRecord.objects.create(construction_object=self.obj, kind="incident", title="Падение", date=date.today())
        url = reverse("object_status", args=[self.obj.pk])
        r = self.client.post(url, {"action": "close"})
        self.assertRedirects(r, reverse("object_tab", args=[self.obj.pk, "closing"]))
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "in_progress")
        r = self.client.get(reverse("object_tab", args=[self.obj.pk, "closing"]))
        blocking = {i["key"] for i in r.context["blocking"]}
        self.assertEqual(blocking, {"works", "tasks", "transport", "safety"})
        self.assertContains(r, "Закрыть пока нельзя")
        task.status = "done"
        task.save()
        contract.status = "done"
        contract.save()
        TransportRequest.objects.update(status="done")
        SafetyRecord.objects.update(confirmed=True)
        self.client.post(url, {"action": "close"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "done")
        self.client.post(url, {"action": "archive"})
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "archive")

    # --- вкладки и данные ---
    def test_all_tabs_and_forms_open(self):
        from core.object_views import NEW, TABS
        for key, *_ in TABS:
            url = reverse("object_detail", args=[self.obj.pk]) if key == "overview" else \
                reverse("object_tab", args=[self.obj.pk, key])
            self.assertEqual(self.client.get(url).status_code, 200, key)
        for what in NEW:
            self.assertEqual(self.client.get(reverse("object_new", args=[self.obj.pk, what])).status_code, 200, what)

    def test_transport_and_safety_created_inside_object(self):
        r = self.client.post(reverse("object_new", args=[self.obj.pk, "transport"]), {
            "construction_object": self.obj.pk, "kind": "crane", "task": "Подача блоков", "date": "2026-12-01",
            "status": "new", "cost": "0"})
        self.assertRedirects(r, reverse("object_tab", args=[self.obj.pk, "transport"]))
        t = TransportRequest.objects.get()
        self.assertTrue(t.number.startswith("ТР-"))
        r = self.client.post(reverse("object_new", args=[self.obj.pk, "safety"]), {
            "construction_object": self.obj.pk, "kind": "permit", "title": "Допуск на высоту", "date": "2026-11-01"})
        self.assertContains(r, "срок действия")
        SafetyRecord.objects.create(construction_object=self.obj, kind="permit", title="Стропальщик",
                                    date=date.today(), valid_until=date.today() - timedelta(days=1), confirmed=True)
        r = self.client.get(reverse("object_tab", args=[self.obj.pk, "safety"]))
        self.assertContains(r, "Просрочены допуски: 1")
        # заявка на технику сразу видна в согласованиях и в реестре документов
        self.assertContains(self.client.get(reverse("object_tab", args=[self.obj.pk, "approvals"])), t.number)
        self.assertContains(self.client.get(reverse("object_tab", args=[self.obj.pk, "docs"])), t.number)

    def test_list_shows_budget_deviation_and_export_columns(self):
        from finance.models import Transaction
        Transaction.objects.create(construction_object=self.obj, kind="expense", amount=1500, date=date.today())
        r = self.client.get(reverse("object_list"))
        row = r.context["rows"][0]
        self.assertTrue(row["over"])
        self.assertEqual(row["deviation"], -500)
        self.assertIn("Отклонение бюджета, ₸", r.context["export"][0])
        self.assertContains(r, "перерасход")
