"""Заполняет базу демонстрационными данными (Казахстан, суммы в тенге)."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contracts.models import Assignment, Crew, MaterialNorm, Payment, WorkContract, WorkLog
from core.models import AuditLog
from quality.models import DailyReport, Remark
from finance.models import Estimate, EstimateItem, Transaction
from objects.models import Client, ConstructionObject
from staff.models import Employee, Position, Task
from warehouse.models import Material, StockMovement, Supplier

D = Decimal


class Command(BaseCommand):
    help = "Создаёт демонстрационные объекты, объёмы, бригады, склад и финансы."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Добавить данные, даже если база не пуста.")

    @transaction.atomic
    def handle(self, *args, **options):
        if ConstructionObject.objects.exists() and not options["force"]:
            raise CommandError("В базе уже есть объекты. Используйте --force, чтобы всё равно добавить демо-данные.")
        today = date.today()
        self.d = lambda days: today + timedelta(days=days)  # noqa: E731
        d = self.d

        # --- сотрудники ---
        pos = {n: Position.objects.create(name=n) for n in [
            "Директор", "Технический директор", "Руководитель проекта", "Инженер ПТО", "Прораб", "Кладовщик",
            "Бухгалтер", "Каменщик", "Подсобник", "Штукатур", "Арматурщик", "Электрик"]}
        emp = {}
        for i, (full_name, position, phone, salary) in enumerate([
            ("Жумабеков Ерлан Маратович", "Директор", "+7 701 100-10-10", 1500000),
            ("Ахметова Динара Сериковна", "Технический директор", "+7 701 200-20-20", 1200000),
            ("Ким Сергей Викторович", "Руководитель проекта", "+7 702 300-30-30", 900000),
            ("Нурланова Айгерим Болатовна", "Инженер ПТО", "+7 705 400-40-40", 650000),
            ("Сейтказиев Бауыржан Ерикович", "Прораб", "+7 707 500-50-50", 700000),
            ("Оспанов Данияр Канатович", "Прораб", "+7 747 600-60-60", 650000),
            ("Исаева Мадина Ринатовна", "Бухгалтер", "+7 708 700-70-70", 550000),
            ("Тулегенов Асхат Нурланович", "Кладовщик", "+7 775 800-80-80", 400000),
        ]):
            emp[full_name.split()[0]] = Employee.objects.create(
                full_name=full_name, position=pos[position], phone=phone, hired_at=d(-600 + i * 30),
                salary=D(salary), iin=f"8{i}0512{300000 + i * 1111}"[:12])
        workers = {}
        for i, (full_name, position) in enumerate([
            ("Абдрахманов Нурсултан", "Каменщик"), ("Касымов Ерасыл", "Каменщик"), ("Байжанов Арман", "Подсобник"),
            ("Мусин Талгат", "Каменщик"), ("Садыков Ринат", "Подсобник"), ("Ибраев Марат", "Штукатур"),
            ("Есенов Алибек", "Штукатур"), ("Жаксылыков Бекзат", "Арматурщик"), ("Рахимов Тимур", "Электрик"),
        ]):
            workers[full_name.split()[0]] = Employee.objects.create(
                full_name=full_name, position=pos[position], phone=f"+7 70{i} 9{i}{i}-1{i}-2{i}",
                hired_at=d(-150), iin=f"9{i}0101{400000 + i * 777}"[:12])

        # --- контрагенты и объекты ---
        c1 = Client.objects.create(name="ТОО «Атлант Девелопмент»", bin="180540012345", phone="+7 717 255-10-10")
        gc1 = Client.objects.create(name="ТОО «Астана Курылыс Груп»", bin="150340098765", phone="+7 717 270-20-20")
        c2 = Client.objects.create(name="ТОО «Алатау Строй Инвест»", bin="170840054321", phone="+7 727 330-30-30")
        c3 = Client.objects.create(name="ГУ «Управление образования г. Шымкент»", bin="990140011122")

        o1 = ConstructionObject.objects.create(
            code="AST-01", name="ЖК «Атлант», блок B", city="Астана", address="пр. Туран, 55",
            client=c1, general_contractor=gc1, contract_number="СП-14/2026", contract_amount=D("812000000"),
            budget=D("560000000"), manager=emp["Ким"], foreman=emp["Сейтказиев"], pto=emp["Нурланова"],
            status="in_progress", start_date=d(-60), end_date=d(150),
            description="12-этажный жилой дом. Субподряд: кладка, штукатурка, армирование.")
        o2 = ConstructionObject.objects.create(
            code="ALA-03", name="Бизнес-центр «Алатау»", city="Алматы", address="пр. Аль-Фараби, 120",
            client=c2, general_contractor=c2, contract_number="СП-09/2026", contract_amount=D("96000000"),
            budget=D("60000000"), manager=emp["Ким"], foreman=emp["Оспанов"], pto=emp["Нурланова"],
            status="finishing", start_date=d(-90), end_date=d(15))
        o3 = ConstructionObject.objects.create(
            code="SHM-02", name="Школа на 600 мест", city="Шымкент", address="мкр. Нурсат",
            client=c3, status="preparing", start_date=d(20), end_date=d(300), contract_amount=D("240000000"),
            manager=emp["Ким"])
        o4 = ConstructionObject.objects.create(
            code="AST-02", name="ЖК «Нурлы Жол»", city="Астана", address="ул. Сарайшык, 7", client=c1,
            general_contractor=gc1, status="paused", start_date=d(-200), end_date=d(90), budget=D("40000000"),
            description="Работы приостановлены до согласования фасада.")
        o5 = ConstructionObject.objects.create(
            code="KRG-01", name="Логистический склад", city="Караганда", address="ул. Складская, 3", client=c2,
            status="done", start_date=d(-400), end_date=d(-120), contract_amount=D("63000000"))

        # --- склад ---
        s1 = Supplier.objects.create(name="ТОО «Central Asia Cement»", phone="+7 721 250-00-00")
        s2 = Supplier.objects.create(name="ТОО «КазМеталл Снаб»", phone="+7 727 260-60-60")
        s3 = Supplier.objects.create(name="ТОО «Газоблок Астана»", phone="+7 717 280-80-80")
        mats = {}
        for name, unit, price, min_stock in [
            ("Цемент М400", "т", "38000", "10"), ("Клей для газоблока", "мешок", "2600", "100"),
            ("Газоблок D500", "м³", "26500", "40"), ("Песок", "м³", "4500", "30"),
            ("Штукатурная смесь", "мешок", "2900", "100"), ("Сетка штукатурная", "м²", "450", "300"),
            ("Арматура Ø12", "т", "345000", "5"), ("Кабель ВВГ 3×2,5", "м", "520", "500"),
        ]:
            mats[name] = Material.objects.create(name=name, unit=unit, price=D(price), min_stock=D(min_stock))

        # --- объёмы (субподряд) ---
        crew1 = Crew.objects.create(name="Бригада Абдрахманова", leader=workers["Абдрахманов"], phone="+7 700 911-10-20")
        crew1.members.set([workers[k] for k in ("Абдрахманов", "Касымов", "Байжанов")])
        crew2 = Crew.objects.create(name="Бригада Мусина", leader=workers["Мусин"], phone="+7 703 933-13-23")
        crew2.members.set([workers["Мусин"], workers["Садыков"]])
        crew3 = Crew.objects.create(name="Штукатуры Ибраева", leader=workers["Ибраев"])
        crew3.members.set([workers["Ибраев"], workers["Есенов"]])

        def contract(obj, work, section, floor, unit, volume, price, start, end, status="active"):
            return WorkContract.objects.create(
                construction_object=obj, work_type=work, section=section, floor=floor, unit=unit,
                volume=D(volume), price=D(price), start_date=d(start), end_date=d(end), status=status,
                responsible=emp["Нурланова"])

        k1 = contract(o1, "Кладка газоблока D500", "B", "1–12", "м³", "3200", "14500", -55, 110)
        k2 = contract(o1, "Штукатурка стен", "B", "1–6", "м²", "10000", "2500", -25, 40)
        k3 = contract(o2, "Кладка перегородок", "1", "1–4", "м³", "420", "15500", -80, 10)
        k4 = contract(o4, "Утепление фасада", "", "", "м²", "4800", "5200", 30, 150, status="paused")
        k5 = contract(o5, "Вязка арматуры", "", "", "т", "120", "65000", -390, -150, status="done")

        MaterialNorm.objects.create(contract=k1, material=mats["Клей для газоблока"], per_unit=D("1.2"))
        MaterialNorm.objects.create(contract=k1, material=mats["Газоблок D500"], per_unit=D("1.03"))
        MaterialNorm.objects.create(contract=k2, material=mats["Штукатурная смесь"], per_unit=D("0.4"))
        MaterialNorm.objects.create(contract=k2, material=mats["Сетка штукатурная"], per_unit=D("1.1"))
        MaterialNorm.objects.create(contract=k3, material=mats["Клей для газоблока"], per_unit=D("1.2"))

        a1 = Assignment.objects.create(contract=k1, crew=crew1, pay_type="unit", rate=D("8500"),
                                       planned_volume=D("2000"))
        a2 = Assignment.objects.create(contract=k1, crew=crew2, pay_type="unit", rate=D("8800"),
                                       planned_volume=D("1200"))
        a3 = Assignment.objects.create(contract=k2, crew=crew3, pay_type="day", rate=D("18000"))
        a4 = Assignment.objects.create(contract=k3, crew=crew2, pay_type="unit", rate=D("9000"))
        a5 = Assignment.objects.create(contract=k5, employee=workers["Жаксылыков"], pay_type="unit", rate=D("30000"))

        def logs(a, days, volumes, people, floor_from=1, pending_last=0):
            for n, i in enumerate(days):
                v = D(volumes[n % len(volumes)])
                if not v:
                    continue
                floor = str(floor_from + n // 6)
                log = WorkLog.objects.create(assignment=a, date=d(-i), volume=v, people=people,
                                             section=a.contract.section, floor=floor)
                if i > pending_last:
                    accepted = v if n % 9 else v - D(2)  # иногда ПТО принимает не всё
                    log.status = WorkLog.Status.ACCEPTED
                    log.accepted_volume = accepted
                    if accepted < v:
                        log.review_note = "Не принято: брак кладки, переделать"
                    log.save()

        logs(a1, range(1, 50), ["38", "44", "41", "0", "47", "40", "36", "45"], 3, pending_last=2)
        logs(a2, range(2, 46, 2), ["22", "25", "19", "24"], 2, pending_last=3)
        logs(a3, range(1, 22), ["160", "185", "170", "0", "190"], 2, pending_last=1)
        logs(a4, range(10, 70, 2), ["12", "14", "13"], 2)
        logs(a5, range(160, 380, 9), ["5"], 1)

        for k, kind, a, amount, days, note in [
            (k1, "income", None, "15000000", -50, "Аванс 30%"),
            (k1, "income", None, "11500000", -20, "Акт №1"),
            (k1, "worker", a1, "8000000", -30, "Аванс бригаде"),
            (k1, "worker", a1, "6500000", -6, "За 2 недели"),
            (k1, "worker", a2, "3000000", -9, ""),
            (k1, "material", None, "2400000", -35, "Клей, инструмент"),
            (k2, "income", None, "8000000", -18, "Аванс"),
            (k2, "worker", a3, "1100000", -7, "За неделю"),
            (k2, "material", None, "1600000", -20, "Маяки, уголки"),
            (k3, "income", None, "5000000", -40, "Аванс"),
            (k3, "worker", a4, "3200000", -12, "Расчёт"),
            (k5, "income", None, "7800000", -140, "Окончательный расчёт"),
            (k5, "worker", a5, "3600000", -145, "Полный расчёт"),
            (k5, "other", None, "250000", -300, "Доставка рабочих"),
        ]:
            Payment.objects.create(contract=k, kind=kind, assignment=a, amount=D(amount), date=d(days), note=note)

        # Движение материалов (расход привязан к виду работ — для план-факта по нормам).
        for mat, kind, qty, days, sup, obj, k in [
            ("Газоблок D500", "in", "2400", -55, s3, None, None),
            ("Газоблок D500", "out", "2250", -10, None, o1, k1),
            ("Клей для газоблока", "in", "3350", -55, s1, None, None),
            ("Клей для газоблока", "out", "2790", -8, None, o1, k1),
            ("Клей для газоблока", "out", "455", -30, None, o2, k3),
            ("Штукатурная смесь", "in", "1400", -25, s1, None, None),
            ("Штукатурная смесь", "out", "1225", -3, None, o1, k2),
            ("Сетка штукатурная", "in", "3600", -25, None, None, None),
            ("Сетка штукатурная", "out", "3150", -3, None, o1, k2),
            ("Цемент М400", "in", "40", -40, s1, None, None),
            ("Цемент М400", "out", "32", -12, None, o1, None),
            ("Песок", "in", "120", -30, None, None, None),
            ("Песок", "out", "95", -4, None, o1, None),
            ("Арматура Ø12", "in", "18", -35, s2, None, None),
            ("Арматура Ø12", "out", "6", -10, None, o1, None),
            ("Кабель ВВГ 3×2,5", "in", "2000", -15, None, None, None),
            ("Кабель ВВГ 3×2,5", "out", "600", -2, None, o2, None),
        ]:
            StockMovement.objects.create(material=mats[mat], kind=kind, quantity=D(qty), date=d(days),
                                         supplier=sup, construction_object=obj, contract=k)

        # --- задачи, сметы, общие финансы ---
        for title, obj, who, status, prio, due, src in [
            ("Принять газоблок на объект", o1, "Тулегенов", "in_progress", 3, d(1), "supply"),
            ("Проверить кладку 7-го этажа", o1, "Нурланова", "accepted", 2, d(3), "pto"),
            ("Подготовить акт за ноябрь", o1, "Нурланова", "new", 3, d(-2), "pto"),
            ("Заявка на штукатурную смесь", o1, "Сейтказиев", "review", 2, d(2), "foreman"),
            ("Согласовать фасад с заказчиком", o4, "Ким", "new", 1, d(30), "management"),
            ("Обследование здания школы", o3, "Ахметова", "new", 2, d(25), "management"),
            ("Сдать исполнительную документацию", o5, "Нурланова", "done", 2, d(-130), "pto"),
        ]:
            Task.objects.create(title=title, construction_object=obj, assignee=emp[who], status=status,
                                priority=prio, due_date=due, source=src)
        est = Estimate.objects.create(construction_object=o1, title="Смета субподряда, блок B")
        for name, unit, qty, price in [("Кладка газоблока D500", "м³", "3200", "14500"),
                                       ("Штукатурка стен", "м²", "10000", "2500")]:
            EstimateItem.objects.create(estimate=est, name=name, unit=unit, quantity=D(qty), unit_price=D(price))
        for obj, kind, amount, days, category in [
            (o1, "expense", "1800000", -40, "Аренда бытовок"),
            (o1, "expense", "950000", -15, "Транспорт"),
            (o2, "expense", "700000", -20, "Аренда подъёмника"),
            (o4, "expense", "41500000", -150, "Материалы и работы"),
            (None, "expense", "850000", -5, "Аренда офиса"),
            (None, "income", "2000000", -60, "Прочие доходы"),
        ]:
            Transaction.objects.create(construction_object=obj, kind=kind, amount=D(amount), date=d(days),
                                       category=category)

        # --- обходы и замечания ---
        status_to_task = {"open": "new", "in_work": "in_progress", "review": "review", "returned": "in_progress",
                          "closed": "done"}
        for obj, sec, fl, place, text, prio, who, days, status, fix in [
            (o1, "B", "5", "кв. 18, оконный проём", "Кладка не по уровню, отклонение 12 мм", 3, "Сейтказиев", 2, "in_work", ""),
            (o1, "B", "4", "лестничная клетка", "Не заполнены вертикальные швы", 2, "Сейтказиев", -1, "open", ""),
            (o1, "B", "3", "кв. 9", "Трещина в штукатурке у откоса", 2, "Сейтказиев", 3, "review", "Перештукатурили откос, сетка"),
            (o1, "B", "2", "техэтаж", "Мусор на этаже, нет ограждения проёма", 4, "Сейтказиев", -3, "returned", ""),
            (o2, "1", "2", "офис 204", "Перегородка не перевязана с несущей стеной", 3, "Оспанов", 1, "open", ""),
            (o2, "1", "1", "холл", "Сколы газоблока у входа", 1, "Оспанов", -10, "closed", "Заменили блоки"),
            (o1, "B", "3", "кв. 9", "Повторно: трещина у откоса после высыхания", 3, "Сейтказиев", 4, "open", ""),
        ]:
            r = Remark.objects.create(
                construction_object=obj, section=sec, floor=fl, place=place, description=text, priority=prio,
                responsible=emp[who], deadline=d(days), status=status, fix_comment=fix,
                executor=workers["Ибраев"] if status != "open" else None)
            r.task = Task.objects.create(title=f"Устранить замечание {r.number}", construction_object=obj,
                                         assignee=emp[who], due_date=d(days), priority=min(prio, 3),
                                         status=status_to_task[status], source="inspection", description=text)
            r.save()

        # --- ежедневные отчёты прораба ---
        for i, (weather, temp, people, problems, plan) in enumerate([
            ("cloud", -4, 9, "", "Кладка 6-го этажа, приёмка газоблока"),
            ("snow", -9, 7, "Снег, кладку начали в 10:00. Не хватает клея — 2 дня запаса.", "Очистить перекрытие, кладка 5-го этажа"),
            ("sun", -2, 9, "", "Штукатурка 2-го этажа"),
            ("wind", -6, 6, "Ветер, кран не работал 3 часа", "Догнать план по кладке"),
        ]):
            rep = DailyReport.objects.create(
                construction_object=o1, date=d(-i - 1), weather=weather, temperature=temp, workers_count=people,
                works="Кладка газоблока — секция B; штукатурка стен — секция B, 1 этаж",
                equipment="Башенный кран, подъёмник" if i % 2 == 0 else "Подъёмник", problems=problems,
                plan_next=plan, confirmed=i > 0)
            rep.crews.set([crew1, crew2, crew3] if i % 2 == 0 else [crew1, crew3])

        AuditLog.objects.create(action="create", module="Объекты", object_id=str(o1.pk), object_repr=str(o1),
                                construction_object=o1, changes='[["Статус", "", "Активный"]]',
                                reason="Подписан договор субподряда")
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы."))
