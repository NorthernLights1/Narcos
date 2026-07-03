"""Tax computation (§5, D32 + D50 + D64) — the ONLY algorithm allowed.
Every document's stored ※ totals come from here; nothing recomputes tax
another way. Pure functions, no DB access."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TWO_DP = Decimal("0.01")


def round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Part:
    """One line or charge entering the computation."""

    value: Decimal  # net (already minus line-level discount), 2 dp
    is_taxable: bool


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    doc_discount: Decimal
    taxable_base: Decimal
    exempt_base: Decimal
    tax_total: Decimal
    grand_total: Decimal


class TaxError(ValueError):
    """Invalid inputs (negative values, discount exceeding subtotal)."""


def allocate_discount(parts: list[Part], doc_discount: Decimal) -> list[Decimal]:
    """D64: pro-rata by value, 2 dp per part, LAST part absorbs the rounding
    remainder so the allocations sum exactly to doc_discount."""
    subtotal = sum((p.value for p in parts), Decimal("0.00"))
    if doc_discount == 0 or not parts:
        return [Decimal("0.00")] * len(parts)
    if subtotal <= 0:
        raise TaxError("Cannot allocate a discount over a zero subtotal.")
    allocations = []
    allocated = Decimal("0.00")
    for part in parts[:-1]:
        share = round2(doc_discount * part.value / subtotal)
        allocations.append(share)
        allocated += share
    allocations.append(doc_discount - allocated)  # last absorbs remainder
    return allocations


def compute_totals(parts: list[Part], doc_discount: Decimal,
                   regime: str, rate: Decimal) -> Totals:
    """§5 verbatim. regime: VAT | TOT | NONE; rate in percent (e.g. 15.00)."""
    if any(p.value < 0 for p in parts):
        raise TaxError("Line values cannot be negative.")
    if doc_discount < 0:
        raise TaxError("Discount cannot be negative.")
    subtotal = sum((p.value for p in parts), Decimal("0.00"))
    if doc_discount > subtotal:
        raise TaxError("Document discount cannot exceed the subtotal.")

    allocations = allocate_discount(parts, doc_discount)
    taxable_base = Decimal("0.00")
    exempt_base = Decimal("0.00")
    for part, alloc in zip(parts, allocations):
        net = part.value - alloc
        if part.is_taxable:
            taxable_base += net
        else:
            exempt_base += net

    if regime in ("VAT", "TOT"):
        tax_total = round2(taxable_base * rate / 100)  # once, at doc level (D32)
    else:
        tax_total = Decimal("0.00")

    return Totals(
        subtotal=subtotal,
        doc_discount=doc_discount,
        taxable_base=taxable_base,
        exempt_base=exempt_base,
        tax_total=tax_total,
        grand_total=taxable_base + exempt_base + tax_total,
    )
