from django import template
from django.utils.text import capfirst

register = template.Library()


@register.filter
def field_label(model, name):
    """Column header from the field's verbose_name — never the raw field name."""
    return capfirst(str(model._meta.get_field(name).verbose_name))


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
