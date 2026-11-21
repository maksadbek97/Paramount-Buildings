from django.db import migrations
from django.db.models import F


def accept_existing(apps, schema_editor):
    """Выработка, внесённая до появления приёмки ПТО, считается принятой — цифры не меняются."""
    WorkLog = apps.get_model("contracts", "WorkLog")
    WorkLog.objects.filter(status="submitted", reviewed_at__isnull=True).update(
        status="accepted", accepted_volume=F("volume"))


class Migration(migrations.Migration):
    dependencies = [("contracts", "0002_alter_workcontract_options_workcontract_floor_and_more")]
    operations = [migrations.RunPython(accept_existing, migrations.RunPython.noop)]
