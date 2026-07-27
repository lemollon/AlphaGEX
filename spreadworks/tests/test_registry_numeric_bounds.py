"""Every registry default must FIT its bot_config column.

Why this file exists (2026-07-27 production incident): UPDRAFT shipped with
`pt_pct: 99.0` to mean "no profit target". `pt_pct` is NUMERIC(5,4), whose
maximum is 9.9999. SQLite does not enforce NUMERIC precision, so all 616
tests passed; Postgres does, so on deploy the seed raised

    (psycopg2.errors.NumericValueOutOfRange) numeric field overflow

and because create_bot_tables() seeds EVERY bot inside a single transaction,
one bad value rolled back the whole pass. No new bot got its tables, and the
config API returned 500.

The test suite could not catch this by exercising the database, so it checks
the declared bounds directly instead.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.bots.registry import BOT_REGISTRY

# (column, precision, scale) as declared in bots/db.py _CONFIG_DDL.
# max magnitude = 10**(precision - scale) - 10**-scale
NUMERIC_COLUMNS = {
    "starting_capital": (12, 2),
    "bp_pct": (4, 3),
    "sd_mult": (4, 2),
    "pt_pct": (5, 4),
    "sl_pct": (5, 4),
}


def _max_for(precision: int, scale: int) -> Decimal:
    return Decimal(10) ** (precision - scale) - Decimal(10) ** -scale


@pytest.mark.parametrize("bot", sorted(BOT_REGISTRY))
def test_numeric_defaults_fit_their_columns(bot):
    defaults = BOT_REGISTRY[bot].get("defaults") or {}
    for col, (precision, scale) in NUMERIC_COLUMNS.items():
        if col not in defaults:
            continue
        value = Decimal(str(defaults[col]))
        limit = _max_for(precision, scale)
        assert abs(value) <= limit, (
            f"{bot}.{col} = {value} exceeds NUMERIC({precision},{scale}) "
            f"(max {limit}). Postgres will raise numeric field overflow on "
            f"seed and roll back create_bot_tables for EVERY bot. SQLite "
            f"will not catch this."
        )


@pytest.mark.parametrize("bot", sorted(BOT_REGISTRY))
def test_config_seed_reads_every_required_key(bot):
    """db.py seeds these with defs[...] (not .get), so a missing key is a
    KeyError that aborts the same shared transaction."""
    required = ("starting_capital", "enabled", "max_contracts", "bp_pct",
                "sd_mult", "pt_pct", "sl_pct", "entry_start_ct",
                "entry_end_ct", "eod_close_ct", "discord_alerts",
                "delta_skew", "use_gex_walls")
    defaults = BOT_REGISTRY[bot].get("defaults") or {}
    missing = [k for k in required if k not in defaults]
    assert not missing, f"{bot} defaults missing {missing}"
    assert "front_dte" in BOT_REGISTRY[bot], f"{bot} missing front_dte"
    assert "back_dte" in BOT_REGISTRY[bot], f"{bot} missing back_dte"


def test_the_incident_value_would_now_be_caught():
    """Regression guard on the guard itself."""
    limit = _max_for(5, 4)
    assert limit == Decimal("9.9999")
    assert Decimal("99.0") > limit
