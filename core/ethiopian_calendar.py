"""Gregorian <-> Ethiopian calendar conversion (D19, spec §12).

Fixed arithmetic via Julian Day Numbers. The Ethiopian calendar has twelve
30-day months plus Pagume (5 days, 6 in a leap year). Leap years are those
where year % 4 == 3; the new year lands on Gregorian Sep 11, or Sep 12 when
the *following* Gregorian year is a leap year. All of that falls out of the
JDN math below — do not special-case it.
"""

from datetime import date, timedelta

# JDN of the day before 1 Meskerem 1 EC (Amete Mihret epoch).
_EPOCH = 1723856
# date.toordinal() -> JDN offset (proleptic Gregorian).
_ORDINAL_TO_JDN = 1721425

MONTHS = [
    "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
    "Megabit", "Miyazya", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume",
]


def is_leap(eth_year: int) -> bool:
    return eth_year % 4 == 3


def validate(eth_year: int, month: int, day: int) -> None:
    if eth_year < 1:
        raise ValueError(f"Ethiopian year must be >= 1, got {eth_year}")
    if not 1 <= month <= 13:
        raise ValueError(f"Ethiopian month must be 1..13, got {month}")
    max_day = 30 if month <= 12 else (6 if is_leap(eth_year) else 5)
    if not 1 <= day <= max_day:
        raise ValueError(
            f"Day {day} invalid for {MONTHS[month - 1]} {eth_year} (max {max_day})"
        )


def to_ethiopian(gregorian: date) -> tuple[int, int, int]:
    """Return (year, month, day) in the Ethiopian calendar."""
    jdn = gregorian.toordinal() + _ORDINAL_TO_JDN
    r = (jdn - _EPOCH) % 1461
    n = r % 365 + 365 * (r // 1460)
    year = 4 * ((jdn - _EPOCH) // 1461) + r // 365 - r // 1460
    month = n // 30 + 1
    day = n % 30 + 1
    return year, month, day


def to_gregorian(eth_year: int, month: int, day: int) -> date:
    validate(eth_year, month, day)
    jdn = (
        _EPOCH + 365
        + 365 * (eth_year - 1) + eth_year // 4
        + 30 * (month - 1) + (day - 1)
    )
    return date.fromordinal(jdn - _ORDINAL_TO_JDN)


def format_ethiopian(gregorian: date) -> str:
    year, month, day = to_ethiopian(gregorian)
    return f"{MONTHS[month - 1]} {day}, {year} EC"


def fiscal_year_bounds(gregorian: date, start_month: int) -> tuple[int, date, date]:
    """(fiscal Ethiopian year, first Gregorian day, last Gregorian day) of the
    business fiscal year containing `gregorian` (D19). start_month is 1..12."""
    if not 1 <= start_month <= 12:
        raise ValueError(f"Fiscal start month must be 1..12, got {start_month}")
    year, month, _day = to_ethiopian(gregorian)
    fiscal_year = year if month >= start_month else year - 1
    start = to_gregorian(fiscal_year, start_month, 1)
    end = to_gregorian(fiscal_year + 1, start_month, 1) - timedelta(days=1)
    return fiscal_year, start, end
