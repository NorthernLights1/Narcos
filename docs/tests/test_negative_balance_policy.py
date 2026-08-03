"""D101 — whether cash and bank may go negative is the owner's choice.

Stock can never go negative (D4, a DB CHECK backs it). Money never had an
equivalent: an expense could be paid from an empty drawer, and voiding an
opening-cash document after the money was spent left the account below zero.

Blocking that outright would stop real work for a business that does not run
every birr through the books — the payment is real, the income behind it was
never recorded. So the rule is a setting with three positions, defaulting to
today's behaviour (D89: a new switch changes nothing until it is flipped).
"""

from decimal import Decimal as D

import pytest

from catalog.models import Account, ExpenseCategory
from core.models import CompanySettings
from docs.models import Document, DocType
from docs.posting import PostingError, post, void
from money.models import PaymentLine, account_balance

pytestmark = pytest.mark.django_db

Policy = CompanySettings.NegativeBalance


@pytest.fixture
def cash(db):
    return Account.objects.create(name="Cash drawer", type=Account.Type.CASH)


def _policy(value):
    settings = CompanySettings.load()
    settings.negative_balance_policy = value
    settings.save()


def _expense(owner, cash, amount="4000.00"):
    category, _created = ExpenseCategory.objects.get_or_create(name="Rent")
    doc = Document.objects.create(doc_type=DocType.EXPENSE, created_by=owner,
                                  expense_category=category,
                                  grand_total=D(amount))
    PaymentLine.objects.create(document=doc, account=cash, amount=D(amount))
    return doc


def _opening_cash(owner, cash, amount="5000.00"):
    doc = Document.objects.create(doc_type=DocType.OPENING_CASH, created_by=owner)
    PaymentLine.objects.create(document=doc, account=cash, amount=D(amount))
    return post(doc, owner)


# --- Allowed (the default) ------------------------------------------------

def test_the_default_is_todays_behaviour(owner, cash):
    assert CompanySettings.load().negative_balance_policy == Policy.ALLOW
    post(_expense(owner, cash), owner)
    assert account_balance(cash) == D("-4000.00")


# --- Never -----------------------------------------------------------------

def test_never_refuses_an_overdrawing_posting(owner, cash):
    _policy(Policy.BLOCK_POSTING)
    with pytest.raises(PostingError) as caught:
        post(_expense(owner, cash), owner)
    message = str(caught.value)
    assert "Cash drawer" in message          # names the account, not an id
    assert "4000.00" in message
    assert account_balance(cash) == D("0.00")


def test_never_still_allows_a_covered_posting(owner, cash):
    _policy(Policy.BLOCK_POSTING)
    _opening_cash(owner, cash)
    post(_expense(owner, cash), owner)
    assert account_balance(cash) == D("1000.00")


def test_never_also_refuses_the_void(owner, cash):
    _opening_cash(owner, cash)
    post(_expense(owner, cash), owner)     # allowed while the policy is ALLOW
    _policy(Policy.BLOCK_POSTING)
    opening = Document.objects.get(doc_type=DocType.OPENING_CASH)

    with pytest.raises(PostingError, match="Cash drawer"):
        void(opening, owner, "opening was wrong")

    assert account_balance(cash) == D("1000.00")


# --- Not when voiding ------------------------------------------------------

def test_not_when_voiding_leaves_daily_entry_alone(owner, cash):
    """The whole point of this position: staff are never stopped."""
    _policy(Policy.BLOCK_VOID)
    post(_expense(owner, cash), owner)
    assert account_balance(cash) == D("-4000.00")


def test_not_when_voiding_refuses_the_void(owner, cash):
    _policy(Policy.BLOCK_VOID)
    opening = _opening_cash(owner, cash)
    post(_expense(owner, cash), owner)      # cash now 1000

    with pytest.raises(PostingError) as caught:
        void(opening, owner, "opening was wrong")

    message = str(caught.value)
    assert "Cash drawer" in message
    assert "-4000.00" in message            # says where it would land
    assert account_balance(cash) == D("1000.00")


def test_a_void_that_keeps_the_account_positive_is_untouched(owner, cash):
    _policy(Policy.BLOCK_VOID)
    _opening_cash(owner, cash)
    expense = post(_expense(owner, cash, "1000.00"), owner)

    void(expense, owner, "keyed twice")

    assert account_balance(cash) == D("5000.00")
