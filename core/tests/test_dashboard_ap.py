"""AP overdue on the owner dashboard: posted receivings / opening payables
past their due date with an unpaid balance."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Item, Supplier
from core.models import User
from docs.forms import DOC_CONFIG
from docs.models import Document, DocType, DocumentLine
from docs.posting import post

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def owner():
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


def test_receiving_form_captures_due_date():
    assert "due_date" in DOC_CONFIG[DocType.RECEIVING]["fields"]


def test_dashboard_lists_overdue_payables(client, owner):
    supplier = Supplier.objects.create(code="S001", name="Addis Pharma")
    item = Item.objects.create(code="GLOVE", name="Gloves", base_unit="pair",
                               is_batch_tracked=False, has_expiry=False)
    grn = Document.objects.create(
        doc_type=DocType.RECEIVING, created_by=owner, supplier=supplier,
        due_date=timezone.localdate() - datetime.timedelta(days=3),
    )
    DocumentLine.objects.create(
        document=grn, item=item, qty_entered=10, unit_cost_entered=D("5.00"),
        unit_label=item.base_unit, factor=1,
    )
    grn = post(grn, owner)
    client.force_login(owner)
    response = client.get(reverse("dashboard"))
    rows = response.context["ap_overdue"]
    assert [row["doc"].pk for row in rows] == [grn.pk]
    assert rows[0]["balance"] == D("50.00")
    assert grn.doc_no in response.content.decode()
