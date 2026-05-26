"""DRIFT — Double Diagonal entry signal builder.

Identical to Double Calendar but the long-back strikes are shifted 1 OTM
relative to the short-front strikes (call up, put down). Optional
`delta_skew` config knob shifts BOTH back strikes by N (bullish if +).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .double_calendar import (
    MIN_DEBIT, MAX_DEBIT, MAX_VIX, MIN_VEGA_EDGE, _mid, _find,
    _strikes_for, _nearest,
)


@dataclass
class DoubleDiagonalSignal:
    ticker: str
    front_expiration: str
    back_expiration: str
    short_call_strike: int
    short_put_strike: int
    long_call_strike: int
    long_put_strike: int
    short_front_call_mid: float
    short_front_put_mid: float
    long_back_call_mid: float
    long_back_put_mid: float
    debit: float
    contracts: int
    max_profit: float
    max_loss: float
    pt_target_pnl: float
    sl_target_pnl: float
    delta_skew: int

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.short_call_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_call_mid},
            {"side": "short", "type": "put",  "strike": self.short_put_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_put_mid},
            {"side": "long",  "type": "call", "strike": self.long_call_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_call_mid},
            {"side": "long",  "type": "put",  "strike": self.long_put_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_put_mid},
        ]


def build_double_diagonal_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> DoubleDiagonalSignal | None:
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return _reject(f"vix_too_high: vix={vix:.2f} max={MAX_VIX}")

    front_iv = float(front_chain.get("iv_atm", 0))
    back_iv = float(back_chain.get("iv_atm", 0))
    edge_vp = (back_iv - front_iv) * 100.0
    min_edge = float(config.get("min_vega_edge", MIN_VEGA_EDGE))
    if edge_vp < min_edge:
        return _reject(
            f"vega_edge_below_min: front_iv={front_iv:.4f} back_iv={back_iv:.4f} "
            f"edge={edge_vp:.2f}vp min={min_edge}vp"
        )

    implied_move = float(front_chain.get("atm_straddle_mid", 0))
    if implied_move <= 0:
        return _reject(f"implied_move_zero: atm_straddle_mid={implied_move}")

    skew = int(config.get("delta_skew", 0))
    target_short_call = round(spot + implied_move)
    target_short_put = round(spot - implied_move)

    # Snap shorts to nearest available strike in the FRONT chain. The
    # front month (1DTE SPY) is usually $1-spaced so snap = exact.
    front_calls = _strikes_for(front_chain, "call")
    front_puts = _strikes_for(front_chain, "put")
    short_call_strike = _nearest(front_calls, target_short_call)
    short_put_strike = _nearest(front_puts, target_short_put)
    if short_call_strike is None or short_put_strike is None:
        return _reject(f"front_chain_empty: calls={len(front_calls)} puts={len(front_puts)}")

    # Long strikes target 1 OTM from the shorts (+ delta_skew). Back-month
    # SPY chains are typically $5-spaced, so snap to the nearest available
    # back strike in the OTM direction we want — call: just above the short,
    # put: just below.
    back_calls = _strikes_for(back_chain, "call")
    back_puts = _strikes_for(back_chain, "put")
    target_long_call = short_call_strike + 1 + skew
    target_long_put = short_put_strike - 1 + skew

    long_call_candidates = [s for s in back_calls if s >= target_long_call] or back_calls
    long_put_candidates = [s for s in back_puts if s <= target_long_put] or back_puts
    long_call_strike = _nearest(long_call_candidates, target_long_call)
    long_put_strike = _nearest(long_put_candidates, target_long_put)
    if long_call_strike is None or long_put_strike is None:
        return _reject(f"back_chain_empty: calls={len(back_calls)} puts={len(back_puts)}")

    sfc = _find(front_chain, short_call_strike, "call")
    sfp = _find(front_chain, short_put_strike, "put")
    lbc = _find(back_chain, long_call_strike, "call")
    lbp = _find(back_chain, long_put_strike, "put")
    if not all([sfc, sfp, lbc, lbp]):
        return _reject(
            f"strike_missing_after_snap: short_call={short_call_strike} short_put={short_put_strike} "
            f"long_call={long_call_strike} long_put={long_put_strike}"
        )

    sfc_m, sfp_m = _mid(sfc), _mid(sfp)
    lbc_m, lbp_m = _mid(lbc), _mid(lbp)
    debit = round((lbc_m + lbp_m) - (sfc_m + sfp_m), 4)
    if debit < MIN_DEBIT or debit > MAX_DEBIT:
        return _reject(f"debit_out_of_range: debit={debit:.2f} min={MIN_DEBIT} max={MAX_DEBIT}")

    max_loss_per = (debit + 1.0) * 100.0  # debit + 1-strike width worst case
    max_profit_per = debit * 100.0

    bp_pct = float(config.get("bp_pct", 0.10))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    # max_contracts=0 means "no ceiling, size by BP alone" (matches FLOW/MEADOW).
    contracts = (
        max(0, raw_contracts)
        if raw_max_contracts <= 0
        else max(0, min(raw_max_contracts, raw_contracts))
    )
    if contracts < 1:
        return _reject(f"sizing_below_one: equity={equity:.0f} bp_pct={bp_pct} max_loss_per={max_loss_per:.0f}")

    pt_pct = float(config.get("pt_pct", 0.50))
    sl_pct = float(config.get("sl_pct", 1.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_loss_per * contracts

    return DoubleDiagonalSignal(
        ticker=front_chain.get("ticker", "SPY"),
        front_expiration=front_chain["expiration"],
        back_expiration=back_chain["expiration"],
        short_call_strike=short_call_strike,
        short_put_strike=short_put_strike,
        long_call_strike=long_call_strike,
        long_put_strike=long_put_strike,
        short_front_call_mid=sfc_m,
        short_front_put_mid=sfp_m,
        long_back_call_mid=lbc_m,
        long_back_put_mid=lbp_m,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
        delta_skew=skew,
    )
