"""The platform's accounting rules, defined once.

Every monetary or quantity value that reaches PostgreSQL goes through
`to_decimal`, so rounding behaviour is stated here rather than implied by
whatever each call site happens to do.

Decisions
---------

**Account currency is USDT.** The platform trades USDT-quoted pairs priced from
a live Binance order book, and performs no FX conversion anywhere in the code.
The schema previously defaulted to ``"GBP"`` in a ``String(3)`` column, which
nothing in the system honoured and which could not even hold the string
``"USDT"``. Balances were therefore labelled in a currency they were never
denominated in.

**Scale is 8 decimal places.** That is the smallest unit Binance quotes, for
both quantities and prices. The previous scale of 6 silently rounded any
quantity below 0.000001 to zero, which for a crypto venue is a correctness
bug, not a rounding preference.

**Rounding is half-up.** Ties round away from zero (0.000000005 -> 0.00000001),
which is what a person reading a balance expects. Banker's rounding
(ROUND_HALF_EVEN) has better statistical properties across many operations,
but it surprises people and this system's rounding happens once per fill at
the persistence boundary, not repeatedly inside a calculation.

**Short positions are not allowed.** The engine rejects a SELL for more than
the account holds (``INSUFFICIENT_POSITION``), so quantities never go negative.
"""
from decimal import Decimal, ROUND_HALF_UP

ACCOUNT_CURRENCY = "USDT"

#: Column width for currency codes. "USDT" is four characters; the old
#: String(3) could not store it at all.
CURRENCY_CODE_LENGTH = 10

#: Numeric(28, 8): scale 8 matches Binance's smallest quoted unit, and 20
#: integer digits is far beyond any balance this platform will hold.
DECIMAL_PRECISION = 28
DECIMAL_SCALE = 8

_QUANTUM = Decimal(1).scaleb(-DECIMAL_SCALE)  # Decimal("0.00000001")


def to_decimal(value) -> Decimal:
    """Convert a float, int, str or Decimal to the platform's canonical Decimal.

    Rounds half-up to `DECIMAL_SCALE` places.

    Floats are routed through ``str()`` first, which matters: ``Decimal(0.1)``
    is ``0.1000000000000000055511151231257827`` because 0.1 has no exact binary
    representation, whereas ``Decimal(str(0.1))`` is exactly ``Decimal("0.1")``.
    The C++ engine sends doubles over gRPC, so this function is the boundary
    where approximate binary floats become exact decimals.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
