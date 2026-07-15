"""Cash Sales Attachment print layout — the paper form the owner's trade
expects (modelled on the sample he provided): company header, buyer block
with TIN/license, fixed 20-row line table, signature lines, copy footer."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.models import Account, Customer, Item, Supplier
from core.models import CompanySettings, User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post
from money.models import PaymentLine
from stock.models import Batch

pytestmark = pytest.mark.django_db

D = Decimal
FAR_EXPIRY = datetime.date(2030, 1, 1)


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def company():
    settings = CompanySettings.load()
    settings.name = "Novel Drugs and Medical Wholeseller"
    settings.tin = "0096816383"
    settings.phone = "+251 96 605 3869 | +251 92 644 2965"
    settings.save()
    return settings


@pytest.fixture
def buyer():
    return Customer.objects.create(
        code="C001", name="Selam Pharmacy", tin="0011223344",
        license_no="PH-MK-0042", city="Mekelle", phone="0344 400 000",
        mobile="0912 345 678",
    )


@pytest.fixture
def sale(owner, buyer):
    supplier = Supplier.objects.create(code="S001", name="Addis Pharma")
    cash = Account.objects.create(name="Cash", type=Account.Type.CASH)
    item = Item.objects.create(
        code="AMOX", name="Amoxil", generic_name="Amoxicillin",
        strength="500mg", dosage_form="Capsule", base_unit="pack",
        is_batch_tracked=True, has_expiry=True, vat_exempt=True,
        maintained_price=D("15.00"),
    )
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("10.00"),
        batch_no_entered="BX-77", expiry_entered=FAR_EXPIRY,
        unit_label=item.base_unit, factor=1,
    )
    post(grn, owner)
    doc = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                  customer=buyer,
                                  sale_kind=Document.SaleKind.CASH)
    DocumentLine.objects.create(
        document=doc, item=item, batch=Batch.objects.get(item=item),
        qty_entered=2, unit_price=D("15.00"), unit_label=item.base_unit,
        factor=1,
    )
    PaymentLine.objects.create(document=doc, account=cash, amount=D("30.00"))
    return post(doc, owner)


def test_layout_renders_form_structure(client, owner, company, buyer, sale):
    client.force_login(owner)
    response = client.get(
        reverse("document_print", args=[sale.pk]), {"layout": "SALES_ATT"})
    content = response.content.decode()
    assert "Cash Sales Attachment" in content
    assert "Novel Drugs and Medical Wholeseller" in content
    assert "0096816383" in content                       # company TIN
    assert "+251 96 605 3869" in content                 # company phones
    assert "not valid unless" in content                 # fiscal note
    assert "1st Copy: Customer" in content               # copy distribution


def test_buyer_block_shows_new_master_fields(client, owner, company, buyer, sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_print", args=[sale.pk]), {"layout": "SALES_ATT"},
    ).content.decode()
    assert "Selam Pharmacy" in content
    assert "0011223344" in content                       # buyer TIN
    assert "PH-MK-0042" in content                       # license no
    assert "Mekelle" in content                          # city
    assert "0912 345 678" in content                     # mobile


def test_line_table_composed_and_padded_to_20(client, owner, company, buyer, sale):
    client.force_login(owner)
    content = client.get(
        reverse("document_print", args=[sale.pk]), {"layout": "SALES_ATT"},
    ).content.decode()
    assert "Amoxil" in content
    assert "Amoxicillin" in content
    assert "500mg" in content
    assert "BX-77" in content                            # batch no
    assert "2030-01-01" in content                       # expiry
    assert content.count('<td class="sno">') == 20       # fixed-height table


def test_csi_and_fs_receipt_slots(client, owner, company, buyer, sale):
    sale.fiscal_receipt_no = "FS-0001234"
    sale.save(update_fields=["fiscal_receipt_no"])
    client.force_login(owner)
    content = client.get(
        reverse("document_print", args=[sale.pk]), {"layout": "SALES_ATT"},
    ).content.decode()
    assert sale.doc_no in content                        # CSI No.
    assert "FS-0001234" in content                       # FS receipt no
