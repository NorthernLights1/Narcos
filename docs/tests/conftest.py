"""Shared fixtures for posting-engine tests."""

from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Account, ExpenseCategory, Item
from core.models import User
from docs.models import Document, DocType
from money.models import PaymentLine
from stock.models import CostLot, StockBalance, Zone


@pytest.fixture
def owner(db):
    return User.objects.create_user("boss", password="pw", role=User.Role.OWNER)


@pytest.fixture
def employee(db):
    return User.objects.create_user("staff", password="pw", role=User.Role.EMPLOYEE)


@pytest.fixture
def cash(db):
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


@pytest.fixture
def bank(db):
    return Account.objects.create(name="CBE account", type=Account.Type.BANK)


@pytest.fixture
def rent(db):
    return ExpenseCategory.objects.create(name="Rent")


def make_expense(actor, account, category, amount="100.00") -> Document:
    doc = Document.objects.create(
        doc_type=DocType.EXPENSE, created_by=actor,
        expense_category=category, payee="Landlord",
        grand_total=Decimal(amount),
    )
    PaymentLine.objects.create(document=doc, account=account, amount=Decimal(amount))
    return doc


def make_transfer(actor, from_account, to_account, amount="50.00") -> Document:
    return Document.objects.create(
        doc_type=DocType.TRANSFER, created_by=actor,
        from_account=from_account, to_account=to_account,
        grand_total=Decimal(amount),
    )


def make_stocked_item(qty=100, cost="10.00") -> tuple[Item, CostLot, StockBalance]:
    """A warehouse balance for engine tests that need stock to consume."""
    item = Item.objects.create(code=f"IT-{Item.objects.count() + 1}",
                               name="Test item", base_unit="pack",
                               is_batch_tracked=False, has_expiry=False)
    lot = CostLot.objects.create(item=item, received_at=timezone.now(),
                                 qty_received=qty, unit_cost=Decimal(cost))
    balance = StockBalance.objects.create(item=item, lot=lot,
                                          zone=Zone.WAREHOUSE, qty=qty)
    return item, lot, balance
