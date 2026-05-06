"""Verify get_closed_trades supports since/until/before keyset cursor across all 10 perp/futures bots."""
import importlib
from unittest.mock import MagicMock
import pytest

from trading.agape_btc_perp.db import AgapeBtcPerpDatabase


BOT_DB_MODULES = [
    ("trading.agape_eth_perp.db", "AgapeEthPerpDatabase"),
    ("trading.agape_sol_perp.db", "AgapeSolPerpDatabase"),
    ("trading.agape_avax_perp.db", "AgapeAvaxPerpDatabase"),
    ("trading.agape_btc_perp.db", "AgapeBtcPerpDatabase"),
    ("trading.agape_xrp_perp.db", "AgapeXrpPerpDatabase"),
    ("trading.agape_doge_perp.db", "AgapeDogePerpDatabase"),
    ("trading.agape_shib_futures.db", "AgapeShibFuturesDatabase"),
    ("trading.agape_link_futures.db", "AgapeLinkFuturesDatabase"),
    ("trading.agape_ltc_futures.db", "AgapeLtcFuturesDatabase"),
    ("trading.agape_bch_futures.db", "AgapeBchFuturesDatabase"),
]


def _mock_conn(rows):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_closed_trades_passes_since_filter_to_sql(monkeypatch):
    db = AgapeBtcPerpDatabase.__new__(AgapeBtcPerpDatabase)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=10, since="2026-05-01T00:00:00+00:00")
    sql, params = cursor.execute.call_args[0]
    assert "close_time >= %s" in sql
    assert "2026-05-01T00:00:00+00:00" in params


def test_get_closed_trades_passes_until_filter_to_sql(monkeypatch):
    db = AgapeBtcPerpDatabase.__new__(AgapeBtcPerpDatabase)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=10, until="2026-05-06T00:00:00+00:00")
    sql, params = cursor.execute.call_args[0]
    assert "close_time <= %s" in sql
    assert "2026-05-06T00:00:00+00:00" in params


def test_get_closed_trades_keyset_cursor(monkeypatch):
    db = AgapeBtcPerpDatabase.__new__(AgapeBtcPerpDatabase)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(
        limit=10,
        before_close_time="2026-05-05T12:00:00+00:00",
        before_position_id="abc-123",
    )
    sql, params = cursor.execute.call_args[0]
    assert "close_time < %s OR" in sql
    assert "2026-05-05T12:00:00+00:00" in params
    assert "abc-123" in params


def test_get_closed_trades_no_filters_keeps_legacy_behavior(monkeypatch):
    db = AgapeBtcPerpDatabase.__new__(AgapeBtcPerpDatabase)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=50)
    sql, params = cursor.execute.call_args[0]
    assert "close_time >=" not in sql
    assert "close_time <=" not in sql
    assert params[-1] == 50


@pytest.mark.parametrize("modpath,clsname", BOT_DB_MODULES)
def test_all_bots_accept_new_kwargs(modpath, clsname, monkeypatch):
    mod = importlib.import_module(modpath)
    cls = getattr(mod, clsname)
    db = cls.__new__(cls)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(
        limit=5,
        since="2026-05-01T00:00:00+00:00",
        until="2026-05-06T00:00:00+00:00",
        before_close_time="2026-05-05T12:00:00+00:00",
        before_position_id="zzz",
    )
    sql, _params = cursor.execute.call_args[0]
    assert "ORDER BY close_time DESC, position_id ASC" in sql
