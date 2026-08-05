"""R61: the "Reference fields" page becomes a pencil next to each field a
posted document still allows to change.

The page needed explaining — its own owner asked what it was. A ✎ beside
the box explains itself, and the fields *without* one teach the D90 rule
better than a separate screen ever did: everything that moved a ledger is
untouchable, everything ledger-free is editable and audited.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import AuditLog, CompanySettings
from docs.posting import post
from docs.tests.conftest import make_expense

pytestmark = pytest.mark.django_db

D = Decimal
EDITABLE = ["fiscal_receipt_no", "machine_total", "withholding_certificate_no",
            "notes", "due_date"]


def _url(doc, field):
    return reverse("document_field_edit", args=[doc.pk, field])


@pytest.fixture
def posted(client, owner, cash, rent):
    client.force_login(owner)
    return post(make_expense(owner, cash, rent), owner)


def test_every_editable_field_offers_a_pencil(client, posted):
    content = client.get(
        reverse("document_detail", args=[posted.pk])).content.decode()
    for field in EDITABLE:
        assert _url(posted, field) in content, field


def test_ledger_fields_offer_none(client, posted):
    """D90 in the interface: no pencil means the ledgers depend on it."""
    content = client.get(
        reverse("document_detail", args=[posted.pk])).content.decode()
    assert reverse("document_field_edit", args=[posted.pk, "grand_total"]) not in content


def test_get_returns_an_editor_for_that_field_alone(client, posted):
    content = client.get(_url(posted, "fiscal_receipt_no")).content.decode()
    assert 'name="fiscal_receipt_no"' in content
    assert 'name="withholding_certificate_no"' not in content


def test_saving_writes_the_value_and_audits_the_change(client, posted):
    response = client.post(_url(posted, "fiscal_receipt_no"),
                           {"fiscal_receipt_no": "FS-123"})
    assert response.status_code == 200
    posted.refresh_from_db()
    assert posted.fiscal_receipt_no == "FS-123"
    entry = AuditLog.objects.get(action="DOCUMENT_FIELD_UPDATE",
                                 entity_id=str(posted.pk))
    assert entry.after == {"fiscal_receipt_no": "FS-123"}


def test_saving_returns_the_new_value_for_the_page(client, posted):
    content = client.post(_url(posted, "fiscal_receipt_no"),
                          {"fiscal_receipt_no": "FS-9"}).content.decode()
    assert "FS-9" in content
    assert _url(posted, "fiscal_receipt_no") in content   # pencil comes back


def test_notes_and_due_date_are_editable_after_posting(client, posted):
    client.post(_url(posted, "notes"), {"notes": "customer called"})
    client.post(_url(posted, "due_date"), {"due_date": "2026-09-30"})
    posted.refresh_from_db()
    assert posted.notes == "customer called"
    assert posted.due_date == datetime.date(2026, 9, 30)


def test_a_field_outside_the_whitelist_is_refused(client, posted):
    before = posted.grand_total
    response = client.post(
        reverse("document_field_edit", args=[posted.pk, "grand_total"]),
        {"grand_total": "1.00"})
    assert response.status_code == 404
    posted.refresh_from_db()
    assert posted.grand_total == before


def test_a_box_switched_off_in_settings_is_refused(client, posted):
    """R56/D106 survives the move: no fiscal machine, no machine total."""
    settings = CompanySettings.load()
    settings.fiscal_machine_present = False
    settings.save()
    assert client.get(_url(posted, "machine_total")).status_code == 404
    content = client.get(
        reverse("document_detail", args=[posted.pk])).content.decode()
    assert _url(posted, "machine_total") not in content


def test_drafts_keep_the_full_edit_form(client, owner, cash, rent):
    client.force_login(owner)
    doc = make_expense(owner, cash, rent)
    assert client.get(_url(doc, "fiscal_receipt_no")).status_code == 404


def test_voided_documents_are_immutable(client, owner, posted):
    from docs.posting import void
    void(posted, owner, reason="test")
    assert client.post(_url(posted, "notes"), {"notes": "x"}).status_code == 404


def test_staff_may_still_enter_a_fiscal_receipt_number(client, employee, posted):
    client.force_login(employee)
    response = client.post(_url(posted, "fiscal_receipt_no"),
                           {"fiscal_receipt_no": "FS-77"})
    assert response.status_code == 200
    posted.refresh_from_db()
    assert posted.fiscal_receipt_no == "FS-77"


def test_only_the_owner_may_move_a_payment_due_date(client, employee, posted):
    """It decides what counts as overdue in AR/AP — an owner's call."""
    client.force_login(employee)
    assert client.post(_url(posted, "due_date"),
                       {"due_date": "2026-09-30"}).status_code == 403
    posted.refresh_from_db()
    assert posted.due_date is None


def test_the_reference_page_is_gone(client, posted):
    response = client.get(reverse("document_edit", args=[posted.pk]))
    assert response.status_code == 302
    assert response.url == reverse("document_detail", args=[posted.pk])
