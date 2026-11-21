from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from staff.models import Employee, Position

from .models import BankAccount, Company, CompanyDocument, Department, StaffUnit


class CompanySectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("boss", password="x", first_name="Нурбек",
                                                             last_name="Балтаев")
        cls.pos = Position.objects.create(name="Прораб")
        cls.dep = Department.objects.create(name="Участок")
        cls.e = Employee.objects.create(full_name="Иванов Иван", position=cls.pos, department=cls.dep, salary=500000)
        StaffUnit.objects.create(department=cls.dep, position=cls.pos, count=3, salary=Decimal(500000))
        Company.objects.create(name="ТОО «Тест»", bin="123456789012", director=cls.e)
        BankAccount.objects.create(bank="Банк", bik="HSBKKZKX", iban="KZ866010111000123456", is_main=True)
        cls.late = CompanyDocument.objects.create(kind="certificate", title="Справка об отсутствии долга",
                                                  valid_until=date.today() + timedelta(days=3))
        CompanyDocument.objects.create(kind="order", number="1-ОД", title="Об утверждении штатного")

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_tabs_open(self):
        for name in ["company_profile", "company_docs", "company_structure", "company_staff", "company_schedule",
                     "company_edit", "company_doc_new", "company_employee_new", "company_unit_new",
                     "company_department_new", "company_account_new", "profile"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_profile_requisites_and_attention(self):
        r = self.client.get(reverse("company_profile"))
        self.assertContains(r, "123456789012")
        self.assertContains(r, "KZ86 6010 1110 0012 3456")
        self.assertContains(r, "Справка об отсутствии долга")  # истекает через 3 дня
        self.assertContains(r, "Моя компания")

    def test_docs_filter(self):
        r = self.client.get(reverse("company_docs") + "?kind=order")
        self.assertContains(r, "Об утверждении штатного")
        self.assertNotContains(r, "Справка об отсутствии долга")
        r = self.client.get(reverse("company_docs") + "?kind=expiring")
        self.assertContains(r, "Справка об отсутствии долга")

    def test_schedule_counts_vacancies(self):
        r = self.client.get(reverse("company_schedule"))
        self.assertEqual(r.context["total"]["vacant"], 2)
        self.assertEqual(r.context["total"]["fund"], Decimal(1500000))

    def test_staff_filter_by_department(self):
        Employee.objects.create(full_name="Без отдела")
        r = self.client.get(reverse("company_staff") + f"?dept={self.dep.pk}")
        self.assertContains(r, "Иванов Иван")
        self.assertNotContains(r, "Без отдела")

    def test_salary_hidden_without_permission(self):
        u = get_user_model().objects.create_user("worker", password="x")
        self.client.force_login(u)
        r = self.client.get(reverse("company_staff"))
        self.assertNotContains(r, "500 000")

    def test_main_account_is_unique(self):
        self.client.post(reverse("company_account_new"), {"bank": "Второй", "iban": "KZ11 2222 3333 4444 5555",
                                                         "currency": "KZT", "is_main": "on"})
        self.assertEqual(BankAccount.objects.filter(is_main=True).count(), 1)
        self.assertEqual(BankAccount.objects.get(is_main=True).iban, "KZ112222333344445555")

    def test_header_shows_user_name_and_menu(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Балтаев Нурбек")
        self.assertContains(r, ">Профиль</a>")
        self.assertContains(r, "Выйти</button>")

    def test_brigade_workers_not_in_staff(self):
        Employee.objects.create(full_name="Рабочий Бригады", in_staff=False)
        r = self.client.get(reverse("company_staff"))
        self.assertNotContains(r, "Рабочий Бригады")
        self.assertContains(r, "Иванов Иван")
