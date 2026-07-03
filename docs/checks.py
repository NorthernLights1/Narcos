"""Business checks shared by handlers and screens: expiry status (D46/D59)
and credit exposure (D25/§8)."""

import datetime
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from money.models import PartyLedger


class ExpiryStatus:
    EXPIRED = "EXPIRED"
    NEAR = "NEAR"
    OK = "OK"


def add_months(day: datetime.date, months: int) -> datetime.date:
    """Calendar-safe month addition (Jan 31 + 1m → Feb 28/29)."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return datetime.date(year, month, min(day.day, last_day))


def expiry_status(expiry_date, on_date: datetime.date, near_months: int) -> str:
    """D46: expired = past its date (the expiry day itself is still sellable).
    Near = within `near_months` (D59)."""
    if expiry_date is None:
        return ExpiryStatus.OK
    if expiry_date < on_date:
        return ExpiryStatus.EXPIRED
    if expiry_date <= add_months(on_date, near_months):
        return ExpiryStatus.NEAR
    return ExpiryStatus.OK


def ar_balance(customer_id: int) -> Decimal:
    total = Decimal("0.00")
    rows = PartyLedger.objects.filter(
        party_type=PartyLedger.PartyType.CUSTOMER, party_id=customer_id
    ).values_list("amount_delta", flat=True)
    for amount in rows:
        total += amount
    return total


def consigned_exposure(customer_id: int) -> Decimal:
    """D25: locked-price value of stock in CONSIGNED(customer). Real values
    arrive with P6 consignment; until then customers have nothing consigned."""
    from stock.models import StockBalance, Zone  # local import avoids cycles

    total = Decimal("0.00")
    balances = StockBalance.objects.filter(
        zone=Zone.CONSIGNED, consignment_customer_id=customer_id, qty__gt=0
    ).select_related("lot")
    for balance in balances:
        # ponytail: valued at lot cost until P6 stores locked issue prices
        total += Decimal(balance.qty) * balance.lot.unit_cost
    return total


def credit_check(customer, settings, additional: Decimal) -> tuple[str, str]:
    """Returns (action, message). action: 'OK' | 'WARN' | 'BLOCK' (D25/§8)."""
    limit = customer.credit_limit if customer.credit_limit is not None \
        else settings.default_credit_limit
    if limit is None:
        return "OK", ""
    exposure = ar_balance(customer.pk) + consigned_exposure(customer.pk) + additional
    if exposure <= limit:
        return "OK", ""
    action = customer.credit_action or settings.default_credit_action
    message = _(
        "Credit limit exceeded for %(name)s: exposure %(exposure)s over limit %(limit)s."
    ) % {"name": customer.name, "exposure": exposure, "limit": limit}
    return action, str(message)
