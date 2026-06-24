"""TIDE — Double Calendar entry signal builder.

Sells 1DTE strangle (put + call OTM), buys 14DTE strangle at SAME strikes.
Vega-positive, mildly theta-positive when back IV > front IV.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_DEBIT = 0.20
# Cap on debit ($) per contract. Sized for the underlying — SPY at $500
# yields ~5.40 typical 14DTE-vs-1DTE; at $733 (current) we see ~9.95
# legitimately. 12.0 leaves headroom without going into broken-chain
# territory. BP sizing (`max_loss_per <= equity * bp_pct`) still
# protects against oversized positions.
MAX_DEBIT = 12.0
MAX_VIX = 30.0
# Required back-vs-front IV edge in vol points (0.01 = 1 vp). Positive
# values demand contango (back richer than front); negative values allow
# trades in backwardation.
#
# Historical levels:
#   1.0 — original strict gate (rejected ~every flat-IV day on SPY).
#   0.0 — CURRENT (set 2026-06-24 after the TIDE warehouse backtest). The
#         "contango = edge" thesis is NOT supported: an EOD backtest of 817 days
#         showed the 0.3 gate HALVES the trade count and does NOT improve avg
#         P&L; SPY 1DTE/14DTE is normally backwardated (median -1.6vp) and the
#         BACKWARDATION days were the best performers (the structure's P&L comes
#         from the front leg decaying to intrinsic, not the IV spread). So we
#         drop the contango requirement to a mild "back not cheaper than front"
#         floor (0.0). NOTE: the EOD data actually favored trading every day;
#         0.0 is the conservative choice pending a real-fill morning-entry test.
#   0.3 — the (refuted) contango gate. -10 — demo "always trade".
MIN_VEGA_EDGE = 0.0


@dataclass
class DoubleCalendarSignal:
    ticker: str
    front_expiration: str
    back_expiration: str
    call_strike: int
    put_strike: int
    short_front_call_mid: float
    short_front_put_mid: float
    long_back_call_mid: float
    long_back_put_mid: float
    debit: float
    contracts: int
    max_profit: float        # per contract, $ (target reference = debit)
    max_loss: float          # per contract, $ (entire debit)
    pt_target_pnl: float
    sl_target_pnl: float

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.call_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_call_mid},
            {"side": "short", "type": "put",  "strike": self.put_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_put_mid},
            {"side": "long",  "type": "call", "strike": self.call_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_call_mid},
            {"side": "long",  "type": "put",  "strike": self.put_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_put_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _strikes_for(chain: dict, opt_type: str) -> list[int]:
    """Sorted list of unique int strikes for a given option type."""
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


def _nearest(strikes: list[int], target: int) -> int | None:
    """Pick the strike in `strikes` closest to `target`."""
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def _nearest_in_intersection(front_chain: dict, back_chain: dict,
                             opt_type: str, target: int) -> int | None:
    """Find the closest strike to `target` that exists in BOTH chains for
    the given option type. Returns None if no overlap."""
    front_set = set(_strikes_for(front_chain, opt_type))
    back_set = set(_strikes_for(back_chain, opt_type))
    common = sorted(front_set & back_set)
    return _nearest(common, target)


def build_double_calendar_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    call_strike_override: int | None = None,
    put_strike_override: int | None = None,
    diag: list[str] | None = None,
) -> DoubleCalendarSignal | None:
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

    # Strike placement = spot +/- strike_mult * implied_move. A warehouse
    # backtest (2026-06-24) showed the default k=1.0 places the strikes too
    # close: every >1-straddle move blows through the short before the back
    # leg's vega compensates, so ALL the loss came from move days. Widening to
    # ~1.5 flips move days from the loss engine into a profit contributor and
    # cuts the catastrophic tail 2-3x (see TIDE registry strike_mult).
    strike_mult = float(config.get("strike_mult", 1.0))
    target_call = call_strike_override if call_strike_override is not None else round(spot + strike_mult * implied_move)
    target_put = put_strike_override if put_strike_override is not None else round(spot - strike_mult * implied_move)

    # Snap to the nearest strike that exists in BOTH the front and back
    # chain — DC requires the same strike on both legs, and back-month
    # SPY chains are often $5-spaced while the front is $1-spaced.
    call_strike = _nearest_in_intersection(front_chain, back_chain, "call", target_call)
    put_strike = _nearest_in_intersection(front_chain, back_chain, "put", target_put)
    if call_strike is None or put_strike is None:
        return _reject(f"no_overlapping_strikes: target_call={target_call} target_put={target_put}")

    sfc = _find(front_chain, call_strike, "call")
    sfp = _find(front_chain, put_strike, "put")
    lbc = _find(back_chain, call_strike, "call")
    lbp = _find(back_chain, put_strike, "put")
    if not all([sfc, sfp, lbc, lbp]):
        return _reject(
            f"strike_missing_after_snap: call={call_strike} put={put_strike}"
        )

    sfc_m, sfp_m = _mid(sfc), _mid(sfp)
    lbc_m, lbp_m = _mid(lbc), _mid(lbp)
    debit = round((lbc_m + lbp_m) - (sfc_m + sfp_m), 4)
    if debit < MIN_DEBIT or debit > MAX_DEBIT:
        return _reject(f"debit_out_of_range: debit={debit:.2f} min={MIN_DEBIT} max={MAX_DEBIT}")

    max_loss_per = debit * 100.0
    max_profit_per = debit * 100.0  # PT reference: % of debit

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

    return DoubleCalendarSignal(
        ticker=front_chain.get("ticker", "SPY"),
        front_expiration=front_chain["expiration"],
        back_expiration=back_chain["expiration"],
        call_strike=call_strike,
        put_strike=put_strike,
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
    )
