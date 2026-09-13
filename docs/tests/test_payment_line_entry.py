"""Payment-line entry ergonomics (field testing, D86/D87): a row whose
amount was typed and then cleared is not a payment, and the form starts
with a single row — most documents are paid into one account."""

from decimal import Decimal

import pytest

from docs.forms import PaymentLineFormSet
from docs.models import Document, DocType
from money.models import PaymentLine

pytestmark = pytest.mark.django_db


def _draft(owner):
    return Document.objects.create(doc_type=DocType.EXPENSE, created_by=owner)


def _management(total, initial=0):
    return {
        "payments-TOTAL_FORMS": str(total),
        "payments-INITIAL_FORMS": str(initial),
        "payments-MIN_NUM_FORMS": "0",
        "payments-MAX_NUM_FORMS": "1000",
    }


def test_cleared_amount_row_is_ignored(owner, cash):
    """Typing an amount, changing your mind and clearing it must not leave
    the row demanding a number — leftover account/method picks alone are
    not a payment (D86)."""
    doc = _draft(owner)
    data = _management(1) | {
        "payments-0-account": str(cash.pk),    # picked, then amount cleared
        "payments-0-method": "BANK_TRANSFER",  # changed off the CASH default
        "payments-0-amount": "",
    }
    formset = PaymentLineFormSet(data, instance=doc, prefix="payments")
    assert formset.is_valid(), formset.errors
    formset.save()
    assert PaymentLine.objects.count() == 0


def test_saved_row_with_cleared_amount_still_errors(owner, cash):
    """An already-saved payment line is real money — clearing its amount
    must complain, not silently drop it (delete is the ✕ column)."""
    doc = _draft(owner)
    line = PaymentLine.objects.create(document=doc, account=cash,
                                      amount=Decimal("10.00"))
    data = _management(1, initial=1) | {
        "payments-0-id": str(line.pk),
        "payments-0-account": str(cash.pk),
        "payments-0-method": "CASH",
        "payments-0-amount": "",
    }
    formset = PaymentLineFormSet(data, instance=doc, prefix="payments")
    assert not formset.is_valid()


def test_filled_row_still_saves(owner, cash):
    doc = _draft(owner)
    data = _management(1) | {
        "payments-0-account": str(cash.pk),
        "payments-0-method": "CASH",
        "payments-0-amount": "25.00",
    }
    formset = PaymentLineFormSet(data, instance=doc, prefix="payments")
    assert formset.is_valid(), formset.errors
    formset.save()
    assert PaymentLine.objects.get().amount == Decimal("25.00")


def test_payment_lines_default_to_one_row(owner):
    """D87: one blank row by default — payments almost always go into a
    single account; + Add row covers the split case."""
    formset = PaymentLineFormSet(instance=_draft(owner), prefix="payments")
    assert len(formset.forms) == 1
