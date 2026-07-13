"""Derived settlement visibility (D73): how much of a posted document is
settled and how much is still outstanding. Everything is computed from posted
allocations and settlement lines (D11: balances are sums, never stored), so a
voided payment or settlement reopens its target automatically. Display only —
nothing here writes to the database."""

from decimal import Decimal

from django.db.models import (
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _

from docs.handlers_payments import AP_TARGET_TYPES, AR_TARGET_TYPES, open_balance
from docs.handlers_sales import outstanding_by_item_batch
from docs.models import DocType, Document, DocumentLine
from money.models import PaymentAllocation

# Money-settled targets (payment allocations) vs quantity-settled issues (CS lines)
MONEY_TARGET_TYPES = AR_TARGET_TYPES | AP_TARGET_TYPES
CONSIGNMENT_ISSUE_TYPES = {DocType.CONSIGNMENT_ISSUE, DocType.OPENING_CONSIGNMENT}

ZERO = Decimal("0.00")

# Filter choices for the transactions list
SETTLEMENT_FILTERS = [("open", _("Outstanding")), ("settled", _("Settled"))]


def annotate_settlement(queryset):
    """Attach the sums settlement_state() reads — three subqueries total, so
    the transactions list never runs per-row queries."""
    allocated = (
        PaymentAllocation.objects.filter(
            target=OuterRef("pk"), payment__status=Document.Status.POSTED,
        )
        .values("target")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    issued = (
        DocumentLine.objects.filter(document=OuterRef("pk"))
        .values("document")
        .annotate(total=Sum("qty_base"))
        .values("total")
    )
    settled_qty = (
        DocumentLine.objects.filter(
            document__related_document=OuterRef("pk"),
            document__doc_type=DocType.CONSIGNMENT_SETTLEMENT,
            document__status=Document.Status.POSTED,
        )
        .values("document__related_document")
        .annotate(total=Sum(F("qty_sold") + F("qty_returned") + F("qty_expired_unfit")))
        .values("total")
    )
    money = DecimalField(max_digits=14, decimal_places=2)
    return queryset.annotate(
        settled_amount=Coalesce(Subquery(allocated, output_field=money), Value(ZERO)),
        issued_qty=Coalesce(Subquery(issued, output_field=IntegerField()), Value(0)),
        settled_qty=Coalesce(Subquery(settled_qty, output_field=IntegerField()), Value(0)),
    ).annotate(
        open_amount=F("grand_total") - F("settled_amount"),
        outstanding_qty=F("issued_qty") - F("settled_qty"),
    )


def _money_target_q() -> Q:
    """Posted documents that carry an AR/AP balance a payment can settle.
    Cash sales/settlements are excluded — their auto payment settles them at
    posting, so a badge would be noise."""
    credit_kinds = Q(
        doc_type__in=[DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT],
        sale_kind=Document.SaleKind.CREDIT,
    )
    always = Q(doc_type__in=[DocType.RECEIVING, DocType.OPENING_AR, DocType.OPENING_AP])
    return Q(status=Document.Status.POSTED) & (credit_kinds | always)


def filter_settlement(queryset, state: str):
    """Apply the transactions-list settlement filter to an annotated queryset."""
    money = _money_target_q()
    issues = Q(status=Document.Status.POSTED, doc_type__in=CONSIGNMENT_ISSUE_TYPES)
    if state == "open":
        return queryset.filter(
            (money & Q(open_amount__gt=0)) | (issues & Q(outstanding_qty__gt=0))
        )
    if state == "settled":
        return queryset.filter(
            (money & Q(open_amount__lte=0)) | (issues & Q(outstanding_qty__lte=0))
        )
    return queryset


def _settled_line_qty(issue: Document) -> int:
    """Base units already settled against an issue — same line arithmetic the
    dashboard and consignment report use."""
    rows = DocumentLine.objects.filter(
        document__related_document=issue,
        document__doc_type=DocType.CONSIGNMENT_SETTLEMENT,
        document__status=Document.Status.POSTED,
    ).aggregate(total=Sum(F("qty_sold") + F("qty_returned") + F("qty_expired_unfit")))
    return rows["total"] or 0


def settlement_state(doc: Document) -> dict | None:
    """Badge + numbers for one document. Reads annotate_settlement() values
    when present; falls back to direct queries for a single document."""
    if doc.status != Document.Status.POSTED:
        return None
    if doc.doc_type in CONSIGNMENT_ISSUE_TYPES:
        issued = getattr(doc, "issued_qty", None)
        if issued is None:
            issued = doc.lines.aggregate(total=Sum("qty_base"))["total"] or 0
            settled = _settled_line_qty(doc)
        else:
            settled = doc.settled_qty
        outstanding = max(issued - settled, 0)
        if outstanding == 0:
            state, label = "CLOSED", _("Closed")
        elif settled > 0:
            state, label = "PARTIAL", _("Partial")
        else:
            state, label = "OPEN", _("Open")
        return {"kind": "qty", "state": state, "label": label,
                "issued": issued, "settled": min(settled, issued), "open": outstanding}
    if doc.doc_type not in MONEY_TARGET_TYPES:
        return None
    if doc.doc_type in (DocType.SALE, DocType.CONSIGNMENT_SETTLEMENT) \
            and doc.sale_kind != Document.SaleKind.CREDIT:
        return None  # settled by its auto payment the moment it posts
    settled = getattr(doc, "settled_amount", None)
    if settled is None:
        settled = doc.grand_total - open_balance(doc)
    open_amount = doc.grand_total - settled
    if open_amount <= 0:
        state, label = "SETTLED", _("Settled")
    elif settled > 0:
        state, label = "PARTIAL", _("Partial")
    else:
        state, label = "UNPAID", _("Unpaid")
    return {"kind": "money", "state": state, "label": label,
            "total": doc.grand_total, "settled": settled, "open": open_amount}


def settlement_context(doc: Document) -> dict | None:
    """Everything the detail page's settlement card shows: the state summary,
    the allocation history (both directions), and what is still out on an
    issue per item+batch."""
    state = settlement_state(doc)
    context: dict = {"state": state}
    if state and state["kind"] == "money":
        context["received"] = list(
            PaymentAllocation.objects.filter(
                target=doc, payment__status=Document.Status.POSTED,
            )
            .select_related("payment")
            .order_by("payment__document_date", "pk")
        )
    if state and state["kind"] == "qty":
        context["groups"] = outstanding_by_item_batch(doc)
        context["settlements"] = list(
            Document.objects.filter(
                related_document=doc,
                doc_type=DocType.CONSIGNMENT_SETTLEMENT,
                status=Document.Status.POSTED,
            ).order_by("document_date", "pk")
        )
    if doc.doc_type in (DocType.CUSTOMER_PAYMENT, DocType.SUPPLIER_PAYMENT) \
            and doc.status == Document.Status.POSTED:
        made = (
            PaymentAllocation.objects.filter(payment=doc)
            .select_related("target")
            .order_by("pk")
        )
        context["made"] = [
            {"allocation": allocation, "open": open_balance(allocation.target)}
            for allocation in made
        ]
    if state is None and not context.get("made"):
        return None
    return context
