from django import template

register = template.Library()


@register.filter
def get_field(form, name):
    """{{ form|get_field:"name" }} — поле формы по имени (или None)."""
    try:
        return form[name]
    except KeyError:
        return None


@register.filter
def plural(n, forms):
    """{{ n|plural:"задача,задачи,задач" }}"""
    one, few, many = forms.split(",")
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def initials(name):
    """«Ким Сергей Викторович» -> «Ким С. В.»"""
    parts = str(name or "").split()
    if len(parts) < 2:
        return name or ""
    return parts[0] + " " + " ".join(p[0] + "." for p in parts[1:3])
