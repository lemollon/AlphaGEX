"""TIDE — Double Calendar entry signal builder.

Sells 1DTE strangle (put + call OTM), buys 14DTE strangle at SAME strikes.
Vega-positive, mildly theta-positive when back IV > front IV.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_DEBIT = 0.20
MAX_DEBIT = 6.0   # raised from 5.0: realistic 14DTE-vs-1DTE on $500 SPY yields ~5.40
MAX_VIX = 30.0
MIN_VEGA_EDGE = 1.0  # back_iv - front_iv in vol points (0.01 = 1 vp)


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


def build_double_calendar_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    call_strike_override: int | None = None,
    put_strike_override: int | None = None,
) -> DoubleCalendarSignal | None:
    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return None

    front_iv = float(front_chain.get("iv_atm", 0))
    back_iv = float(back_chain.get("iv_atm", 0))
    # vol-point gap (0.01 per vp)
    if (back_iv - front_iv) < (MIN_VEGA_EDGE / 100.0):
        return None

    implied_move = float(front_chain.get("atm_straddle_mid", 0))
    if implied_move <= 0:
        return None

    call_strike = call_strike_override if call_strike_override is not None else round(spot + implied_move)
    put_strike = put_strike_override if put_strike_override is not None else round(spot - implied_move)

    sfc = _find(front_chain, call_strike, "call")
    sfp = _find(front_chain, put_strike, "put")
    lbc = _find(back_chain, call_strike, "call")
    lbp = _find(back_chain, put_strike, "put")
    if not all([sfc, sfp, lbc, lbp]):
        return None

    sfc_m, sfp_m = _mid(sfc), _mid(sfp)
    lbc_m, lbp_m = _mid(lbc), _mid(lbp)
    debit = round((lbc_m + lbp_m) - (sfc_m + sfp_m), 4)
    if debit < MIN_DEBIT or debit > MAX_DEBIT:
        return None

    max_loss_per = debit * 100.0
    max_profit_per = debit * 100.0  # PT reference: % of debit

    bp_pct = float(config.get("bp_pct", 0.10))
    max_contracts = int(config.get("max_contracts", 1))
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, min(max_contracts, raw_contracts))
    if contracts < 1:
        return None

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
