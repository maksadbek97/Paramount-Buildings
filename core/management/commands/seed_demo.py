"""Заполняет базу демонстрационными данными (Казахстан, суммы в тенге)."""
from datetime import date, timedelta

from django.core.files.base import ContentFile
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from company.models import BankAccount, Company, CompanyDocument, Department, StaffUnit
from contracts.models import Assignment, Crew, MaterialNorm, Payment, WorkContract, WorkLog
from core.models import AuditLog
from quality.models import DailyReport, Remark
from finance.models import Estimate, EstimateItem, Transaction
from objects.models import Client, ConstructionObject
from staff.models import Employee, Position, Task
from warehouse.models import Inventory, InventoryLine, Material, PurchaseRequest, StockMovement, Supplier, Warehouse

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

        # --- сотрудники: реальный штат компании (кадровая система enbek.kz + штатное расписание) ---
        pos = {n: Position.objects.create(name=n) for n in [
            "Директор", "Заместитель директора", "Энергетик", "Инженер ПТО", "Прораб", "Бухгалтер", "Завсклад",
            "Каменщик", "Подсобник", "Штукатур", "Арматурщик", "Электрик"]}
        staff = {}
        for key, full_name, position, hired, salary in [
            ("Балтаев", "Балтаев Нурбек Шарипжанұлы", "Директор", date(2023, 1, 1), 300000),
            ("Абдужаббаров", "Абдужаббаров Максадбек Хусанович", "Заместитель директора", None, 300000),
            ("Ирискулов", "Ирискулов Мухаммадали Махмуджанович", "Энергетик", date(2023, 5, 10), 100000),
            ("Мадениет", "Мадениет Әділ Нұрдаулетұлы", "Инженер ПТО", date(2026, 11, 17), 200000),
            ("Равшанов", "Равшанов Огабек Атабекович", "Прораб", date(2026, 11, 17), 100000),
            ("Истилевов", "Истилевов Хасан Айбекович", "Завсклад", date(2023, 4, 4), 0),
        ]:
            staff[key] = Employee.objects.create(full_name=full_name, position=pos[position], hired_at=hired,
                                                 salary=D(salary))
        # Телефоны — из реквизитов и фирменного бланка («Исп.: М. Абдужаббаров, тел. …»).
        Employee.objects.filter(pk=staff["Балтаев"].pk).update(phone="+7 775 339 46 16")
        Employee.objects.filter(pk=staff["Абдужаббаров"].pk).update(phone="+7 707 170 07 74")
        for k in ("Балтаев", "Абдужаббаров"):
            staff[k].refresh_from_db()
        # Роли в демо-процессах (объекты, задачи, замечания) — на реальных людей.
        emp = {"Жумабеков": staff["Балтаев"], "Ахметова": staff["Абдужаббаров"], "Ким": staff["Абдужаббаров"],
               "Нурланова": staff["Мадениет"], "Сейтказиев": staff["Равшанов"], "Оспанов": staff["Равшанов"],
               "Исаева": staff["Балтаев"], "Тулегенов": staff["Истилевов"]}
        self.staff = staff
        workers = {}
        for i, (full_name, position) in enumerate([
            ("Абдрахманов Нурсултан", "Каменщик"), ("Касымов Ерасыл", "Каменщик"), ("Байжанов Арман", "Подсобник"),
            ("Мусин Талгат", "Каменщик"), ("Садыков Ринат", "Подсобник"), ("Ибраев Марат", "Штукатур"),
            ("Есенов Алибек", "Штукатур"), ("Жаксылыков Бекзат", "Арматурщик"), ("Рахимов Тимур", "Электрик"),
        ]):
            workers[full_name.split()[0]] = Employee.objects.create(
                full_name=full_name, position=pos[position], phone=f"+7 70{i} 9{i}{i}-1{i}-2{i}",
                hired_at=d(-150), iin=f"9{i}0101{400000 + i * 777}"[:12], in_staff=False)

        self._company(emp, workers, pos)

        # --- контрагенты и объекты ---
        c1 = Client.objects.create(name="ТОО «Атлант Девелопмент»", bin="180540012345", phone="+7 717 255-10-10")
        gc1 = Client.objects.create(name="ТОО «Астана Курылыс Груп»", bin="150340098765", phone="+7 717 270-20-20")
        c2 = Client.objects.create(name="ТОО «Алатау Строй Инвест»", bin="170840054321", phone="+7 727 330-30-30")
        c3 = Client.objects.create(name="ГУ «Управление образования г. Шымкент»", bin="990140011122")

        # Объекты компании — 6 объектов из таблицы «Фин план до 2026 года». Реквизиты, адреса и суммы договоров
        # вносятся в карточке объекта; деньги по объекту ведутся в «Финансах».
        def obj(code, name, **kw):
            return ConstructionObject.objects.create(code=code, name=name, status="in_progress", manager=emp["Ким"],
                                                     **kw)
        o1 = obj("ATL-01", "Atlant", foreman=emp["Сейтказиев"], pto=emp["Нурланова"], start_date=d(-60))
        o2 = obj("DAR-01", "Daryn", foreman=emp["Оспанов"], pto=emp["Нурланова"], start_date=d(-90))
        o3 = obj("ARN-01", "Arna", start_date=d(-30))
        o4 = obj("NEX-01", "Nexpo Global", start_date=d(-20))
        o5 = obj("NAK-01", "NAK", start_date=d(-45))
        o6 = obj("ZER-01", "Zerde", start_date=d(-40))
        self.real_objects = {"Atlant": o1, "Daryn": o2, "Arna": o3, "Nexpo Global": o4, "NAK": o5, "Zerde": o6}

        self._object_module(emp, workers, [o1, o2, o3, o4, o5])

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

        # Склады: центральный и склады объектов.
        central = Warehouse.objects.create(name="Центральный склад (Астана)", kind="central", keeper=emp["Тулегенов"])
        obj_wh = {
            o1.pk: Warehouse.objects.create(name="Склад Atlant", kind="object", construction_object=o1,
                                            keeper=emp["Сейтказиев"]),
            o2.pk: Warehouse.objects.create(name="Склад Daryn", kind="object", construction_object=o2,
                                            keeper=emp["Оспанов"]),
        }
        Warehouse.objects.create(name="Склад инструментов", kind="tools", keeper=emp["Тулегенов"])

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
            m = mats[mat]
            if kind == "in":
                StockMovement.objects.create(material=m, kind="in", quantity=D(qty), date=d(days), supplier=sup,
                                             warehouse=central, price=m.price)
            else:
                # Со склада компании на склад объекта (принято прорабом), затем расход в работу.
                wh = obj_wh[obj.pk]
                t = StockMovement.objects.create(material=m, kind="transfer", quantity=D(qty), date=d(days - 1),
                                                 warehouse=central, to_warehouse=wh)
                t.accept(None)
                StockMovement.objects.create(material=m, kind="out", quantity=D(qty), date=d(days),
                                             warehouse=wh, construction_object=obj, contract=k)

        # Перемещение, которое ещё ждёт приёмки прорабом, и списание с причиной.
        StockMovement.objects.create(material=mats["Газоблок D500"], kind="transfer", quantity=D("80"),
                                     date=d(0), warehouse=central, to_warehouse=obj_wh[o1.pk],
                                     note="Машина 2 из 3")
        StockMovement.objects.create(material=mats["Газоблок D500"], kind="writeoff", quantity=D("3"),
                                     date=d(-9), warehouse=central, note="Бой при разгрузке")
        inv = Inventory.objects.create(warehouse=central, date=d(-20), note="Плановая")
        for m in (mats["Песок"], mats["Цемент М400"]):
            InventoryLine.objects.create(inventory=inv, material=m, book_qty=m.balance(central),
                                         actual_qty=m.balance(central))
        line = inv.lines.first()
        line.actual_qty = line.book_qty - 2
        line.save()
        inv.approve(None)

        # Заявки на материалы.
        for mat, qty, obj, wh, status, sup, price, days in [
            ("Клей для газоблока", "600", o1, obj_wh[o1.pk], "new", None, "2650", 4),
            ("Штукатурная смесь", "900", o1, obj_wh[o1.pk], "approved", s1, "3250", 3),
            ("Цемент М400", "20", o1, central, "ordered", s1, "38500", 2),
            ("Газоблок D500", "1100", o1, obj_wh[o1.pk], "received", s3, "26500", -14),
            ("Кабель ВВГ 3×2,5", "300", o2, obj_wh[o2.pk], "rejected", None, None, 5),
        ]:
            PurchaseRequest.objects.create(material=mats[mat], quantity=D(qty), construction_object=obj,
                                           warehouse=wh, status=status, supplier=sup,
                                           price=D(price) if price else None, needed_by=d(days),
                                           payment_terms="Предоплата 50%" if sup else "")

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
        from docflow.demo import seed as seed_docflow
        seed_docflow()  # раздел «Документы»
        from finance.demo import seed as seed_finance
        seed_finance(self.real_objects)  # раздел «Финансы»: финплан из таблицы компании
        self._activity_feed()
        self.stdout.write(self.style.SUCCESS("Демо-данные созданы."))

    def _activity_feed(self):
        """Журнал действий для «Последних операций» на Главной — по уже созданным записям."""
        from datetime import datetime, time, timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from contracts.models import Payment, WorkLog
        from quality.models import DailyReport, Remark
        from warehouse.models import PurchaseRequest, StockMovement
        users = {name: get_user_model().objects.get_or_create(username=name, defaults={"first_name": name})[0]
                 for name in ("Мадениет Ә.", "Равшанов О.", "Абдужаббаров М.", "Истилевов Х.")}
        events = []
        for log in WorkLog.objects.filter(status="accepted").select_related("assignment__contract__construction_object")[:4]:
            c = log.assignment.contract
            events.append((log.date, 17, "accept", "Выработка по дням", log, c.construction_object, users["Мадениет Ә."],
                           f"Принято ПТО: {c.work_type}, {log.accepted_volume.normalize():f} {c.unit}"))
        for pay in Payment.objects.select_related("contract__construction_object")[:4]:
            events.append((pay.date, 11, "create", "Платежи по договорам", pay, pay.contract.construction_object,
                           users["Истилевов Х."], f"{pay.get_kind_display()}: {int(pay.amount):,} ₸".replace(",", " ")))
        for pr in PurchaseRequest.objects.select_related("construction_object", "material")[:4]:
            events.append((pr.created_at.date() - timedelta(days=pr.pk % 4), 10, "create", "Заявки и закупки", pr,
                           pr.construction_object, users["Равшанов О."], f"Заявка {pr.number}: {pr.material}"))
        for mv in StockMovement.objects.filter(kind="transfer").select_related("material", "to_warehouse")[:2]:
            events.append((mv.date, 9, "create", "Движения материалов", mv, mv.construction_object,
                           users["Равшанов О."], f"Перемещение: {mv.material} → {mv.to_warehouse}"))
        for r in Remark.objects.select_related("construction_object")[:3]:
            events.append((r.created_at.date() - timedelta(days=r.pk % 5), 15, "create", "Замечания", r,
                           r.construction_object, users["Абдужаббаров М."], f"Замечание {r.number}: {r.description[:50]}"))
        for rep in DailyReport.objects.select_related("construction_object")[:2]:
            events.append((rep.date, 19, "create", "Ежедневные отчёты", rep, rep.construction_object,
                           users["Равшанов О."], f"Отчёт прораба за {rep.date:%d.%m}"))
        tz = timezone.get_current_timezone()
        for i, (day, hour, action, module, inst, obj, user, text) in enumerate(events):
            e = AuditLog.objects.create(action=action, module=module, object_id=str(inst.pk), object_repr=text,
                                        construction_object=obj, user=user)
            AuditLog.objects.filter(pk=e.pk).update(
                created_at=timezone.make_aware(datetime.combine(day, time(hour, (i * 7) % 60)), tz))

    def _company(self, emp, workers, pos):
        """Раздел «Моя компания»: профиль, счета, структура, штатное расписание, документы."""
        d = self.d
        Company.objects.all().delete()
        # Реквизиты — из файла «Реквизиты Paramount» и фирменных бланков компании.
        Company.objects.create(
            legal_form="too", name="ТОО «Paramount Buildings»", short_name="Paramount Buildings", bin="210540017144",
            activity="43.99 — Прочие специализированные строительные работы", kbe="17", vat_payer=True,
            director=self.staff["Балтаев"], accountant=None,
            legal_address="010000, г. Астана, р-н Сарыарка, ул. Косшыгулулы, дом 19, кв. 238",
            actual_address="010000, РК, г. Астана, р-н Сарыарка, ул. Косшыгулулы, дом 19",
            phone="+7 775 339 46 16", email="avangard.nbs@gmail.com", website="paramountbuild.kz",
            description="Субподрядная строительная компания: каменная кладка, штукатурные и армирующие работы "
                        "на жилых и коммерческих объектах в Астане, Алматы и Шымкенте.")
        BankAccount.objects.create(bank="АО «Народный Банк Казахстана»", bik="HSBKKZKX", iban="KZ27601A871002925661",
                                   is_main=True, note="Основной расчётный счёт")

        # Структура и штатное расписание — из утверждённого штатного расписания ТОО (6 единиц).
        st = self.staff
        top = Department.objects.create(name="Администрация", head=st["Балтаев"], order=0)
        deps = {name: Department.objects.create(name=name, parent=top, order=i) for i, name in enumerate(
            ["Техническая служба", "Производственно-технический отдел", "Производственный участок", "Бухгалтерия"], 1)}
        for key, dep in [("Балтаев", top), ("Абдужаббаров", top), ("Ирискулов", deps["Техническая служба"]),
                         ("Мадениет", deps["Производственно-технический отдел"]),
                         ("Равшанов", deps["Производственный участок"])]:
            Employee.objects.filter(pk=st[key].pk).update(department=dep)
        for dep, position, salary in [
            (top, "Директор", 300000), (top, "Заместитель директора", 300000),
            (deps["Техническая служба"], "Энергетик", 100000),
            (deps["Производственно-технический отдел"], "Инженер ПТО", 200000),
            (deps["Производственный участок"], "Прораб", 100000), (deps["Бухгалтерия"], "Бухгалтер", 100000),
        ]:
            StaffUnit.objects.create(department=dep, position=pos[position], count=D(1), salary=D(salary))

        K = CompanyDocument.Kind
        for kind, number, date_, title, valid, who, note in [
            (K.CHARTER, "", date(2021, 5, 10), "Устав ТОО «Paramount Buildings»", None, "Жумабеков",
             "Редакция с изменениями от 12.03.2024"),
            (K.CHARTER, "", date(2021, 5, 14), "Справка о государственной регистрации юридического лица", None,
             "Исаева", "Электронная справка egov.kz"),
            (K.CHARTER, "", date(2021, 5, 20), "Талон о постановке на учёт по НДС", None, "Исаева", ""),
            (K.DECISION, "1", date(2021, 5, 10), "Решение единственного участника о создании товарищества", None,
             "Жумабеков", ""),
            (K.DECISION, "4", d(-410), "Решение о назначении директора на новый срок", d(685), "Жумабеков",
             "Полномочия на 3 года"),
            (K.DECISION, "7", d(-95), "Решение об открытии валютного счёта", None, "Исаева", ""),
            (K.ORDER, "12-ОД", d(-320), "Об утверждении штатного расписания", None, "Жумабеков", ""),
            (K.ORDER, "15-ОД", d(-200), "О назначении ответственного за охрану труда и технику безопасности", None,
             "Ахметова", "Ответственный: Абдужаббаров М. Х."),
            (K.ORDER, "21-ЛС", d(-150), "О приёме на работу рабочих на объект Atlant", None, "Исаева", "9 человек"),
            (K.ORDER, "24-ОД", d(-30), "О закреплении объектов за руководителями проектов", None, "Жумабеков", ""),
            (K.CERTIFICATE, "", d(-25), "Справка об отсутствии налоговой задолженности", d(5), "Исаева",
             "Нужна для тендеров"),
            (K.CERTIFICATE, "", d(-40), "Справка банка об отсутствии картотеки", d(-3), "Исаева", ""),
            (K.CERTIFICATE, "", d(-10), "Справка о среднесписочной численности работников", None, "Исаева", ""),
            (K.LICENSE, "21015432", date(2021, 7, 2),
             "Государственная лицензия на строительно-монтажные работы, II категория", None, "Ахметова", ""),
            (K.LICENSE, "KZ.ISO.1234", d(-300), "Сертификат системы менеджмента качества ISO 9001", d(430),
             "Ахметова", ""),
            (K.OTHER, "А-17", d(-345), "Договор аренды офиса", d(20), "Исаева", "Продлить заранее"),
        ]:
            doc = CompanyDocument.objects.create(kind=kind, number=number, date=date_, title=title,
                                                 valid_until=valid, responsible=emp[who], note=note)
            self._doc_file(doc, emp)

    def _doc_file(self, doc, emp):
        """Примерный PDF к документу, чтобы в демо его можно было открыть и скачать."""
        from core.demo_pdf import document_pdf
        company = Company.get()
        lines = []
        if doc.note:
            lines.append(doc.note + ".")
        if doc.valid_until:
            lines.append(f"Документ действителен до {doc.valid_until:%d.%m.%Y}.")
        if doc.responsible:
            lines.append(f"Ответственный за документ: {doc.responsible}.")
        lines.append("Текст документа приведён как образец. В рабочей версии здесь будет загруженный файл: "
                     "скан или PDF с подписью и печатью.")
        director = company.director
        signer = f"{director.position or 'Директор'} {director.full_name}" if director else ""
        kind = {"charter": "Учредительный документ", "decision": "Решение", "order": "Приказ",
                "certificate": "Справка", "license": "Лицензия"}.get(doc.kind, "Документ")
        pdf = document_pdf(company, doc.title, kind, doc.number, f"{doc.date:%d.%m.%Y}", lines, signer)
        doc.file.save(f"doc-{doc.pk}-{doc.kind}.pdf", ContentFile(pdf), save=True)

    def _object_module(self, emp, workers, objs):
        """Раздел «Объекты»: тип, ответственный менеджер, координаты, транспорт и охрана труда (примерные данные)."""
        from datetime import time

        from objects.models import SafetyRecord, TransportRequest
        d = self.d
        o1, o2, o3, o4, o5 = objs
        for o, resp in [(o1, emp["Ахметова"]), (o2, emp["Ахметова"])]:
            o.responsible = resp
            o.save()
        for o, kind, task, route, days, hh, driver, status, hours, cost in [
            (o1, "crane", "Подача газоблока на 7–9 этажи", "Склад объекта → секция 2", 1, 8, "Ержанов К.", "approved", None, 0),
            (o1, "dump", "Вывоз строительного мусора", "Объект → полигон", 2, 9, "", "new", None, 0),
            (o1, "manipulator", "Доставка арматуры с центрального склада", "Центральный склад → объект", -3, 10,
             "Сапаров Е.", "done", D("6"), D("90000")),
            (o1, "crane", "Монтаж перемычек, 5 этаж", "", -8, 8, "Ержанов К.", "done", D("8"), D("176000")),
            (o2, "loader", "Разгрузка штукатурной смеси", "", -1, 14, "Мамыров А.", "in_work", D("3"), D("45000")),
        ]:
            TransportRequest.objects.create(construction_object=o, kind=kind, task=task, route=route, date=d(days),
                                            time=time(hh, 0), driver=driver, status=status, hours=hours, cost=cost,
                                            responsible=emp["Сейтказиев"] if o == o1 else emp["Оспанов"])
        crew = ", ".join(w.full_name for w in list(workers.values())[:5])
        for o, kind, title, days, parts, who, until, measures, ok in [
            (o1, "briefing", "Вводный инструктаж для новой бригады", -58, crew, emp["Сейтказиев"], None, "", True),
            (o1, "briefing", "Повторный инструктаж: работы на высоте", -5, crew, emp["Сейтказиев"], None, "", False),
            (o1, "permit", "Допуск к работам на высоте", -200, "Абдрахманов Нурсултан, Касымов Ерасыл", None,
             d(-4), "", True),
            (o1, "permit", "Удостоверение стропальщика", -300, "Байжанов Арман", None, d(10), "", True),
            (o1, "permit", "Группа по электробезопасности III", -100, "Рахимов Тимур", None, d(260), "", True),
            (o1, "incident", "Падение инструмента с 6 этажа, без пострадавших", -12, "Бригада Мусина",
             emp["Сейтказиев"], None, "Установлены защитные сетки, проведён целевой инструктаж", True),
            (o2, "briefing", "Целевой инструктаж: работа с подъёмником", -20, "Штукатуры Ибраева", emp["Оспанов"],
             None, "", True),
        ]:
            SafetyRecord.objects.create(construction_object=o, kind=kind, title=title, date=d(days), participants=parts,
                                        instructor=who, valid_until=until, measures=measures, confirmed=ok)
