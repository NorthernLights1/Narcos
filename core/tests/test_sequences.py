import pytest
from django.db import transaction

from core.models import NumberSequence

pytestmark = pytest.mark.django_db


def test_take_increments_per_doc_type():
    with transaction.atomic():
        assert NumberSequence.take("SI") == 1
        assert NumberSequence.take("SI") == 2
        assert NumberSequence.take("GRN") == 1  # independent sequences
    with transaction.atomic():
        assert NumberSequence.take("SI") == 3
