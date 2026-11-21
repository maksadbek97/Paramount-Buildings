from django.conf import settings
from django.utils.functional import SimpleLazyObject


def _nav_objects():
    from objects.models import ConstructionObject
    objs = list(ConstructionObject.objects.only("id", "name", "code", "status"))
    return [o for o in objs if o.is_working] + [o for o in objs if not o.is_working]


def demo(request):
    """DEMO_MODE включается при сборке статической демо-версии (build_static).
    nav_objects — список объектов для выбора в верхней панели."""
    def notif_items():
        if not request.user.is_authenticated:
            return []
        from .views import notifications_for
        return notifications_for(request.user)
    return {"DEMO": getattr(settings, "DEMO_MODE", False), "nav_objects": SimpleLazyObject(_nav_objects),
            "notif_items": SimpleLazyObject(notif_items)}
