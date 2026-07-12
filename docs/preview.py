"""Expected totals for DRAFT documents — display only. Posting recomputes and
freezes the real numbers (D32); this module mirrors the handlers' math so a
clerk can confirm the money before making the document permanent."""

from decimal import Decimal

from core.models import CompanySettings
from docs.handlers_sales import issue_line_value
from docs.models import DocType, Document
from docs.tax import Part, TaxError, compute_totals, round2

PRICED_TYPES = (DocType.SALE, DocType.PROFORMA)


def draft_expected_totals(doc: Document) -> dict | None:
    """Preview dict for the detail template, or None when no preview applies
    (posted docs, types without document money, or invalid draft data)."""
    if doc.status != Document.Status.DRAFT:
        return None
    if doc.doc_type == DocType.RECEIVING:
        total = Decimal("0.00")
        for line in doc.lines.all():
            total += round2(Decimal(line.qty_entered) * (line.unit_cost_entered or 0))
        return {"subtotal": total, "discount": Decimal("0.00"),
                "tax": Decimal("0.00"), "grand": total, "withholding": Decimal("0.00")}
    if doc.doc_type == DocType.CONSIGNMENT_SETTLEMENT:
        return _settlement_expected(doc)
    if doc.doc_type not in PRICED_TYPES:
        return None

    settings = CompanySettings.load()
    parts = []
    try:
        for line in doc.lines.select_related("item"):
            gross = Decimal(line.qty_entered) * line.unit_price
            parts.append(Part(value=round2(gross - line.line_discount),
                              is_taxable=not line.item.vat_exempt))
        for charge in doc.charges.all():
            parts.append(Part(value=charge.amount, is_taxable=charge.is_taxable))
        rate = {
            CompanySettings.TaxRegime.VAT: settings.vat_rate,
            CompanySettings.TaxRegime.TOT: settings.tot_rate,
        }.get(settings.tax_regime, Decimal("0"))
        totals = compute_totals(parts, doc.doc_discount, settings.tax_regime, rate)
    except TaxError:
        return None  # invalid draft (e.g. discount > line) — posting will explain

    withholding = Decimal("0.00")
    if settings.withholding_on_sales and doc.customer_will_withhold:
        withholding = round2(
            settings.withholding_rate / 100 * (totals.grand_total - totals.tax_total)
        )
    return {"subtotal": totals.subtotal, "discount": totals.doc_discount,
            "tax": totals.tax_total, "grand": totals.grand_total,
            "withholding": withholding}


def _settlement_expected(doc: Document) -> dict | None:
    """Money due on a settlement: sold quantities × the issue's frozen prices,
    taxed at the issue's rate snapshot (§7.5). Returned/expired earn nothing."""
    issue = doc.related_document
    if issue is None:
        return None
    parts = []
    for line in doc.lines.all():
        if line.qty_sold <= 0:
            continue
        value = issue_line_value(issue, line.item_id, line.batch_id)
        if value is None:
            return None  # mixed-price issue: posting will demand split lines
        per_base, is_taxable = value
        parts.append(Part(value=round2(Decimal(line.qty_sold) * per_base),
                          is_taxable=is_taxable))
    rate = issue.tax_rate_snapshot
    try:
        totals = compute_totals(parts, doc.doc_discount,
                                "VAT" if rate else "NONE", rate)
    except TaxError:
        return None
    settings = CompanySettings.load()
    withholding = Decimal("0.00")
    will_withhold = doc.customer_will_withhold or issue.customer_will_withhold  # D70
    if settings.withholding_on_sales and will_withhold:
        withholding = round2(
            settings.withholding_rate / 100 * (totals.grand_total - totals.tax_total)
        )
    return {"subtotal": totals.subtotal, "discount": totals.doc_discount,
            "tax": totals.tax_total, "grand": totals.grand_total,
            "withholding": withholding}
