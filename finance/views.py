"""Раздел «Финансы»: финплан «план / факт» по шаблону компании, в виде таблицы как в Excel.

Страницы отдают данные (finance/state.py), таблицу рисует и пересчитывает static/fingrid.js.
Каждая правка ячейки сохраняется сразу: на сервере — через /finance/api/, на сайте по ссылке — в браузере.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from core import audit
from core.models import AuditLog
from objects.models import ConstructionObject

from . import state as st
from .models import ObjectContract, PlanLine, WorkAct

S = PlanLine.Section


def base_ctx(tab, **extra):
    return {"tab": tab, "fin_objects": st.objects(), "fin_state": st.state_json(), "today": date.today(), **extra}


@login_required
def home(request):
    return render(request, "finance/home.html", base_ctx("home"))


@login_required
def object_plan(request, pk):
    obj = get_object_or_404(ConstructionObject, pk=pk)
    return render(request, "finance/object.html", base_ctx(f"o{obj.pk}", obj=obj, cur_obj=obj))


@login_required
def debts(request):
    return render(request, "finance/debts.html", base_ctx("debts"))


# ---------------- Сохранение правок из таблицы ----------------

MODELS = {"line": PlanLine, "contract": ObjectContract, "act": WorkAct}
TEXT = {"line": {"name": 250, "note": 300}, "contract": {"number": 60, "subject": 250, "note": 300},
        "act": {"work": 250, "note": 300}}
MONEY = {"line": ("plan_amount", "fact_amount"), "contract": ("amount",), "act": ("amount",)}
DATES = {"line": ("plan_date", "fact_date"), "contract": ("date",), "act": ("date",)}
# Имена полей в таблице → поля модели
ALIAS = {"plan": "plan_amount", "fact": "fact_amount", "pdate": "plan_date", "fdate": "fact_date", "pos": "position"}


def _money(v):
    if v in (None, ""):
        return Decimal(0)
    try:
        return Decimal("".join(str(v).split()).replace(",", ".").replace("−", "-"))
    except InvalidOperation:
        raise ValidationError("Сумма указана неверно.")


def _date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValidationError("Дата указана неверно.")


def _apply(kind, obj, data):
    data = {ALIAS.get(k, k): v for k, v in data.items()}
    for f, limit in TEXT[kind].items():
        if f in data:
            setattr(obj, f, str(data[f] or "").strip()[:limit])
    for f in MONEY[kind]:
        if f in data:
            setattr(obj, f, _money(data[f]))
    for f in DATES[kind]:
        if f in data:
            setattr(obj, f, _date(data[f]))
    if "object" in data:
        oid = data["object"]
        obj.construction_object = ConstructionObject.objects.filter(pk=oid).first() if oid not in (None, "") else None
    if "position" in data:
        try:
            obj.position = max(int(data["position"]), 0)
        except (TypeError, ValueError):
            pass
    if kind == "line" and "section" in data:
        if data["section"] not in S.values:
            raise ValidationError("Неизвестный блок.")
        obj.section = data["section"]
    if kind == "contract" and "kind" in data:
        obj.kind = data["kind"] if data["kind"] in ObjectContract.Kind.values else ObjectContract.Kind.MAIN
    if kind == "line" and obj.fact_amount and not obj.fact_date:
        obj.fact_date = date.today()
    if kind == "contract" and not obj.construction_object_id:
        raise ValidationError("Укажите объект.")


@login_required
@require_POST
def api(request):
    """{kind: line|contract|act, op: save|delete, id?, data: {...}} → {ok, row}."""
    try:
        body = json.loads(request.body or b"{}")
        kind, op = body.get("kind"), body.get("op", "save")
        model = MODELS[kind]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "error": "Неверный запрос."}, status=400)
    pk = body.get("id")
    obj = model.objects.filter(pk=pk).first() if pk and int(pk) > 0 else None
    if op == "delete":
        if obj:
            audit.log(request, obj, AuditLog.Action.DELETE, before=audit.snapshot(obj), reason="Удалено в «Финансах»")
            obj.delete()
        return JsonResponse({"ok": True})
    editing = obj is not None
    obj = obj or model()
    before = audit.snapshot(obj) if editing else None
    try:
        _apply(kind, obj, body.get("data") or {})
        obj.full_clean()
    except ValidationError as e:
        msg = "; ".join(m for ms in getattr(e, "message_dict", {"": e.messages}).values() for m in ms)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    obj.save()
    audit.log(request, obj, AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE, before=before)
    return JsonResponse({"ok": True, "row": st.ROW[kind](obj)})
