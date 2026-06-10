"""UNDERTOW — single-leg long-call dip-buy entry signal builder.

Buys an ATM call when an underlying pulls back >= D% from its rolling
N-day reference high, confirmed oversold (RSI) and still in an uptrend
(above its SMA). Debit strategy: entry_price = the call mid (premium
paid); max loss = full premium. Mirrors the debit plumbing of RIVER
(long_butterfly) so the executor / MTM / close paths work unchanged.

All numeric defaults are STARTING HYPOTHESES to tune from the paper
track record — the entry edge is unproven and unbacktested (see spec §0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


def closed_bars(history: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Return daily bars strictly BEFORE `today`, sorted ascending by date.

    Drops today's partial/in-progress bar so the reference high and
    indicators are computed only from completed sessions.
    """
    bars = [b for b in history if str(b["date"]) < today.isoformat()]
    return sorted(bars, key=lambda b: str(b["date"]))


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values; None if too few."""
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(float(v) for v in window) / period


def rsi(values: list[float], period: int) -> float | None:
    """Wilder-style RSI over `period` using simple gain/loss averages.

    Needs at least `period + 1` values. Returns 0..100, or None if too few.
    All-gains -> 100, all-losses -> 0.
    """
    if len(values) < period + 1 or period <= 0:
        return None
    deltas = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    window = deltas[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 4)


# Starting-hypothesis params (spec §2/§3). Overridden per-bot via the
# registry meta "params" dict; this is the in-code default/fallback.
DEFAULT_PARAMS: dict[str, Any] = {
    "lookback_n": 5,
    "dip_threshold": 0.03,
    "use_rsi_confirm": True,
    "rsi_period": 2,
    "rsi_max": 10,
    "use_trend_gate": True,
    "sma_period": 20,
    "max_spread_pct": 0.15,
    "min_option_price": 0.20,
    "earnings_exclude_days": 3,
    "hold_days": 2,
}


@dataclass
class DipBuySignal:
    ticker: str
    expiration: str
    strike: int
    call_mid: float
    debit: float             # per contract premium paid (== call_mid)
    contracts: int
    max_profit: float        # per contract, $ (cosmetic: PT target)
    max_loss: float          # per contract, $ (== debit * 100)
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total
    # Dip context — journaled, and used by the scanner to pick the deepest dip.
    dip_pct: float
    reference_high: float
    rsi_value: float | None

    def legs(self) -> list[dict[str, Any]]:
        return [{
            "side": "long", "type": "call", "strike": self.strike,
            "expiration": self.expiration, "entry_price": self.call_mid,
        }]


def _nearest_call(chain: dict, spot: float) -> dict | None:
    calls = [o for o in chain["options"] if o["type"] == "call"]
    if not calls:
        return None
    return min(calls, key=lambda o: abs(float(o["strike"]) - spot))


def build_dip_buy_signal(
    *,
    chain: dict[str, Any],
    history: list[dict[str, Any]],
    today: date,
    params: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> DipBuySignal | None:
    """Build a single-leg long-call dip-buy signal or return None.

    `diag` (optional) collects ONE rejection reason for scan_activity.reason.
    Earnings exclusion is enforced by the scanner (needs the calendar), not here.
    """
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    n = int(params["lookback_n"])
    sma_period = int(params["sma_period"])
    rsi_period = int(params["rsi_period"])
    need = max(n, sma_period, rsi_period + 1)

    bars = closed_bars(history, today)
    if len(bars) < need:
        return _reject(f"insufficient_history: have={len(bars)} need={need}")

    highs = [float(b["high"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    spot = float(chain["spot"])
    if spot <= 0:
        return _reject("missing_spot")

    reference_high = max(highs[-n:])
    if reference_high <= 0:
        return _reject("bad_reference_high")
    dip_pct = (reference_high - spot) / reference_high
    if dip_pct < float(params["dip_threshold"]):
        return _reject(
            f"dip_too_shallow: dip={dip_pct:.3f} min={float(params['dip_threshold']):.3f}"
        )

    rsi_value = rsi(closes, rsi_period)
    if bool(params.get("use_rsi_confirm")):
        if rsi_value is None or rsi_value >= float(params["rsi_max"]):
            return _reject(f"rsi_not_oversold: rsi={rsi_value} max={params['rsi_max']}")

    if bool(params.get("use_trend_gate")):
        sma_value = sma(closes, sma_period)
        if sma_value is None or spot <= sma_value:
            return _reject(f"below_sma_downtrend: spot={spot:.2f} sma={sma_value}")

    call = _nearest_call(chain, spot)
    if call is None:
        return _reject("no_call_strikes")
    bid = float(call["bid"] or 0)
    ask = float(call["ask"] or 0)
    mid = (bid + ask) / 2.0
    if mid < float(params["min_option_price"]):
        return _reject(f"price_too_low: mid={mid:.2f} min={params['min_option_price']}")
    if mid <= 0 or (ask - bid) / mid > float(params["max_spread_pct"]):
        spr = (ask - bid) / mid if mid > 0 else 999
        return _reject(f"spread_too_wide: spread_pct={spr:.3f} max={params['max_spread_pct']}")

    debit = round(mid, 4)
    max_loss_per = debit * 100.0
    bp_pct = float(config.get("bp_pct", 0.02))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = (
        max(0, raw_contracts)
        if raw_max_contracts <= 0
        else max(0, min(raw_max_contracts, raw_contracts))
    )
    if contracts < 1:
        return _reject(
            f"sizing_below_one: equity={equity:.0f} bp_pct={bp_pct} "
            f"max_loss_per={max_loss_per:.0f}"
        )

    pt_pct = float(config.get("pt_pct", 0.40))
    sl_pct = float(config.get("sl_pct", 0.50))
    pt_target = pt_pct * max_loss_per * contracts
    sl_target = sl_pct * max_loss_per * contracts
    max_profit_per = pt_pct * max_loss_per  # cosmetic headline

    return DipBuySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        strike=int(call["strike"]),
        call_mid=debit,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=round(pt_target, 2),
        sl_target_pnl=round(sl_target, 2),
        dip_pct=round(dip_pct, 4),
        reference_high=round(reference_high, 4),
        rsi_value=rsi_value,
    )
