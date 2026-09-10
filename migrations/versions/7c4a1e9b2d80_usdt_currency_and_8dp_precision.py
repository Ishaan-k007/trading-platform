"""USDT account currency and 8dp decimal precision

The schema was created with a 3-character currency column defaulting to "GBP",
but the platform trades USDT-quoted pairs against a live Binance order book and
does no FX conversion anywhere. "USDT" is four characters, so it could not even
be stored. This widens the column and restates existing rows in the currency
they were always actually denominated in.

Scale also goes from 6 to 8 decimal places, which is the smallest unit Binance
quotes. At scale 6 any quantity below 0.000001 rounded to zero -- a correctness
problem for a crypto venue rather than a rounding preference. See core/money.py
for the full policy.

Widening a Numeric and a String is lossless, so the upgrade needs no data
backfill beyond the currency relabel. The downgrade narrows both, which can
lose precision on rows written after this migration; it is provided for
completeness, not as a safe round-trip.

Revision ID: 7c4a1e9b2d80
Revises: 5d3d32b880d4
Create Date: 2026-09-11 00:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7c4a1e9b2d80'
down_revision = '5d3d32b880d4'
branch_labels = None
depends_on = None


NEW = sa.Numeric(precision=28, scale=8)
OLD = sa.Numeric(precision=18, scale=6)

# (table, column) pairs holding money or quantities.
AMOUNT_COLUMNS = [
    ('market_prices', 'price'),
    ('accounts', 'cash_balance'),
    ('orders', 'quantity'),
    ('orders', 'limit_price'),
    ('orders', 'requested_price'),
    ('orders', 'filled_price'),
    ('positions', 'quantity'),
    ('positions', 'average_price'),
    ('positions', 'realised_pnl'),
    ('ledger_entries', 'amount'),
    ('ledger_entries', 'running_balance'),
]

CURRENCY_COLUMNS = [
    ('accounts', 'currency'),
    ('ledger_entries', 'currency'),
]


def upgrade():
    for table, column in AMOUNT_COLUMNS:
        op.alter_column(table, column, type_=NEW, existing_type=OLD)

    for table, column in CURRENCY_COLUMNS:
        op.alter_column(table, column,
                        type_=sa.String(length=10),
                        existing_type=sa.String(length=3),
                        existing_nullable=False,
                        server_default=None)
        # Existing rows say "GBP" but were never GBP-denominated: balances came
        # from a fixed 10,000 opening deposit and USDT-priced fills, with no
        # conversion at any point. Relabelling is a correction, not a
        # conversion, so no arithmetic is applied.
        op.execute(f"UPDATE {table} SET currency = 'USDT' WHERE currency = 'GBP'")


def downgrade():
    for table, column in CURRENCY_COLUMNS:
        op.execute(f"UPDATE {table} SET currency = 'GBP' WHERE currency = 'USDT'")
        op.alter_column(table, column,
                        type_=sa.String(length=3),
                        existing_type=sa.String(length=10),
                        existing_nullable=False,
                        server_default=None)

    for table, column in AMOUNT_COLUMNS:
        op.alter_column(table, column, type_=OLD, existing_type=NEW)
