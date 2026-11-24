"""Финплан для демо — из таблицы компании «Paramount Фин план до 2026 года» (план на период до 31.12.2026).

Факт в таблице ещё не заполнен, поэтому и здесь факт пустой: его вносят кнопкой «Оплатить» / «Получено».
"""
from datetime import date
from decimal import Decimal

from objects.models import ConstructionObject

from .models import PlanLine

S = PlanLine.Section

# Лист объекта: [(блок, наименование / получатель, план, плановая дата, примечание)]
PLAN = {
    "Daryn": [
        (S.INCOME, "Поступление от заказчика", 35000000, date(2026, 12, 29), ""),
        (S.LABOR, "Бригада — оплата за работу", 1500000, None, ""),
        (S.LABOR, "Гулом — оплата за работу", 1000000, None, ""),
        (S.MATERIAL, "Материальные расходы", 400000, None, ""),
        (S.OVERHEAD, "Накладные расходы", 100000, None, ""),
    ],
    "Atlant": [
        (S.INCOME, "Поступление от заказчика", 24000000, None, ""),
        (S.LABOR, "Бригада — оплата за работу", 1200000, None, ""),
        (S.MATERIAL, "Материальные расходы", 200000, None, ""),
        (S.OVERHEAD, "Накладные расходы", 400000, None, ""),
    ],
    "Nexpo Global": [
        (S.INCOME, "Поступление от заказчика", 20000000, None, ""),
        (S.LABOR, "Ринат — оплата за работу", 7000000, None, ""),
        (S.MATERIAL, "Профиль", 6000000, None, "Предварительно — объём не подтверждён"),
        (S.MATERIAL, "Гипсокартон", 4000000, None, "Предварительно — объём не подтверждён"),
        (S.MATERIAL, "Акустика", 2000000, None, "Предварительно — объём не подтверждён"),
        (S.OVERHEAD, "Накладные расходы", 200000, None, ""),
    ],
    "Arna": [
        (S.INCOME, "Поступление от заказчика", 32000000, None, ""),
        (S.LABOR, "Гулом — оплата за работу", 2000000, None, ""),
        (S.LABOR, "Оплата за работу", 1000000, None, "Аванс"),
        (S.LABOR, "Мурат — оплата за работу", 2500000, None, ""),
        (S.LABOR, "Султан — оплата за работу", 1500000, None, ""),
        (S.LABOR, "Мадияр — оплата за работу", 2000000, None, ""),
        (S.LABOR, "Кафель — оплата за работу", 1500000, None, ""),
        (S.LABOR, "Штукатурка — оплата за работу", 2000000, None, ""),
        (S.MATERIAL, "Материал", 1500000, None, ""),
        (S.MATERIAL, "Гипсокартон", 2000000, None, ""),
    ],
    "NAK": [
        (S.INCOME, "Поступление от заказчика", 10000000, None, ""),
        (S.LABOR, "Ристлау — оплата за работу", 5000000, None, "Вид работ уточнить"),
        (S.LABOR, "Мадияр — оплата за работу", 3000000, None, "Вид работ уточнить"),
        (S.LABOR, "Дианиал — оплата за работу", 3000000, None, "Вид работ уточнить"),
    ],
    "Zerde": [
        (S.INCOME, "Поступление от заказчика", 19000000, None, ""),
        (S.LABOR, "Мадияр — оплата за работу", 2000000, None, "Вид работ уточнить"),
    ],
}

# Лист «Долги»: общий долг компании, не распределяется по объектам.
DEBTS = [
    ("Хару KZ", 4000000, "Задолженность к оплате"),
    ("Казгер", 3000000, "Задолженность к оплате"),
    ("Алина", 10000000, "Задолженность к оплате"),
    ("Сет Астана", 1700000, "Задолженность к оплате"),
    ("Велотерн", 300000, "Задолженность к оплате"),
    ("Nsoltion", 800000, "Задолженность к оплате"),
    ("Izo Market", 200000, "Задолженность к оплате"),
    ("ASM — Раим", 1134000, "Задолженность к оплате"),
    ("Нал долг", 6600000, ""),
    ("Кредит Хусан Шарапов", 1300000, ""),
]


def seed(objects=None):
    """objects — {имя листа: объект}, чтобы связать лист с уже созданным объектом (например, Atlant)."""
    objects = dict(objects or {})
    pos = 0
    for name, rows in PLAN.items():
        obj = objects.get(name) or ConstructionObject.objects.filter(name=name).first() or \
            ConstructionObject.objects.create(name=name, status=ConstructionObject.Status.IN_PROGRESS)
        for section, title, plan, plan_date, note in rows:
            pos += 1
            PlanLine.objects.create(construction_object=obj, section=section, name=title, plan_amount=Decimal(plan),
                                    plan_date=plan_date, note=note, position=pos)
    for title, amount, note in DEBTS:
        pos += 1
        PlanLine.objects.create(section=S.DEBT, name=title, plan_amount=Decimal(amount), note=note, position=pos)
