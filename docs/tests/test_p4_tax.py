"""I8 golden tax cases (§5, D32/D50/D64) — exact expected values, no DB.
These numbers were hand-computed; if one fails, the engine is wrong, not the test."""

from decimal import Decimal

import pytest

from docs.tax import Part, TaxError, allocate_discount, compute_totals

D = Decimal


def taxable(value):
    return Part(value=D(value), is_taxable=True)


def exempt(value):
    return Part(value=D(value), is_taxable=False)


# --- Golden case 1: all-exempt invoice (the common case — medicines) ---


def test_all_exempt_invoice_has_zero_tax():
    totals = compute_totals([exempt("500.00"), exempt("250.00")],
                            D("0"), "VAT", D("15.00"))
    assert totals.subtotal == D("750.00")
    assert totals.taxable_base == D("0.00")
    assert totals.exempt_base == D("750.00")
    assert totals.tax_total == D("0.00")
    assert totals.grand_total == D("750.00")


# --- Golden case 2: mixed invoice with doc discount (D64 pro-rata) ---


def test_mixed_invoice_prorata_discount_remainder_on_last():
    # 3 parts: exempt 100, taxable 200, taxable 50; discount 10 over 350
    # alloc: 10×100/350 = 2.857→2.86 · 10×200/350 = 5.714→5.71 · last: 10−8.57 = 1.43
    parts = [exempt("100.00"), taxable("200.00"), taxable("50.00")]
    allocations = allocate_discount(parts, D("10.00"))
    assert allocations == [D("2.86"), D("5.71"), D("1.43")]
    assert sum(allocations) == D("10.00")  # exact — remainder absorbed

    totals = compute_totals(parts, D("10.00"), "VAT", D("15.00"))
    assert totals.exempt_base == D("97.14")          # 100 − 2.86
    assert totals.taxable_base == D("242.86")        # (200−5.71) + (50−1.43)
    assert totals.tax_total == D("36.43")            # 242.86 × 0.15 = 36.429 → 36.43
    assert totals.grand_total == D("376.43")         # 97.14 + 242.86 + 36.43


# --- Golden case 3: taxable charge on an exempt-goods invoice (D37) ---


def test_taxable_delivery_charge_on_exempt_goods():
    # 1000 exempt medicines + 50 taxable delivery charge
    totals = compute_totals([exempt("1000.00"), taxable("50.00")],
                            D("0"), "VAT", D("15.00"))
    assert totals.taxable_base == D("50.00")
    assert totals.exempt_base == D("1000.00")
    assert totals.tax_total == D("7.50")
    assert totals.grand_total == D("1057.50")


# --- Golden case 4: TOT regime (exempt flag still honored) ---


def test_tot_regime():
    totals = compute_totals([taxable("300.00"), exempt("100.00")],
                            D("0"), "TOT", D("2.00"))
    assert totals.tax_total == D("6.00")  # 300 × 2%
    assert totals.grand_total == D("406.00")


def test_none_regime_zero_tax():
    totals = compute_totals([taxable("300.00")], D("0"), "NONE", D("15.00"))
    assert totals.tax_total == D("0.00")
    assert totals.grand_total == D("300.00")


# --- Golden case 5: rounding edges (ROUND_HALF_UP, once, at doc level) ---


def test_rounding_edge_half_up():
    # taxable_base 0.10 → tax 0.015 → 0.02 (half-up), NOT 0.01 (banker's)
    totals = compute_totals([taxable("0.10")], D("0"), "VAT", D("15.00"))
    assert totals.tax_total == D("0.02")


def test_rounding_edge_below_half():
    # taxable_base 0.03 → tax 0.0045 → 0.00
    totals = compute_totals([taxable("0.03")], D("0"), "VAT", D("15.00"))
    assert totals.tax_total == D("0.00")


def test_tax_computed_once_not_per_line():
    # Two lines of 0.10: per-line tax would be 0.02+0.02=0.04;
    # doc-level (D32) is 0.20×0.15=0.03.
    totals = compute_totals([taxable("0.10"), taxable("0.10")],
                            D("0"), "VAT", D("15.00"))
    assert totals.tax_total == D("0.03")


# --- Full-discount and validation edges ---


def test_full_discount_zeroes_everything():
    totals = compute_totals([taxable("100.00")], D("100.00"), "VAT", D("15.00"))
    assert totals.taxable_base == D("0.00")
    assert totals.tax_total == D("0.00")
    assert totals.grand_total == D("0.00")


def test_discount_cannot_exceed_subtotal():
    with pytest.raises(TaxError):
        compute_totals([taxable("100.00")], D("100.01"), "VAT", D("15.00"))


def test_negative_line_rejected():
    with pytest.raises(TaxError):
        compute_totals([taxable("-1.00")], D("0"), "VAT", D("15.00"))


def test_empty_invoice_is_all_zero():
    totals = compute_totals([], D("0"), "VAT", D("15.00"))
    assert totals.grand_total == D("0.00")


def test_single_part_gets_whole_discount():
    assert allocate_discount([taxable("100.00")], D("7.77")) == [D("7.77")]


# --- Review-gate HIGH regression: bounded allocation, no negative bases ---


def test_near_total_discount_never_negative_bases():
    """21 exempt lines + tiny taxable charge, discount ≈ subtotal: the naive
    last-absorbs rule pushed taxable_base negative. Must stay bounded."""
    parts = [exempt("1.00") for _ in range(21)] + [taxable("0.43")]
    subtotal = D("21.43")
    totals = compute_totals(parts, D("21.00"), "VAT", D("15.00"))
    assert totals.taxable_base >= D("0.00")
    assert totals.exempt_base >= D("0.00")
    assert totals.tax_total >= D("0.00")
    # exact-sum property preserved: bases sum to subtotal − discount
    assert totals.taxable_base + totals.exempt_base == subtotal - D("21.00")


def test_allocation_never_exceeds_part_value_fuzz():
    import random
    rng = random.Random(7)
    for _ in range(300):
        parts = [Part(value=D(rng.randint(1, 5000)) / 100,
                      is_taxable=rng.random() < 0.5)
                 for _ in range(rng.randint(1, 12))]
        subtotal = sum((p.value for p in parts), D("0"))
        discount = (subtotal * D(rng.randint(0, 10000)) / 10000).quantize(D("0.01"))
        allocations = allocate_discount(parts, discount)
        assert sum(allocations) == discount
        for part, alloc in zip(parts, allocations):
            assert D("0.00") <= alloc <= part.value
