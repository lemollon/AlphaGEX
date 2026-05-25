"""Per-bot Postgres table helpers + idempotent migration.

Tables created (per bot in {frost, tide, drift}):
  {bot}_config            -- single-row config (1 = enabled, NULL/0 = disabled)
  {bot}_positions         -- open positions
  {bot}_closed_trades     -- realized P&L
  {bot}_equity_snapshots  -- equity curve points (1 per scan cycle)
  {bot}_scan_activity     -- scanner outcomes

Tables are created with `CREATE TABLE IF NOT EXISTS` and config rows are
seeded with `INSERT ... ON CONFLICT DO NOTHING` so a restart never
overwrites user-edited values (mirrors the IronForge SPARK config-lock fix).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .registry import BOT_REGISTRY, list_bots


def bot_table(bot: str, name: str) -> str:
    """Return `{bot}_{name}` after validating `bot` is registered."""
    if bot not in BOT_REGISTRY:
        raise ValueError(f"Unknown bot: {bot!r}. Known: {list_bots()}")
    return f"{bot}_{name}"


_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id                INTEGER PRIMARY KEY,
    starting_capital  NUMERIC(12,2) NOT NULL DEFAULT 10000,
    enabled           BOOLEAN NOT NULL DEFAULT FALSE,
    max_contracts     INTEGER NOT NULL DEFAULT 1,
    bp_pct            NUMERIC(4,3) NOT NULL DEFAULT 0.10,
    sd_mult           NUMERIC(4,2) NOT NULL DEFAULT 1.0,
    front_dte         INTEGER NOT NULL DEFAULT 0,
    back_dte          INTEGER,
    pt_pct            NUMERIC(5,4) NOT NULL DEFAULT 0.30,
    sl_pct            NUMERIC(5,4) NOT NULL DEFAULT 2.0,
    entry_start_ct    TEXT NOT NULL DEFAULT '08:35',
    entry_end_ct      TEXT NOT NULL DEFAULT '10:30',
    eod_close_ct      TEXT NOT NULL DEFAULT '14:45',
    discord_alerts    BOOLEAN NOT NULL DEFAULT FALSE,
    delta_skew        INTEGER NOT NULL DEFAULT 0,
    use_gex_walls     BOOLEAN NOT NULL DEFAULT FALSE,
    entry_days        TEXT NOT NULL DEFAULT '',
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_POSITIONS_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    position_id     TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL DEFAULT 'SPY',
    strategy        TEXT NOT NULL,
    legs            TEXT NOT NULL,
    entry_price     NUMERIC(10,4) NOT NULL,
    contracts       INTEGER NOT NULL,
    entry_time      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL DEFAULT 'OPEN',
    mtm_value       NUMERIC(10,4),
    mtm_pnl         NUMERIC(10,2),
    mtm_updated_at  TIMESTAMP,
    pt_target_pnl   NUMERIC(10,2) NOT NULL,
    sl_target_pnl   NUMERIC(10,2) NOT NULL,
    max_profit      NUMERIC(10,2) NOT NULL,
    max_loss        NUMERIC(10,2) NOT NULL,
    account_label   TEXT NOT NULL DEFAULT 'paper',
    notes           TEXT
)
"""

_CLOSED_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    position_id     TEXT PRIMARY KEY,
    close_price     NUMERIC(10,4) NOT NULL,
    close_time      TIMESTAMP NOT NULL,
    close_reason    TEXT NOT NULL,
    realized_pnl    NUMERIC(10,2) NOT NULL,
    contracts       INTEGER NOT NULL,
    legs            TEXT NOT NULL,
    entry_price     NUMERIC(10,4) NOT NULL,
    entry_time      TIMESTAMP NOT NULL,
    ticker          TEXT NOT NULL,
    strategy        TEXT NOT NULL
)
"""

_EQUITY_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time       TIMESTAMP NOT NULL,
    equity              NUMERIC(12,2) NOT NULL,
    unrealized_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
    realized_pnl_today  NUMERIC(10,2) NOT NULL DEFAULT 0,
    cumulative_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
    open_positions      INTEGER NOT NULL DEFAULT 0
)
"""

_SCAN_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_time       TIMESTAMP NOT NULL,
    outcome         TEXT NOT NULL,
    reason          TEXT,
    signal_data     TEXT,
    position_id     TEXT
)
"""

_TABLES = {
    "config": _CONFIG_DDL,
    "positions": _POSITIONS_DDL,
    "closed_trades": _CLOSED_DDL,
    "equity_snapshots": _EQUITY_DDL,
    "scan_activity": _SCAN_DDL,
}


def _is_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def _autoincrement_for_dialect(ddl: str, engine: Engine) -> str:
    """Postgres uses SERIAL / BIGSERIAL, SQLite uses AUTOINCREMENT on INTEGER PK."""
    if _is_sqlite(engine):
        return ddl
    # Translate SQLite-style PKs to Postgres SERIAL.
    return (
        ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
           .replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
    )


def _column_exists(conn, table: str, column: str, engine: Engine) -> bool:
    """Dialect-portable check for whether `table.column` exists."""
    if _is_sqlite(engine):
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    # Postgres
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return row is not None


def _ensure_position_overrides(conn, engine: Engine) -> None:
    """Idempotent column add for the manual-override flag introduced when
    the Adjust button shipped (2026-05-19). pt_override = TRUE means the
    scanner must keep the stored pt_target_pnl as-is instead of recomputing
    from the time-of-day ladder (relevant for iron_butterfly / iron_condor).
    """
    for bot in list_bots():
        t = bot_table(bot, "positions")
        if not _column_exists(conn, t, "pt_override", engine):
            conn.execute(text(
                f"ALTER TABLE {t} ADD COLUMN pt_override BOOLEAN NOT NULL DEFAULT FALSE"
            ))


def _ensure_config_entry_days(conn, engine: Engine) -> None:
    """Idempotent column add for the day-of-week entry gate (2026-05-24,
    introduced with MEADOW). entry_days is a CSV of lowercase weekday
    abbreviations (e.g. 'mon,fri'); empty string = no restriction. Existing
    bots get '' so their behavior is unchanged.
    """
    for bot in list_bots():
        t = bot_table(bot, "config")
        if not _column_exists(conn, t, "entry_days", engine):
            conn.execute(text(
                f"ALTER TABLE {t} ADD COLUMN entry_days TEXT NOT NULL DEFAULT ''"
            ))


def create_bot_tables(engine: Engine) -> None:
    """Create all per-bot tables and seed a config row per bot.

    Idempotent — safe to call on every startup.
    """
    with engine.begin() as conn:
        for bot in list_bots():
            for short, ddl in _TABLES.items():
                t = bot_table(bot, short)
                conn.execute(text(_autoincrement_for_dialect(ddl.format(t=t), engine)))
        _ensure_position_overrides(conn, engine)
        _ensure_config_entry_days(conn, engine)
        # Seed config rows — ON CONFLICT DO NOTHING means restart never
        # overwrites user-edited values.
        for bot in list_bots():
            d = BOT_REGISTRY[bot]
            defs = d["defaults"]
            t = bot_table(bot, "config")
            if _is_sqlite(engine):
                # SQLite uses INSERT OR IGNORE
                stmt = text(
                    f"INSERT OR IGNORE INTO {t} ("
                    "id, starting_capital, enabled, max_contracts, bp_pct, sd_mult, "
                    "front_dte, back_dte, pt_pct, sl_pct, entry_start_ct, entry_end_ct, "
                    "eod_close_ct, discord_alerts, delta_skew, use_gex_walls, entry_days"
                    ") VALUES ("
                    ":id, :sc, :en, :mc, :bp, :sd, :fdte, :bdte, :pt, :sl, "
                    ":es, :ee, :eod, :dc, :ds, :gw, :ed"
                    ")"
                )
            else:
                stmt = text(
                    f"INSERT INTO {t} ("
                    "id, starting_capital, enabled, max_contracts, bp_pct, sd_mult, "
                    "front_dte, back_dte, pt_pct, sl_pct, entry_start_ct, entry_end_ct, "
                    "eod_close_ct, discord_alerts, delta_skew, use_gex_walls, entry_days"
                    ") VALUES ("
                    ":id, :sc, :en, :mc, :bp, :sd, :fdte, :bdte, :pt, :sl, "
                    ":es, :ee, :eod, :dc, :ds, :gw, :ed"
                    ") ON CONFLICT (id) DO NOTHING"
                )
            conn.execute(stmt, {
                "id": 1,
                "sc": defs["starting_capital"],
                "en": defs["enabled"],
                "mc": defs["max_contracts"],
                "bp": defs["bp_pct"],
                "sd": defs["sd_mult"],
                "fdte": d["front_dte"],
                "bdte": d["back_dte"],
                "pt": defs["pt_pct"],
                "sl": defs["sl_pct"],
                "es": defs["entry_start_ct"],
                "ee": defs["entry_end_ct"],
                "eod": defs["eod_close_ct"],
                "dc": defs["discord_alerts"],
                "ds": defs["delta_skew"],
                "gw": defs["use_gex_walls"],
                "ed": defs.get("entry_days", ""),
            })


def load_config(engine: Engine, bot: str) -> dict[str, Any]:
    """Read the (single-row) config for `bot`."""
    t = bot_table(bot, "config")
    with engine.begin() as conn:
        row = conn.execute(text(f"SELECT * FROM {t} WHERE id = 1")).mappings().first()
    if row is None:
        raise RuntimeError(f"{t} not seeded — call create_bot_tables() first")
    return dict(row)
