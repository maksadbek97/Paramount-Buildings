from django.db import migrations


def assign_central(apps, schema_editor):
    """Все старые движения относятся к центральному складу."""
    Warehouse = apps.get_model("warehouse", "Warehouse")
    StockMovement = apps.get_model("warehouse", "StockMovement")
    if StockMovement.objects.filter(warehouse__isnull=True).exists():
        central, _ = Warehouse.objects.get_or_create(name="Центральный склад", defaults={"kind": "central"})
        StockMovement.objects.filter(warehouse__isnull=True).update(warehouse=central)


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0003_alter_stockmovement_options_material_brand_and_more")]
    operations = [migrations.RunPython(assign_central, migrations.RunPython.noop)]
