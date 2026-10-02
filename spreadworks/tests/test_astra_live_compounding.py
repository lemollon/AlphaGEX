from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

import pytest

from backend.ember import astra_live as astra

def cfg(max_contracts: int = 2) -> astra.Config:
    return astra.Config(
        armed=True,
        dry_run=False,
        forward_gate_override=True,
        starting_equity=Decimal("500"),
        bp_pct=Decimal("0.25"),
        max_contracts=max_contracts,
        cash_reserve=Decimal("20"),
        max_drawdown=Decimal("80"),
        daily_loss=Decimal("80"),
        max_live_trades=20,
        max_trades_per_day=1,
        max_adverse_slippage=Decimal("0.01"),
        max_spread_pct=Decimal("0.15"),
        max_quote_age_seconds=90,
        max_signal_age_seconds=120,
        entry_start_ct=time(8, 31),
        entry_cutoff_ct=time(13, 55),
        hard_exit_ct=time(14, 25),
        exit_depth_wait_minutes=5,
        api_base="https://example.invalid",
        claude_model="haiku",
        claude_bin="claude",
    )


def state(
    *,
    completed: int = 0,
    equity: float = 500.0,
    high: float | None = None,
    max_dd: float = 0.0,
    promotion: str = "PROBATION",
) -> dict:
    realized = equity - 500.0
    return {
        "version": 1,
        "account": astra.ACCOUNT,
        "sleeve": {
            "starting_equity": 500.0,
            "realized_pnl": realized,
            "equity": equity,
            "high_water": equity if high is None else high,
            "max_drawdown": max_dd,
            "completed_trades": completed,
            "promotion_state": promotion,
            "promoted_at_ct": None,
            "daily_realized": {},
        },
        "processed_paper_positions": [],
        "history": [],
        "active": None,
        "kill_latched": False,
        "kill_reason": None,
    }


def now() -> datetime:
    return datetime(2026, 9, 18, 10, 0, tzinfo=astra.CT)


def probe(*, ask: float = 0.50, ask_size: int = 10, bp: float = 651.18) -> dict:
    return {
        "ok": True,
        "account_ok": True,
        "error": None,
        "message": "ok",
        "matching_open_order": False,
        "position_quantity": 0,
        "bid": ask - 0.02,
        "ask": ask,
        "ask_size": ask_size,
        "buying_power": bp,
        "quote_updated_at": now().isoformat(),
        "option_id": "opt-1",
    }


def signal(ask: float = 0.50) -> dict:
    return {"paper_entry_ask": ask}


def test_config_allows_only_validated_caps() -> None:
    cfg(1).validate()
    cfg(2).validate()
    with pytest.raises(ValueError, match="one or two"):
        cfg(3).validate()


def test_probation_stays_one_contract() -> None:
    snapshot = astra._sizing_snapshot(cfg(), state(completed=0))
    assert snapshot["target_contracts"] == 1
    assert snapshot["promoted"] is False


def test_promoted_equity_targets_two_and_throttles_at_eight_percent() -> None:
    promoted = state(
        completed=20, equity=1040.0, high=1040.0, max_dd=-58.4,
        promotion="PROMOTED",
    )
    snapshot = astra._sizing_snapshot(cfg(), promoted)
    assert snapshot["target_contracts"] == 2
    assert snapshot["throttled"] is False

    promoted["sleeve"].update(equity=1840.0, high_water=2000.0, max_drawdown=-160.0)
    snapshot = astra._sizing_snapshot(cfg(), promoted)
    assert snapshot["target_contracts"] == 1
    assert snapshot["throttled"] is True
    assert snapshot["promoted"] is True


def test_entry_guards_size_to_target_depth_and_broker_capacity() -> None:
    promoted = state(
        completed=20, equity=1040.0, high=1040.0, max_dd=-58.4,
        promotion="PROMOTED",
    )
    passed, reason, price, quantity = astra._entry_guards(
        cfg(), promoted, signal(), probe(), now())
    assert passed is True
    assert quantity == 2
    assert price == Decimal("0.5")
    assert "target=2" in reason

    passed, _, _, quantity = astra._entry_guards(
        cfg(), promoted, signal(), probe(ask_size=1), now())
    assert passed is True
    assert quantity == 1

    passed, reason, _, quantity = astra._entry_guards(
        cfg(), promoted, signal(), probe(bp=60.0), now())
    assert passed is False
    assert quantity == 0
    assert "no executable quantity" in reason


def test_exact_and_partial_fill_confirmation() -> None:
    full = {"cumulative_quantity": 2, "average_price": 0.50}
    partial = {"cumulative_quantity": 1, "average_price": 0.50}
    assert astra._fill_confirmed(full, 2) is True
    assert astra._fill_confirmed(partial, 2) is False
    assert astra._partial_fill_confirmed(partial, 2) is True

    active = {
        "entry": {"requested_qty": 2, "own_qty": 0},
        "status": "entry_pending",
    }
    adopted = astra._adopt_entry_fill(active, partial, now())
    assert adopted == 1
    assert active["entry"]["own_qty"] == 1
    assert active["entry"]["filled_qty"] == 1
    assert active["status"] == "open"


def test_partial_exit_chunks_preserve_exact_owned_quantity() -> None:
    active = {
        "entry": {"own_qty": 2, "filled_qty": 2},
        "exit": {"requested_qty": 2, "order_id": "sell-1"},
        "exit_fills": [],
    }
    first = {"cumulative_quantity": 1, "average_price": 0.80}
    remaining, total, average, filled = astra._record_exit_fill(active, first, now())
    assert (remaining, total, filled) == (1, 1, 1)
    assert average == Decimal("0.8")
    assert active["entry"]["own_qty"] == 1

    active["exit"] = {"requested_qty": 1, "order_id": "sell-2"}
    second = {"cumulative_quantity": 1, "average_price": 0.70}
    remaining, total, average, filled = astra._record_exit_fill(active, second, now())
    assert (remaining, total, filled) == (0, 2, 1)
    assert average == Decimal("0.75")


def test_terminal_partial_entry_is_adopted_from_own_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    result = {
        "cumulative_quantity": 1,
        "average_price": 0.50,
        "order_state": "cancelled",
    }
    monkeypatch.setattr(astra, "_order_reconcile", lambda *_args, **_kwargs: result)
    s = state()
    s["active"] = {
        "paper_position_id": "paper-1",
        "status": "entry_pending",
        "entry": {
            "requested_qty": 2,
            "own_qty": 0,
            "order_id": "buy-1",
            "placed_at_ct": now().isoformat(),
        },
    }
    message = astra._reconcile_entry(cfg(), s, now())
    assert "ENTRY PARTIAL FINAL" in message
    assert s["active"]["status"] == "open"
    assert s["active"]["entry"]["own_qty"] == 1
    assert s["kill_latched"] is False


def test_terminal_partial_exit_reconciles_remaining_broker_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    result = {
        "cumulative_quantity": 1,
        "average_price": 0.80,
        "order_state": "cancelled",
        "position_quantity": 1,
    }
    monkeypatch.setattr(astra, "_order_reconcile", lambda *_args, **_kwargs: result)
    s = state(completed=20, equity=1040.0, promotion="PROMOTED")
    s["active"] = {
        "paper_position_id": "paper-21",
        "status": "exit_pending",
        "entry": {"own_qty": 2, "filled_qty": 2, "fill_price": 0.50},
        "exit": {
            "requested_qty": 2,
            "order_id": "sell-1",
            "placed_at_ct": now().isoformat(),
        },
        "exit_fills": [],
    }
    message = astra._reconcile_exit(cfg(), s, now())
    assert "EXIT PARTIAL FINAL" in message
    assert s["active"]["status"] == "open"
    assert s["active"]["entry"]["own_qty"] == 1
    assert s["active"]["exit"] is None
    assert s["kill_latched"] is False


def test_terminal_partial_exit_kills_on_missing_remaining_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    result = {
        "cumulative_quantity": 1,
        "average_price": 0.80,
        "order_state": "cancelled",
        "position_quantity": 0,
    }
    monkeypatch.setattr(astra, "_order_reconcile", lambda *_args, **_kwargs: result)
    s = state(completed=20, equity=1040.0, promotion="PROMOTED")
    s["active"] = {
        "paper_position_id": "paper-21",
        "status": "exit_pending",
        "entry": {"own_qty": 2, "filled_qty": 2, "fill_price": 0.50},
        "exit": {
            "requested_qty": 2,
            "order_id": "sell-1",
            "placed_at_ct": now().isoformat(),
        },
        "exit_fills": [],
    }
    message = astra._reconcile_exit(cfg(), s, now())
    assert "MISMATCH" in message
    assert s["kill_latched"] is True
    assert s["active"]["entry"]["own_qty"] == 2


def test_trade_twenty_promotes_and_two_contract_pnl_is_quantity_aware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    s = state(completed=19, equity=500.0, high=500.0, max_dd=-58.4)
    s["active"] = {
        "paper_position_id": "paper-20",
        "entry": {"fill_price": 0.50, "filled_qty": 1, "own_qty": 0},
        "exit": {},
        "exit_fills": [{"quantity": 1, "average_price": 5.90}],
    }
    message = astra._complete_trade(cfg(), s, now(), Decimal("5.90"), 1)
    assert s["sleeve"]["completed_trades"] == 20
    assert s["sleeve"]["promotion_state"] == "PROMOTED"
    assert s["kill_latched"] is False
    assert "promotion=PROMOTED" in message

    s = state(
        completed=20, equity=1040.0, high=1040.0, max_dd=-58.4,
        promotion="PROMOTED",
    )
    s["active"] = {
        "paper_position_id": "paper-21",
        "entry": {"fill_price": 0.50, "filled_qty": 2, "own_qty": 0},
        "exit": {},
        "exit_fills": [{"quantity": 2, "average_price": 0.75}],
    }
    astra._complete_trade(cfg(), s, now(), Decimal("0.75"), 2)
    assert s["sleeve"]["realized_pnl"] == pytest.approx(588.6)
    assert s["sleeve"]["equity"] == pytest.approx(1088.6)


def test_post_gate_entry_allowed_and_failed_gate_blocked() -> None:
    status = {
        "enabled": True,
        "forward_gate": {"paper_only": True, "live_money_authorized": False},
    }
    promoted = state(
        completed=20, equity=1040.0, high=1040.0, max_dd=-58.4,
        promotion="PROMOTED",
    )
    allowed, reason = astra._entry_allowed(cfg(), promoted, now(), status)
    assert allowed is True
    assert "target_qty=2" in reason

    failed = state(
        completed=20, equity=450.0, high=500.0, max_dd=-85.0,
        promotion="FAILED",
    )
    allowed, reason = astra._entry_allowed(cfg(), failed, now(), status)
    assert allowed is False
    assert "not passed" in reason


def test_trade_twenty_failed_gate_latches_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    s = state(completed=19, equity=500.0, high=500.0, max_dd=-70.0)
    s["active"] = {
        "paper_position_id": "paper-20",
        "entry": {"fill_price": 0.50, "filled_qty": 1, "own_qty": 0},
        "exit": {},
        "exit_fills": [{"quantity": 1, "average_price": 0.00}],
    }
    astra._complete_trade(cfg(), s, now(), Decimal("0.00"), 1)
    assert s["sleeve"]["promotion_state"] == "FAILED"
    assert s["kill_latched"] is True
    assert "promotion failed" in s["kill_reason"]


def test_operator_alerts_include_skips_and_partial_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(astra, "_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        astra, "_notify", lambda tone, headline: alerts.append((tone, headline)))

    astra._log(now(), "ENTRY", "NO-OP insufficient BP; paper_id=p1")
    astra._log(now(), "FILLCHECK", "ENTRY PARTIAL FINAL own_qty=1/2 avg=0.50")
    astra._log(now(), "IDLE", "armed; no fresh ASTRA-3 paper position")

    assert [tone for tone, _ in alerts] == ["warn", "trade"]
