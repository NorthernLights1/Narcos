"""R50: the generic printout (print.html — "Attachment / not a fiscal
receipt", COMPACT default) gets a Prepared By + signature block. The Cash
Sales Attachment already had one; this layout had no signature markup at
all. Prepared = who entered it (`created_by`), same meaning as there.
No stamp box, no Received By — the client will confirm those later."""

import pytest
from django.urls import reverse

from docs.posting import post
from docs.tests.conftest import make_expense

pytestmark = pytest.mark.django_db


@pytest.fixture
def printed_expense(client, owner, cash, rent):
    owner.first_name = "Alem"
    owner.last_name = "Kidane"
    owner.save()
    doc = make_expense(owner, cash, rent)
    post(doc, owner)
    client.force_login(owner)
    return client.get(reverse("document_print", args=[doc.pk])).content.decode()


def test_prepared_by_prints_the_creators_full_name(printed_expense):
    assert "Prepared By" in printed_expense
    assert "Alem Kidane" in printed_expense


def test_signature_block_cannot_split_across_pages(printed_expense):
    assert "break-inside: avoid" in printed_expense


def test_no_stamp_box_and_no_received_by(printed_expense):
    assert "Received By" not in printed_expense
    assert "Stamp" not in printed_expense
