from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from objects.models import ConstructionObject

from .models import Inventory, InventoryLine, Material, PurchaseRequest, StockMovement, Warehouse

D = Decimal
TODAY = date.today()


class MaterialMovementTests(TestCase):
    """ТЗ п. 32.1: 100 т на складе → 20 т на объект → приёмка прорабом → списано 5 → на объекте 15."""

    def test_tz_32_1(self):
        user = get_user_model().objects.create_superuser("k", password="x")
        self.client.force_login(user)
        obj = ConstructionObject.objects.create(name="ЖК Атлант")
        central = Warehouse.objects.create(name="Центральный")
        site = Warehouse.objects.create(name="Склад объекта", kind="object", construction_object=obj)
        cement = Material.objects.create(name="Цемент", unit="т", price=D("38000"))
        StockMovement.objects.create(material=cement, kind="in", quantity=D("100"), date=TODAY, warehouse=central)

        self.client.post(reverse("movement_create"), {"kind": "transfer", "material": cement.pk, "quantity": "20",
                                                      "date": TODAY.isoformat(), "warehouse": central.pk,
                                                      "to_warehouse": site.pk})
        t = StockMovement.objects.get(kind="transfer")
        self.assertEqual(cement.balance(central), D("80"))
        self.assertEqual(cement.card(site)["pending"], D("20"))  # пришло, но ещё не принято
        self.assertEqual(cement.balance(site), 0)
        self.assertEqual(cement.stock, D("100"))  # в пути — всё ещё наше

        self.client.post(reverse("transfer_accept", args=[t.pk]))
        self.assertEqual(cement.balance(site), D("20"))
        r = self.client.post(reverse("transfer_accept", args=[t.pk]))  # второй раз не принять
        self.assertEqual(cement.balance(site), D("20"))

        self.client.post(reverse("movement_create"), {"kind": "out", "material": cement.pk, "quantity": "5",
                                                      "date": TODAY.isoformat(), "warehouse": site.pk})
        self.assertEqual(cement.balance(site), D("15"))
        self.assertEqual(cement.stock, D("95"))
        self.assertEqual(StockMovement.objects.get(kind="out").construction_object, obj)
        self.assertEqual(r.status_code, 302)

    def test_writeoff_needs_reason_and_transfer_needs_target(self):
        user = get_user_model().objects.create_user("u", password="x")
        self.client.force_login(user)
        w = Warehouse.objects.create(name="W")
        m = Material.objects.create(name="Песок", unit="м³")
        StockMovement.objects.create(material=m, kind="in", quantity=D("10"), date=TODAY, warehouse=w)
        base = {"material": m.pk, "quantity": "1", "date": TODAY.isoformat(), "warehouse": w.pk}
        r = self.client.post(reverse("movement_create"), {**base, "kind": "writeoff"})
        self.assertContains(r, "причину")
        r = self.client.post(reverse("movement_create"), {**base, "kind": "transfer"})
        self.assertContains(r, "на какой склад")
        self.assertEqual(StockMovement.objects.count(), 1)


class InventoryTests(TestCase):
    def test_inventory_creates_adjustment(self):
        user = get_user_model().objects.create_superuser("k", password="x")
        self.client.force_login(user)
        w = Warehouse.objects.create(name="W")
        m = Material.objects.create(name="Цемент", unit="т")
        StockMovement.objects.create(material=m, kind="in", quantity=D("50"), date=TODAY, warehouse=w)
        self.client.post(reverse("inventory_start"), {"warehouse": w.pk})
        inv = Inventory.objects.get()
        line = InventoryLine.objects.get()
        self.assertEqual(line.book_qty, D("50"))
        self.client.post(reverse("inventory_detail", args=[inv.pk]), {f"actual_{line.pk}": "47,5", "approve": "1"})
        inv.refresh_from_db()
        self.assertEqual(inv.status, "approved")
        self.assertTrue(inv.number.startswith("ИНВ-"))
        self.assertEqual(m.balance(w), D("47.5"))
        self.assertEqual(StockMovement.objects.get(kind="adj_minus").quantity, D("2.5"))


class PurchaseTests(TestCase):
    def test_request_flow_analysis_and_single_receipt(self):
        user = get_user_model().objects.create_superuser("s", password="x")
        self.client.force_login(user)
        obj = ConstructionObject.objects.create(name="О")
        site = Warehouse.objects.create(name="Склад О", kind="object", construction_object=obj)
        other = Warehouse.objects.create(name="Центральный")
        m = Material.objects.create(name="Клей", unit="мешок")
        StockMovement.objects.create(material=m, kind="in", quantity=D("30"), date=TODAY, warehouse=other,
                                     price=D("2500"))
        self.client.post(reverse("purchase_create"), {
            "construction_object": obj.pk, "warehouse": site.pk, "material": m.pk, "quantity": "100",
            "price": "3000"})
        p = PurchaseRequest.objects.get()
        a = p.analysis()
        self.assertEqual(a["elsewhere"], D("30"))
        self.assertTrue(any("других складах" in w for w in a["warnings"]))
        self.assertTrue(any("Цена выше" in w for w in a["warnings"]))

        self.client.post(reverse("purchase_act", args=[p.pk]), {"to": "approved"})
        r = self.client.post(reverse("purchase_act", args=[p.pk]), {"to": "ordered"})
        p.refresh_from_db()
        self.assertEqual(p.status, "approved")  # без поставщика заказать нельзя
        from .models import Supplier
        p.supplier = Supplier.objects.create(name="ТОО Клей")
        p.save()
        self.client.post(reverse("purchase_act", args=[p.pk]), {"to": "ordered"})
        self.client.post(reverse("purchase_act", args=[p.pk]), {"to": "received"})
        self.client.post(reverse("purchase_act", args=[p.pk]), {"to": "received"})  # дважды не провести
        self.assertEqual(m.balance(site), D("100"))
        self.assertEqual(StockMovement.objects.filter(request=p).count(), 1)
        self.assertEqual(r.status_code, 302)
