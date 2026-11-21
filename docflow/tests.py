import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from company.models import Company
from staff.models import Employee, Position

from . import services
from .models import ArchiveRecord, CaseFile, DocTask, Document, Journal, Seal, SealUsage, Template

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class DocflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("boss", password="pass12345", last_name="Балтаев")
        director = Employee.objects.create(full_name="Балтаев Нурбек Шарипжанұлы",
                                           position=Position.objects.create(name="Директор"))
        cls.deputy = Employee.objects.create(full_name="Абдужаббаров Максадбек Хусанович")
        Company.objects.create(name="ТОО «Paramount Buildings»", bin="210540033211", director=director)
        cls.out = Journal.objects.create(name="Исходящие", kind="outgoing", prefix="ИСХ", digits=4)
        cls.inc = Journal.objects.create(name="Входящие", kind="incoming", prefix="ВХ", digits=4)
        Journal.objects.create(name="Приказы", kind="order", suffix="ОД", use_year=False, digits=1)
        cls.case = CaseFile.objects.create(index="01-03", title="Исходящая корреспонденция",
                                           doc_types="Исходящие письма")
        cls.tpl = Template.objects.create(name="Основной бланк", code="BLANK-MAIN", is_letterhead=True)
        cls.seal = Seal.objects.create(name="Основная печать", kind="seal")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.user)

    def test_numbers_are_unique_and_sequential(self):
        year = date.today().year
        nums = [self.out.next_number() for _ in range(3)]
        self.assertEqual(nums, [f"ИСХ-{year}-0001", f"ИСХ-{year}-0002", f"ИСХ-{year}-0003"])
        order = Journal.objects.get(kind="order")
        self.assertEqual(order.next_number(), "1-ОД")

    def test_pages_open(self):
        doc = Document.objects.create(kind="order", title="О тесте", status="draft")
        for name in ["docflow_home", "docflow_all", "docflow_orders", "docflow_letters", "docflow_letters_out",
                     "docflow_letters_internal", "docflow_contracts", "docflow_tasks", "docflow_cases",
                     "docflow_journals", "docflow_templates", "docflow_seals", "docflow_archive", "docflow_letter",
                     "docflow_task_new"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for kind in ["order", "incoming", "outgoing", "internal", "contract"]:
            self.assertEqual(self.client.get(reverse("docflow_new", args=[kind])).status_code, 200, kind)
        self.assertEqual(self.client.get(reverse("docflow_detail", args=[doc.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("docflow_journal", args=[self.out.pk])).status_code, 200)

    def test_letter_generator_registers_and_logs_seal(self):
        r = self.client.post(reverse("docflow_letter"), {
            "template": self.tpl.pk, "addressee": "Директору ТОО «Заказчик»", "subject": "О графике",
            "body": "Первый абзац.\nВторой абзац.", "sign_mode": "both", "seal": self.seal.pk})
        doc = Document.objects.get(kind="outgoing")
        self.assertRedirects(r, reverse("docflow_detail", args=[doc.pk]) + "?done=1")
        self.assertTrue(doc.number.startswith("ИСХ-"))
        self.assertEqual(doc.status, "registered")
        self.assertTrue(doc.file.name.endswith(".pdf"))
        self.assertEqual(doc.journal, self.out)
        self.assertEqual(SealUsage.objects.filter(document=doc).count(), 1)
        self.assertTrue(doc.events.filter(kind="register").exists())

    def test_letter_generator_requires_sign_question(self):
        r = self.client.post(reverse("docflow_letter"), {
            "template": self.tpl.pk, "addressee": "Кому", "subject": "Тема", "body": "Текст"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Document.objects.exists())
        self.assertEqual(self.out.documents.count(), 0)

    def test_approval_flow_and_reason_required(self):
        doc = Document.objects.create(kind="outgoing", title="Письмо", counterparty="ТОО", status="draft")
        doc.approvals.create(step=1, role="approver", employee=self.deputy)
        doc.approvals.create(step=2, role="signer", employee=Employee.objects.get(full_name__startswith="Балтаев"))
        url = reverse("docflow_action", args=[doc.pk])
        self.client.post(url, {"action": "to_approval"})
        doc.refresh_from_db()
        self.assertEqual(doc.status, "approval")
        self.client.post(url, {"action": "reject", "reason": ""})
        doc.refresh_from_db()
        self.assertEqual(doc.status, "approval")  # без причины не отклоняется
        self.client.post(url, {"action": "approve"})
        doc.refresh_from_db()
        self.assertEqual(doc.status, "signing")
        self.client.post(url, {"action": "sign"})
        doc.refresh_from_db()
        self.assertEqual(doc.status, "registered")
        self.assertTrue(doc.number)
        self.assertTrue(doc.is_locked)

    def test_incoming_needs_file_and_archive_needs_case(self):
        doc = Document.objects.create(kind="incoming", title="Письмо", counterparty="ТОО", status="registering")
        with self.assertRaises(services.ActionError):
            services.apply_action(doc, "register", self.user)
        doc.status = "executed"
        doc.save()
        with self.assertRaises(services.ActionError):
            services.archive(doc, self.user)
        doc.case = self.case
        doc.save()
        DocTask.objects.create(title="Ответить", document=doc, assignee=self.deputy, due=date.today())
        with self.assertRaises(services.ActionError):
            services.archive(doc, self.user)
        doc.tasks.update(status="done")
        services.archive(doc, self.user)
        self.assertEqual(ArchiveRecord.objects.get(document=doc).case, self.case)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "archived")

    def test_task_postpone_needs_reason(self):
        t = DocTask.objects.create(title="Сделать", assignee=self.deputy, due=date.today())
        url = reverse("docflow_task_act", args=[t.pk])
        self.client.post(url, {"act": "postpone", "due": str(date.today() + timedelta(3)), "reason": ""})
        t.refresh_from_db()
        self.assertEqual(t.due, date.today())
        self.client.post(url, {"act": "postpone", "due": str(date.today() + timedelta(3)), "reason": "Ждём поставку"})
        t.refresh_from_db()
        self.assertEqual(t.due, date.today() + timedelta(3))
        self.client.post(url, {})
        t.refresh_from_db()
        self.assertEqual(t.status, "accepted")
