"""Финплан — из таблицы компании «Paramount Фин план до 2026 года» (последняя версия, 27.11.2026).

Листы объектов: (блок, наименование / получатель, план, плановая дата, факт, дата факта, примечание).
«Долги» — общий долг компании. «Лист1» (АВР) — акты выполненных работ по объектам и видам работ.
"""
from datetime import date
from decimal import Decimal

from objects.models import ConstructionObject

from .models import PlanLine, WorkAct

S = PlanLine.Section

PLAN = {
    'Daryn': [
        (S.INCOME, 'Поступление от заказчика', 35000000, date(2026, 12, 29), 4194000, date(2026, 11, 24), ''),
        (S.INCOME, '', 0, None, 1824000, date(2026, 11, 25), ''),
        (S.LABOR, 'Бригада работа', 1500000, None, 0, None, ''),
        (S.LABOR, 'Гулом — оплата за работу', 1000000, None, 0, None, ''),
        (S.LABOR, 'Диас', 0, None, 75000, None, ''),
        (S.LABOR, 'Хасан Плинтус', 0, None, 92000, None, ''),
        (S.LABOR, 'Аман', 0, None, 30000, None, ''),
        (S.LABOR, 'Сетка', 0, None, 50000, None, ''),
        (S.LABOR, 'Лочин', 0, None, 108000, None, ''),
        (S.LABOR, 'Руфат', 0, None, 300000, None, ''),
        (S.MATERIAL, 'Материальные расходы', 400000, None, 0, None, ''),
        (S.MATERIAL, 'Смат шкурка', 0, None, 250000, None, ''),
        (S.OVERHEAD, 'Накладные расходы', 100000, None, 0, None, ''),
        (S.OVERHEAD, 'Кистичка валик краска', 0, None, 17000, None, ''),
        (S.OVERHEAD, 'Айгул гупка', 0, None, 14000, None, ''),
    ],
    'Atlant': [
        (S.INCOME, 'Поступление от заказчика', 24000000, None, 0, None, ''),
        (S.LABOR, 'Бригада — оплата за работу', 1200000, None, 0, None, ''),
        (S.MATERIAL, 'Материальные расходы', 200000, None, 0, None, ''),
        (S.OVERHEAD, 'Накладные расходы', 400000, None, 0, None, ''),
    ],
    'Nexpo Global': [
        (S.INCOME, 'Поступление от заказчика', 20000000, None, 0, None, ''),
        (S.LABOR, 'Ринат — оплата за работу', 7000000, None, 0, None, ''),
        (S.MATERIAL, 'Профиль', 5600000, None, 0, None, 'Предварительно — объём не подтверждён'),
        (S.MATERIAL, 'Гипсокартон', 3400000, None, 0, None, 'Предварительно — объём не подтверждён'),
        (S.MATERIAL, 'Акустика', 1800000, None, 0, None, 'Предварительно — объём не подтверждён'),
        (S.OVERHEAD, 'Накладные расходы', 200000, None, 0, None, ''),
    ],
    'Arna': [
        (S.INCOME, 'Поступление от заказчика', 32000000, None, 0, None, ''),
        (S.LABOR, 'Гулом — оплата за работу', 2500000, None, 0, None, ''),
        (S.LABOR, 'Бегзод - оплата за работу', 1500000, None, 0, None, 'Аванс'),
        (S.LABOR, 'Мурат — оплата за работу', 2000000, None, 300000, date(2026, 11, 23), ''),
        (S.LABOR, 'Султаш — оплата за работу', 2000000, None, 850000, date(2026, 11, 23), ''),
        (S.LABOR, 'Икрам — оплата за работу', 1500000, None, 0, None, ''),
        (S.LABOR, 'Сардор Кафель - оплаза за работу', 1000000, None, 130000, None, ''),
        (S.LABOR, 'Ербол Шкатурка - оплата за работу', 2500000, None, 650000, None, ''),
        (S.MATERIAL, 'Профиль', 1600000, None, 0, None, '300'),
        (S.MATERIAL, 'ГКЛ', 853000, None, 0, None, ''),
        (S.MATERIAL, 'Минвата', 1000000, None, 0, None, ''),
        (S.MATERIAL, 'Гипс белый', 1140000, None, 380000, date(2026, 11, 25), ''),
        (S.MATERIAL, 'Гипс серый', 1407000, None, 273000, date(2026, 11, 26), ''),
        (S.MATERIAL, 'Клей кафельный', 930000, None, 0, None, ''),
        (S.MATERIAL, 'ГКЛ обычный', 500000, None, 0, None, ''),
        (S.OVERHEAD, 'Крепежи', 100000, None, 0, None, ''),
        (S.OVERHEAD, 'Фуга, зажим', 100000, None, 31700, None, ''),
    ],
    'NAK': [
        (S.INCOME, 'Поступление от заказчика', 10000000, None, 0, None, ''),
        (S.LABOR, 'Изтилеу — оплата за работу', 5000000, None, 2000000, date(2026, 11, 22), 'Вид работ уточнить'),
        (S.LABOR, 'Мадияр — оплата за работу', 3000000, None, 0, None, 'Вид работ уточнить'),
        (S.LABOR, 'Даниял — оплата за работу', 2000000, None, 0, None, 'Вид работ уточнить'),
    ],
    'Zerde': [
        (S.INCOME, 'Поступление от заказчика', 19000000, None, 10000000, date(2026, 11, 22), ''),
        (S.LABOR, 'Мадияр — оплата за работу', 2000000, None, 80000, date(2026, 11, 25), 'Вид работ уточнить'),
    ],
}
DEBTS = [
        (S.DEBT, 'TOO HARD KZ', 4000000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'TOO KazGer', 3000000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'ТОО Селена ЦА', 1650000, None, 0, None, ''),
        (S.DEBT, 'Alina Group', 10000000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'TOO SET Astana', 1700000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'Вилатерм Каз', 300000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'Nsulation', 800000, None, 0, None, 'Задолженность к оплате'),
        (S.DEBT, 'IzoMarket', 435700, None, 209500, date(2026, 11, 25), 'Задолженность к оплате'),
        (S.DEBT, 'Алишер Рынок', 620000, None, 300000, date(2026, 11, 25), ''),
        (S.DEBT, 'ACM — Раим', 1134000, None, 1134000, date(2026, 11, 24), 'Задолженность к оплате'),
        (S.DEBT, 'Нал долг', 6900000, None, 3600000, date(2026, 11, 23), ''),
        (S.DEBT, 'Кредит Хусан Шарапов', 1300000, None, 0, None, ''),
        (S.DEBT, 'Кредит Нурбек', 3060000, None, 1033000, None, 'Ноябрь 1033'),
        (S.DEBT, 'ТОО Home Group Urban', 6400000, None, 0, None, ''),
        (S.DEBT, 'МФО Алтын Кредит', 9000000, None, 0, None, ''),
        (S.DEBT, 'Убайдулла', 900000, None, 0, None, ''),
        (S.DEBT, 'Рахим', 1200000, None, 0, None, ''),
        (S.DEBT, 'Ахмад', 900000, None, 700000, date(2026, 11, 25), ''),
]
ACTS = [
    ('Арна ВО', 57361258),
    ('Дарын кладка', 35890462),
    ('Арна кладка', 18137622),
    ('Атлант кладка', 2133889),
    ('Атлант ВО', 13721663),
    ('Дарын ГКЛ', 1755933),
    ('Арт кладка', 7270119),
    ('Зерде кладка', 19571190),
    ('Дарын кладка', 5847870),
    ('Дарын ЧО', 8967904),
    ('Атлант кладка', 3561936),
    ('Арна ГКЛ', 43363418),
    ('Глобал кладка', 20000000),
    ('Арна ВО', 22000000),
    ('Дарын ВО', 60000000),
    ('Атлант ЧО', 10000000),
    ('Атлант кладка', 4000000),
    ('Атлант ВО', 6000000),
]


# Как объект назван в АВР → лист таблицы. «Арт кладка» в таблице не привязана к объекту.
ACT_OBJECT = {"Арна": "Arna", "Дарын": "Daryn", "Атлант": "Atlant", "Зерде": "Zerde", "Глобал": "Nexpo Global",
              "NAK": "NAK"}
OBJECTS = list(PLAN)


def seed(objects=None):
    """objects — {имя листа: объект}; недостающие объекты создаются."""
    objects = dict(objects or {})
    for name in OBJECTS:
        if name not in objects:
            objects[name] = ConstructionObject.objects.filter(name=name).first() or \
                ConstructionObject.objects.create(name=name, status=ConstructionObject.Status.IN_PROGRESS)
    pos = 0
    for name, rows in PLAN.items():
        for section, title, plan, plan_date, fact, fact_date, note in rows:
            pos += 1
            PlanLine.objects.create(construction_object=objects[name], section=section, name=title,
                                    plan_amount=Decimal(plan), plan_date=plan_date, fact_amount=Decimal(fact),
                                    fact_date=fact_date, note=note, position=pos)
    for section, title, plan, plan_date, fact, fact_date, note in DEBTS:
        pos += 1
        PlanLine.objects.create(section=S.DEBT, name=title, plan_amount=Decimal(plan), plan_date=plan_date,
                                fact_amount=Decimal(fact), fact_date=fact_date, note=note, position=pos)
    for i, (title, amount) in enumerate(ACTS, 1):
        key, _, work = title.partition(" ")
        obj = objects.get(ACT_OBJECT.get(key, ""))
        WorkAct.objects.create(construction_object=obj, work=work if obj else title, amount=Decimal(amount),
                               note="" if obj else "Объект в таблице не указан", position=i)
    return objects
