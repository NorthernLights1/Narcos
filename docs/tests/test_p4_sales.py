"""P4 sales: I9 (FIFO COGS), I10 (expiry rules), I11 (returns), credit checks,
cash/credit paths, withholding_expected display math."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Customer, Item, Supplier
from core.models import AuditLog, CompanySettings
from docs.checks import ExpiryStatus, add_months, expiry_status
from docs.models import Document, DocType, DocumentCharge, DocumentLine
from docs.posting import PostingError, post, void
from money.models import PaymentLine, account_balance
from stock.models import Batch, CostLot, StockBalance, Zone

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def customer(db):
    return Customer.objects.create(code="C001", name="Selam Pharmacy")


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(code="S001", name="Addis Pharma")


@pytest.fixture
def drug(db):
    return Item.objects.create(code="AMOX", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=True, has_expiry=True,
                               vat_exempt=True, maintained_price=D("15.00"))


@pytest.fixture
def taxable_item(db):
    return Item.objects.create(code="STETH", name="Stethoscope", base_unit="unit",
                               is_batch_tracked=False, has_expiry=False,
                               vat_exempt=False, maintained_price=D("900.00"))


def receive(actor, supplier, item, qty, cost, batch_no="B-1", expiry=FAR_EXPIRY):
    doc = Document.objects.create(doc_type=DocType.RECEIVING, created_by=actor,
                                  supplier=supplier)
    DocumentLine.objects.create(
        document=doc, item=item, qty_entered=qty, unit_cost_entered=D(cost),
        batch_no_entered=batch_no if item.is_batch_tracked else "",
        expiry_entered=expiry if item.has_expiry else None,
        unit_label=item.base_unit, factor=1,
    )
    return post(doc, actor)


def sale_draft(actor, customer, kind="CASH", **doc_fields) -> Document:
    fields = {"doc_type": DocType.SALE, "created_by": actor, "customer": customer,
              "sale_kind": kind}
    if kind == "CREDIT":
        fields["due_date"] = datetime.date(2026, 8, 1)
    fields.update(doc_fields)
    return Document.objects.create(**fields)


def add_sale_line(doc, item, qty, price, batch=None, discount="0.00"):
    return DocumentLine.objects.create(
        document=doc, item=item, batch=batch, qty_entered=qty,
        unit_price=D(price), line_discount=D(discount),
        unit_label=item.base_unit, factor=1,
    )


def pay(doc, account, amount):
    PaymentLine.objects.create(document=doc, account=account, amount=D(amount))


def warehouse_qty(lot):
    row = StockBalance.objects.filter(lot=lot, zone=Zone.WAREHOUSE).first()
    return row.qty if row else 0


# --- Cash and credit sale basics ---


def test_cash_sale_moves_stock_and_money(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 20, "15.00", batch=batch)
    pay(doc, cash, "300.00")
    doc = post(doc, owner)
    assert doc.doc_no == "SI-000001"
    assert doc.grand_total == D("300.00")
    assert doc.tax_total == D("0.00")  # exempt medicine
    receipt = Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT,
                                   related_document=doc)
    assert receipt.doc_no == "RC-000001"
    assert doc.money_rows.count() == 0
    assert account_balance(cash) == D("300.00")
    assert doc.party_rows.count() == 0  # cash sale: no AR
    lot = CostLot.objects.get()
    assert warehouse_qty(lot) == 80
    line = doc.lines.get()
    assert line.cogs_total == D("200.00")  # 20 × 10.00


def test_credit_sale_books_ar_not_money(owner, customer, supplier, drug):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer, kind="CREDIT")
    add_sale_line(doc, drug, 10, "15.00", batch=batch)
    doc = post(doc, owner)
    ar = doc.party_rows.get()
    assert ar.party_type == "CUSTOMER" and ar.amount_delta == D("150.00")
    assert doc.money_rows.count() == 0


def test_cash_sale_payment_must_match_total(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 10, "15.00", batch=batch)
    pay(doc, cash, "100.00")  # wrong: total is 150
    with pytest.raises(PostingError):
        post(doc, owner)


def test_taxable_sale_gets_vat(owner, customer, supplier, taxable_item, cash):
    receive(owner, supplier, taxable_item, 10, "500.00")
    doc = sale_draft(owner, customer)
    add_sale_line(doc, taxable_item, 1, "900.00")
    pay(doc, cash, "1035.00")  # 900 + 15%
    doc = post(doc, owner)
    assert doc.tax_total == D("135.00")
    assert doc.grand_total == D("1035.00")


def test_charge_joins_tax_base(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 10, "15.00", batch=batch)  # 150 exempt
    DocumentCharge.objects.create(document=doc, label="Delivery",
                                  amount=D("50.00"), is_taxable=True)
    pay(doc, cash, "207.50")  # 150 + 50 + 7.50 VAT on charge
    doc = post(doc, owner)
    assert doc.tax_total == D("7.50")
    assert doc.grand_total == D("207.50")


# --- I9: FIFO lot consumption ---


def test_i9_sale_spans_lots_oldest_first(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 30, "10.00")   # lot 1
    receive(owner, supplier, drug, 30, "12.00")   # lot 2, same batch
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 40, "20.00", batch=batch)
    pay(doc, cash, "800.00")
    doc = post(doc, owner)
    line = doc.lines.get()
    consumptions = list(line.lot_consumptions.order_by("pk"))
    assert [c.qty for c in consumptions] == [30, 10]  # oldest lot drained first
    assert line.cogs_total == D("420.00")  # 30×10 + 10×12
    lots = list(CostLot.objects.order_by("received_at", "pk"))
    assert warehouse_qty(lots[0]) == 0
    assert warehouse_qty(lots[1]) == 20


def test_i9_oversell_blocked_cleanly(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 10, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 11, "15.00", batch=batch)
    pay(doc, cash, "165.00")
    with pytest.raises(PostingError):
        post(doc, owner)
    lot = CostLot.objects.get()
    assert warehouse_qty(lot) == 10  # rollback complete


# --- I10: expiry rules at the exact D59 boundary ---


def test_i10_expired_sale_blocked(owner, customer, supplier, drug, cash):
    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    receive(owner, supplier, drug, 10, "10.00", expiry=yesterday)
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 1, "15.00", batch=batch)
    pay(doc, cash, "15.00")
    with pytest.raises(PostingError):
        post(doc, owner)


def test_i10_expiry_boundaries():
    today = datetime.date(2026, 7, 3)
    assert expiry_status(datetime.date(2026, 7, 2), today, 6) == ExpiryStatus.EXPIRED
    assert expiry_status(today, today, 6) == ExpiryStatus.NEAR  # expiry day: sellable, near
    exactly_six_months = add_months(today, 6)
    assert expiry_status(exactly_six_months, today, 6) == ExpiryStatus.NEAR
    assert expiry_status(exactly_six_months + datetime.timedelta(days=1),
                         today, 6) == ExpiryStatus.OK
    assert expiry_status(None, today, 6) == ExpiryStatus.OK


# --- Credit limit (D25/§8) ---


def test_credit_block_needs_owner_override(owner, employee, customer, supplier, drug):
    customer.credit_limit = D("100.00")
    customer.credit_action = "BLOCK"
    customer.save()
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(employee, customer, kind="CREDIT")
    add_sale_line(doc, drug, 10, "15.00", batch=batch)  # 150 > 100 limit
    with pytest.raises(PostingError):
        post(doc, employee)
    with pytest.raises(PostingError):  # employee cannot override
        post(doc, employee, override_reason="please")
    posted = post(doc, owner, override_reason="approved by owner")
    assert posted.status == Document.Status.POSTED
    assert AuditLog.objects.filter(action="OVERRIDE").exists()


def test_credit_warn_proceeds_and_audits(owner, customer, supplier, drug):
    customer.credit_limit = D("100.00")
    customer.credit_action = "WARN"
    customer.save()
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer, kind="CREDIT")
    add_sale_line(doc, drug, 10, "15.00", batch=batch)
    posted = post(doc, owner)
    assert posted.status == Document.Status.POSTED
    assert AuditLog.objects.filter(action="CREDIT_WARN").exists()


def test_cash_sales_never_credit_checked(owner, customer, supplier, drug, cash):
    customer.credit_limit = D("1.00")
    customer.credit_action = "BLOCK"
    customer.save()
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)  # CASH
    add_sale_line(doc, drug, 10, "15.00", batch=batch)
    pay(doc, cash, "150.00")
    assert post(doc, owner).status == Document.Status.POSTED


# --- D51: withholding expected (display only) ---


def test_withholding_expected_display_math(owner, customer, supplier, drug):
    settings = CompanySettings.load()
    settings.withholding_on_sales = True
    settings.save()
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer, kind="CREDIT", customer_will_withhold=True)
    add_sale_line(doc, drug, 100, "15.00", batch=batch)  # 1500, exempt → no VAT
    doc = post(doc, owner)
    assert doc.withholding_expected == D("45.00")  # 3% × 1500
    # D53: receivable is still the FULL amount
    assert doc.party_rows.get().amount_delta == D("1500.00")


# --- Proforma (§7.3) ---


def test_proforma_freezes_totals_touches_nothing(owner, customer, supplier, drug):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = Document.objects.create(doc_type=DocType.PROFORMA, created_by=owner,
                                  customer=customer)
    add_sale_line(doc, drug, 10, "15.00", batch=batch)
    doc = post(doc, owner)
    assert doc.doc_no == "PF-000001"
    assert doc.grand_total == D("150.00")
    assert doc.stock_moves.count() == 0
    assert doc.money_rows.count() == 0
    assert doc.party_rows.count() == 0
    lot = CostLot.objects.get()
    assert warehouse_qty(lot) == 100  # untouched


# --- Void of a sale (I2 applied to sales) ---


def test_void_sale_restores_stock_and_money(owner, customer, supplier, drug, cash):
    receive(owner, supplier, drug, 100, "10.00")
    batch = Batch.objects.get()
    doc = sale_draft(owner, customer)
    add_sale_line(doc, drug, 20, "15.00", batch=batch)
    pay(doc, cash, "300.00")
    doc = post(doc, owner)
    receipt = Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT)
    with pytest.raises(PostingError):
        void(receipt, owner, "void source instead")
    void(doc, owner, "entry error")
    assert Document.objects.get(doc_type=DocType.CUSTOMER_PAYMENT).status == Document.Status.VOIDED
    lot = CostLot.objects.get()
    assert warehouse_qty(lot) == 100
    assert account_balance(cash) == D("0.00")
