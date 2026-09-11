"""D142: what an item already in the catalogue hands a new one.

The receiving desk types the same nine boxes for the eleventh strength of a
drug it already stocks, and the catalogue shows what happens when it goes
wrong: sizes typed into the name, generics left blank (06-client-data.md §3).

D139 offered a "same as" picker that deliberately withheld `name` and
`strength`, on the argument that copying them clones the sibling. The owner's
answer is that clearing one box is easier than remembering which four to fill,
so the copy is now complete and the operator edits what differs. The code is
never copied — D67 assigns it at save, like a document number.
"""

from catalog.models import Item

COPIED_FIELDS = (
    "name", "category", "is_batch_tracked", "has_expiry", "vat_exempt",
    "base_unit", "generic_name", "dosage_form", "strength",
    "pack_description", "maintained_price", "pricing_mode",
    "auto_margin_pct", "min_margin_pct", "reorder_level", "shelf_bin",
)


def _value(item: Item, field: str):
    """Booleans stay boolean for the checkboxes; everything else becomes the
    string a text or number box carries, with `None` as an empty box."""
    value = getattr(item, field)
    if isinstance(value, bool):
        return value
    return "" if value is None else str(value)


def item_copy_context(enabled: bool) -> dict:
    """Sources for the copy-from picker, and their values.

    Retired items are not offered (D125) — copying from one would spread a
    description the owner has already withdrawn. `is_active` is not among the
    copied fields for the same reason: every source is active, so copying it
    could only ever say what the default already says.
    """
    if not enabled:
        return {"copy_items": [], "copy_data": {}}
    items = list(Item.objects.filter(is_active=True).order_by("code"))
    return {
        "copy_items": items,
        "copy_data": {
            str(item.pk): {field: _value(item, field) for field in COPIED_FIELDS}
            for item in items
        },
    }
