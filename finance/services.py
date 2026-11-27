"""Расчёты раздела «Финансы» по шаблону компании «Фин план»: план / факт / остаток.

Ничего не хранится в виде итогов: суммы блоков, объектов и компании считаются из строк,
поэтому после любой правки всё сходится само.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from .models import PlanLine

ZERO = Decimal(0)
S = PlanLine.Section
OBJECT_SECTIONS = [S.INCOME, S.LABOR, S.MATERIAL, S.OVERHEAD]
SHORT = {S.INCOME: "Поступления", S.LABOR: "Оплата работ", S.MATERIAL: "Материалы",
         S.OVERHEAD: "Накладные", S.DEBT: "Долг компании"}
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
          "ноябрь", "декабрь"]


def money(plan=ZERO, fact=ZERO):
    plan, fact = plan or ZERO, fact or ZERO
    return {"plan": plan, "fact": fact, "left": plan - fact,
            "pct": min(int(fact * 100 / plan), 100) if plan else (100 if fact else 0)}


def add(*items):
    return money(sum((i["plan"] for i in items), ZERO), sum((i["fact"] for i in items), ZERO))


def sums(lines):
    return money(sum((ln.plan_amount for ln in lines), ZERO), sum((ln.fact_amount for ln in lines), ZERO))


def object_plan(obj, lines):
    """Финплан одного объекта: блоки со строками и итоги, как лист объекта в таблице."""
    sections = []
    for key in OBJECT_SECTIONS:
        rows = [ln for ln in lines if ln.section == key]
        sections.append({"key": key, "label": S(key).label, "short": SHORT[key], "lines": rows,
                         "is_income": key == S.INCOME, **sums(rows)})
    by = {s["key"]: s for s in sections}
    income = money(by[S.INCOME]["plan"], by[S.INCOME]["fact"])
    expense = add(*(by[k] for k in PlanLine.EXPENSES))
    return {"o": obj, "sections": sections, "by": by, "income": income, "expense": expense,
            "balance": {"plan": income["plan"] - expense["plan"], "fact": income["fact"] - expense["fact"]},
            "count": len(lines), "late": sum(ln.overdue for ln in lines)}


def plan_objects():
    """Объекты, у которых есть строки финплана, — в том порядке, как их добавляли (вкладки как листы)."""
    from objects.models import ConstructionObject
    first = {}
    for oid, pk in PlanLine.objects.exclude(construction_object=None).values_list("construction_object_id", "pk"):
        first[oid] = min(first.get(oid, pk), pk)
    objs = ConstructionObject.objects.in_bulk(list(first))
    return [objs[i] for i in sorted(first, key=first.get) if i in objs]


def summary():
    """Сводная таблица: каждый объект по блокам + общий долг + итог по компании."""
    lines = list(PlanLine.objects.select_related("construction_object"))
    objs = plan_objects()
    rows = [object_plan(o, [ln for ln in lines if ln.construction_object_id == o.pk]) for o in objs]
    debts = [ln for ln in lines if ln.section == S.DEBT]
    debt = sums(debts)
    total = {k: add(*(r["by"][k] for r in rows)) if rows else money() for k in OBJECT_SECTIONS}
    income = total[S.INCOME]
    expense = add(*(total[k] for k in PlanLine.EXPENSES))
    expense_all = add(expense, debt)  # как в таблице: «Итого расходы» по компании включает общий долг
    return {"rows": rows, "total": total, "income": income, "expense": expense, "expense_all": expense_all,
            "debt": debt, "debts": debts,
            "balance": {"plan": income["plan"] - expense_all["plan"], "fact": income["fact"] - expense_all["fact"]},
            "lines": lines}


def attention(lines, today=None):
    """Что требует внимания: просрочки, срок в ближайшие 7 дней, строки с пометкой «предварительно/уточнить»."""
    t = today or date.today()
    items = []
    for ln in lines:
        where = ln.construction_object.name if ln.construction_object else "Долг компании"
        if ln.overdue:
            items.append(("bad", f"Просрочено с {ln.plan_date:%d.%m.%Y}", ln, where))
        elif ln.left > 0 and ln.plan_date and ln.plan_date <= t + timedelta(days=7):
            items.append(("warn", f"Срок {ln.plan_date:%d.%m.%Y}", ln, where))
    for ln in lines:
        note = ln.note.lower()
        if ln.left > 0 and any(w in note for w in ("предварит", "уточн", "не подтвержд")):
            items.append(("info", ln.note, ln, ln.construction_object.name if ln.construction_object else ""))
    return items


def calendar(lines, today=None):
    """Платёжный календарь: всё, что ещё не получено и не оплачено, по срокам."""
    t = today or date.today()
    open_ = [ln for ln in lines if ln.left > 0]
    groups = {}

    def put(key, title, ln):
        g = groups.setdefault(key, {"key": key, "title": title, "lines": [], "in": ZERO, "out": ZERO})
        g["lines"].append(ln)
        g["in" if ln.is_income else "out"] += ln.left

    for ln in sorted(open_, key=lambda x: (x.plan_date or date.max, x.pk)):
        d = ln.plan_date
        if d is None:
            put("9999", "Без даты", ln)
        elif d < t:
            put("0000", "Просрочено", ln)
        else:
            put(f"{d:%Y-%m}", f"{MONTHS[d.month - 1].capitalize()} {d.year}", ln)
    result = [groups[k] for k in sorted(groups)]
    for g in result:
        g["net"] = g["in"] - g["out"]
    total_in = sum((g["in"] for g in result), ZERO)
    total_out = sum((g["out"] for g in result), ZERO)
    week = [ln for ln in open_ if ln.plan_date and ln.plan_date <= t + timedelta(days=7)]
    return {"groups": result, "in": total_in, "out": total_out, "net": total_in - total_out,
            "week": sorted(week, key=lambda x: x.plan_date), "count": len(open_)}


def month_end(d):
    return d.replace(day=monthrange(d.year, d.month)[1])


def overruns(lines):
    """Где факт больше плана: по строке (если план задан) и по блоку объекта. [(level, где, текст, object_id)]."""

    def m(x):
        return f"{int(x):,}".replace(",", " ") + " ₸"
    items, blocks = [], {}
    for ln in lines:
        if ln.section == S.INCOME:
            continue
        key = (ln.construction_object_id, ln.section)
        b = blocks.setdefault(key, [ZERO, ZERO, ln])
        b[0] += ln.plan_amount or ZERO
        b[1] += ln.fact_amount or ZERO
        if ln.plan_amount and ln.fact_amount > ln.plan_amount:
            where = ln.construction_object.name if ln.construction_object else "Долг компании"
            items.append(("warn", where, f"{ln.name or S(ln.section).label}: факт {m(ln.fact_amount)} больше плана "
                                         f"{m(ln.plan_amount)} на {m(ln.fact_amount - ln.plan_amount)}",
                          ln.construction_object_id))
    for (oid, sec), (plan, fact, ln) in blocks.items():
        if fact > plan:
            where = ln.construction_object.name if ln.construction_object else "Долг компании"
            items.insert(0, ("bad", where, f"{S(sec).label}: факт {m(fact)} больше плана {m(plan)} на {m(fact - plan)}",
                             oid))
    return items
