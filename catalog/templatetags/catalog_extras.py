from django import template

register = template.Library()


@register.filter
def attr(obj, name):
    """Dynamic attribute lookup for generic list columns; choice fields show labels."""
    display = getattr(obj, f"get_{name}_display", None)
    if callable(display):
        return display()
    value = getattr(obj, name, "")
    if value is True:
        return "✓"
    if value is False:
        return "—"
    return value
