"""Attachment views: upload / download / delete / void.

Files are served only through the login-required download view — MEDIA is
never exposed as static URLs. Deletion is allowed only while the parent
document is a DRAFT; after posting the owner can void (hide + audit), but
the bytes stay on disk — evidence is never destroyed."""

from pathlib import Path

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.audit import log_event
from docs.models import (
    ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_DOC,
    Attachment,
    Document,
)


class AttachmentForm(forms.Form):
    file = forms.FileField()
    note = forms.CharField(required=False, max_length=200)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        ext = Path(upload.name).suffix.lower()
        if ext not in ATTACHMENT_TYPES:
            raise forms.ValidationError(
                _("Only PDF, JPG, PNG or WebP files are accepted."))
        if upload.size > MAX_ATTACHMENT_BYTES:
            raise forms.ValidationError(
                _("File is larger than %(mb)d MB.")
                % {"mb": MAX_ATTACHMENT_BYTES // (1024 * 1024)})
        head = upload.read(12)
        upload.seek(0)
        _content_type, magics = ATTACHMENT_TYPES[ext]
        if not any(head.startswith(magic) for magic in magics):
            raise forms.ValidationError(
                _("File content does not match its extension."))
        if ext == ".webp" and head[8:12] != b"WEBP":
            raise forms.ValidationError(
                _("File content does not match its extension."))
        return upload


@login_required
@require_POST
def attachment_upload(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.attachments.count() >= MAX_ATTACHMENTS_PER_DOC:
        messages.error(request, _("This document already has %(n)d attachments.")
                       % {"n": MAX_ATTACHMENTS_PER_DOC})
        return redirect("document_detail", pk=doc.pk)
    form = AttachmentForm(request.POST, request.FILES)
    if not form.is_valid():
        for error_list in form.errors.values():
            for error in error_list:
                messages.error(request, error)
        return redirect("document_detail", pk=doc.pk)
    upload = form.cleaned_data["file"]
    attachment = Attachment.objects.create(
        document=doc,
        file=upload,
        original_name=upload.name[:200],
        size=upload.size,
        note=form.cleaned_data["note"],
        uploaded_by=request.user,
    )
    log_event(request.user, "ATTACHMENT_ADD", "Document", doc.pk,
              {"file": attachment.original_name, "attachment": attachment.pk})
    messages.success(request, _("Attachment added."))
    return redirect("document_detail", pk=doc.pk)


@login_required
def attachment_download(request, pk):
    attachment = get_object_or_404(
        Attachment.objects.select_related("document"), pk=pk)
    if attachment.is_voided and not request.user.is_owner:
        raise Http404
    response = FileResponse(
        attachment.file.open("rb"),
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def attachment_delete(request, pk):
    attachment = get_object_or_404(
        Attachment.objects.select_related("document"), pk=pk)
    doc = attachment.document
    if doc.status != Document.Status.DRAFT:
        raise PermissionDenied(
            _("Attachments on a posted document cannot be deleted — "
              "the owner may mark one as uploaded in error."))
    if not (request.user.is_owner or attachment.uploaded_by_id == request.user.pk):
        raise PermissionDenied
    name = attachment.original_name
    attachment.file.delete(save=False)
    attachment.delete()
    log_event(request.user, "ATTACHMENT_DELETE", "Document", doc.pk,
              {"file": name})
    messages.success(request, _("Attachment deleted."))
    return redirect("document_detail", pk=doc.pk)


@login_required
@require_POST
def attachment_void(request, pk):
    if not request.user.is_owner:
        raise PermissionDenied
    attachment = get_object_or_404(
        Attachment.objects.select_related("document"), pk=pk)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, _("A reason is required to void an attachment."))
        return redirect("document_detail", pk=attachment.document_id)
    attachment.is_voided = True
    attachment.voided_by = request.user
    attachment.voided_at = timezone.now()
    attachment.void_reason = reason[:300]
    attachment.save(update_fields=["is_voided", "voided_by", "voided_at",
                                   "void_reason"])
    log_event(request.user, "ATTACHMENT_VOID", "Document", attachment.document_id,
              {"file": attachment.original_name, "reason": attachment.void_reason})
    messages.success(request, _("Attachment marked as uploaded in error."))
    return redirect("document_detail", pk=attachment.document_id)
