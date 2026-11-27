"""Данные финплана для таблицы на странице (static/fingrid.js): одна структура и для сервера, и для сайта по ссылке."""
import json
from decimal import Decimal

from django.urls import reverse

from objects.models import ConstructionObject

from . import services
from .models import ObjectContract, PlanLine, WorkAct


def _n(v):
    v = v or Decimal(0)
    return int(v) if v == v.to_integral_value() else float(v)


def _d(v):
    return v.isoformat() if v else ""


def line_row(ln):
    return {"id": ln.pk, "object": ln.construction_object_id, "section": ln.section, "name": ln.name,
            "plan": _n(ln.plan_amount), "pdate": _d(ln.plan_date), "fact": _n(ln.fact_amount),
            "fdate": _d(ln.fact_date), "note": ln.note, "pos": ln.position}


def contract_row(c):
    return {"id": c.pk, "object": c.construction_object_id, "kind": c.kind, "number": c.number, "date": _d(c.date),
            "subject": c.subject, "amount": _n(c.amount), "note": c.note, "pos": c.position}


def act_row(a):
    return {"id": a.pk, "object": a.construction_object_id, "work": a.work, "amount": _n(a.amount),
            "date": _d(a.date), "note": a.note, "pos": a.position}


ROW = {"line": line_row, "contract": contract_row, "act": act_row}


def objects():
    """Все объекты компании (кроме архива): сначала в порядке листов финплана, потом остальные."""
    first = services.plan_objects()
    rest = [o for o in ConstructionObject.objects.exclude(status="archive").order_by("created_at") if o not in first]
    return [o for o in first if o.status != "archive"] + rest


def state():
    return {
        "objects": [{"id": o.pk, "name": o.name, "code": o.code, "url": reverse("object_detail", args=[o.pk]),
                     "fin": reverse("finance_object", args=[o.pk])} for o in objects()],
        "lines": [line_row(x) for x in PlanLine.objects.all()],
        "contracts": [contract_row(x) for x in ObjectContract.objects.all()],
        "acts": [act_row(x) for x in WorkAct.objects.all()],
        "sections": [[k, v] for k, v in PlanLine.Section.choices],
    }


def state_json():
    return json.dumps(state(), ensure_ascii=False).replace("</", "<\\/")
