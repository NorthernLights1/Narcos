"""D90/D92 — "Correct this document": void the wrong paper and hand back an
editable copy in one click.

D92 defers the void: correcting only opens the draft, the original stays
live, and posting the replacement voids it first inside the same
transaction. Abandon the draft and nothing ever happened — the books never
hold a reversal with nothing in its place.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Account, Customer, Item, Supplier
from docs.models import Document, DocType, DocumentCharge, DocumentLine
from docs.posting import post
from money.models import PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer():
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier():
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def stocked_item(owner, supplier):
    item = Item.objects.create(code="AMOX", name="Amoxicillin",
                               base_unit="pack", is_batch_tracked=True,
                               has_expiry=True, vat_exempt=True,
                               maintained_price=D("15.00"))
    grn = Document.objects.create(doc_type=DocType.RECEIVING,
                                  created_by=owner, supplier=supplier)
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("10.00"),
        batch_no_entered="B-1", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    post(grn, owner)
    return item


def _posted_sale(owner, customer, item, qty=2):
    cash = Account.objects.create(name="Cash drawer", type=Account.Type.CASH)
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CASH,
                                   notes="original")
    DocumentLine.objects.create(
        document=sale, item=item, batch=Batch.objects.get(item=item),
        qty_entered=qty, unit_price=D("15.00"),
        unit_label=item.base_unit, factor=1,
    )
    DocumentCharge.objects.create(document=sale, label="Delivery",
                                  amount=D("3.00"), is_taxable=False)
    PaymentLine.objects.create(document=sale, account=cash,
                               amount=D("15.00") * qty + D("3.00"))
    return post(sale, owner)


def _correct(client, doc, reason="wrong quantity"):
    return client.post(reverse("document_correct", args=[doc.pk]),
                       {"reason": reason})


def _draft_sale():
    return Document.objects.get(doc_type=DocType.SALE,
                                status=Document.Status.DRAFT)


# --- correcting only opens the draft -------------------------------------

def test_correcting_leaves_the_original_live(client, owner, customer,
                                             stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)

    response = _correct(client, sale)

    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED   # untouched until we post
    assert not sale.void_reason

    draft = _draft_sale()
    assert draft.corrects_id == sale.pk
    assert draft.correction_reason == "wrong quantity"
    assert not draft.doc_no                        # numbered at posting (D8)
    assert response.status_code == 302
    assert response.url == reverse("document_edit", args=[draft.pk])


def test_the_copy_carries_the_whole_document(client, owner, customer,
                                             stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale, "wrong price")

    draft = _draft_sale()
    assert draft.customer == customer
    assert draft.sale_kind == sale.sale_kind
    line = draft.lines.get()
    assert line.item == stocked_item
    assert line.qty_entered == 2
    assert line.unit_price == D("15.00")
    assert draft.charges.get().label == "Delivery"
    assert draft.payment_lines.get().amount == D("33.00")


def test_the_copy_points_back_at_what_it_replaces(client, owner, customer,
                                                  stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    assert sale.doc_no in _draft_sale().notes


def test_abandoning_the_draft_changes_nothing(client, owner, customer,
                                              stocked_item):
    """The whole point of D92: walking away is safe."""
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)

    client.post(reverse("document_delete", args=[_draft_sale().pk]))

    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED


# --- posting the replacement is what voids --------------------------------

def test_posting_the_correction_voids_the_original(client, owner, customer,
                                                   stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    draft = _draft_sale()
    line = draft.lines.get()
    line.qty_entered = 3          # the fix
    line.save()
    payment = draft.payment_lines.get()   # cash sale: money must match (D44)
    payment.amount = D("48.00")           # 3 × 15.00 + 3.00 delivery
    payment.save()

    response = client.post(reverse("document_post", args=[draft.pk]))
    assert response.status_code == 302

    sale.refresh_from_db()
    draft.refresh_from_db()
    assert sale.status == Document.Status.VOIDED
    assert sale.void_reason == "wrong quantity"
    assert sale.voided_by == owner
    assert draft.status == Document.Status.POSTED
    assert draft.doc_no                       # its own number, not the old one
    assert draft.doc_no != sale.doc_no


def test_the_replacement_may_reuse_the_stock_the_original_held(
        client, owner, customer, stocked_item):
    """Only 10 packs exist. A sale of 8 corrected to 9 must post: the void
    runs first inside the same transaction and hands the goods back."""
    sale = _posted_sale(owner, customer, stocked_item, qty=8)
    client.force_login(owner)
    _correct(client, sale, "miscounted")
    draft = _draft_sale()
    line = draft.lines.get()
    line.qty_entered = 9
    line.save()
    payment = draft.payment_lines.get()
    payment.amount = D("138.00")          # 9 × 15.00 + 3.00 delivery
    payment.save()

    client.post(reverse("document_post", args=[draft.pk]))

    draft.refresh_from_db()
    sale.refresh_from_db()
    assert draft.status == Document.Status.POSTED
    assert sale.status == Document.Status.VOIDED


def test_only_the_owner_may_post_a_correction(client, employee, owner,
                                              customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    draft = _draft_sale()

    client.force_login(employee)
    client.post(reverse("document_post", args=[draft.pk]))

    sale.refresh_from_db()
    draft.refresh_from_db()
    assert sale.status == Document.Status.POSTED     # nothing voided
    assert draft.status == Document.Status.DRAFT     # nothing posted


def test_neither_half_lands_when_the_void_is_refused(client, owner, customer,
                                                     supplier, stocked_item):
    """D5: a receiving whose goods were sold cannot be voided. Its
    correction therefore cannot be posted — and the draft survives intact
    rather than half-applying."""
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)
    _correct(client, grn, "wrong cost")
    draft = Document.objects.get(doc_type=DocType.RECEIVING,
                                 status=Document.Status.DRAFT)
    _posted_sale(owner, customer, stocked_item)   # consumes the lot afterwards

    client.post(reverse("document_post", args=[draft.pk]))

    grn.refresh_from_db()
    draft.refresh_from_db()
    assert grn.status == Document.Status.POSTED
    assert draft.status == Document.Status.DRAFT


# --- guards ---------------------------------------------------------------

def test_a_reason_is_required(client, owner, customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale, "")

    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED
    assert not Document.objects.filter(status=Document.Status.DRAFT).exists()


def test_only_the_owner_may_correct(client, employee, owner, customer,
                                    stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(employee)
    response = _correct(client, sale)
    assert response.status_code == 403
    sale.refresh_from_db()
    assert sale.status == Document.Status.POSTED


def test_one_pending_correction_at_a_time(client, owner, customer,
                                          stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    _correct(client, sale, "again")

    assert Document.objects.filter(corrects=sale).count() == 1


def test_correcting_is_refused_early_when_the_void_cannot_work(
        client, owner, customer, supplier, stocked_item):
    """The goods are already sold, so this receiving can never be voided —
    say so now rather than at posting time."""
    _posted_sale(owner, customer, stocked_item)
    grn = Document.objects.get(doc_type=DocType.RECEIVING)
    client.force_login(owner)
    _correct(client, grn, "wrong cost")

    assert not Document.objects.filter(doc_type=DocType.RECEIVING,
                                       status=Document.Status.DRAFT).exists()


def test_a_draft_cannot_be_corrected(client, owner, customer, stocked_item):
    draft = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                    customer=customer)
    client.force_login(owner)
    assert _correct(client, draft, "typo").status_code == 404


# --- what the screens say -------------------------------------------------

def test_posted_page_offers_the_button(client, owner, customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert reverse("document_correct", args=[sale.pk]) in html


def test_employees_are_not_offered_the_button(client, employee, owner,
                                              customer, stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(employee)
    html = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert reverse("document_correct", args=[sale.pk]) not in html


def test_both_documents_say_a_correction_is_pending(client, owner, customer,
                                                    stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    draft = _draft_sale()

    on_draft = client.get(reverse("document_detail", args=[draft.pk])).content.decode()
    assert sale.doc_no in on_draft
    assert "pending-correction" in on_draft

    on_original = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert "pending-correction" in on_original


# --- the dialogs (D93) ----------------------------------------------------

def test_correct_and_void_buttons_explain_themselves(client, owner, customer,
                                                     stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    html = client.get(reverse("document_detail", args=[sale.pk])).content.decode()
    assert "data-confirm-title" in html
    assert "Correct %s?" % sale.doc_no in html
    # D98 renamed the void dialog: it stops asking and starts warning
    assert "Void %s — read this first" % sale.doc_no in html
    # Void is the sharp one now — it must say so
    assert "cannot be undone" in html
    # D98: only the irreversible one is type-gated
    assert 'data-confirm-type="%s"' % sale.doc_no in html
    assert "data-confirm-danger" in html


def test_posting_a_correction_warns_before_the_void(client, owner, customer,
                                                    stocked_item):
    sale = _posted_sale(owner, customer, stocked_item)
    client.force_login(owner)
    _correct(client, sale)
    draft = _draft_sale()
    html = client.get(reverse("document_detail", args=[draft.pk])).content.decode()
    assert "This posts and voids %s — read this first" % sale.doc_no in html
    assert "Post and void %s" % sale.doc_no in html
    # D98: this is the moment the void actually fires, so it is type-gated too
    assert 'data-confirm-type="%s"' % sale.doc_no in html


def test_an_ordinary_draft_posts_without_a_dialog(client, owner, customer,
                                                  stocked_item):
    draft = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                    customer=customer)
    client.force_login(owner)
    html = client.get(reverse("document_detail", args=[draft.pk])).content.decode()
    assert "This posts and voids" not in html
    assert "data-confirm-danger" not in html
