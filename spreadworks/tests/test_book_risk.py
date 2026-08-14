"""Book Risk endpoint — the money math, not the rendering.

These assert the four things the page would silently lie about if they were
wrong: that max_loss sums without a second contracts multiply, that remaining
downside is measured from today's mark rather than from entry, that fleet
drawdown is recomputed on the combined curve instead of summed, and that a
correlation is withheld when the paired sample is too small.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from backend.bots.db import bot_table, create_bot_tables
from backend import routes_book_risk as br


@pytest.fixture
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(eng)
    monkeypatch.setattr(br, "ENGINE", eng)
    return eng


def _config(eng, bot, *, capital=10000.0, enabled=True, bp_pct=0.10):
    with eng.begin() as c:
        c.execute(text(
            f"UPDATE {bot_table(bot, 'config')} SET starting_capital=:s, "
            "enabled=:e, bp_pct=:b WHERE id=1"
        ), {"s": capital, "e": enabled, "b": bp_pct})


def _open_position(eng, bot, *, pid, max_loss, mtm_pnl, contracts=1, when=None):
    when = when or datetime(2026, 8, 14, 10, 6)
    with eng.begin() as c:
        c.execute(text(
            f"INSERT INTO {bot_table(bot, 'positions')} "
            "(position_id, ticker, strategy, legs, entry_price, contracts, "
            " entry_time, status, mtm_value, mtm_pnl, mtm_updated_at, "
            " pt_target_pnl, sl_target_pnl, max_profit, max_loss, account_label) "
            "VALUES (:id,'SPY','x','[]',1.0,:n,:t,'OPEN',1.0,:p,:t,10,-10,:mp,:ml,'paper')"
        ), {"id": pid, "n": contracts, "t": when, "p": mtm_pnl,
            "mp": 100.0, "ml": max_loss})


def _closed(eng, bot, *, pid, pnl, on: date):
    with eng.begin() as c:
        c.execute(text(
            f"INSERT INTO {bot_table(bot, 'closed_trades')} "
            "(position_id, close_price, close_time, close_reason, realized_pnl, "
            " contracts, legs, entry_price, entry_time, ticker, strategy) "
            "VALUES (:id, 1.0, :t, 'EOD', :p, 1, '[]', 1.0, :t, 'SPY', 'x')"
        ), {"id": pid, "t": datetime.combine(on, datetime.min.time()).replace(hour=15),
            "p": pnl})


def _bot_row(payload, section, bot):
    return next(b for b in payload[section]["bots"] if b["bot"] == bot)


def test_defined_risk_sums_max_loss_without_re_multiplying_contracts(engine):
    """positions.max_loss is already total dollars for the whole position.

    The executor writes `signal.max_loss * signal.contracts`, so a 3-lot
    position storing 900 is $900 of risk, not $2,700. Multiplying again here
    would have overstated book risk by the contract count on every bot.
    """
    bot = br.list_bots()[0]
    _config(engine, bot)
    _open_position(engine, bot, pid="p1", max_loss=900.0, mtm_pnl=0.0, contracts=3)

    exp = _bot_row(br.get_book_risk(), "exposure", bot)
    assert exp["defined_risk"] == 900.0
    assert exp["contracts"] == 3


def test_remaining_downside_is_measured_from_todays_mark(engine):
    """A position already down $80 of a $400 floor has $320 left to give.

    Reporting the full $400 would double-count the loss that has already
    landed in equity_mtm.
    """
    bot = br.list_bots()[0]
    _config(engine, bot)
    _open_position(engine, bot, pid="p1", max_loss=400.0, mtm_pnl=-80.0)

    exp = _bot_row(br.get_book_risk(), "exposure", bot)
    assert exp["defined_risk"] == 400.0
    assert exp["unrealized_pnl"] == -80.0
    assert exp["remaining_downside"] == 320.0


def test_remaining_downside_floors_at_zero_when_already_past_max_loss(engine):
    """A mark worse than the structural floor must not produce negative risk."""
    bot = br.list_bots()[0]
    _config(engine, bot)
    _open_position(engine, bot, pid="p1", max_loss=400.0, mtm_pnl=-500.0)

    assert _bot_row(br.get_book_risk(), "exposure", bot)["remaining_downside"] == 0.0


def test_one_day_budget_breach_is_flagged(engine):
    """bp_pct x starting_capital is the one-day risk budget."""
    bot = br.list_bots()[0]
    _config(engine, bot, capital=10000.0, bp_pct=0.10)   # budget = $1,000
    _open_position(engine, bot, pid="p1", max_loss=1500.0, mtm_pnl=0.0)

    exp = _bot_row(br.get_book_risk(), "exposure", bot)
    assert exp["one_day_budget"] == 1000.0
    assert exp["over_budget"] is True


def test_fleet_drawdown_is_not_the_sum_of_per_bot_drawdowns(engine):
    """Two bots that bottom out on DIFFERENT days.

    A loses $500 on day 1 and recovers; B loses $500 on day 2. Each has a $500
    drawdown, but the book never sits $1,000 under water — it is only ever
    down $500 at a time. Summing per-bot drawdowns would report a book risk
    that never existed.
    """
    a, b = br.list_bots()[0], br.list_bots()[1]
    for bot in (a, b):
        _config(engine, bot, capital=10000.0)
    d1, d2, d3 = date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12)
    _closed(engine, a, pid="a1", pnl=-500.0, on=d1)
    _closed(engine, a, pid="a2", pnl=500.0, on=d2)
    _closed(engine, b, pid="b1", pnl=-500.0, on=d2)
    _closed(engine, b, pid="b2", pnl=500.0, on=d3)

    p = br.get_book_risk()
    assert _bot_row(p, "drawdown", a)["max_dd"] == -500.0
    assert _bot_row(p, "drawdown", b)["max_dd"] == -500.0
    # The book's worst point is one bot's loss, never both stacked.
    assert p["drawdown"]["fleet"]["max_dd"] == -500.0


def test_correlation_is_withheld_when_the_paired_sample_is_too_small(engine):
    """Six shared days is not evidence of anything — say so, don't print an r."""
    a, b = br.list_bots()[0], br.list_bots()[1]
    for bot in (a, b):
        _config(engine, bot)
    for i in range(6):
        day = date(2026, 8, 3) + timedelta(days=i)
        _closed(engine, a, pid=f"a{i}", pnl=100.0 * (i % 2 or -1), on=day)
        _closed(engine, b, pid=f"b{i}", pnl=100.0 * (i % 2 or -1), on=day)

    pair = next(p for p in br.get_book_risk()["concentration"]["correlation"]["pairs"]
                if {p["a"], p["b"]} == {a, b})
    assert pair["n_days"] == 6
    assert pair["underpowered"] is True
    assert pair["r"] is None


def test_correlation_is_reported_once_the_sample_is_powered(engine):
    """Two bots making the identical trade every day are r=1 — the exact
    'diversified fleet' illusion this block exists to break."""
    a, b = br.list_bots()[0], br.list_bots()[1]
    for bot in (a, b):
        _config(engine, bot)
    for i in range(br.MIN_PAIRED_DAYS + 5):
        day = date(2026, 6, 1) + timedelta(days=i)
        pnl = 100.0 if i % 3 else -250.0
        _closed(engine, a, pid=f"a{i}", pnl=pnl, on=day)
        _closed(engine, b, pid=f"b{i}", pnl=pnl, on=day)

    pair = next(p for p in br.get_book_risk()["concentration"]["correlation"]["pairs"]
                if {p["a"], p["b"]} == {a, b})
    assert pair["underpowered"] is False
    assert pair["r"] == pytest.approx(1.0, abs=1e-6)


def test_config_drift_is_detected_against_the_registry_defaults(engine):
    """The validated cell is BOT_REGISTRY[bot]['defaults']; the DB wins at
    runtime, so a DB edit away from it is exactly what must be surfaced."""
    bot = br.list_bots()[0]
    validated = br.BOT_REGISTRY[bot]["defaults"]["bp_pct"]
    _config(engine, bot, bp_pct=float(validated) + 0.15)

    row = _bot_row(br.get_book_risk(), "config_audit", bot)
    drift = {d["key"]: d for d in row["drift"]}
    assert "bp_pct" in drift
    assert drift["bp_pct"]["validated"] == pytest.approx(float(validated))
    assert row["clean"] is False


def test_clean_config_reports_no_drift(engine):
    bot = br.list_bots()[0]
    d = br.BOT_REGISTRY[bot]["defaults"]
    _config(engine, bot, capital=float(d["starting_capital"]),
            enabled=bool(d["enabled"]), bp_pct=float(d["bp_pct"]))

    assert _bot_row(br.get_book_risk(), "config_audit", bot)["clean"] is True


def test_every_block_carries_freshness_and_a_source(engine):
    """The whole point of the page: nothing renders without saying how old it
    is and what writes it."""
    _config(engine, br.list_bots()[0])
    p = br.get_book_risk()
    for section in ("exposure", "drawdown", "concentration", "config_audit"):
        f = p[section]["fresh"]
        assert "age_seconds" in f
        assert f["source"]
        assert f["cadence"]
    assert p["clock"]["next_scan_ct"]
    assert isinstance(p["clock"]["in_scan_window"], bool)


def test_mark_age_is_computed_server_side_in_ct(engine):
    """Ages must not depend on the browser parsing a naive CT string — that
    bug made a dead bot read 'just now' forever on BotDashboard."""
    bot = br.list_bots()[0]
    _config(engine, bot)
    stale_mark = datetime.now(br.CT).replace(tzinfo=None) - timedelta(minutes=42)
    _open_position(engine, bot, pid="p1", max_loss=400.0, mtm_pnl=0.0, when=stale_mark)

    exp = _bot_row(br.get_book_risk(), "exposure", bot)
    assert 2400 < exp["oldest_mark_age_seconds"] < 2640     # ~42 min


def test_a_timestamp_ahead_of_the_clock_is_flagged_not_shown_as_fresh(engine):
    """If the stored column is really UTC, a CT read lands ~5h in the future.

    Absorbed silently that becomes a tiny negative age formatting to "just
    now" — a dead bot reading freshly alive. It must trip clock_mismatch and
    mark the block stale instead.
    """
    bot = br.list_bots()[0]
    _config(engine, bot)
    future = datetime.now(br.CT).replace(tzinfo=None) + timedelta(hours=5)
    _open_position(engine, bot, pid="p1", max_loss=400.0, mtm_pnl=0.0, when=future)

    f = br.get_book_risk()["exposure"]["fresh"]
    assert f["age_seconds"] < 0
    assert f["clock_mismatch"] is True


def test_normal_ages_do_not_trip_the_clock_mismatch_flag(engine):
    bot = br.list_bots()[0]
    _config(engine, bot)
    _open_position(engine, bot, pid="p1", max_loss=400.0, mtm_pnl=0.0,
                   when=datetime.now(br.CT).replace(tzinfo=None) - timedelta(minutes=3))

    assert br.get_book_risk()["exposure"]["fresh"]["clock_mismatch"] is False


def test_next_scan_lands_inside_the_window_and_frozen_flag_agrees(engine):
    _config(engine, br.list_bots()[0])
    clock = br.get_book_risk()["clock"]
    nxt = datetime.strptime(clock["next_scan_ct"], "%Y-%m-%d %H:%M:%S")
    assert nxt.weekday() < 5
    assert br.SCAN_FIRST_HOUR <= nxt.hour <= br.SCAN_LAST_HOUR
    assert clock["frozen"] is not clock["in_scan_window"]


def test_a_bot_with_missing_tables_does_not_500_the_page(engine):
    """One broken bot must degrade to a listed 'unavailable' row, not take the
    whole risk page down."""
    bot = br.list_bots()[0]
    _config(engine, bot)
    with engine.begin() as c:
        c.execute(text(f"DROP TABLE {bot_table(br.list_bots()[1], 'positions')}"))

    p = br.get_book_risk()
    assert any(u["bot"] == br.list_bots()[1] for u in p["unavailable"])
    assert _bot_row(p, "exposure", bot)          # the healthy bot still renders
