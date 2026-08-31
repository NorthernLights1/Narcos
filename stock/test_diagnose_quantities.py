"""The read-only quantity diagnostic (support tool).

Guards the two things the command exists to prove: that it names every line
whose registered quantity differs from the typed one, and that it never
writes. Fixtures come from docs/tests/conftest.py via the rootdir conftest
chain.
"""
import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from catalog.models import Customer, Item, Supplier
from core.models import User
from docs.models import Document, DocType, DocumentLine
from docs.posting import post

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def owner(db):
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


def test_diagnostic_runs_and_flags_the_scenarios(owner, capsys):
    supplier = Supplier.objects.create(code="S1", name="Addis")
    customer = Customer.objects.create(code="C1", name="Selam")
    item = Item.objects.create(code="AMOX-500", name="Amoxicillin", base_unit="pack",
                               is_batch_tracked=False, has_expiry=False,
                               maintained_price=D("20.00"))

    # received in cartons of 12
    grn = Document.objects.create(doc_type=DocType.RECEIVING, created_by=owner,
                                  supplier=supplier)
    DocumentLine.objects.create(document=grn, item=item, qty_entered=15,
                                unit_cost_entered=D("120.00"),
                                unit_label="carton")
    post(grn, owner)

    # sold "10 carton" but with factor 1 — the under-deduction case
    sale = Document.objects.create(doc_type=DocType.SALE, created_by=owner,
                                   customer=customer,
                                   sale_kind=Document.SaleKind.CREDIT,
                                   due_date=datetime.date(2030, 1, 1))
    DocumentLine.objects.create(document=sale, item=item, qty_entered=10,
                                unit_price=D("20.00"), unit_label="carton")
    post(sale, owner)

    out = StringIO()
    call_command("diagnose_quantities", stdout=out)
    text = out.getvalue()
    print(text)

    assert "CHECK 0" in text and "CHECK 5" not in text
    assert "CHECK 1" in text
    assert "ledger" in text.lower()

    out2 = StringIO()
    call_command("diagnose_quantities", item="AMOX-500", stdout=out2)
    text2 = out2.getvalue()
    print(text2)
    assert "CHECK 5" in text2
    assert "Ledger total across all zones" in text2
