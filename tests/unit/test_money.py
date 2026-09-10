"""The accounting rules in core/money.py.

These pin down the decisions documented there: USDT as the account currency,
8 decimal places, and half-up rounding at the persistence boundary.
"""
from decimal import Decimal

import pytest

from core.money import (
    ACCOUNT_CURRENCY,
    CURRENCY_CODE_LENGTH,
    DECIMAL_SCALE,
    to_decimal,
)


def test_account_currency_is_usdt_and_fits_the_column():
    """The old String(3) could not physically hold "USDT"."""
    assert ACCOUNT_CURRENCY == "USDT"
    assert len(ACCOUNT_CURRENCY) <= CURRENCY_CODE_LENGTH
    assert CURRENCY_CODE_LENGTH >= 4


def test_floats_become_exact_decimals():
    """Decimal(0.1) is 0.1000000000000000055…; Decimal(str(0.1)) is exactly 0.1."""
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(0.1) + to_decimal(0.2) == to_decimal(0.3)


def test_everything_is_quantised_to_the_platform_scale():
    for value in (1, 1.5, "2.25", Decimal("3")):
        assert to_decimal(value).as_tuple().exponent == -DECIMAL_SCALE


def test_eight_decimal_places_survive():
    """At the old scale of 6 this rounded to zero, which for a crypto venue
    silently destroys a real holding."""
    smallest = to_decimal(0.00000001)
    assert smallest == Decimal("0.00000001")
    assert smallest > 0


@pytest.mark.parametrize("value,expected", [
    ("0.000000005", "0.00000001"),   # ties round away from zero
    ("0.000000004", "0.00000000"),
    ("0.000000015", "0.00000002"),   # not banker's rounding, which would give 0.00000002 here too
    ("0.000000025", "0.00000003"),   # banker's rounding would give 0.00000002
    ("-0.000000005", "-0.00000001"),
])
def test_rounding_is_half_up_not_bankers(value, expected):
    assert to_decimal(value) == Decimal(expected)


def test_large_balances_are_not_truncated():
    """Precision 28 with scale 8 leaves 20 integer digits."""
    big = to_decimal("12345678901234567890.12345678")
    assert big == Decimal("12345678901234567890.12345678")


def test_a_buy_and_a_complete_sell_return_the_original_cash():
    """A round trip at the same price must be exactly cash-neutral in decimal.

    Doing this in float would leave a residue; the point of fixing the scale is
    that it does not.
    """
    start = to_decimal("10000")
    price = to_decimal("77210.51")
    quantity = to_decimal("0.00130123")

    cost = to_decimal(price * quantity)
    after_buy = to_decimal(start - cost)
    proceeds = to_decimal(price * quantity)
    after_sell = to_decimal(after_buy + proceeds)

    assert after_sell == start


def test_fractional_quantities_accumulate_exactly():
    """Ten buys of 0.1 must be exactly 1, not 0.9999999999999999."""
    total = to_decimal(0)
    for _ in range(10):
        total = to_decimal(total + to_decimal(0.1))
    assert total == to_decimal(1)
