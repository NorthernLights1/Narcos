"""D146: month-and-year only on the expiry box, per line, by a tick.

The carton often shows `09/2026` and nothing more, and the operator has to
invent a day. The tick swaps the day picker for a month picker and the server
stores the **last day** of that month.

Two constraints the owner set, and both are what keep this cheap:

*Nothing changes in the database.* `expiry_entered` stays a plain date column
and the tick is never stored — it is how the value was typed, not what it
means.

*Existing batches carry on exactly as they are.* Round 23 cancelled the
company-wide version of this feature because it made 76 batches on the shelf
impossible to re-receive: `Batch.get_or_create` keeps the stored expiry and
`docs/handlers.py` refuses a different one, and with no day picker anywhere the
operator could not express the stored day. A per-line tick has an escape — leave
it unticked — and D128's autofill means re-receiving never needs it.
"""

import datetime

import pytest
from django.urls import reverse

from catalog.models import Item, Supplier
from core.models import User
from docs.forms import ExpiryField
from docs.models import DocType, Document, DocumentLine
from docs.posting import post
from stock.models import Batch

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug():
    return Item.objects.create(code="AMOX", name="Amoxil", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               maintained_price=15)


# --- the field ------------------------------------------------------------

def test_a_month_becomes_the_last_day_of_that_month():
    assert ExpiryField().clean("2026-09") == datetime.date(2026, 9, 30)


def test_a_31_day_month_lands_on_the_31st():
    assert ExpiryField().clean("2026-12") == datetime.date(2026, 12, 31)


def test_february_lands_on_the_28th():
    assert ExpiryField().clean("2027-02") == datetime.date(2027, 2, 28)


def test_february_in_a_leap_year_lands_on_the_29th():
    assert ExpiryField().clean("2028-02") == datetime.date(2028, 2, 29)


def test_a_full_date_is_left_exactly_as_typed():
    """The tick is off by default, and an untouched entry must be untouched."""
    assert ExpiryField().clean("2026-09-15") == datetime.date(2026, 9, 15)


def test_a_month_that_does_not_exist_is_refused():
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        ExpiryField().clean("2026-13")


def test_an_empty_value_stays_empty():
    assert ExpiryField(required=False).clean("") is None


# --- through the form -----------------------------------------------------

def _receiving_post(drug, supplier, expiry):
    return {
        "supplier": str(supplier.pk), "notes": "",
        "supplier_invoice_date": "", "due_date": "",
        "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "1000",
        "lines-0-item": str(drug.pk), "lines-0-batch_no_entered": "B-1",
        "lines-0-expiry_entered": expiry, "lines-0-unit_label": "pack",
        "lines-0-factor": "1", "lines-0-qty_entered": "10",
        "lines-0-unit_cost_entered": "10.00",
        "payments-TOTAL_FORMS": "0", "payments-INITIAL_FORMS": "0",
        "payments-MIN_NUM_FORMS": "0", "payments-MAX_NUM_FORMS": "1000",
    }


def test_a_month_typed_on_a_receiving_line_saves_as_the_month_end(
        client, owner, supplier, drug):
    client.force_login(owner)
    response = client.post(reverse("document_create", args=["RECEIVING"]),
                           _receiving_post(drug, supplier, "2026-09"))
    assert response.status_code == 302
    line = DocumentLine.objects.get()
    assert line.expiry_entered == datetime.date(2026, 9, 30)


def test_a_full_date_typed_on_a_receiving_line_saves_unchanged(
        client, owner, supplier, drug):
    client.force_login(owner)
    client.post(reverse("document_create", args=["RECEIVING"]),
                _receiving_post(drug, supplier, "2026-09-15"))
    assert DocumentLine.objects.get().expiry_entered == datetime.date(2026, 9, 15)


# --- the tick on the page -------------------------------------------------

def test_the_tick_sits_beside_the_expiry_on_receiving(client, owner):
    client.force_login(owner)
    content = client.get(reverse("document_create",
                                 args=["RECEIVING"])).content.decode()
    assert "data-month-only" in content
    assert "Month and year only" in content


def test_a_sale_has_no_expiry_box_and_so_no_tick(client, owner):
    client.force_login(owner)
    content = client.get(reverse("document_create",
                                 args=["SALE"])).content.decode()
    assert "data-month-only" not in content


# --- the constraint that cancelled this in round 23 ----------------------

def test_an_existing_batch_still_re_receives_on_its_stored_day(
        owner, supplier, drug):
    """The 76-batch case. D128's autofill supplies the stored day, the tick is
    not involved, and the second receipt posts exactly as it does today."""
    first = Document.objects.create(doc_type=DocType.RECEIVING,
                                    created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=first, item=drug, qty_entered=10,
                                unit_cost_entered=10, batch_no_entered="B-1",
                                expiry_entered=datetime.date(2026, 9, 15),
                                unit_label="pack", factor=1)
    post(first, owner)

    second = Document.objects.create(doc_type=DocType.RECEIVING,
                                     created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=second, item=drug, qty_entered=5,
                                unit_cost_entered=10, batch_no_entered="B-1",
                                expiry_entered=datetime.date(2026, 9, 15),
                                unit_label="pack", factor=1)
    post(second, owner)

    batch = Batch.objects.get(item=drug, batch_no="B-1")
    assert batch.expiry_date == datetime.date(2026, 9, 15)


def test_a_month_end_entry_against_a_mid_month_batch_says_what_to_do(
        owner, supplier, drug):
    """It is still refused — the owner asked that existing batches carry on
    unchanged. What changes is that the message names the way out."""
    from docs.posting import PostingError

    first = Document.objects.create(doc_type=DocType.RECEIVING,
                                    created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=first, item=drug, qty_entered=10,
                                unit_cost_entered=10, batch_no_entered="B-1",
                                expiry_entered=datetime.date(2026, 9, 15),
                                unit_label="pack", factor=1)
    post(first, owner)

    second = Document.objects.create(doc_type=DocType.RECEIVING,
                                     created_by=owner, supplier=supplier)
    DocumentLine.objects.create(document=second, item=drug, qty_entered=5,
                                unit_cost_entered=10, batch_no_entered="B-1",
                                expiry_entered=datetime.date(2026, 9, 30),
                                unit_label="pack", factor=1)
    with pytest.raises(PostingError) as caught:
        post(second, owner)
    message = str(caught.value)
    assert "2026-09-15" in message
    assert "month and year only" in message.lower()
