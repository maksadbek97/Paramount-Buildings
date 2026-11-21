from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import audit
from core.models import AuditLog
from core.views import form_page

from .forms import InventoryStartForm, PurchaseRequestForm, SupplierForm, WarehouseForm
from .models import Inventory, InventoryLine, PurchaseRequest, StockMovement, Warehouse


@login_required
def warehouse_detail(request, pk):
    w = get_object_or_404(Warehouse.objects.select_related("construction_object", "keeper"), pk=pk)
    rows = w.balances()
    return render(request, "warehouse/warehouse_detail.html", {
        "w": w, "rows": rows, "value": sum((r["value"] for r in rows), 0),
        "pending": w.pending_transfers(),
        "movements": StockMovement.objects.filter(warehouse=w).select_related(
            "material", "to_warehouse", "construction_object")[:30],
        "inventories": w.inventories.all()[:5],
    })


@login_required
def warehouse_create(request):
    return form_page(request, WarehouseForm, "Новый склад", lambda w: reverse("warehouse_detail", args=[w.pk]),
                     back=reverse("warehouse_list"))


@login_required
def supplier_create(request):
    return form_page(request, SupplierForm, "Новый поставщик", reverse("purchase_list"),
                     back=reverse("purchase_list"))


@login_required
@require_POST
def transfer_accept(request, pk):
    mv = get_object_or_404(StockMovement, pk=pk)
    before = audit.snapshot(mv)
    try:
        mv.accept(request.user)
    except ValidationError as e:
        messages.error(request, e.messages[0])
    else:
        audit.log(request, mv, AuditLog.Action.ACCEPT, before=before)
        messages.success(request, f"Принято: {mv.material} {mv.quantity.normalize():f} {mv.material.unit}")
    return redirect("warehouse_detail", mv.to_warehouse_id)


@login_required
def inventory_start(request):
    form = InventoryStartForm(request.POST or None, initial=dict(request.GET.items()))
    if request.method == "POST" and form.is_valid():
        w = form.cleaned_data["warehouse"]
        inv = Inventory.objects.create(warehouse=w, author=request.user, note=form.cleaned_data["note"])
        for row in w.balances():
            InventoryLine.objects.create(inventory=inv, material=row["material"], book_qty=row["balance"],
                                         actual_qty=row["balance"])
        audit.log(request, inv, AuditLog.Action.CREATE)
        return redirect("inventory_detail", inv.pk)
    return render(request, "form.html", {"form": form, "title": "Инвентаризация", "submit": "Начать",
                                         "subtitle": "Система покажет учётные остатки, вы введёте фактические.",
                                         "back": reverse("warehouse_list")})


@login_required
def inventory_detail(request, pk):
    inv = get_object_or_404(Inventory.objects.select_related("warehouse"), pk=pk)
    lines = list(inv.lines.select_related("material"))
    if request.method == "POST" and inv.status == Inventory.Status.DRAFT:
        for line in lines:
            raw = request.POST.get(f"actual_{line.pk}", "").replace(" ", "").replace(",", ".")
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue
            if value >= 0 and value != line.actual_qty:
                line.actual_qty = value
                line.save(update_fields=["actual_qty"])
        if request.POST.get("approve"):
            if not request.user.has_perm("warehouse.approve_inventory"):
                messages.error(request, "Утвердить акт может только ответственный с правом утверждения.")
            else:
                inv.approve(request.user)
                audit.log(request, inv, AuditLog.Action.ACCEPT, reason="Утверждение акта инвентаризации")
                messages.success(request, "Акт утверждён, остатки скорректированы")
        else:
            messages.success(request, "Сохранено")
        return redirect("inventory_detail", pk)
    return render(request, "warehouse/inventory.html", {"inv": inv, "lines": lines})


@login_required
def purchase_list(request):
    qs = PurchaseRequest.objects.select_related("material", "construction_object", "supplier", "warehouse")
    f = request.GET.get("status", "open")
    if f == "open":
        qs = qs.filter(status__in=PurchaseRequest.OPEN)
    elif f in PurchaseRequest.Status.values:
        qs = qs.filter(status=f)
    return render(request, "warehouse/purchase_list.html", {"requests": qs, "current": f})


@login_required
def purchase_create(request):
    return form_page(request, PurchaseRequestForm, "Заявка на материал",
                     lambda p: reverse("purchase_detail", args=[p.pk]), form_kwargs={"user": request.user},
                     subtitle="Система проверит нормы, остатки на объекте и других складах и уже заказанное.",
                     back=reverse("purchase_list"))


@login_required
def purchase_detail(request, pk):
    p = get_object_or_404(PurchaseRequest.objects.select_related("material", "construction_object", "supplier",
                                                                 "warehouse", "author"), pk=pk)
    history = AuditLog.objects.filter(module=PurchaseRequest._meta.verbose_name_plural, object_id=str(p.pk))
    prices = StockMovement.objects.filter(material=p.material, kind="in", price__isnull=False).select_related(
        "supplier")[:6]
    return render(request, "warehouse/purchase_detail.html", {
        "p": p, "a": p.analysis(), "history": history, "prices": prices,
        "can_approve": request.user.has_perm("warehouse.approve_purchase")})


@login_required
@require_POST
def purchase_act(request, pk):
    p = get_object_or_404(PurchaseRequest, pk=pk)
    to = request.POST.get("to")
    before = audit.snapshot(p)
    if to in ("approved", "rejected") and not request.user.has_perm("warehouse.approve_purchase"):
        messages.error(request, "Согласовать заявку может снабженец или руководитель с правом согласования.")
        return redirect("purchase_detail", pk)
    try:
        if to == "received":
            p.receive(request.user)
            action = AuditLog.Action.ACCEPT
        elif to == "rejected" and p.status in PurchaseRequest.OPEN:
            p.status = to
            p.save(update_fields=["status"])
            action = AuditLog.Action.REJECT
        elif PurchaseRequest.FLOW.get(p.status, (None,))[0] == to:
            if to == "ordered" and not p.supplier_id:
                raise ValidationError("Перед заказом выберите поставщика (кнопка «Изменить»).")
            p.status = to
            p.save(update_fields=["status"])
            action = AuditLog.Action.UPDATE
        else:
            raise ValidationError("Это действие сейчас недоступно.")
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect("purchase_detail", pk)
    audit.log(request, p, action, before=before, reason=request.POST.get("comment", "")[:300])
    messages.success(request, p.get_status_display())
    return redirect("purchase_detail", pk)


@login_required
def purchase_edit(request, pk):
    p = get_object_or_404(PurchaseRequest, pk=pk)
    return form_page(request, PurchaseRequestForm, f"Заявка {p.number}", reverse("purchase_detail", args=[pk]),
                     instance=p, back=reverse("purchase_detail", args=[pk]))


