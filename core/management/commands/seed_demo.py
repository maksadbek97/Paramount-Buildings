"""Заполняет базу демонстрационными данными (для демо-версии на GitHub Pages)."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contracts.models import Assignment, Crew, Payment, WorkContract, WorkLog

from finance.models import Estimate, EstimateItem, Transaction
from objects.models import Client, ConstructionObject
from staff.models import Employee, Position, Task
from warehouse.models import Material, StockMovement, Supplier


class Command(BaseCommand):
    help = "Создаёт демонстрационные объекты, сотрудников, материалы и финансы."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Добавить данные, даже если база не пуста.")

    @transaction.atomic
    def handle(self, *args, **options):
        if ConstructionObject.objects.exists() and not options["force"]:
            raise CommandError("В базе уже есть объекты. Используйте --force, чтобы всё равно добавить демо-данные.")

        today = date.today()
        d = lambda days: today + timedelta(days=days)  # noqa: E731

        pos = {name: Position.objects.create(name=name) for name in
               ["Прораб", "Инженер ПТО", "Сметчик", "Бухгалтер", "Каменщик", "Электрик"]}
        emp = {}
        for full_name, position, phone in [
            ("Каримов Азиз Рустамович", "Прораб", "+998 90 123-45-67"),
            ("Юсупова Дилноза Бахтиёровна", "Инженер ПТО", "+998 91 234-56-78"),
            ("Петров Сергей Иванович", "Сметчик", "+998 93 345-67-89"),
            ("Рахимова Нигора Алишеровна", "Бухгалтер", "+998 94 456-78-90"),
            ("Тошматов Бекзод Олимович", "Каменщик", "+998 97 567-89-01"),
            ("Ли Виктор Андреевич", "Электрик", "+998 99 678-90-12"),
        ]:
            emp[full_name.split()[0]] = Employee.objects.create(
                full_name=full_name, position=pos[position], phone=phone,
                hired_at=d(-400), salary=Decimal("6000000"),
            )

        c1 = Client.objects.create(name="ООО «Ташкент Сити Девелопмент»", phone="+998 71 200-10-10")
        c2 = Client.objects.create(name="Частный заказчик Абдуллаев А.", phone="+998 90 111-22-33")
        c3 = Client.objects.create(name="ГУП «Обод махалла»", phone="+998 71 233-44-55")

        o1 = ConstructionObject.objects.create(
            name="Жилой комплекс «Навруз», корпус 2", address="г. Ташкент, Юнусабадский р-н, ул. Амира Темура, 108",
            client=c1, manager=emp["Каримов"], status="in_progress", start_date=d(-180), end_date=d(240),
            description="9-этажный монолитный жилой дом на 72 квартиры.",
        )
        o2 = ConstructionObject.objects.create(
            name="Частный дом в Кибрае", address="Ташкентская обл., Кибрайский р-н", client=c2,
            manager=emp["Юсупова"], status="in_progress", start_date=d(-60), end_date=d(120),
            description="Двухэтажный дом 240 м², газоблок, монолитные перекрытия.",
        )
        o3 = ConstructionObject.objects.create(
            name="Реконструкция школы №45", address="г. Ташкент, Чиланзарский р-н", client=c3,
            manager=emp["Каримов"], status="planned", start_date=d(30), end_date=d(300),
        )
        o4 = ConstructionObject.objects.create(
            name="Офисный центр «Минор»", address="г. Ташкент, Мирзо-Улугбекский р-н", client=c1,
            manager=emp["Юсупова"], status="paused", start_date=d(-300), end_date=d(60),
            description="Работы приостановлены до согласования проекта фасада.",
        )
        o5 = ConstructionObject.objects.create(
            name="Склад логистической компании", address="г. Ташкент, Сергелийский р-н", client=c1,
            manager=emp["Каримов"], status="done", start_date=d(-500), end_date=d(-90),
        )

        for title, obj, who, status, prio, due in [
            ("Заливка перекрытия 6-го этажа", o1, "Каримов", "in_progress", 3, d(5)),
            ("Приёмка арматуры", o1, "Юсупова", "new", 2, d(3)),
            ("Кладка стен 7-го этажа", o1, "Тошматов", "new", 2, d(20)),
            ("Разводка электрики в подвале", o1, "Ли", "in_progress", 2, d(12)),
            ("Устройство фундамента", o2, "Тошматов", "done", 3, d(-20)),
            ("Кладка стен первого этажа", o2, "Тошматов", "in_progress", 3, d(10)),
            ("Согласовать смету на кровлю", o2, "Петров", "new", 2, d(7)),
            ("Обследование здания школы", o3, "Юсупова", "new", 2, d(25)),
            ("Подготовить смету реконструкции", o3, "Петров", "in_progress", 3, d(14)),
            ("Согласование фасада с заказчиком", o4, "Юсупова", "new", 1, d(30)),
            ("Сдать акты выполненных работ", o5, "Рахимова", "done", 2, d(-95)),
        ]:
            Task.objects.create(title=title, construction_object=obj, assignee=emp[who],
                                status=status, priority=prio, due_date=due)

        s1 = Supplier.objects.create(name="ООО «Кызылкумцемент»", phone="+998 79 223-00-00")
        s2 = Supplier.objects.create(name="ЧП «Арматура Сервис»", phone="+998 71 250-50-50")
        s3 = Supplier.objects.create(name="ООО «Газоблок Плюс»", phone="+998 71 260-60-60")
        mats = {}
        for name, unit, price, min_stock in [
            ("Цемент М400", "мешок", "65000", "200"),
            ("Арматура Ø12", "т", "9800000", "5"),
            ("Газоблок D500", "м³", "780000", "30"),
            ("Песок", "м³", "120000", "40"),
            ("Кабель ВВГ 3×2,5", "м", "14500", "500"),
            ("Кирпич облицовочный", "шт", "2400", "5000"),
        ]:
            mats[name] = Material.objects.create(name=name, unit=unit, price=Decimal(price), min_stock=Decimal(min_stock))
        for mat, kind, qty, days, sup, obj in [
            ("Цемент М400", "in", "800", -40, s1, None),
            ("Цемент М400", "out", "450", -20, None, o1),
            ("Цемент М400", "out", "210", -6, None, o2),
            ("Арматура Ø12", "in", "18", -35, s2, None),
            ("Арматура Ø12", "out", "11", -10, None, o1),
            ("Газоблок D500", "in", "120", -25, s3, None),
            ("Газоблок D500", "out", "45", -4, None, o2),
            ("Песок", "in", "150", -30, None, None),
            ("Песок", "out", "125", -3, None, o1),
            ("Кабель ВВГ 3×2,5", "in", "2000", -15, None, None),
            ("Кабель ВВГ 3×2,5", "out", "600", -2, None, o1),
            ("Кирпич облицовочный", "in", "12000", -50, None, None),
        ]:
            StockMovement.objects.create(material=mats[mat], kind=kind, quantity=Decimal(qty), date=d(days),
                                         supplier=sup, construction_object=obj)

        for obj, title, items in [
            (o1, "Монолитные работы, корпус 2", [
                ("Бетон В25", "м³", "950", "780000"), ("Арматура Ø12", "т", "85", "9800000"),
                ("Работы по бетонированию", "м³", "950", "150000")]),
            (o2, "Коробка дома", [
                ("Газоблок D500", "м³", "110", "780000"), ("Кладочные работы", "м³", "110", "250000"),
                ("Перекрытия", "м²", "240", "420000")]),
            (o3, "Реконструкция кровли и фасада", [
                ("Кровельное покрытие", "м²", "1200", "185000"), ("Утепление фасада", "м²", "2100", "230000")]),
        ]:
            est = Estimate.objects.create(construction_object=obj, title=title)
            for name, unit, qty, price in items:
                EstimateItem.objects.create(estimate=est, name=name, unit=unit,
                                            quantity=Decimal(qty), unit_price=Decimal(price))

        for obj, kind, amount, days, category in [
            (o1, "income", "2500000000", -150, "Аванс заказчика"),
            (o1, "expense", "780000000", -120, "Материалы"),
            (o1, "expense", "420000000", -60, "Зарплата"),
            (o1, "income", "1200000000", -30, "Оплата этапа"),
            (o1, "expense", "310000000", -8, "Материалы"),
            (o2, "income", "350000000", -55, "Аванс заказчика"),
            (o2, "expense", "190000000", -40, "Материалы"),
            (o2, "expense", "95000000", -10, "Субподряд"),
            (o4, "income", "600000000", -280, "Аванс заказчика"),
            (o4, "expense", "540000000", -200, "Материалы"),
            (o5, "income", "1800000000", -100, "Окончательный расчёт"),
            (o5, "expense", "1350000000", -110, "Материалы и работы"),
            (None, "expense", "45000000", -5, "Аренда офиса"),
        ]:
            Transaction.objects.create(construction_object=obj, kind=kind, amount=Decimal(amount),
                                       date=d(days), category=category)

        self.seed_subcontract(d, pos, emp, o1, o2, o4, o5)
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы."))

    def seed_subcontract(self, d, pos, emp, o1, o2, o4, o5):
        """Субподряд: объёмы у генподрядчика, бригады, выработка, платежи."""
        pos["Подсобник"] = Position.objects.create(name="Подсобник")
        pos["Штукатур"] = Position.objects.create(name="Штукатур")
        pos["Арматурщик"] = Position.objects.create(name="Арматурщик")
        workers = {}
        for full_name, position, phone in [
            ("Эргашев Шерзод", "Каменщик", "+998 90 701-11-11"),
            ("Холматов Улугбек", "Каменщик", "+998 90 702-22-22"),
            ("Норматов Жасур", "Подсобник", "+998 91 703-33-33"),
            ("Саидов Фаррух", "Каменщик", "+998 93 704-44-44"),
            ("Мирзаев Отабек", "Подсобник", "+998 94 705-55-55"),
            ("Абдуллаев Санжар", "Штукатур", "+998 97 706-66-66"),
            ("Курбанов Достон", "Арматурщик", "+998 99 707-77-77"),
        ]:
            workers[full_name.split()[0]] = Employee.objects.create(
                full_name=full_name, position=pos[position], phone=phone, hired_at=d(-120))

        crew1 = Crew.objects.create(name="Бригада Тошматова", leader=emp["Тошматов"], phone="+998 97 567-89-01")
        crew1.members.set([emp["Тошматов"], workers["Эргашев"], workers["Холматов"], workers["Норматов"]])
        crew2 = Crew.objects.create(name="Бригада Саидова", leader=workers["Саидов"], phone="+998 93 704-44-44")
        crew2.members.set([workers["Саидов"], workers["Мирзаев"]])

        def contract(obj, work, unit, volume, price, start, end, status="active"):
            return WorkContract.objects.create(
                construction_object=obj, work_type=work, unit=unit, volume=Decimal(volume),
                price=Decimal(price), start_date=d(start), end_date=d(end), status=status)

        k1 = contract(o1, "Кладка газоблока D500", "м³", "1800", "280000", -45, 75)
        k2 = contract(o1, "Штукатурка стен", "м²", "9500", "65000", -20, 120)
        k3 = contract(o2, "Кладка газоблока", "м³", "110", "300000", -30, 10)
        k4 = contract(o4, "Утепление фасада", "м²", "2100", "120000", 15, 90, status="paused")
        k5 = contract(o5, "Вязка арматуры", "т", "85", "1500000", -200, -100, status="done")

        a1 = Assignment.objects.create(contract=k1, crew=crew1, pay_type="unit", rate=Decimal("160000"),
                                       planned_volume=Decimal("1200"))
        a2 = Assignment.objects.create(contract=k1, crew=crew2, pay_type="unit", rate=Decimal("165000"),
                                       planned_volume=Decimal("600"))
        a3 = Assignment.objects.create(contract=k2, employee=workers["Абдуллаев"], pay_type="day",
                                       rate=Decimal("300000"))
        a4 = Assignment.objects.create(contract=k3, crew=crew2, pay_type="unit", rate=Decimal("170000"))
        a5 = Assignment.objects.create(contract=k5, employee=workers["Курбанов"], pay_type="unit",
                                       rate=Decimal("800000"))

        pattern = ["24", "31", "28", "0", "35", "30", "26", "33", "29", "0", "32", "27"]
        for i in range(1, 37):
            v = Decimal(pattern[i % len(pattern)])
            if v:
                WorkLog.objects.create(assignment=a1, date=d(-i), volume=v, people=4)
            if i % 2 == 0 and i <= 30:
                WorkLog.objects.create(assignment=a2, date=d(-i), volume=Decimal("14") + i % 5, people=2)
        for i in range(1, 15):
            WorkLog.objects.create(assignment=a3, date=d(-i), volume=Decimal("38") + i % 4 * 3, people=2,
                                   note="с подсобником" if i % 3 == 0 else "")
        for i in range(12, 30, 2):
            WorkLog.objects.create(assignment=a4, date=d(-i), volume=Decimal("10.5"), people=2)
        for i in range(0, 85, 5):
            WorkLog.objects.create(assignment=a5, date=d(-190 + i), volume=Decimal("5"), people=1)

        for k, kind, assignment, amount, days, note in [
            (k1, "income", None, "120000000", -40, "Аванс 30%"),
            (k1, "income", None, "95000000", -10, "Акт за месяц"),
            (k1, "worker", a1, "60000000", -25, "Аванс бригаде"),
            (k1, "worker", a1, "48000000", -5, "За 2 недели"),
            (k1, "worker", a2, "30000000", -8, ""),
            (k1, "material", None, "6500000", -30, "Клей для газоблока, инструмент"),
            (k2, "income", None, "25000000", -15, "Аванс"),
            (k2, "worker", a3, "4200000", -7, "За неделю"),
            (k2, "material", None, "3800000", -18, "Сетка, маяки"),
            (k3, "income", None, "33000000", -6, "Полная оплата"),
            (k3, "worker", a4, "15300000", -10, "Расчёт"),
            (k5, "income", None, "127500000", -95, "Окончательный расчёт"),
            (k5, "worker", a5, "68000000", -98, "Полный расчёт"),
            (k5, "other", None, "2000000", -150, "Доставка рабочих"),
        ]:
            Payment.objects.create(contract=k, kind=kind, assignment=assignment, amount=Decimal(amount),
                                   date=d(days), note=note)
