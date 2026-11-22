from django.conf import settings
from django.urls import reverse
from django.utils.functional import SimpleLazyObject


def _nav_objects():
    from objects.models import ConstructionObject
    objs = list(ConstructionObject.objects.only("id", "name", "code", "city", "status"))
    return [o for o in objs if o.is_working] + [o for o in objs if not o.is_working]


# Списки «Документов», где выбор объекта в шапке сразу фильтрует таблицу на странице.
DOC_LISTS = {"docflow_all", "docflow_orders", "docflow_letters", "docflow_letters_out",
             "docflow_letters_internal", "docflow_contracts"}


def object_picker(request, objects):
    """Выбор объекта в верхней панели (рядом с логотипом).

    mode:
      sync   — страница сама показывает выбранный объект (Главная, обзор «Документов»): ссылки ведут
               на эту же страницу с ?object=<id>; без параметра страница подставит сохранённый выбор;
      filter — списки «Документов»: выбор фильтрует таблицу на странице без перехода;
      link   — остальные страницы: ссылка ведёт в карточку объекта.
    Выбор запоминается в браузере (localStorage), поэтому сохраняется при переходах и в демо-версии.
    """
    match = getattr(request, "resolver_match", None)
    name = (match.url_name if match else "") or ""
    obj_id = request.GET.get("object", "")
    explicit = "object" in request.GET
    cur = next((o for o in objects if obj_id.isdigit() and o.pk == int(obj_id)), None)

    if name == "dashboard":
        keep = {k: request.GET.get(k, "") for k in ("period", "from", "to")}

        def href(pk):
            params = {**keep, "object": pk}
            return "?" + "&".join(f"{k}={v}" for k, v in params.items() if v) if any(params.values()) \
                else reverse("dashboard")
        mode = "sync"
    elif name == "docflow_home" or name in DOC_LISTS or name.startswith("docflow"):
        base = reverse("docflow_home")

        def href(pk):
            return f"{base}?object={pk}" if pk else base
        mode = "sync" if name == "docflow_home" else ("filter" if name in DOC_LISTS else "link")
    else:
        def href(pk):
            return reverse("object_detail", args=[pk]) if pk else reverse("object_list")
        mode = "link"
    if mode != "sync":
        cur, explicit = None, False
    return {"mode": mode, "cur": cur, "explicit": explicit, "all_href": href(""),
            "items": [(o, href(o.pk)) for o in objects]}


def demo(request):
    """DEMO_MODE включается при сборке статической демо-версии (build_static).
    nav_objects — список объектов для выбора в верхней панели."""
    def notif_items():
        if not request.user.is_authenticated:
            return []
        from .views import notifications_for
        return notifications_for(request.user)
    nav_objects = SimpleLazyObject(_nav_objects)
    return {"DEMO": getattr(settings, "DEMO_MODE", False), "nav_objects": nav_objects,
            "obj_pick": SimpleLazyObject(lambda: object_picker(request, nav_objects)),
            "notif_items": SimpleLazyObject(notif_items)}
