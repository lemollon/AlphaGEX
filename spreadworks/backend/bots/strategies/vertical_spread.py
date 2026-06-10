"""Two-leg vertical-spread builders (greeks-free, % of spot).

Four kinds:
  bull_call_spread / bear_put_spread  -> DEBIT (not in CREDIT_STRATEGIES)
  bull_put_spread  / bear_call_spread -> CREDIT (in CREDIT_STRATEGIES)

Leg `side` follows the executor's sign convention (short +mid, long -mid). Strikes
are chosen by % of spot and snapped to available strikes. All defaults are starting
hypotheses (spec §0).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

DEFAULT_VERTICAL_PARAMS: dict[str, Any] = {
    "spread_pct": 0.04,
    "short_otm_pct": 0.03,
    "max_spread_pct": 0.15,
    "min_option_price": 0.20,
    "min_credit": 0.20,
}

DEBIT_KINDS = {"bull_call_spread", "bear_put_spread"}
CREDIT_KINDS = {"bull_put_spread", "bear_call_spread"}


@dataclass
class VerticalSignal:
    kind: str
    ticker: str
    expiration: str
    contracts: int
    max_profit: float
    max_loss: float
    pt_target_pnl: float
    sl_target_pnl: float
    _legs: list[dict[str, Any]]
    width: int
    net: float = 0.0
    is_credit: bool = False

    def legs(self) -> list[dict[str, Any]]:
        return list(self._legs)


def _avail(chain, opt_type):
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


def _nearest(strikes, target):
    return min(strikes, key=lambda s: abs(s - target)) if strikes else None


def _find(chain, strike, opt_type):
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _mid(o):
    return (float(o["bid"] or 0) + float(o["ask"] or 0)) / 2.0


def _spread_ok(o, params):
    bid = float(o["bid"] or 0); ask = float(o["ask"] or 0)
    mid = (bid + ask) / 2.0
    if mid < float(params["min_option_price"]):
        return False, f"price_too_low: mid={mid:.2f}"
    if mid <= 0 or (ask - bid) / mid > float(params["max_spread_pct"]):
        return False, "spread_too_wide"
    return True, ""


def build_vertical_signal(*, kind, chain, config, equity, params, diag=None):
    def _reject(msg):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(chain["spot"])
    if spot <= 0:
        return _reject("missing_spot")
    opt_type = "call" if kind in ("bull_call_spread", "bear_call_spread") else "put"
    strikes = _avail(chain, opt_type)
    if not strikes:
        return _reject("no_strikes")
    spread_w = float(params["spread_pct"]) * spot
    otm = float(params["short_otm_pct"]) * spot

    if kind == "bull_call_spread":
        near = _nearest(strikes, round(spot)); far = _nearest(strikes, round(spot + spread_w))
        long_k, short_k = near, far
    elif kind == "bear_put_spread":
        near = _nearest(strikes, round(spot)); far = _nearest(strikes, round(spot - spread_w))
        long_k, short_k = near, far
    elif kind == "bull_put_spread":
        near = _nearest(strikes, round(spot - otm)); far = _nearest(strikes, round(spot - otm - spread_w))
        short_k, long_k = near, far
    else:
        near = _nearest(strikes, round(spot + otm)); far = _nearest(strikes, round(spot + otm + spread_w))
        short_k, long_k = near, far
    if long_k is None or short_k is None or long_k == short_k:
        return _reject(f"strike_select_failed: long={long_k} short={short_k}")

    lo = _find(chain, long_k, opt_type); so = _find(chain, short_k, opt_type)
    if not lo or not so:
        return _reject("strike_missing")
    for o in (lo, so):
        ok, why = _spread_ok(o, params)
        if not ok:
            return _reject(why)

    long_mid, short_mid = _mid(lo), _mid(so)
    width = abs(short_k - long_k)
    is_credit = kind in CREDIT_KINDS
    if is_credit:
        net = round(short_mid - long_mid, 4)
        if net < float(params["min_credit"]):
            return _reject(f"credit_too_low: credit={net:.2f}")
        max_loss_per = (width - net) * 100.0
        max_profit_per = net * 100.0
    else:
        net = round(long_mid - short_mid, 4)
        if net <= 0:
            return _reject(f"non_positive_debit: debit={net:.2f}")
        max_loss_per = net * 100.0
        max_profit_per = (width - net) * 100.0
    if max_loss_per <= 0:
        return _reject(f"non_positive_max_loss width={width} net={net}")

    bp_pct = float(config.get("bp_pct", 0.02))
    raw_cap = int(config.get("max_contracts", 0) or 0)
    raw = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, raw) if raw_cap <= 0 else max(0, min(raw_cap, raw))
    if contracts < 1:
        return _reject(f"sizing_below_one: max_loss_per={max_loss_per:.0f}")

    pt_pct = float(config.get("pt_pct", 0.50)); sl_pct = float(config.get("sl_pct", 0.50))
    base = max_profit_per if is_credit else max_loss_per
    pt = pt_pct * base * contracts
    sl = sl_pct * base * contracts

    legs = [
        {"side": "long", "type": opt_type, "strike": long_k,
         "expiration": chain["expiration"], "entry_price": long_mid},
        {"side": "short", "type": opt_type, "strike": short_k,
         "expiration": chain["expiration"], "entry_price": short_mid},
    ]
    sig = VerticalSignal(
        kind=kind, ticker=chain.get("ticker", "SPY"), expiration=chain["expiration"],
        contracts=contracts, max_profit=round(max_profit_per, 2), max_loss=round(max_loss_per, 2),
        pt_target_pnl=round(pt, 2), sl_target_pnl=round(sl, 2), _legs=legs, width=width,
        net=net, is_credit=is_credit,
    )
    if is_credit:
        sig.credit = net
    else:
        sig.debit = net
    return sig
