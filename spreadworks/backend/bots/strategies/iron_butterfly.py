"""BREEZE — Iron Butterfly 0DTE entry signal builder.

Pure function `build_iron_butterfly_signal(chain, config, equity)` returns
an `IronButterflySignal` dataclass or `None` if no setup passes the gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_CREDIT = 0.30
MAX_VIX = 28.0
MIN_FLIP_DIST = 1.0


@dataclass
class IronButterflySignal:
    ticker: str
    expiration: str
    body_strike: int
    long_put_strike: int
    long_call_strike: int
    short_call_mid: float
    short_put_mid: float
    long_call_mid: float
    long_put_mid: float
    credit: float
    contracts: int
    max_profit: float        # per contract, $
    max_loss: float          # per contract, $
    wing_width: int          # min(call_wing, put_wing) for collateral math; use long_*_strike for actual shape
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.short_call_mid},
            {"side": "short", "type": "put",  "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.short_put_mid},
            {"side": "long",  "type": "call", "strike": self.long_call_strike,
             "expiration": self.expiration, "entry_price": self.long_call_mid},
            {"side": "long",  "type": "put",  "strike": self.long_put_strike,
             "expiration": self.expiration, "entry_price": self.long_put_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find_option(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def build_iron_butterfly_signal(
    *,
    chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> IronButterflySignal | None:
    """Build a signal or return None.

    `diag` is an optional list that gets a single human-readable rejection
    reason appended when this function returns None. Used by the scanner
    to surface the gate that killed the cycle into scan_activity.reason.
    """
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(chain["spot"])
    vix = float(chain.get("vix", 0))
    if vix >= MAX_VIX:
        return _reject(f"vix_too_high: vix={vix:.2f} max={MAX_VIX}")

    gex = chain.get("gex") or {}
    flip = gex.get("flip_point")
    if flip is not None and abs(float(flip) - spot) < MIN_FLIP_DIST:
        return _reject(f"too_close_to_flip: spot={spot:.2f} flip={float(flip):.2f}")

    atm_straddle = float(chain.get("atm_straddle_mid", 0))
    sd_mult = float(config.get("sd_mult", 1.0))
    wing_distance = max(1, round(sd_mult * atm_straddle * 0.85))

    body = round(spot)
    long_call_strike = body + wing_distance
    long_put_strike = body - wing_distance

    if config.get("use_gex_walls"):
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        if cw is not None and body < cw < long_call_strike:
            long_call_strike = int(round(cw))
        if pw is not None and long_put_strike < pw < body:
            long_put_strike = int(round(pw))

    short_call = _find_option(chain, body, "call")
    short_put = _find_option(chain, body, "put")
    long_call = _find_option(chain, long_call_strike, "call")
    long_put = _find_option(chain, long_put_strike, "put")
    if not all([short_call, short_put, long_call, long_put]):
        return _reject(f"strike_missing: body={body} put_wing={long_put_strike} call_wing={long_call_strike}")

    sc_mid, sp_mid = _mid(short_call), _mid(short_put)
    lc_mid, lp_mid = _mid(long_call), _mid(long_put)
    credit = round(sc_mid + sp_mid - lc_mid - lp_mid, 4)
    if credit < MIN_CREDIT:
        return _reject(f"credit_too_low: credit={credit:.2f} min={MIN_CREDIT}")

    wing_width_call = long_call_strike - body
    wing_width_put = body - long_put_strike
    wing_width = min(wing_width_call, wing_width_put)
    max_profit_per = credit * 100.0
    max_loss_per = (wing_width - credit) * 100.0
    if max_loss_per <= 0:
        return _reject(f"negative_max_loss: wing={wing_width} credit={credit:.2f}")

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

    pt_pct = float(config.get("pt_pct", 0.30))
    sl_pct = float(config.get("sl_pct", 2.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_profit_per * contracts

    return IronButterflySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        body_strike=body,
        long_put_strike=long_put_strike,
        long_call_strike=long_call_strike,
        short_call_mid=sc_mid,
        short_put_mid=sp_mid,
        long_call_mid=lc_mid,
        long_put_mid=lp_mid,
        credit=credit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
