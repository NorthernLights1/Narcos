"""D75 inventory pages: per-zone quantities, low/out-of-stock filters, the
item drill-down, and the dashboard low-stock card showing qty vs reorder."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from stock.models import Batch
from stock.views import _stock_status

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)
TODAY = timezone.localdate().isoformat()   # matches the view, not the OS clock


@pytest.fixture
def owner(db):
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Mekelle Hospital PLC")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


def make_item(code, name, reorder_level=None, generic_name=""):
    return Item.objects.create(code=code, name=name, generic_name=generic_name,
                               base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True, reorder_level=reorder_level)


def receive(actor, supplier, item, qty=100, cost="10.00"):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(document=doc, item=item, qty_entered=qty,
                                unit_cost_entered=D(cost),
                                batch_no_entered=f"B-{item.code}",
                                expiry_entered=FAR_EXPIRY, unit_label="pack", factor=1)
    return post(doc, actor)


def consign(actor, customer, item, qty):
    doc = Document.objects.create(doc_type=DocType.CONSIGNMENT_ISSUE,
                                  created_by=actor, customer=customer)
    DocumentLine.objects.create(document=doc, item=item,
                                batch=Batch.objects.get(item=item),
                                qty_entered=qty, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    return post(doc, actor)


def sell(actor, customer, item, qty):
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=actor,
                                  customer=customer, sale_kind="CREDIT",
                                  due_date=datetime.date(2026, 8, 1))
    DocumentLine.objects.create(document=doc, item=item,
                                batch=Batch.objects.get(item=item),
                                qty_entered=qty, unit_price=D("15.00"),
                                unit_label="pack", factor=1)
    return post(doc, actor)


def test_stock_status_rule():
    assert _stock_status(0, None) == "OUT"
    assert _stock_status(0, 5) == "OUT"
    assert _stock_status(5, 5) == "LOW"
    assert _stock_status(6, 5) == "OK"
    assert _stock_status(6, None) == "OK"


def test_inventory_list_shows_per_zone_quantities(client, owner, customer,
                                                  supplier):
    item = make_item("GLV", "Exam Gloves", reorder_level=4)
    receive(owner, supplier, item, qty=100)
    consign(owner, customer, item, qty=40)
    sell(owner, customer, item, qty=20)
    client.force_login(owner)
    response = client.get(reverse("inventory_list"))
    content = response.content.decode()
    assert "Exam Gloves" in content
    row = next(r for r in response.context["rows"] if r["item"].pk == item.pk)
    assert row["warehouse"] == 40   # 100 − 40 consigned − 20 sold
    assert row["consigned"] == 40
    assert row["total"] == 80
    assert row["status"] == "OK"    # 40 > reorder level 4


def test_inventory_low_and_out_filters(client, owner, supplier, customer):
    low = make_item("LOW", "Advil", reorder_level=50)
    receive(owner, supplier, low, qty=5)
    ok = make_item("OK", "Parecetamol", reorder_level=3)
    receive(owner, supplier, ok, qty=100)
    out = make_item("OUT", "Bandage", reorder_level=10)  # never received
    client.force_login(owner)

    rows = client.get(reverse("inventory_list"), {"show": "low"}).context["rows"]
    codes = {row["item"].code for row in rows}
    assert codes == {"LOW", "OUT"}

    rows = client.get(reverse("inventory_list"), {"show": "out"}).context["rows"]
    assert {row["item"].code for row in rows} == {"OUT"}

    rows = client.get(reverse("inventory_list"), {"q": "advil"}).context["rows"]
    assert {row["item"].code for row in rows} == {"LOW"}


def test_inventory_search_finds_an_item_by_its_generic_name(client, owner,
                                                            supplier):
    """R105: the client reported "catheter is not in my database". It was.

    This trade reads by generic name — `Item.__str__` leads with it (R48) — and
    the brand on the box says `Folly`. Searching the one screen that answers
    "how many have I got" looked only at code and name, so four real catheters
    were invisible there while Master → Items found them.
    """
    folly = make_item("ITM-0053", "Folly", generic_name="Catheter 3 way 18Fr")
    other = make_item("ITM-0080", "Ibuprofen", generic_name="Ibuprofen")
    receive(owner, supplier, folly, qty=30)
    receive(owner, supplier, other, qty=30)
    client.force_login(owner)

    rows = client.get(reverse("inventory_list"), {"q": "catheter"}).context["rows"]
    assert {row["item"].code for row in rows} == {"ITM-0053"}

    # the brand still works, and the search stays narrow
    rows = client.get(reverse("inventory_list"), {"q": "folly"}).context["rows"]
    assert {row["item"].code for row in rows} == {"ITM-0053"}


def test_inventory_item_page_shows_batches_and_movements(client, owner,
                                                         customer, supplier):
    item = make_item("GLV", "Exam Gloves", reorder_level=4)
    receive(owner, supplier, item, qty=100)
    cn = consign(owner, customer, item, qty=40)
    client.force_login(owner)
    response = client.get(reverse("inventory_item", args=[item.pk]))
    content = response.content.decode()
    assert response.context["warehouse"] == 60
    assert response.context["consigned"] == 40
    assert f"B-{item.code}" in content            # batch row
    assert customer.name in content               # consignment holder
    assert cn.doc_no in content                   # recent movement links the doc


def test_dashboard_low_stock_shows_qty_against_reorder_level(client, owner,
                                                             supplier, customer):
    low = make_item("LOW", "Advil", reorder_level=50)
    receive(owner, supplier, low, qty=5)
    client.force_login(owner)
    content = client.get(reverse("dashboard")).content.decode()
    assert "Advil" in content
    assert "5 in warehouse (reorder at 50)" in content
    assert reverse("inventory_item", args=[low.pk]) in content


# --- R62/D121: correcting a mistyped batch expiry -------------------------

@pytest.fixture
def employee(db):
    return User.objects.create_user("staff", password="pw",
                                    role=User.Role.EMPLOYEE)


def _expiry_url(batch):
    return reverse("batch_expiry_edit", args=[batch.pk])


def test_the_owner_can_correct_a_mistyped_expiry(client, owner, supplier,
                                                 customer):
    """The case this was built for: a typo caught after some of the stock has
    already been sold, when void-and-repost is refused."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    sell(owner, customer, item, 10)                 # stock has already moved
    batch = Batch.objects.get(item=item)
    Batch.objects.filter(pk=batch.pk).update(
        expiry_date=datetime.date(2026, 7, 22))     # the typo
    client.force_login(owner)

    review = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22",
        "reason": "read 2026 off the carton, it says 2029",
    })
    assert review.status_code == 200          # step one: shown, not saved
    assert Batch.objects.get(pk=batch.pk).expiry_date == datetime.date(2026, 7, 22)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22",
        "reason": "read 2026 off the carton, it says 2029",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": "2026-07-22", "reviewed_on": TODAY,
    })

    batch.refresh_from_db()
    assert batch.expiry_date == datetime.date(2029, 7, 22)
    assert response.status_code == 204
    assert response["HX-Refresh"] == "true"
    row = AuditLog.objects.get(action="BATCH_EXPIRY_UPDATE")
    assert row.after["from"] == "2026-07-22"
    assert row.after["to"] == "2029-07-22"
    assert row.after["batch_no"] == batch.batch_no
    assert "carton" in row.after["reason"]
    assert row.actor == owner


def test_the_audit_row_names_the_documents_that_share_the_batch(
        client, owner, supplier, customer):
    """The change lands on every document holding the batch, so the log has to
    say which ones — the owner cannot see that afterwards otherwise."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    grn = receive(owner, supplier, item)
    sale = sell(owner, customer, item, 10)
    batch = Batch.objects.get(item=item)
    client.force_login(owner)

    client.post(_expiry_url(batch), {"expiry_date": "2029-07-22",
                                     "reason": "corrected from the carton",
                                     "confirm": "1",
                                     "reviewed_expiry": "2029-07-22",
                                     "reviewed_from": FAR_EXPIRY.isoformat(),
                                     "reviewed_on": TODAY})

    named = AuditLog.objects.get(action="BATCH_EXPIRY_UPDATE").after["documents"]
    assert grn.doc_no in named
    assert sale.doc_no in named


def test_staff_may_not_correct_an_expiry(client, employee, owner, supplier):
    """Owner-only: it moves what may be sold (D46) across every document."""
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    was = batch.expiry_date
    client.force_login(employee)

    response = client.post(_expiry_url(batch), {"expiry_date": "2029-07-22",
                                                "reason": "not my call",
                                                "confirm": "1",
                                                "reviewed_expiry": "2029-07-22",
                                                "reviewed_from": FAR_EXPIRY.isoformat(),
                                                "reviewed_on": TODAY})

    batch.refresh_from_db()
    assert response.status_code == 403
    assert batch.expiry_date == was


def test_staff_do_not_even_see_the_pencil(client, employee, owner, supplier):
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    client.force_login(employee)

    content = client.get(reverse("inventory_item", args=[item.pk])).content.decode()

    assert _expiry_url(Batch.objects.get(item=item)) not in content


def test_a_reason_is_required(client, owner, supplier):
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    was = batch.expiry_date
    client.force_login(owner)

    blank = client.post(_expiry_url(batch), {"expiry_date": "2029-07-22",
                                             "reason": "  "})
    terse = client.post(_expiry_url(batch), {"expiry_date": "2029-07-22",
                                             "reason": "x"})

    batch.refresh_from_db()
    # 200, not 400: htmx 2.0.4 will not swap a 4xx body, so a 400 shows the
    # user nothing at all. The error has to arrive in a response it renders.
    assert blank.status_code == 200
    assert "required" in blank.content.decode()
    assert terse.status_code == 200
    assert "Say why" in terse.content.decode()
    assert batch.expiry_date == was
    assert not AuditLog.objects.filter(action="BATCH_EXPIRY_UPDATE").exists()


def test_the_dialog_warns_when_expired_stock_becomes_sellable(client, owner,
                                                              supplier):
    """The dangerous direction: pushing a date out puts expired goods back on
    sale. The owner is told, not left to infer it from two dates."""
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    Batch.objects.filter(pk=batch.pk).update(
        expiry_date=datetime.date(2020, 1, 1))      # already expired
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "corrected from the carton",
    })

    assert response.status_code == 200        # the review step, not saved yet
    assert "back on sale" in response.content.decode()
    assert Batch.objects.get(pk=batch.pk).expiry_date == datetime.date(2020, 1, 1)


def test_an_item_without_expiry_has_nothing_to_correct(client, owner, supplier):
    item = Item.objects.create(code="STETH", name="Stethoscope",
                               base_unit="unit", is_batch_tracked=True,
                               has_expiry=False, vat_exempt=True)
    batch = Batch.objects.create(item=item, batch_no="NA-1")
    client.force_login(owner)

    assert client.get(_expiry_url(batch)).status_code == 404


def test_the_dialog_warns_when_good_stock_becomes_expired(client, owner,
                                                          supplier):
    """The other direction: pulling a date back takes goods off sale."""
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)     # FAR_EXPIRY, well in the future
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2020-01-01", "reason": "carton says 2020",
    })

    assert "from selling" in response.content.decode()


def test_changing_the_date_after_review_sends_you_round_again(client, owner,
                                                              supplier):
    """The warnings were computed for the reviewed date. Submit a different
    one with the same confirm and the review is stale, so it is redone."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    was = batch.expiry_date
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2020-01-01",              # not what was reviewed
        "reason": "corrected from the carton",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": FAR_EXPIRY.isoformat(), "reviewed_on": TODAY,
    })

    batch.refresh_from_db()
    assert response.status_code == 200            # review again, not saved
    assert batch.expiry_date == was
    assert not AuditLog.objects.filter(action="BATCH_EXPIRY_UPDATE").exists()


def test_confirming_an_unchanged_date_writes_nothing(client, owner, supplier):
    """An audit row reading "from X to X" is noise that buries the real ones."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": batch.expiry_date.isoformat(),
        "reason": "no change at all", "confirm": "1",
        "reviewed_expiry": batch.expiry_date.isoformat(),
        "reviewed_from": batch.expiry_date.isoformat(), "reviewed_on": TODAY,
    })

    assert response.status_code == 204
    assert not AuditLog.objects.filter(action="BATCH_EXPIRY_UPDATE").exists()


def test_a_backdated_expiry_names_what_already_went_out(client, owner,
                                                        supplier, customer):
    """The safety case: pulling the date back can mean this batch was sold
    after it had really expired. That is a recall question, so it is named."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    sale = sell(owner, customer, item, 10)
    batch = Batch.objects.get(item=item)
    client.force_login(owner)

    review = client.post(_expiry_url(batch), {
        "expiry_date": "2020-01-01", "reason": "carton really says 2020",
    })

    body = review.content.decode()
    assert "already left the building" in body
    assert sale.doc_no in body

    client.post(_expiry_url(batch), {
        "expiry_date": "2020-01-01", "reason": "carton really says 2020",
        "confirm": "1", "reviewed_expiry": "2020-01-01",
        "reviewed_from": FAR_EXPIRY.isoformat(), "reviewed_on": TODAY,
    })
    row = AuditLog.objects.get(action="BATCH_EXPIRY_UPDATE")
    assert sale.doc_no in row.after["issued_after_expiry"]


def test_a_voided_document_still_counts_as_sharing_the_batch(client, owner,
                                                             supplier, customer):
    """It cites the batch too, so leaving it out understates the blast radius."""
    from core.models import AuditLog
    from docs.posting import void
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    sale = sell(owner, customer, item, 10)
    void(sale, owner, "wrong customer")
    batch = Batch.objects.get(item=item)
    client.force_login(owner)

    client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "corrected from the carton",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": FAR_EXPIRY.isoformat(), "reviewed_on": TODAY,
    })

    named = AuditLog.objects.get(action="BATCH_EXPIRY_UPDATE").after["documents"]
    assert sale.doc_no in named


def test_stock_outside_the_warehouse_does_not_claim_to_become_sellable(
        client, owner, supplier, customer):
    """Only the warehouse feeds a sale. Consigned goods stay consigned however
    the date moves, so promising they go back on sale would be a lie."""
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item, qty=10)
    consign(owner, customer, item, 10)           # warehouse now empty
    batch = Batch.objects.get(item=item)
    Batch.objects.filter(pk=batch.pk).update(expiry_date=datetime.date(2020, 1, 1))
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "corrected from the carton",
    })

    assert "back on sale" not in response.content.decode()


def test_a_date_moved_underneath_the_review_sends_you_round_again(client, owner,
                                                                  supplier):
    """The warnings were computed against the date being replaced. If another
    tab changed that first, they describe a starting point that is gone."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "corrected from the carton",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": "2027-01-01",        # not what the row actually holds
        "reviewed_on": TODAY,
    })

    batch.refresh_from_db()
    assert response.status_code == 200        # review again, not saved
    assert batch.expiry_date == FAR_EXPIRY
    assert not AuditLog.objects.filter(action="BATCH_EXPIRY_UPDATE").exists()


def test_a_batch_with_no_expiry_yet_can_be_given_one(client, owner, supplier):
    """The template writes an empty string for a missing date; the server has
    to read it the same way, or this review loops forever."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    Batch.objects.filter(pk=batch.pk).update(expiry_date=None)
    client.force_login(owner)

    review = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "carton says 2029",
    })
    assert review.status_code == 200

    saved = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "carton says 2029",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": "", "reviewed_on": TODAY,
    })

    batch.refresh_from_db()
    assert saved.status_code == 204
    assert batch.expiry_date == datetime.date(2029, 7, 22)
    assert AuditLog.objects.get(action="BATCH_EXPIRY_UPDATE").after["from"] == "None"


def test_a_review_from_yesterday_is_not_accepted_today(client, owner, supplier):
    """EXPIRED and NEAR are relative to today, so yesterday's verdict is not
    a verdict on this change."""
    from core.models import AuditLog
    item = make_item("ITM-0032", "Amoxicillin")
    receive(owner, supplier, item)
    batch = Batch.objects.get(item=item)
    yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
    client.force_login(owner)

    response = client.post(_expiry_url(batch), {
        "expiry_date": "2029-07-22", "reason": "corrected from the carton",
        "confirm": "1", "reviewed_expiry": "2029-07-22",
        "reviewed_from": FAR_EXPIRY.isoformat(), "reviewed_on": yesterday,
    })

    batch.refresh_from_db()
    assert response.status_code == 200
    assert batch.expiry_date == FAR_EXPIRY
    assert not AuditLog.objects.filter(action="BATCH_EXPIRY_UPDATE").exists()
