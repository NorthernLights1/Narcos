"""Row removal on entry forms (field testing, D88): every formset row
carries its own ✕ button. The Django DELETE checkbox stays in the page
(it is what actually deletes a saved row on submit) but is never shown —
staff asked for a button, not a tick-then-save ritual."""

from decimal import Decimal

import pytest
from django.urls import reverse

from docs.models import Document, DocType
from money.models import PaymentLine

pytestmark = pytest.mark.django_db


def _receiving_form_html(client) -> str:
    return client.get(
        reverse("document_create", args=[DocType.RECEIVING])
    ).content.decode()


def test_every_row_has_a_delete_button(client, owner):
    client.force_login(owner)
    html = _receiving_form_html(client)
    assert "data-del-row" in html


def test_delete_checkbox_is_present_but_hidden(client, owner):
    """The checkbox is the mechanism, not the interface: Django needs
    prefix-N-DELETE on submit to drop a saved row."""
    client.force_login(owner)
    html = _receiving_form_html(client)
    assert "-DELETE" in html            # still submitted
    assert "row-del-box" in html        # ...inside the hidden wrapper


def test_saved_row_is_deleted_when_its_box_is_ticked(client, owner, cash, rent):
    """Regression: the ✕ button ticks this box, so the server contract
    behind it must keep working."""
    doc = Document.objects.create(doc_type=DocType.EXPENSE, created_by=owner,
                                  expense_category=rent, payee="Landlord",
                                  grand_total=Decimal("80.00"))
    line = PaymentLine.objects.create(document=doc, account=cash,
                                      amount=Decimal("80.00"))
    client.force_login(owner)
    response = client.post(reverse("document_edit", args=[doc.pk]), {
        "expense_category": str(rent.pk),
        "payee": "Landlord",
        "grand_total": "80.00",
        "notes": "",
        "payments-TOTAL_FORMS": "1",
        "payments-INITIAL_FORMS": "1",
        "payments-MIN_NUM_FORMS": "0",
        "payments-MAX_NUM_FORMS": "1000",
        "payments-0-id": str(line.pk),
        "payments-0-account": str(cash.pk),
        "payments-0-method": "CASH",
        "payments-0-amount": "80.00",
        "payments-0-DELETE": "on",
    })
    assert response.status_code == 302
    assert PaymentLine.objects.count() == 0
