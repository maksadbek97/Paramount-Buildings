"""Демо-данные раздела «Документы»: журналы, номенклатура, бланки, печати, ~50 документов с PDF,
маршрутами согласования, поручениями, историей и архивом. Люди и компания — из «Моей компании»."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from company.models import Company, Department
from core.demo_pdf import document_pdf
from objects.models import ConstructionObject
from staff.models import Employee

from . import pdf
from .models import (Approval, ArchiveRecord, CaseFile, DocEvent, DocTask, Document, DocumentFile, Journal,
                     Recipient, Seal, SealUsage, Template)


def seed():
    today = date.today()

    def d(n):
        return today + timedelta(days=n)

    tz = timezone.get_current_timezone()

    def at(day, h=10, m=0):
        return timezone.make_aware(datetime.combine(day, time(h, m)), tz)

    company = Company.get()
    emp = {e.full_name.split()[0]: e for e in Employee.objects.filter(in_staff=True)}
    B, A, I, M, R, H = (emp["Балтаев"], emp["Абдужаббаров"], emp["Ирискулов"], emp["Мадениет"], emp["Равшанов"],
                        emp["Истилевов"])
    dep = {x.name: x for x in Department.objects.all()}
    adm = dep.get("Администрация")
    pto = dep.get("Производственно-технический отдел")
    site = dep.get("Производственный участок")
    tech = dep.get("Техническая служба")
    acc = dep.get("Бухгалтерия")
    ob = {o.code: o for o in ConstructionObject.objects.all()}
    o1, o2, o3, o4, o5 = ob["AST-01"], ob["ALA-03"], ob["SHM-02"], ob["AST-02"], ob["KRG-01"]

    def short(e):
        p = e.full_name.split()
        return p[0] + " " + " ".join(x[0] + "." for x in p[1:3])

    # ---------- журналы ----------
    J = {}
    for kind, name, prefix, suffix, use_year, digits, counter in [
        ("incoming", "Журнал входящих документов", "ВХ", "", True, 4, 161),
        ("outgoing", "Журнал исходящих документов", "ИСХ", "", True, 4, 0),
        ("order", "Приказы по основной деятельности", "", "ОД", False, 1, 27),
        ("contract", "Журнал договоров", "Д", "", True, 3, 14),
        ("internal", "Внутренние документы", "ВН", "", True, 3, 41),
        ("custom", "Акты и накладные", "АКТ", "", True, 3, 0),
    ]:
        J[kind] = Journal.objects.create(name=name, kind=kind, prefix=prefix, suffix=suffix, use_year=use_year,
                                         digits=digits, counter=counter, counter_year=today.year)
    J["outgoing"].counter = 211  # с начала года
    J["outgoing"].save()

    # ---------- номенклатура дел ----------
    C = {}
    for idx, title, dp, types, ret, years, basis, who, loc in [
        ("01-01", "Приказы по основной деятельности", adm, "Приказы", "Постоянно", 0, "Перечень, ст. 19а", A,
         "Кабинет директора, шкаф 1"),
        ("01-02", "Входящая корреспонденция", adm, "Входящие письма", "5 лет", 5, "Перечень, ст. 27", A,
         "Приёмная, шкаф 2"),
        ("01-03", "Исходящая корреспонденция", adm, "Исходящие письма", "5 лет", 5, "Перечень, ст. 27", A,
         "Приёмная, шкаф 2"),
        ("01-04", "Служебные записки и внутренние распоряжения", adm, "Внутренние документы", "3 года", 3,
         "Перечень, ст. 31", A, "Приёмная, шкаф 3"),
        ("01-05", "Договоры с заказчиками и генподрядчиками", adm, "Договоры", "5 лет после окончания", 5,
         "Перечень, ст. 315", B, "Сейф директора"),
        ("01-06", "Протоколы совещаний", adm, "Протоколы", "10 лет", 10, "Перечень, ст. 18", A,
         "Приёмная, шкаф 3"),
        ("02-01", "Исполнительная документация по объектам", pto, "Акты скрытых работ, схемы", "10 лет", 10,
         "Перечень, ст. 1102", M, "ПТО, стеллаж 1"),
        ("02-02", "Акты выполненных работ (КС-2, КС-3)", pto, "Акты", "5 лет", 5, "Перечень, ст. 362", M,
         "ПТО, стеллаж 2"),
        ("02-03", "Переписка с генподрядчиками по объектам", pto, "Письма по объектам", "5 лет", 5,
         "Перечень, ст. 27", M, "ПТО, стеллаж 2"),
        ("03-01", "Документы по охране труда на объектах", site, "Приказы, инструктажи", "10 лет", 10,
         "Перечень, ст. 610", R, "Прорабская ЖК «Атлант»"),
        ("04-01", "Договоры поставки и услуг", acc, "Договоры", "5 лет после окончания", 5, "Перечень, ст. 315",
         H, "Бухгалтерия, шкаф 1"),
        ("04-02", "Счета, накладные, акты сверки", acc, "Первичные документы", "5 лет", 5, "Перечень, ст. 362", H,
         "Бухгалтерия, шкаф 2"),
        ("05-01", "Документы по электроснабжению объектов", tech, "Акты, графики, допуски", "5 лет", 5,
         "Перечень, ст. 1050", I, "Техническая служба"),
    ]:
        C[idx] = CaseFile.objects.create(index=idx, title=title, department=dp, doc_types=types, year=today.year,
                                         retention=ret, retention_years=years, basis=basis, responsible=who,
                                         location=loc)
    C["01-01/25"] = CaseFile.objects.create(index="01-01", title="Приказы по основной деятельности", department=adm,
                                            year=today.year - 1, retention="Постоянно", retention_years=0,
                                            responsible=A, status="archived", location="Архив, стеллаж А-1")
    C["01-05/25"] = CaseFile.objects.create(index="01-05", title="Договоры с заказчиками и генподрядчиками",
                                            department=adm, year=today.year - 1, retention="5 лет после окончания",
                                            retention_years=5, responsible=B, status="archived",
                                            location="Архив, стеллаж А-2")

    # ---------- шаблоны и бланки ----------
    T = {}
    for code, name, cat, lh, ver, rule, access, body, days, active in [
        ("BLANK-MAIN", "Фирменный бланк для письма", "letter", True, 1, "ask", "Все сотрудники",
         "{компания}\n{адресат}\n№ {номер} от {дата}", -9, True),
        ("BLANK-ORD", "Фирменный бланк для приказа", "order", True, 1, "sign", "Директор, заместитель",
         "БҰЙРЫҚ · ПРИКАЗ № {номер} от {дата}\n{компания}\nПРИКАЗЫВАЮ: …", -9, True),
        ("TPL-ORD", "Приказ по основной деятельности", "order", False, 2, "sign", "Администрация",
         "ПРИКАЗ № {номер} от {дата}\n{компания}\nПРИКАЗЫВАЮ: …", -300, True),
        ("TPL-ORD-OBJ", "Приказ о назначении ответственного за объект", "order", False, 1, "sign", "Администрация",
         "Назначить ответственным за объект {объект}…", -200, True),
        ("TPL-SUB", "Договор субподряда", "contract", False, 2, "both", "Директор, ПТО",
         "{компания} и {адресат}… объект {объект}, договор {договор}", -120, True),
        ("TPL-SUB-1", "Договор субподряда (редакция 2025)", "contract", False, 1, "both", "Директор, ПТО",
         "{компания} и {адресат}", -500, False),
        ("TPL-SUP", "Договор поставки материалов", "contract", False, 1, "both", "Директор, склад",
         "{компания} и {адресат}…", -260, True),
        ("TPL-KS2", "Акт выполненных работ (КС-2)", "act", False, 1, "both", "ПТО",
         "Объект {объект}, договор {договор}, номер {номер}", -240, True),
        ("TPL-SZ", "Служебная записка", "internal", False, 1, "none", "Все сотрудники", "Кому… От… {дата}", -300,
         True),
        ("TPL-PROT", "Протокол совещания", "internal", False, 1, "sign", "Все сотрудники",
         "Протокол № {номер} от {дата}, объект {объект}", -280, True),
        ("TPL-CLAIM", "Ответ на претензию", "letter", False, 1, "both", "Директор, ПТО",
         "{адресат} · по договору {договор} · объект {объект}", -100, True),
    ]:
        T[code] = Template.objects.create(code=code, name=name, category=cat, is_letterhead=lh, version=ver,
                                          sign_rule=rule, access=access, body=body, active_from=d(days),
                                          is_active=active, author=A)
    # Утверждённые бланки компании (DOCX) и их вид для просмотра (PDF)
    blanks_dir = Path(__file__).resolve().parent / "blanks"
    for code, base in (("BLANK-MAIN", "paramount-blank-pismo"), ("BLANK-ORD", "paramount-blank-prikaz")):
        T[code].file.save(f"{base}.docx", ContentFile((blanks_dir / f"{base}.docx").read_bytes()), save=False)
        T[code].preview.save(f"{base}.pdf", ContentFile((blanks_dir / f"{base}.pdf").read_bytes()), save=False)
        T[code].save()

    # ---------- печати и подписи ----------
    S = {
        "seal": Seal.objects.create(name="Основная печать ТОО «Paramount Buildings»", kind="seal", owner=B,
                                    location="Сейф в кабинете директора",
                                    access="Директор; заместитель директора — по доверенности"),
        "in": Seal.objects.create(name="Штамп «Входящий № ___»", kind="stamp", owner=A, location="Приёмная",
                                  access="Канцелярия (заместитель директора)"),
        "wh": Seal.objects.create(name="Штамп «Для документов» склада", kind="stamp", owner=H,
                                  location="Склад ЖК «Атлант»", access="Завсклад: накладные и акты приёмки",
                                  issued_to=R),
        "sigB": Seal.objects.create(name=f"Образ подписи: {B.full_name}", kind="signature", owner=B,
                                    location="Защищённое хранилище системы", access="Только директор"),
        "sigA": Seal.objects.create(name=f"Образ подписи: {A.full_name}", kind="signature", owner=A,
                                    location="Защищённое хранилище системы", access="Заместитель директора"),
        "old": Seal.objects.create(name="Печать «Для договоров» (старая, 2021)", kind="seal", owner=B,
                                   location="Изъята, акт № 2 от 15.01.2026", access="Не используется",
                                   is_active=False),
    }

    docs = {}

    def mk(key, kind, title, day, **kw):
        kw.setdefault("direction", {"incoming": "in", "outgoing": "out"}.get(kind, "internal"))
        kw.setdefault("journal", J.get(kind) if kind != "act" else J["custom"])
        if kw.get("number") is None:
            kw["number"] = ""
        if kw["number"] and "reg_date" not in kw:
            kw["reg_date"] = d(day)
        doc = Document.objects.create(kind=kind, title=title, doc_date=d(day), created_at=at(d(day), 9, 5), **kw)
        docs[key] = doc
        return doc

    # ========== Договоры ==========
    mk("C1", "contract", "Субподряд: кладка, штукатурка и армирование, ЖК «Атлант», блок B", -62,
       number="СП-14/2026", counterparty="ТОО «Астана Курылыс Груп»", construction_object=o1,
       contract_type="subcontract", amount=D("812000000"), paid=D("34500000"), valid_from=d(-60), valid_until=d(150),
       guarantee_until=d(880), status="execution", responsible=A, signer=B, author=M, department=adm, case=C["01-05"],
       template=T["TPL-SUB"], keywords="субподряд, кладка, штукатурка, армирование",
       summary="Выполнение работ по кладке перегородок из газоблока, штукатурке стен и армированию на 12-этажном "
               "жилом доме ЖК «Атлант», блок B. Оплата ежемесячно по актам КС-2 и справкам КС-3 в течение "
               "15 банковских дней. Гарантия на работы — 24 месяца с даты подписания акта приёмки.")
    mk("C2", "contract", "Субподряд: отделочные работы, бизнес-центр «Алатау»", -92, number="СП-09/2026",
       counterparty="ТОО «Алатау Строй Инвест»", construction_object=o2, contract_type="subcontract",
       amount=D("96000000"), paid=D("5000000"), valid_from=d(-90), valid_until=d(15), guarantee_until=d(745),
       status="execution", responsible=A, signer=B, author=M, department=adm, case=C["01-05"], template=T["TPL-SUB"],
       keywords="субподряд, отделка, штукатурка",
       summary="Штукатурные и отделочные работы, кладка перегородок 3–9 этажей бизнес-центра. Окончание работ — "
               "по графику, приёмка поэтажно.")
    mk("C3", "contract", "Генподряд: строительство школы на 600 мест, мкр. Нурсат, г. Шымкент", -6,
       counterparty="ГУ «Управление образования г. Шымкент»", construction_object=o3, contract_type="customer",
       amount=D("240000000"), valid_from=d(20), valid_until=d(300), status="approval", responsible=A, signer=B,
       author=A, department=adm, case=C["01-05"], due_date=d(3), priority="high", journal=J["contract"],
       keywords="школа, генподряд, госзаказ",
       summary="Проект договора по итогам конкурса. Строительно-монтажные работы, сроки — 280 дней с даты "
               "передачи площадки. Аванс 30% после подписания.")
    mk("C4", "contract", "Поставка цемента М400 и песка на объекты в Астане", -150, number="Д-2026-011",
       counterparty="ТОО «Central Asia Cement»", contract_type="supply", amount=D("18500000"), paid=D("11200000"),
       valid_from=d(-150), valid_until=d(40), status="execution", responsible=H, signer=B, author=H, department=acc,
       case=C["04-01"], template=T["TPL-SUP"], keywords="цемент, песок, поставка",
       summary="Поставка цемента М400 и песка по заявкам, доставка на объекты в г. Астане, оплата по факту поставки.")
    mk("C5", "contract", "Поставка арматуры Ø12", -120, number="Д-2026-012", counterparty="ТОО «КазМеталл Снаб»",
       contract_type="supply", amount=D("24150000"), paid=D("24150000"), valid_from=d(-120), valid_until=d(-5),
       status="closed", responsible=H, signer=B, author=H, department=acc, case=C["04-01"], template=T["TPL-SUP"],
       keywords="арматура, металл", summary="Поставка 70 т арматуры А500С Ø12. Обязательства выполнены полностью.")
    mk("C6", "contract", "Поставка газоблока D500 и клея", -70, number="Д-2026-013", counterparty="ТОО «Газоблок Астана»",
       contract_type="supply", construction_object=o1, amount=D("31800000"), paid=D("19080000"), valid_from=d(-70),
       valid_until=d(110), status="execution", responsible=H, signer=B, author=H, department=acc, case=C["04-01"],
       template=T["TPL-SUP"], keywords="газоблок, клей",
       summary="Поставка газоблока D500 (1200 м³) и клея для газоблока по графику отгрузок на ЖК «Атлант».")
    mk("C7", "contract", "Аренда офиса", -345, number="А-17", counterparty="ТОО «Нурсая Инвест»",
       contract_type="rent", amount=D("9600000"), paid=D("8800000"), valid_from=d(-345), valid_until=d(20),
       status="execution", responsible=B, signer=B, author=A, department=adm, case=C["04-01"],
       keywords="аренда, офис", summary="Аренда офиса 120 м², 800 000 ₸ в месяц. Продлить заранее — за 30 дней.")
    mk("C8", "contract", "Услуги автокрана 25 т на ЖК «Атлант»", -40, number="Д-2026-014",
       counterparty="ИП «Ержанов К. С.»", construction_object=o1, contract_type="services", amount=D("4400000"),
       paid=D("1320000"), valid_from=d(-40), valid_until=d(80), status="execution", responsible=R, signer=B,
       author=R, department=site, case=C["04-01"], keywords="автокран, техника",
       summary="Услуги автокрана 25 т с машинистом, 22 000 ₸ за машино-час, по заявкам прораба.")
    mk("C9", "contract", "Дополнительное соглашение № 1 к договору СП-14/2026: увеличение объёма кладки", -3,
       counterparty="ТОО «Астана Курылыс Груп»", construction_object=o1, contract_type="subcontract",
       amount=D("38600000"), valid_from=d(0), valid_until=d(150), status="signing", responsible=A, signer=B, author=M,
       department=adm, case=C["01-05"], subtype="Допсоглашение", due_date=d(2), journal=J["contract"],
       keywords="допсоглашение, кладка", summary="Дополнительный объём кладки перегородок 10–12 этажей — 1450 м².")
    mk("C10", "contract", "Субподряд: монтаж ограждающих конструкций, логистический склад", -400,
       number="СП-03/2025", counterparty="ТОО «Алатау Строй Инвест»", construction_object=o5,
       contract_type="subcontract", amount=D("63000000"), paid=D("63000000"), valid_from=d(-400), valid_until=d(-120),
       guarantee_until=d(610), status="closed", responsible=A, signer=B, author=M, department=adm,
       case=C["01-05/25"], keywords="склад, Караганда", summary="Работы выполнены и приняты, расчёты завершены.")
    docs["C9"].parent = docs["C1"]
    docs["C9"].contract = docs["C1"]
    docs["C9"].save()

    # ========== Приказы ==========
    def order(key, num, title, day, sub, status, points, resp, obj=None, **kw):
        doc = mk(key, "order", title, day, number=num, subtype=sub, status=status, construction_object=obj,
                 responsible=resp, signer=B, author=kw.pop("author", A), department=adm, case=C["01-01"],
                 template=T["TPL-ORD-OBJ" if obj else "TPL-ORD"],
                 summary=kw.pop("basis", "В целях организации работы компании") + ".\nПРИКАЗЫВАЮ:\n" +
                 "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1)), **kw)
        doc._points = points
        return doc

    order("O1", "15-ОД", "О назначении ответственного за охрану труда и технику безопасности", -200,
          "Ответственность за безопасность", "executed",
          [f"Назначить ответственным за охрану труда и технику безопасности на всех объектах {A.full_name}.",
           "Прорабам проводить инструктажи и вести журналы на объектах.",
           "Контроль исполнения оставляю за собой."], A, keywords="охрана труда, ТБ")
    order("O2", "24-ОД", "О закреплении объектов за руководителями проектов", -30, "Ответственные за объекты",
          "execution", [f"Закрепить ЖК «Атлант», блок B и бизнес-центр «Алатау» за {A.full_name}.",
                        f"Инженеру ПТО {M.full_name} вести исполнительную документацию по всем объектам.",
                        "Назначить руководителя проекта по школе в Шымкенте до начала работ."], A,
          due_date=d(4), keywords="объекты, ответственные")
    order("O3", "25-ОД", "О создании комиссии по инвентаризации склада ЖК «Атлант»", -21, "Комиссия, инвентаризация",
          "executed", [f"Создать комиссию: председатель {A.full_name}, члены {H.full_name}, {R.full_name}.",
                       "Провести инвентаризацию материалов на складе объекта до конца месяца.",
                       "Результаты оформить актом и передать директору."], A, o1, keywords="инвентаризация, склад")
    order("O4", "26-ОД", "О запуске проекта «Школа на 600 мест» в г. Шымкент", -12, "Запуск проекта", "execution",
          ["Начать подготовительный период на объекте с даты передачи площадки.",
           f"Ответственным за подготовку назначить {R.full_name}.",
           f"Инженеру ПТО {M.full_name} разработать ППР на подготовительный период.",
           f"Энергетику {I.full_name} обеспечить временное электроснабжение площадки."], R, o3, due_date=d(18),
          keywords="школа, запуск проекта")
    order("O5", "19-ОД", "О закрытии проекта «Логистический склад» и передаче документации в архив", -115,
          "Закрытие проекта", "archived", ["Считать работы на объекте завершёнными.",
                                           "Исполнительную документацию передать в архив по описи.",
                                           "Остатки материалов вернуть на центральный склад."], A, o5,
          keywords="закрытие, Караганда")
    order("O6", "", "Об утверждении регламента документооборота", -4, "Внутренний регламент", "signing",
          ["Утвердить регламент документооборота (приложение 1).",
           "Все входящие и исходящие документы регистрировать только в системе Smart Building.",
           f"Ответственным за ведение журналов назначить {A.full_name}."], A, due_date=d(1),
          keywords="регламент, документооборот")
    order("O7", "", "О назначении ответственного за сохранность имущества на объекте БЦ «Алатау»", -2,
          "Ответственность за имущество", "approval",
          [f"Назначить {R.full_name} ответственным за сохранность материалов и инструмента на объекте.",
           "Обеспечить охрану склада объекта в нерабочее время."], R, o2, due_date=d(2))
    order("O8", "", "О проведении внеплановой проверки охраны труда на объектах", 0, "Проверка", "draft",
          ["Провести внеплановую проверку охраны труда на объектах в Астане и Алматы.",
           "Результаты оформить актом с фото."], A, author=A)
    order("O9", "27-ОД", "Об утверждении графика дежурств энергетика на объектах в выходные дни", -6,
          "Организационный", "registered", ["Утвердить график дежурств на декабрь.",
                                            f"Ответственный — энергетик {I.full_name}."], I, keywords="график, энергетик")

    # ========== Входящие ==========
    inc_n = [151]

    def incoming(key, sender, sub, title, day, status, resp, due=None, obj=None, contract=None, sn="", res="",
                 channel="email", summary="", case="01-02", **kw):
        num = ""
        if status != "registering":
            num = f"ВХ-{today.year}-{inc_n[0]:04d}"
            inc_n[0] += 1
        doc = mk(key, "incoming", title, day - 1, number=num, reg_date=d(day) if num else None, counterparty=sender,
                 sender_number=sn, status=status, responsible=resp, due_date=due, construction_object=obj,
                 contract=contract, resolution=res, channel=channel, summary=summary, author=A, department=adm,
                 case=C[case], subtype=sub, **kw)
        return doc

    incoming("I10", "АО «Народный Банк Казахстана»", "Справка", "Справка об отсутствии картотеки по счетам", -40,
             "archived", B, sn="12-08/5531", summary="Справка по запросу компании для участия в тендере.",
             channel="edo", case="04-02")
    incoming("I11", "Департамент государственных доходов по г. Астане", "Уведомление",
             "Уведомление о предоставлении пояснений по декларации по НДС за III квартал", -20, "executed", B,
             due=d(-8), sn="МКД-08-2/4417", summary="Предоставить пояснения в течение 10 рабочих дней.",
             res=f"{B.full_name}: подготовить пояснения с бухгалтером на аутсорсе.", channel="edo", case="04-02",
             priority="high")
    incoming("I8", "ГУ «Управление архитектурно-строительного контроля г. Астаны»", "Предписание",
             "Предписание об устранении замечаний по исполнительной документации", -16, "executed", M, due=d(-2),
             obj=o1, sn="05-17/1123", res=f"{M.full_name}: устранить замечания, ответ — за подписью директора.",
             channel="hand", case="02-03", priority="high",
             summary="Отсутствуют акты скрытых работ на армирование перегородок 4–6 этажей, секция 1.")
    incoming("I7", "ТОО «Газоблок Астана»", "Уведомление", "Уведомление о задержке отгрузки газоблока D500 на 5 дней",
             -11, "executed", H, due=d(-8), obj=o1, contract=docs["C6"], sn="214", case="02-03",
             res=f"{H.full_name}: потребовать отгрузку по графику, {R.full_name}: скорректировать план кладки.",
             summary="Задержка из-за ремонта автоклава. Отгрузка 80 м³ переносится на 5 дней.")
    incoming("I4", "ГУ «Управление образования г. Шымкент»", "Письмо",
             "О передаче строительной площадки под школу на 600 мест", -9, "execution", A, due=d(10), obj=o3,
             sn="02-11/3390", channel="post", case="01-02",
             res=f"{A.full_name}: подготовить состав техники и персонала, согласовать дату передачи площадки.",
             summary="Площадка будет передана по акту после подписания договора генподряда.")
    incoming("I1", "ТОО «Астана Курылыс Груп»", "Претензия",
             "Претензия о нарушении сроков кладки перегородок, секция 2", -5, "execution", M, due=d(-1), obj=o1,
             contract=docs["C1"], sn="1187/АКГ", case="02-03", priority="urgent",
             res=f"{A.full_name}, {M.full_name}: подготовить ответ с графиком восстановления темпа. Срок — "
                 f"{d(-1):%d.%m}.",
             summary="Генподрядчик сообщает об отставании от графика на 6 дней на 7–9 этажах секции 2 и требует "
                     "представить график восстановления темпа.", keywords="претензия, сроки, кладка")
    incoming("I5", "ТОО «Central Asia Cement»", "Уведомление", "Об изменении цен на цемент М400 с 1 декабря", -4,
             "registered", H, due=d(6), contract=docs["C4"], sn="ЦЕМ-447", case="04-02",
             summary="Цена на цемент М400 увеличивается на 6% с 1 декабря.")
    incoming("I3", "ТОО «Алатау Строй Инвест»", "Уведомление", "Уведомление о приёмке этажей 5–7 по отделке", -3,
             "execution", M, due=d(2), obj=o2, contract=docs["C2"], sn="АСИ-902", case="02-03",
             res=f"{M.full_name}: организовать приёмку с представителем заказчика.",
             summary="Заказчик готов принять этажи 5–7 в четверг в 10:00.")
    incoming("I2", "ТОО «Атлант Девелопмент»", "Письмо", "О согласовании фасадных решений ЖК «Нурлы Жол»", -25,
             "execution", A, due=d(5), obj=o4, sn="АД-77/2", case="02-03",
             res=f"{A.full_name}: подготовить два варианта фасада с расчётом стоимости.",
             summary="Работы на объекте приостановлены до согласования фасада. Заказчик просит варианты.")
    incoming("I6", "ТОО «КазМеталл Снаб»", "Акт сверки", "Акт сверки взаиморасчётов за III квартал", -30, "executed",
             H, contract=docs["C5"], sn="КМС-1550", case="04-02", summary="Задолженности нет.")
    incoming("I9", "ТОО «Астана Курылыс Груп»", "Письмо", "График производства работ на декабрь", -1, "registering",
             M, due=d(4), obj=o1, contract=docs["C1"], sn="1203/АКГ", case="02-03",
             summary="Направляем график работ на декабрь для согласования.")
    J["incoming"].counter = inc_n[0] - 1
    J["incoming"].save()

    # ========== Исходящие (через генератор на бланке) ==========
    from .views import build_letter
    outs = [
        ("X6", -42, T["BLANK-MAIN"], "АО «Народный Банк Казахстана», Астанинский региональный филиал",
         "Запрос справки об отсутствии картотеки", "Просим выдать справку об отсутствии картотеки к счетам "
         f"ТОО «Paramount Buildings» (ИИК KZ27601A871002925661) для участия в тендере.", "none", None, None,
         "edo", "archived", "04-02", A),
        ("X2", -20, T["BLANK-MAIN"], "Директору ТОО «Атлант Девелопмент»",
         "О сроках возобновления работ на ЖК «Нурлы Жол»",
         "Сообщаем, что работы на объекте ЖК «Нурлы Жол» приостановлены до согласования фасадных решений.\n"
         "Возобновление работ возможно в течение 5 рабочих дней после получения согласованного варианта фасада.\n"
         "Бригады и материалы для продолжения работ зарезервированы.", "both", o4, None, "email", "closed", "02-03",
         A),
        ("X7", -18, T["BLANK-MAIN"], "Директору ТОО «КазМеталл Снаб»", "Гарантийное письмо об оплате арматуры",
         "ТОО «Paramount Buildings» гарантирует оплату поставленной арматуры Ø12 по счёту № 1520 на сумму "
         "6 900 000 тенге в срок до конца текущего месяца.\nПросим отгрузить оставшиеся 20 т без предоплаты.",
         "both", o1, "C5", "email", "closed", "04-02", H),
        ("X8", -12, T["BLANK-MAIN"], "Руководителю ДГД по г. Астане",
         "Пояснения по декларации по НДС за III квартал",
         "В ответ на уведомление сообщаем, что расхождение вызвано счётом-фактурой поставщика, выписанным в "
         "следующем периоде.\nКопии подтверждающих документов прилагаем.", "both", None, None, "edo", "closed",
         "04-02", B),
        ("X3", -10, T["BLANK-MAIN"], "Директору ТОО «Газоблок Астана»",
         "Требование об отгрузке газоблока D500 по графику",
         "Задержка отгрузки газоблока D500 приводит к простою бригад на ЖК «Атлант», блок B.\n"
         "Просим отгрузить 80 м³ не позднее трёх дней с даты письма. В противном случае будем вынуждены применить "
         "штрафные санкции по п. 7.2 договора Д-2026-013.", "both", o1, "C6", "email", "sent", "02-03", H),
        ("X5", -8, T["BLANK-MAIN"], "Руководителю ГУ «Управление архитектурно-строительного контроля г. Астаны»",
         "Об устранении замечаний по исполнительной документации",
         "Сообщаем, что замечания по предписанию устранены: акты скрытых работ на армирование перегородок 4–6 "
         "этажей секции 1 оформлены и подписаны технадзором.\nКопии актов прилагаем.", "both", o1, None, "hand",
         "closed", "02-03", M),
        ("X4", -2, T["BLANK-MAIN"], "Коммерческому директору ТОО «Central Asia Cement»",
         "Заявка на поставку цемента М400 на декабрь",
         "Просим поставить на объект ЖК «Атлант», блок B (г. Астана, пр. Туран, 55) цемент М400 — 60 т по графику:\n"
         "— 20 т в первую неделю декабря;\n— 20 т во вторую неделю;\n— 20 т в третью неделю.\n"
         "Оплата — по договору Д-2026-011.", "seal", o1, "C4", "email", "sent", "04-02", H),
    ]
    parents = {"X3": "I7", "X5": "I8", "X8": "I11", "X6": None}
    for key, day, tpl, to, subj, body, mode, obj, con, channel, status, case, author in outs:
        doc = build_letter(company, template=tpl, addressee=to, subject=subj, body=body, signer=B, sign_mode=mode,
                           seal=S["seal"], obj=obj, contract=docs.get(con) if con else None,
                           parent=docs.get(parents.get(key) or ""), author=author, when=d(day), channel=channel,
                           status=status, attachments=["Копии подтверждающих документов"] if key in ("X5", "X8")
                           else ())
        doc.case = C[case]
        doc.doc_date = doc.reg_date = d(day)
        doc.sent_at = d(day) if status in ("sent", "closed", "archived") else None
        doc.delivery_confirmed = status in ("closed", "archived")
        doc.created_at = at(d(day), 9, 20)
        doc.save()
        doc.files.update(created_at=at(d(day), 11, 40))
        doc.seal_usages.update(at=at(d(day), 11, 45))
        doc.approvals.update(decided_at=at(d(day), 11, 30))
        docs[key] = doc

    def draft_letter(key, day, to, subj, body, status, author, obj=None, parent=None, due=None):
        doc = mk(key, "outgoing", subj, day, counterparty=to, status=status, author=author, responsible=author,
                 signer=B, construction_object=obj, parent=docs.get(parent) if parent else None, due_date=due,
                 summary=body, channel="email", template=T["BLANK-MAIN"], case=C["02-03"], department=pto)
        content = pdf.letter_pdf(company, "", f"{d(day):%d.%m.%Y}", to, subj, body.split("\n"), "Директор",
                                 short(B), executor=author.full_name)
        doc.file.save(f"proekt-{doc.pk}.pdf", ContentFile(content), save=True)
        return doc

    draft_letter("X1", -1, "Генеральному директору ТОО «Астана Курылыс Груп»",
                 "Ответ на претензию: график восстановления темпа кладки, секция 2",
                 "На претензию № 1187/АКГ сообщаем, что отставание вызвано задержкой поставки газоблока D500 "
                 "поставщиком (письмо прилагаем).\nДля восстановления темпа бригада увеличена на 2 каменщиков, "
                 "работы ведутся в две смены. Отставание будет устранено в течение 8 рабочих дней.\n"
                 "График восстановления темпа прилагаем.", "approval", M, o1, "I1", d(1))
    draft_letter("X10", 0, "Директору ТОО «Алатау Строй Инвест»", "О готовности этажей 8–9 к приёмке",
                 "Сообщаем о готовности этажей 8–9 бизнес-центра «Алатау» к приёмке отделочных работ.\n"
                 "Просим назначить дату приёмки на этой неделе.", "signing", M, o2, None, d(2))
    draft_letter("X9", 0, "Руководителю ГУ «Управление образования г. Шымкент»",
                 "Состав мобилизуемой техники и персонала на объект «Школа на 600 мест»",
                 "Направляем состав техники и персонала для подготовительного периода.", "draft", A, o3, "I4")

    # ========== Внутренние ==========
    def internal(key, num, title, day, sub, status, author, resp, obj=None, summary="", case="01-04", **kw):
        return mk(key, "internal", title, day, number=num, subtype=sub, status=status, author=author,
                  responsible=resp, construction_object=obj, summary=summary, case=C[case],
                  department=author.department, **kw)

    internal("N1", "ВН-2026-041", "Протокол совещания по графику работ ЖК «Атлант», блок B", -7, "Протокол совещания",
             "execution", A, A, o1, "Присутствовали: Балтаев Н. Ш., Абдужаббаров М. Х., Мадениет Ә. Н., Равшанов О. А., "
             "Истилевов Х. А.\nРешили: увеличить бригаду на 7–9 этажах, обеспечить поставку газоблока, "
             "ежедневно докладывать о выработке.", case="01-06", template=T["TPL-PROT"], due_date=d(3))
    internal("N2", "ВН-2026-040", "Служебная записка о потребности в автокране на декабрь", -8, "Служебная записка",
             "execution", R, A, o1, "Для подачи газоблока на 10–12 этажи нужен автокран 25 т: 12 смен в декабре.",
             template=T["TPL-SZ"], due_date=d(1))
    internal("N3", "ВН-2026-038", "Служебная записка о перерасходе штукатурной смеси на БЦ «Алатау»", -9,
             "Служебная записка", "executed", H, A, o2,
             "Перерасход штукатурной смеси на 6% против норм на 5–6 этажах. Причина — неровность стен после кладки.",
             template=T["TPL-SZ"])
    internal("N4", "", "Служебная записка о закупке переносных электрощитов", 0, "Служебная записка", "draft", I, A,
             o3, "Для временного электроснабжения площадки школы нужны 4 переносных щита ЩРВ.",
             template=T["TPL-SZ"])
    internal("N5", "ВН-2026-012", "Распоряжение о порядке выдачи и хранения печати", -180, "Распоряжение",
             "executed", B, A, None, "Печать хранится в сейфе директора, выдаётся по журналу печатей под подпись.")
    J["internal"].counter = 41
    J["internal"].save()

    # ========== Акты ==========
    act_n = [1]

    def act(key, title, day, status, cp, contract, obj, amount, resp, case="02-02"):
        num = f"АКТ-{today.year}-{act_n[0]:03d}"
        act_n[0] += 1
        return mk(key, "act", title, day, number=num, status=status, counterparty=cp, contract=contract,
                  construction_object=obj, amount=amount, responsible=resp, author=resp, case=C[case],
                  department=resp.department, signer=B, template=T["TPL-KS2"] if "КС-2" in title else None)

    act("A4", "Акт передачи исполнительной документации, логистический склад", -116, "archived",
        "ТОО «Алатау Строй Инвест»", docs["C10"], o5, None, M, case="02-01")
    act("A1", "Акт выполненных работ КС-2 № 7 за октябрь, ЖК «Атлант», блок B", -20, "signed",
        "ТОО «Астана Курылыс Груп»", docs["C1"], o1, D("18400000"), M)
    act("A2", "Акт выполненных работ КС-2 № 3 за октябрь, бизнес-центр «Алатау»", -19, "signed",
        "ТОО «Алатау Строй Инвест»", docs["C2"], o2, D("5000000"), M)
    act("A3", "Акт приёмки газоблока D500 по накладной № 4471", -6, "registered", "ТОО «Газоблок Астана»", docs["C6"],
        o1, D("2120000"), H, case="04-02")
    J["custom"].counter = act_n[0] - 1
    J["custom"].save()

    # связи
    docs["C1"].related.add(docs["I1"], docs["I9"])
    docs["I1"].related.add(docs["I7"])
    docs["O3"].related.add(docs["A3"])
    docs["N1"].related.add(docs["I1"], docs["X1"])

    # ---------- PDF ко всем документам без файла ----------
    signer_pos = B.position.name if B.position else "Директор"
    for key, doc in docs.items():
        if doc.file:
            continue
        dt = f"{doc.doc_date:%d.%m.%Y}"
        if doc.kind == "order":
            content = pdf.order_pdf(company, doc.number, dt, doc.title, "В целях организации работы компании",
                                    getattr(doc, "_points", []), signer_pos, short(B),
                                    sign=bool(doc.number), seal=False)
        elif doc.kind == "contract":
            amount_text = (f"Цена договора — {int(doc.amount):,} тенге".replace(",", " ")
                           + (", в том числе НДС 12%." if doc.vat else "."))
            terms = [f"Срок действия: с {doc.valid_from:%d.%m.%Y} по {doc.valid_until:%d.%m.%Y}."
                     if doc.valid_from and doc.valid_until else "Срок действия — до исполнения обязательств.",
                     "Оплата производится в течение 15 банковских дней после подписания актов.",
                     "Споры разрешаются в суде по месту нахождения истца."]
            if doc.guarantee_until:
                terms.append(f"Гарантийный срок на результат работ — до {doc.guarantee_until:%d.%m.%Y}.")
            content = pdf.contract_pdf(company, doc.number, dt, doc.title, doc.counterparty, doc.summary, amount_text,
                                       terms, B.full_name)
        elif doc.kind == "incoming":
            content = pdf.external_pdf(doc.counterparty, "Республика Казахстан", doc.sender_number or "б/н", dt,
                                       f"Директору {company.name} {short(B)}", doc.title,
                                       [doc.summary, "Просим рассмотреть и сообщить о принятом решении."],
                                       "Руководитель ______________")
        else:
            lines = [p for p in doc.summary.split("\n") if p] + [
                f"Ответственный: {doc.responsible}." if doc.responsible else ""]
            kind = {"internal": doc.subtype or "Внутренний документ", "act": "Акт"}.get(doc.kind, "Документ")
            content = document_pdf(company, doc.title, kind, doc.number, dt, [x for x in lines if x],
                                   f"{signer_pos} {B.full_name}" if doc.kind == "act" else str(doc.author or ""))
        doc.file.save(f"doc-{doc.pk}-{doc.kind}.pdf", ContentFile(content), save=True)

    # ---------- файлы и версии ----------
    for doc in docs.values():
        if doc.files.exists():
            continue
        author = doc.author or doc.responsible
        signed = doc.status in ("registered", "signed", "execution", "executed", "closed", "archived") and \
            doc.kind != "incoming"
        size = max(1, doc.file.size // 1024) if doc.file else 0
        if doc.kind == "incoming":
            DocumentFile.objects.create(document=doc, file=doc.file.name, name=f"Скан {doc.sender_number or ''}.pdf",
                                        role="scan", version=1, author=A, comment="Скан оригинала, получен "
                                        + (doc.get_channel_display().lower() if doc.channel else ""),
                                        size_kb=size, locked=bool(doc.number), created_at=at(doc.doc_date + timedelta(1), 10))
            continue
        DocumentFile.objects.create(document=doc, file=doc.file.name, name=f"{doc.title[:60]} — проект.pdf",
                                    role="working", version=1, author=author, comment="Первая редакция",
                                    size_kb=size, created_at=at(doc.doc_date, 9, 30))
        if signed:
            DocumentFile.objects.create(document=doc, file=doc.file.name, name=f"{doc.number or doc.uid} — подписан.pdf",
                                        role="signed", version=2, author=B, comment="Подписанная версия, не редактируется",
                                        size_kb=size, locked=True, created_at=at(doc.reg_date or doc.doc_date, 15, 10))

    # ---------- маршруты согласования ----------
    def route(doc, steps, signer_state):
        base = doc.doc_date
        for i, (e, dec, comment) in enumerate(steps, 1):
            Approval.objects.create(document=doc, step=i, role="approver", employee=e, decision=dec, comment=comment,
                                    decided_at=at(base + timedelta(days=min(i - 1, max((today - base).days, 0))), 11 + i)
                                    if dec in ("approved", "returned", "rejected") else None)
        if signer_state:
            Approval.objects.create(document=doc, step=len(steps) + 1, role="signer", employee=B,
                                    decision=signer_state, method="ЭЦП НУЦ РК" if signer_state == "signed" else "",
                                    decided_at=at(doc.reg_date or base, 15) if signer_state == "signed" else None)

    done_states = ("registered", "signed", "execution", "executed", "closed", "archived")
    for key, doc in docs.items():
        if doc.approvals.exists() or doc.kind == "incoming":
            continue
        if doc.kind in ("order", "contract") and doc.status in done_states:
            route(doc, [(A, "approved", ""), (M, "approved", "Объёмы проверены")] if doc.kind == "contract" and
                  doc.construction_object else [(A, "approved", "")], "signed")
        elif doc.kind == "act" and doc.status in done_states:
            route(doc, [(M, "approved", "Объёмы соответствуют журналу выработки")], "signed")
        elif doc.kind == "internal" and doc.status in done_states and key in ("N1",):
            route(doc, [], "signed")
    route(docs["C3"], [(M, "approved", "Сметная часть проверена"), (A, "pending", ""), (H, "waiting", "")], "waiting")
    route(docs["C9"], [(M, "approved", ""), (A, "approved", "Цена согласована с ГП")], "pending")
    route(docs["O6"], [(A, "approved", ""), (M, "approved", "Добавил раздел о журналах ПТО")], "pending")
    route(docs["O7"], [(A, "pending", "")], "waiting")
    route(docs["X1"], [(M, "approved", ""), (A, "pending", "")], "waiting")
    route(docs["X10"], [(M, "approved", "")], "pending")
    route(docs["N2"], [(A, "approved", "Согласовано, заказать у ИП Ержанов")], None)
    route(docs["N3"], [(A, "approved", "")], None)

    # ---------- адресаты внутренних ----------
    for e, st, h in [(A, "read", -7), (M, "done", -6), (R, "read", -6), (H, "new", 0), (I, "read", -5)]:
        Recipient.objects.create(document=docs["N1"], employee=e, state=st, at=at(d(h), 16) if st != "new" else None)
    for e, st in [(A, "done"), (B, "read")]:
        Recipient.objects.create(document=docs["N3"], employee=e, state=st, at=at(d(-8), 12))
    Recipient.objects.create(document=docs["N2"], employee=A, state="read", at=at(d(-7), 9))

    # ---------- поручения ----------
    n = [140]

    def task(doc, title, who, due, status, obj=None, ctrl=B, pr="normal", reason="", done_day=None, co=""):
        n[0] += 1
        t = DocTask.objects.create(number=f"П-{today.year}-{n[0]:04d}", title=title, document=docs.get(doc),
                                   assignee=who, author=B if doc[0] in "OI" else A, controller=ctrl, due=d(due),
                                   status=status, construction_object=obj, priority=pr, postpone_reason=reason,
                                   co_assignees=co, done_at=d(done_day) if done_day is not None else None,
                                   created_at=at(docs[doc].doc_date + timedelta(1), 10) if doc in docs else timezone.now())
        return t

    task("O1", "Провести вводный инструктаж для всех бригад", R, -190, "done", o1, A, done_day=-192)
    task("O2", "Принять документацию по ЖК «Атлант» и БЦ «Алатау»", A, -25, "done", None, B, done_day=-26)
    task("O2", "Передать исполнительную документацию инженеру ПТО", M, -24, "done", None, A, done_day=-24)
    task("O2", "Назначить руководителя проекта по школе в Шымкенте", A, 4, "in_work", o3, B, "high")
    task("O3", "Провести инвентаризацию склада ЖК «Атлант» и составить акт", H, -14, "done", o1, A, done_day=-15,
         co=R.full_name)
    task("O4", "Оформить пропуска и допуск на площадку школы", R, 6, "accepted", o3, A)
    task("O4", "Разработать ППР на подготовительный период", M, 12, "in_work", o3, A)
    task("O4", "Организовать мобилизацию бытовых вагончиков", R, 15, "new", o3, A)
    task("O4", "Подключить временное электроснабжение площадки", I, 18, "new", o3, A)
    task("O9", "Составить график дежурств энергетика на декабрь", I, 2, "new", None, A)
    task("I1", "Подготовить ответ на претензию с графиком восстановления темпа", M, -1, "review", o1, A, "urgent",
         co=A.full_name)
    task("I2", "Подготовить два варианта фасада с расчётом стоимости", A, 4, "in_work", o4, B, "high",
         reason="Ждём замеры фасада от заказчика", co=M.full_name)
    task("I3", "Организовать приёмку этажей 5–7 с представителем заказчика", M, 2, "accepted", o2, A)
    task("I4", "Согласовать дату передачи площадки школы", A, 10, "in_work", o3, B)
    task("I5", "Проверить влияние новых цен на цемент на бюджет ЖК «Атлант»", H, 5, "new", o1, A)
    task("I8", "Устранить замечания ГАСК по исполнительной документации", M, -9, "done", o1, A, "high", done_day=-9)
    task("I7", "Скорректировать план кладки на время задержки газоблока", R, -9, "done", o1, A, done_day=-10)
    task("I11", "Подготовить пояснения по декларации по НДС", B, -12, "done", None, B, "high", done_day=-12)
    task("N1", "Увеличить бригаду на 7–9 этажах на 2 каменщиков", R, -2, "in_work", o1, A, "high")
    task("N1", "Обеспечить поставку газоблока на 7–9 этажи", H, 3, "review", o1, A)
    task("N1", "Ежедневно докладывать о выработке на 7–9 этажах", R, 7, "accepted", o1, A)
    task("N2", "Согласовать с ИП Ержанов график работы автокрана на декабрь", A, 1, "rework", o1, B)
    task("C2", "Подготовить закрывающие документы по БЦ «Алатау» до окончания договора", M, 12, "new", o2, A)
    task("C7", "Продлить договор аренды офиса на следующий год", A, 10, "accepted", None, B)

    # ---------- архив ----------
    from .services import archive
    for key, day, status, issued in [("C10", -110, "issued", f"{M.full_name} — для тендерной заявки"),
                                     ("O5", -100, "stored", ""), ("A4", -100, "stored", ""),
                                     ("I10", -30, "stored", ""), ("X6", -30, "stored", "")]:
        doc = docs[key]
        doc.status = "closed"
        doc.save(update_fields=["status"])
        archive(doc, archivist=A, when=d(day))
        ArchiveRecord.objects.filter(document=doc).update(status=status, issued_to=issued)

    # ---------- журнал печатей ----------
    for seal, action, day, who, purpose, doc in [
        (S["seal"], "use", -62, B, "Договор субподряда СП-14/2026", "C1"),
        (S["seal"], "use", -150, B, "Договор поставки Д-2026-011", "C4"),
        (S["seal"], "issue", -20, A, "Выдана для подписания актов КС-2 у генподрядчика", None),
        (S["seal"], "return", -19, A, "Возвращена в сейф", None),
        (S["seal"], "use", -20, A, "Акт КС-2 № 7", "A1"),
        (S["seal"], "use", -19, A, "Акт КС-2 № 3", "A2"),
        (S["wh"], "issue", -6, R, "Выдан прорабу на приёмку газоблока", None),
        (S["wh"], "use", -6, R, "Акт приёмки газоблока", "A3"),
        (S["in"], "use", -5, A, "Регистрация входящего", "I1"),
        (S["in"], "use", -4, A, "Регистрация входящего", "I5"),
    ]:
        SealUsage.objects.create(seal=seal, action=action, employee=who, purpose=purpose,
                                 document=docs.get(doc) if doc else None, at=at(d(day), 14, 20))

    # ---------- история (аудит) ----------
    DocEvent.objects.all().delete()
    for key, doc in docs.items():
        _history(doc, at, today, A)
    return docs


def _history(doc, at, today, clerk):
    """Правдоподобная история документа по его этапам."""
    ev = []
    base = doc.doc_date
    author = doc.author.full_name if doc.author else clerk.full_name
    if doc.kind == "incoming":
        ev.append(("receive", f"Поступил: {doc.get_channel_display().lower() if doc.channel else 'почта'}, "
                              f"исх. № {doc.sender_number}", clerk.full_name, base + timedelta(1), 9, "", ""))
        ev.append(("file", "Загружен скан письма", clerk.full_name, base + timedelta(1), 9, "", ""))
    else:
        tpl = f" по шаблону «{doc.template.name}» v{doc.template.version}" if doc.template else ""
        ev.append(("create", f"Создан черновик{tpl}", author, base, 9, "", ""))
    for a in doc.approvals.all():
        if a.decided_at:
            kind = {"approved": "approve", "signed": "sign", "returned": "return", "rejected": "reject"}[a.decision]
            text = {"approve": f"Согласовал: {a.employee}", "sign": f"Подписан: {a.employee} ({a.method or 'подпись'})",
                    "return": f"Вернул на доработку: {a.employee}", "reject": f"Отклонил: {a.employee}"}[kind]
            if a.comment:
                text += f" — «{a.comment}»"
            ev.append((kind, text, a.employee.full_name, timezone.localtime(a.decided_at).date(),
                       timezone.localtime(a.decided_at).hour, "", ""))
    if doc.status in ("approval", "signing") or doc.approvals.filter(decision="pending").exists():
        ev.append(("status", "Отправлен на согласование", author, base, 10, "Черновик", "На согласовании"))
    if doc.number and doc.reg_date:
        ev.append(("register", f"Зарегистрирован в журнале «{doc.journal}» под № {doc.number}", clerk.full_name,
                   doc.reg_date, 11, "", doc.number))
    if doc.resolution:
        ev.append(("assign", f"Резолюция: {doc.resolution[:200]}", "Балтаев Нурбек Шарипжанұлы",
                   (doc.reg_date or base), 12, "", ""))
    for t in doc.tasks.all():
        ev.append(("assign", f"Поручение {t.number}: {t.title[:90]} — {t.assignee}", t.author.full_name if t.author
                   else clerk.full_name, timezone.localtime(t.created_at).date(), 13, "", ""))
        if t.postpone_reason:
            ev.append(("deadline", f"Перенесён срок поручения {t.number}", t.assignee.full_name,
                       min(today, t.due - timedelta(5)), 15, f"{t.due - timedelta(4):%d.%m.%Y}", f"{t.due:%d.%m.%Y}"))
    for u in doc.seal_usages.all():
        ev.append(("seal", f"Проставлена печать: «{u.seal.name}»", u.employee.full_name if u.employee else "",
                   timezone.localtime(u.at).date(), 14, "", ""))
    if doc.sent_at:
        ev.append(("send", f"Отправлен адресату ({doc.get_channel_display().lower() if doc.channel else 'почта'})",
                   author, doc.sent_at, 16, "", ""))
    if doc.delivery_confirmed:
        ev.append(("receive", "Адресат подтвердил получение", author, min(today, doc.sent_at + timedelta(1)), 10,
                   "Отправлен", "Закрыт"))
    if doc.status in ("execution",) and doc.kind != "contract":
        ev.append(("status", "Передан в исполнение", clerk.full_name, (doc.reg_date or base), 12, "Зарегистрирован",
                   "В исполнении"))
    if doc.kind == "contract" and doc.status in ("execution", "closed", "archived") and doc.valid_from:
        ev.append(("status", "Договор вступил в силу", clerk.full_name, min(today, doc.valid_from), 9, "Подписан",
                   "В исполнении"))
    if doc.status in ("executed", "closed", "archived") and doc.kind not in ("outgoing",):
        when = min(today, (doc.reg_date or base) + timedelta(6))
        ev.append(("status", "Исполнен, поручения закрыты" if doc.kind != "contract" else "Обязательства выполнены",
                   doc.responsible.full_name if doc.responsible else clerk.full_name, when, 17, "В исполнении",
                   "Исполнен" if doc.kind != "contract" else "Закрыт"))
    if hasattr(doc, "archive"):
        r = doc.archive
        ev.append(("archive", f"Передан в архив: {r.archive_id}, дело {r.case.index if r.case else ''}",
                   clerk.full_name, r.archived_at, 15, "Исполнен", "В архиве"))
        if r.issued_to:
            ev.append(("download", f"Выдан из архива: {r.issued_to}", clerk.full_name, min(today, r.archived_at +
                                                                                      timedelta(60)), 10, "", ""))
    if doc.status == "registering":
        ev.append(("status", "Ожидает регистрации в канцелярии", clerk.full_name, base + timedelta(1), 9, "", ""))
    if doc.file and doc.status not in ("draft",) and (doc.reg_date or base) < today:
        ev.append(("download", "Скачан PDF", (doc.responsible or doc.author or clerk).full_name,
                   min(today, (doc.reg_date or base) + timedelta(1)), 18, "", ""))
    for i, (kind, text, who, day, hour, old, new) in enumerate(ev):
        DocEvent.objects.create(document=doc, kind=kind, text=text[:300], who=who, old=old, new=new,
                                reason="" if kind not in ("approve", "return") else "",
                                at=at(day, min(hour, 19), (i * 7) % 60))
