from sqlalchemy import create_engine, inspect, text

from backend.bots.db import bot_table, create_bot_tables


def test_bot_table_naming():
    assert bot_table("frost", "config") == "frost_config"
    assert bot_table("tide", "positions") == "tide_positions"
    assert bot_table("drift", "scan_activity") == "drift_scan_activity"


def test_bot_table_rejects_unknown_bot():
    import pytest
    with pytest.raises(ValueError):
        bot_table("hacker", "positions")


def test_create_bot_tables_creates_all_15():
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    insp = inspect(engine)
    names = set(insp.get_table_names())
    for bot in ["frost", "tide", "drift"]:
        for tbl in ["config", "positions", "closed_trades",
                    "equity_snapshots", "scan_activity"]:
            assert f"{bot}_{tbl}" in names, f"missing {bot}_{tbl}"


def test_create_bot_tables_seeds_config():
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    with engine.begin() as conn:
        for bot in ["frost", "tide", "drift"]:
            row = conn.execute(
                text(f"SELECT pt_pct, sl_pct, enabled FROM {bot}_config")
            ).fetchone()
            assert row is not None, f"{bot}_config not seeded"
            assert row.enabled is False or row.enabled == 0


def test_create_bot_tables_does_not_overwrite_existing_config():
    """Memory rule: never auto-reset config values on restart."""
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE frost_config SET pt_pct = 0.99, max_contracts = 99"
        ))
    # Run migration a second time
    create_bot_tables(engine)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT pt_pct, max_contracts FROM frost_config")
        ).fetchone()
        assert float(row.pt_pct) == 0.99
        assert row.max_contracts == 99
