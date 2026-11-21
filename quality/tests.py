from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from contracts.models import Assignment, Crew, WorkContract, WorkLog
from core.models import AuditLog
from objects.models import ConstructionObject
from staff.models import Employee, Task

from .models import DailyReport, Remark

TODAY = date.today()


class RemarkFlowTests(TestCase):
    """ТЗ п. 32.3: замечание → задача прорабу → исполнитель с фото → проверка → возврат или закрытие."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.boss = User.objects.create_superuser("boss", password="x")
        cls.foreman_user = User.objects.create_user("foreman", password="x")
        cls.foreman = Employee.objects.create(full_name="Прораб П.")
        cls.worker = Employee.objects.create(full_name="Исполнитель И.")
        cls.obj = ConstructionObject.objects.create(name="ЖК Атлант", foreman=cls.foreman)

    def test_full_cycle(self):
        self.client.force_login(self.boss)
        r = self.client.post(reverse("remark_create"), {
            "construction_object": self.obj.pk, "floor": "5", "place": "кв. 18", "description": "Кладка не по уровню",
            "priority": "3", "deadline": (TODAY + timedelta(days=3)).isoformat()})
        remark = Remark.objects.get()
        self.assertRedirects(r, reverse("remark_detail", args=[remark.pk]))
        self.assertEqual(remark.responsible, self.foreman)  # прораб объекта по умолчанию
        self.assertTrue(remark.number.startswith(f"ЗМ-{TODAY.year}-"))
        self.assertEqual(remark.task.assignee, self.foreman)  # задача поступила прорабу
        self.assertEqual(remark.author, self.boss)

        self.client.force_login(self.foreman_user)
        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "in_work", "executor": self.worker.pk})
        remark.refresh_from_db()
        self.assertEqual((remark.status, remark.executor), ("in_work", self.worker))
        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "review", "comment": "Переложили"})
        remark.refresh_from_db()
        self.assertEqual(remark.status, "review")
        self.assertEqual(Task.objects.get().status, "review")

        # прораб не может сам принять своё замечание
        r = self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "closed"})
        self.assertEqual(r.status_code, 403)

        self.client.force_login(self.boss)
        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "returned", "comment": "Не по уровню"})
        remark.refresh_from_db()
        self.assertEqual(remark.status, "returned")

        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "in_work"})
        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "review"})
        self.client.post(reverse("remark_act", args=[remark.pk]), {"to": "closed"})
        remark.refresh_from_db()
        self.assertEqual(remark.status, "closed")
        self.assertEqual(remark.reviewer, self.boss)
        self.assertEqual(Task.objects.get().status, "done")
        # история сохраняется
        self.assertEqual(AuditLog.objects.filter(module="Замечания", object_id=str(remark.pk)).count(), 7)
        self.assertTrue(AuditLog.objects.filter(action="reject", reason="Не по уровню").exists())

    def test_return_needs_comment_and_numbers_unique(self):
        r1 = Remark.objects.create(construction_object=self.obj, description="А", responsible=self.foreman,
                                   deadline=TODAY, status="review")
        r2 = Remark.objects.create(construction_object=self.obj, description="Б", responsible=self.foreman,
                                   deadline=TODAY - timedelta(days=1))
        self.assertNotEqual(r1.number, r2.number)
        self.assertTrue(r2.is_overdue)
        self.client.force_login(self.boss)
        self.client.post(reverse("remark_act", args=[r1.pk]), {"to": "returned"})
        r1.refresh_from_db()
        self.assertEqual(r1.status, "review")

    def test_repeats(self):
        a = Remark.objects.create(construction_object=self.obj, floor="3", place="кв. 9", description="Трещина",
                                  responsible=self.foreman, deadline=TODAY)
        b = Remark.objects.create(construction_object=self.obj, floor="3", place="КВ. 9", description="Опять",
                                  responsible=self.foreman, deadline=TODAY)
        self.assertEqual(list(b.repeats()), [a])


class TaskFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u", password="x")
        self.client.force_login(self.user)
        self.emp = Employee.objects.create(full_name="Исполнитель")

    def test_task_needs_assignee(self):
        r = self.client.post(reverse("task_create"), {"title": "Без ответственного", "priority": "2",
                                                      "source": "management"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Task.objects.exists())

    def test_statuses_and_close_needs_permission(self):
        t = Task.objects.create(title="Т", assignee=self.emp, due_date=TODAY - timedelta(days=1))
        self.assertTrue(t.is_overdue)
        for expected in ("accepted", "in_progress", "review"):
            self.client.post(reverse("task_next", args=[t.pk]))
            t.refresh_from_db()
            self.assertEqual(t.status, expected)
        r = self.client.post(reverse("task_next", args=[t.pk]))
        self.assertEqual(r.status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="close_task"))
        self.client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self.client.post(reverse("task_next", args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.status, "done")
        self.assertFalse(t.is_overdue)


class DailyReportTests(TestCase):
    def test_report_pulls_worklogs_and_confirms(self):
        user = get_user_model().objects.create_user("f", password="x")
        self.client.force_login(user)
        obj = ConstructionObject.objects.create(name="Объект")
        c = WorkContract.objects.create(construction_object=obj, work_type="Кладка", volume=100, price=1)
        a = Assignment.objects.create(contract=c, crew=Crew.objects.create(name="Б1"), rate=1)
        WorkLog.objects.create(assignment=a, date=TODAY, volume=12)
        r = self.client.post(reverse("report_create"), {
            "construction_object": obj.pk, "date": TODAY.isoformat(), "weather": "snow", "workers_count": "8",
            "problems": "Снег"})
        rep = DailyReport.objects.get()
        self.assertEqual(rep.author, user)
        page = self.client.get(reverse("report_detail", args=[rep.pk]))
        self.assertContains(page, "Кладка")
        self.assertContains(page, "Подтвердить отчёт")
        self.client.post(reverse("report_confirm", args=[rep.pk]))
        rep.refresh_from_db()
        self.assertTrue(rep.confirmed)
        # второй отчёт за тот же день по тому же объекту не создать
        r = self.client.post(reverse("report_create"), {
            "construction_object": obj.pk, "date": TODAY.isoformat(), "weather": "sun", "workers_count": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(DailyReport.objects.count(), 1)
