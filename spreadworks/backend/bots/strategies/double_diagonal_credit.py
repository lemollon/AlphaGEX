"""MEADOW — Credit Double Diagonal entry signal builder.

The credit-side sibling of DRIFT. Sell a near-dated (front) strangle close to
the money and buy a slightly-longer-dated (back) strangle $5 further OTM, for a
net CREDIT. Short vega, positive theta, negative gamma — the inverse Greek
profile of DRIFT's debit double diagonal.

Risk is iron-condor-shaped and sized conservatively: max_loss is the wing width
minus the credit. The real loss is smaller because the long legs retain time
value in a later expiration, so the IC worst case over-estimates risk — safe
for buying-power sizing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .double_calendar import _mid, _find, _strikes_for, _nearest

# Defaults (overridable via config).
MIN_CREDIT = 0.25       # $ per contract — reject thinner credits
MAX_VIX = 32.0          # matches FLOW
SPREAD_WIDTH = 5        # $ — long legs this far OTM from the shorts


@dataclass
class DoubleDiagonalCreditSignal:
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
    credit: float
    contracts: int
    wing_width: int
    max_profit: float
    max_loss: float
    pt_target_pnl: float
    sl_target_pnl: float

    def legs(self) -> list[dict[str, Any]]:
        # Short (front) legs first so the scanner keys EOD/expiration logic off
        # the front expiration (legs[0]).
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


def build_double_diagonal_credit_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> DoubleDiagonalCreditSignal | None:
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return _reject(f"vix_too_high: vix={vix:.2f} max={MAX_VIX}")

    straddle = float(front_chain.get("atm_straddle_mid", 0))
    if straddle <= 0:
        return _reject(f"implied_move_zero: atm_straddle_mid={straddle}")

    sd_mult = float(config.get("sd_mult", 1.0))
    sd_distance = sd_mult * straddle
    target_short_put = round(spot - sd_distance)
    target_short_call = round(spot + sd_distance)

    front_calls = _strikes_for(front_chain, "call")
    front_puts = _strikes_for(front_chain, "put")
    short_call_strike = _nearest(front_calls, target_short_call)
    short_put_strike = _nearest(front_puts, target_short_put)
    if short_call_strike is None or short_put_strike is None:
        return _reject(f"front_chain_empty: calls={len(front_calls)} puts={len(front_puts)}")
    if short_call_strike <= short_put_strike:
        return _reject(f"shorts_crossed: sp={short_put_strike} sc={short_call_strike}")

    # Long strikes target `spread_width` further OTM than the shorts. Snap to
    # the nearest available BACK strike in the OTM direction (call up, put down).
    wing = int(config.get("spread_width", SPREAD_WIDTH) or SPREAD_WIDTH)
    back_calls = _strikes_for(back_chain, "call")
    back_puts = _strikes_for(back_chain, "put")
    target_long_call = short_call_strike + wing
    target_long_put = short_put_strike - wing
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
    # Sell the front shorts, buy the back longs → net credit.
    credit = round((sfc_m + sfp_m) - (lbc_m + lbp_m), 4)
    min_credit = float(config.get("min_credit", MIN_CREDIT))
    if credit < min_credit:
        return _reject(f"credit_too_low: credit={credit:.2f} min={min_credit}")

    put_wing = short_put_strike - long_put_strike
    call_wing = long_call_strike - short_call_strike
    wing_width = max(put_wing, call_wing)
    max_profit_per = credit * 100.0
    max_loss_per = (wing_width - credit) * 100.0
    if max_loss_per <= 0:
        return _reject(f"negative_max_loss: wing={wing_width} credit={credit:.2f}")

    bp_pct = float(config.get("bp_pct", 0.50))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = (
        max(0, raw_contracts)
        if raw_max_contracts <= 0
        else max(0, min(raw_max_contracts, raw_contracts))
    )
    if contracts < 1:
        return _reject(
            f"sizing_below_one: equity={equity:.0f} bp_pct={bp_pct} max_loss_per={max_loss_per:.0f}"
        )

    # Credit convention: PT/SL are fractions of the collected credit (max_profit).
    pt_pct = float(config.get("pt_pct", 0.50))
    sl_pct = float(config.get("sl_pct", 1.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_profit_per * contracts

    return DoubleDiagonalCreditSignal(
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
        credit=credit,
        contracts=contracts,
        wing_width=wing_width,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
