"""D137: a filter the user set stays set.

D131 settled that nobody is logged in automatically, so staff sign in every
morning on a machine that was switched off overnight. A session-backed memory
would therefore reset daily, which is the thing being complained about, so this
lives on the user row.

**Why it rewrites `request.GET`.** Every filtered view already reads its
parameters from `request.GET`, in a dozen places between them. Replacing that
mapping once, at the top of the view, leaves all of that code correct and
unchanged; threading a second mapping through would touch every read and invite
one of them to be missed. These are read-only list views, so nothing downstream
writes through it.
"""

from django.http import QueryDict

# One entry per filtered screen. The scope name is what the memory is keyed on,
# so two screens never re-filter each other.
DOCUMENT_FILTERS = ("type", "status", "settlement", "q", "customer",
                    "supplier", "start", "end")
INVENTORY_FILTERS = ("q", "show")
REPORT_FILTERS = ("period", "start", "end")


def restore_filters(request, scope: str, keys) -> None:
    """Fill in this user's remembered filters, and remember any they just set.

    An explicit filter always wins, and **presence decides, not truthiness**:
    the filter form submits its boxes even when they are empty, so `?type=` is
    a deliberate "show me everything" and is remembered as such. Only a request
    carrying none of the keys is treated as plain navigation and given the
    remembered values.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return

    if any(key in request.GET for key in keys):
        _remember(user, scope, {key: request.GET.get(key, "") for key in keys})
        return

    saved = (user.filter_state or {}).get(scope) or {}
    if not saved:
        return
    restored = QueryDict(mutable=True)
    restored.update(request.GET)
    for key, value in saved.items():
        if key in keys and value:
            restored[key] = value
    restored._mutable = False
    request.GET = restored


def _remember(user, scope: str, values: dict) -> None:
    """One UPDATE, and only when something actually changed."""
    state = dict(user.filter_state or {})
    if state.get(scope) == values:
        return
    state[scope] = values
    user.filter_state = state
    user.save(update_fields=["filter_state"])
