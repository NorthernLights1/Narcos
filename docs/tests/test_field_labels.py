"""R52: `due_date` doubles as the supplier's credit terms on receivings and
the customer's terms on credit sales — "Due date" alone read ambiguous in
the field. One verbose_name covers both uses."""

import pytest

from docs.forms import DocumentForm
from docs.models import DocType, Document

pytestmark = pytest.mark.django_db


def test_due_date_is_labelled_payment_due_date():
    assert str(Document._meta.get_field("due_date").verbose_name) == "Payment due date"


def test_receiving_form_shows_the_new_label():
    form = DocumentForm(doc_type=DocType.RECEIVING)
    assert str(form.fields["due_date"].label) == "Payment due date"


def test_sale_form_shows_the_new_label():
    form = DocumentForm(doc_type=DocType.SALE)
    assert str(form.fields["due_date"].label) == "Payment due date"
