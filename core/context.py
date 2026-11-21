from django.conf import settings


def demo(request):
    """DEMO_MODE включается при сборке статической демо-версии (build_static)."""
    return {"DEMO": getattr(settings, "DEMO_MODE", False)}
