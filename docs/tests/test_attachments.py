"""Attachments: scanned evidence (supplier invoices, delivery notes) tied to
documents. Evidence follows the void pattern — physically deletable only
while the parent is a draft; on posted documents the owner can void (hide +
audit) but bytes are never destroyed."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog
from docs.models import Attachment, MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_DOC
from docs.posting import post
from docs.tests.conftest import make_expense

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 fake pdf body"
PNG = b"\x89PNG\r\n\x1a\n" + b"fakepng"


@pytest.fixture(autouse=True)
def _media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def draft(owner, cash, rent):
    return make_expense(owner, cash, rent)


@pytest.fixture
def posted(owner, cash, rent):
    return post(make_expense(owner, cash, rent), owner)


def upload(client, doc, name="invoice.pdf", body=PDF, note=""):
    return client.post(
        reverse("attachment_upload", args=[doc.pk]),
        {"file": SimpleUploadedFile(name, body), "note": note},
    )


def test_upload_requires_login(client, draft):
    response = upload(client, draft)
    assert response.status_code == 302
    assert "/login" in response["Location"]
    assert Attachment.objects.count() == 0


def test_upload_to_draft_and_posted(client, owner, draft, posted):
    client.force_login(owner)
    assert upload(client, draft).status_code == 302
    assert upload(client, posted, name="scan.png", body=PNG).status_code == 302
    assert draft.attachments.count() == 1
    assert posted.attachments.count() == 1
    attachment = draft.attachments.get()
    assert attachment.original_name == "invoice.pdf"
    assert attachment.uploaded_by == owner
    # stored under a generated name, never the user's filename
    assert "invoice" not in attachment.file.name


def test_upload_rejects_unknown_extension(client, owner, draft):
    client.force_login(owner)
    upload(client, draft, name="virus.exe", body=b"MZ fake")
    assert draft.attachments.count() == 0


def test_upload_rejects_forged_magic_bytes(client, owner, draft):
    client.force_login(owner)
    upload(client, draft, name="renamed.pdf", body=b"MZ definitely not a pdf")
    assert draft.attachments.count() == 0


def test_upload_rejects_oversize(client, owner, draft):
    client.force_login(owner)
    upload(client, draft, body=b"%PDF" + b"0" * MAX_ATTACHMENT_BYTES)
    assert draft.attachments.count() == 0


def test_upload_respects_per_document_cap(client, owner, draft):
    client.force_login(owner)
    for i in range(MAX_ATTACHMENTS_PER_DOC):
        upload(client, draft, name=f"scan{i}.pdf")
    assert draft.attachments.count() == MAX_ATTACHMENTS_PER_DOC
    upload(client, draft, name="one-too-many.pdf")
    assert draft.attachments.count() == MAX_ATTACHMENTS_PER_DOC


def test_download_requires_login(client, owner, draft):
    client.force_login(owner)
    upload(client, draft)
    attachment = draft.attachments.get()
    client.logout()
    response = client.get(reverse("attachment_download", args=[attachment.pk]))
    assert response.status_code == 302


def test_download_streams_file(client, owner, draft):
    client.force_login(owner)
    upload(client, draft)
    attachment = draft.attachments.get()
    response = client.get(reverse("attachment_download", args=[attachment.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content) == PDF


def test_delete_on_draft_by_uploader(client, owner, draft):
    client.force_login(owner)
    upload(client, draft)
    attachment = draft.attachments.get()
    stored = attachment.file.path
    client.post(reverse("attachment_delete", args=[attachment.pk]))
    assert draft.attachments.count() == 0
    import os
    assert not os.path.exists(stored)


def test_delete_denied_to_non_uploader_employee(client, owner, employee, draft):
    client.force_login(owner)
    upload(client, draft)
    attachment = draft.attachments.get()
    client.force_login(employee)
    response = client.post(reverse("attachment_delete", args=[attachment.pk]))
    assert response.status_code == 403
    assert draft.attachments.count() == 1


def test_delete_refused_on_posted_even_for_owner(client, owner, posted):
    client.force_login(owner)
    upload(client, posted)
    attachment = posted.attachments.get()
    response = client.post(reverse("attachment_delete", args=[attachment.pk]))
    assert response.status_code == 403
    assert posted.attachments.count() == 1


def test_void_on_posted_owner_only_with_reason(client, owner, employee, posted):
    client.force_login(owner)
    upload(client, posted)
    attachment = posted.attachments.get()

    client.force_login(employee)
    assert client.post(reverse("attachment_void", args=[attachment.pk]),
                       {"reason": "x"}).status_code == 403

    client.force_login(owner)
    # missing reason refused
    client.post(reverse("attachment_void", args=[attachment.pk]), {"reason": ""})
    attachment.refresh_from_db()
    assert attachment.is_voided is False

    client.post(reverse("attachment_void", args=[attachment.pk]),
                {"reason": "wrong supplier invoice"})
    attachment.refresh_from_db()
    assert attachment.is_voided is True
    assert attachment.voided_by == owner
    assert attachment.void_reason == "wrong supplier invoice"
    # bytes survive
    import os
    assert os.path.exists(attachment.file.path)


def test_voided_hidden_from_employee_download(client, owner, employee, posted):
    client.force_login(owner)
    upload(client, posted)
    attachment = posted.attachments.get()
    client.post(reverse("attachment_void", args=[attachment.pk]),
                {"reason": "mistake"})
    client.force_login(employee)
    response = client.get(reverse("attachment_download", args=[attachment.pk]))
    assert response.status_code == 404
    client.force_login(owner)
    response = client.get(reverse("attachment_download", args=[attachment.pk]))
    assert response.status_code == 200


def test_attachment_events_are_audited(client, owner, draft, posted):
    client.force_login(owner)
    upload(client, draft)
    attachment = draft.attachments.get()
    client.post(reverse("attachment_delete", args=[attachment.pk]))
    upload(client, posted)
    client.post(reverse("attachment_void", args=[posted.attachments.get().pk]),
                {"reason": "mistake"})
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"ATTACHMENT_ADD", "ATTACHMENT_DELETE", "ATTACHMENT_VOID"} <= actions
