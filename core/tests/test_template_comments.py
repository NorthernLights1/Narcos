"""A `{# ... #}` comment must open and close on the same line.

Django does not treat a wrapped `{# ... #}` as a comment — it renders the
text to the page. This has bitten three times now:

* D82 — a stray paragraph in the party box on every printout.
* D98 — a note about destructive dialogs in `base.html`, so it showed on
  *every page* of the app, and a second one on the document detail page.
* 2026-08-03 — a note about help text, repeated under all 23 fields of the
  settings page. Temesgen caught that one from a screenshot.

Care has failed three times, so this is a test. Use `{% comment %}` when the
note does not fit on one line.
"""

from pathlib import Path

import pytest
from django.conf import settings


def _template_files():
    roots = [Path(directory) for engine in settings.TEMPLATES
             for directory in engine.get("DIRS", [])]
    return sorted(path for root in roots for path in root.rglob("*.html"))


def test_there_are_templates_to_check():
    """Guards the guard: a wrong path would make every assertion below pass."""
    assert _template_files(), "no templates found — check TEMPLATES['DIRS']"


@pytest.mark.parametrize("path", _template_files(), ids=lambda p: p.name)
def test_no_comment_spans_more_than_one_line(path):
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        assert line.count("{#") == line.count("#}"), (
            f"{path}:{number} — a {{# #}} comment does not close on its own "
            f"line, so Django prints it to the page. Use "
            f"{{% comment %}} ... {{% endcomment %}} instead."
        )
