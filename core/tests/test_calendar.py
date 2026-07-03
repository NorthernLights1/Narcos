from datetime import date, timedelta

import pytest

from core.ethiopian_calendar import (
    fiscal_year_bounds,
    format_ethiopian,
    is_leap,
    to_ethiopian,
    to_gregorian,
    validate,
)

# Known anchor pairs (Gregorian <-> Ethiopian).
ANCHORS = [
    (date(2024, 9, 11), (2017, 1, 1)),   # new year
    (date(2023, 9, 12), (2016, 1, 1)),   # new year after an Ethiopian leap year
    (date(2020, 9, 11), (2013, 1, 1)),
    (date(2023, 1, 7), (2015, 4, 29)),   # Genna (Ethiopian Christmas)
    (date(2023, 9, 11), (2015, 13, 6)),  # Pagume 6 — leap year only
]


@pytest.mark.parametrize("greg,eth", ANCHORS)
def test_to_ethiopian(greg, eth):
    assert to_ethiopian(greg) == eth


@pytest.mark.parametrize("greg,eth", ANCHORS)
def test_to_gregorian(greg, eth):
    assert to_gregorian(*eth) == greg


def test_round_trip_two_centuries():
    d = date(1900, 1, 1)
    while d < date(2100, 1, 1):
        assert to_gregorian(*to_ethiopian(d)) == d
        d += timedelta(days=17)


def test_leap_rule():
    assert is_leap(2015)
    assert is_leap(2011)
    assert not is_leap(2016)
    assert not is_leap(2013)


@pytest.mark.parametrize(
    "bad",
    [(2014, 13, 6), (2015, 13, 7), (2017, 14, 1), (2017, 0, 1), (2017, 1, 31), (0, 1, 1)],
)
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        validate(*bad)


def test_format():
    assert format_ethiopian(date(2024, 9, 11)) == "Meskerem 1, 2017 EC"


def test_fiscal_year_bounds_default_hamle():
    # Hamle 1, 2017 EC == 2025-07-08; the fiscal year runs to 2026-07-07.
    fy, start, end = fiscal_year_bounds(date(2026, 7, 3), start_month=11)
    assert (fy, start, end) == (2017, date(2025, 7, 8), date(2026, 7, 7))
    # First day of the fiscal year belongs to that same year.
    fy2, start2, _ = fiscal_year_bounds(date(2025, 7, 8), start_month=11)
    assert (fy2, start2) == (2017, date(2025, 7, 8))


def test_fiscal_year_bounds_rejects_pagume():
    with pytest.raises(ValueError):
        fiscal_year_bounds(date(2026, 7, 3), start_month=13)
