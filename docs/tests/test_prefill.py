"""D23 selling-price prefill: maintained price, or latest cost + margin for
AUTO items. Pure function — no DB."""

from decimal import Decimal

from catalog.models import Item
from docs.forms import _selling_price


def test_manual_mode_uses_maintained_price():
    item = Item(maintained_price=Decimal("3.00"),
                pricing_mode=Item.PricingMode.MANUAL)
    assert _selling_price(item) == Decimal("3.00")


def test_auto_mode_uses_latest_cost_plus_margin():
    item = Item(maintained_price=Decimal("999.00"),
                pricing_mode=Item.PricingMode.AUTO,
                auto_margin_pct=Decimal("50"))
    item.latest_cost = Decimal("2.00")
    assert _selling_price(item) == Decimal("3.00")  # 2.00 × 1.5


def test_auto_mode_rounds_half_up():
    item = Item(pricing_mode=Item.PricingMode.AUTO,
                auto_margin_pct=Decimal("33"))
    item.latest_cost = Decimal("1.99")
    assert _selling_price(item) == Decimal("2.65")  # 1.99 × 1.33 = 2.6467


def test_auto_mode_without_any_cost_falls_back_to_maintained():
    item = Item(maintained_price=Decimal("9.99"),
                pricing_mode=Item.PricingMode.AUTO,
                auto_margin_pct=Decimal("50"))
    assert _selling_price(item) == Decimal("9.99")
