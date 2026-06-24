"""SURGE — Pin + Drift Combo 0DTE/1DTE entry signal builder.

The combo that real-fill backtesting (2022-2025, ThetaData) showed is the best
SPY 0DTE structure: a long butterfly that wins on a PIN, plus two cheap
calendars placed where price could DRIFT to, which win when it doesn't pin.
Net ~+$24/day per 1-lot at realistic fills, ~52% win, positive every year.

It is literally RIVER's butterfly + two of TIDE's calendar legs in one position:

  Front (0DTE):
    long  1x  (body - wing)   call/put   <- butterfly lower wing
    short 2x  (body)          call/put   <- butterfly body (sold twice)
    long  1x  (body + wing)   call/put   <- butterfly upper wing
    short 1x  (body + drift)  call       <- call calendar near leg
    short 1x  (body - drift)  put        <- put calendar near leg
  Back (1DTE):
    long  1x  (body + drift)  call       <- call calendar far leg
    long  1x  (body - drift)  put        <- put calendar far leg

Body / wing are RESOLVED EXACTLY AS RIVER/BREEZE (gamma magnet -> dominant
magnet -> pin -> spot; wing = round(sd_mult * atm_straddle * 0.85)). The
calendars sit `drift_offset` dollars either side of the body (default $3, the
validated sweet spot). Each calendar sells the 0DTE and buys the 1DTE at the
same strike for a small debit.

Economics (per contract):
  debit      = fly_debit + call_cal_debit + put_cal_debit   (total premium paid)
  max_loss   = debit * 100        (defined-risk: the most you put up; calendars
                                   can over-run slightly on a gap, see backtest)
  max_profit = (wing - fly_debit) * 100  (reference: the butterfly's pin payoff;
                                   the calendars add upside when price drifts)

Exits (consumed by scanner/monitor): pt_target = pt_pct * max_profit, sl_target
= sl_pct * max_loss. Mirrors RIVER.

Pure function `build_pin_drift_combo_signal(front_chain, back_chain, config,
equity)` returns a `PinDriftComboSignal` or None if any gate fails.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_VIX = 28.0
MAGNET_PARITY = 0.70
DEFAULT_DRIFT = 3          # $ either side of the body for the two calendars


@dataclass
class PinDriftComboSignal:
    ticker: str
    front_expiration: str
    back_expiration: str
    option_type: str             # butterfly side ('call'/'put'), cheaper OTM side
    body_strike: int
    lower_strike: int            # butterfly lower wing
    upper_strike: int            # butterfly upper wing
    call_cal_strike: int         # body + drift
    put_cal_strike: int          # body - drift
    # mids
    fly_lower_mid: float
    fly_body_mid: float
    fly_upper_mid: float
    cal_call_front_mid: float
    cal_call_back_mid: float
    cal_put_front_mid: float
    cal_put_back_mid: float
    # economics (per contract)
    fly_debit: float
    call_cal_debit: float
    put_cal_debit: float
    debit: float                 # total
    contracts: int
    max_profit: float
    max_loss: float
    wing_width: int
    drift_offset: int
    pt_target_pnl: float
    sl_target_pnl: float

    def legs(self) -> list[dict[str, Any]]:
        ot = self.option_type
        return [
            # --- butterfly (front / 0DTE), body emitted twice (2x short) ---
            {"side": "long",  "type": ot, "strike": self.lower_strike,
             "expiration": self.front_expiration, "entry_price": self.fly_lower_mid},
            {"side": "short", "type": ot, "strike": self.body_strike,
             "expiration": self.front_expiration, "entry_price": self.fly_body_mid},
            {"side": "short", "type": ot, "strike": self.body_strike,
             "expiration": self.front_expiration, "entry_price": self.fly_body_mid},
            {"side": "long",  "type": ot, "strike": self.upper_strike,
             "expiration": self.front_expiration, "entry_price": self.fly_upper_mid},
            # --- call calendar: short front, long back @ body+drift ---
            {"side": "short", "type": "call", "strike": self.call_cal_strike,
             "expiration": self.front_expiration, "entry_price": self.cal_call_front_mid},
            {"side": "long",  "type": "call", "strike": self.call_cal_strike,
             "expiration": self.back_expiration, "entry_price": self.cal_call_back_mid},
            # --- put calendar: short front, long back @ body-drift ---
            {"side": "short", "type": "put", "strike": self.put_cal_strike,
             "expiration": self.front_expiration, "entry_price": self.cal_put_front_mid},
            {"side": "long",  "type": "put", "strike": self.put_cal_strike,
             "expiration": self.back_expiration, "entry_price": self.cal_put_back_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _body_candidates(chain: dict, opt_type: str) -> list[int]:
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


def _nearest(strikes: list[int], target: float) -> int | None:
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def _magnet_gamma(m: dict[str, Any]) -> float:
    g = m.get("gamma")
    if g is None:
        g = m.get("net_gamma", 0)
    return abs(float(g or 0))


def _large_magnets(gex: dict[str, Any]) -> list[tuple[float, float]]:
    raw = gex.get("magnets") or []
    pairs: list[tuple[float, float]] = []
    for m in raw:
        try:
            strike = float(m["strike"])
            gamma = _magnet_gamma(m)
        except (KeyError, TypeError, ValueError):
            continue
        if gamma > 0:
            pairs.append((strike, gamma))
    if not pairs:
        return []
    top = max(g for _, g in pairs)
    return [(s, g) for s, g in pairs if g >= MAGNET_PARITY * top]


def _pin_center(gex: dict[str, Any], spot: float) -> float:
    large = _large_magnets(gex)
    if len(large) >= 2:
        gsum = sum(g for _, g in large)
        if gsum > 0:
            return sum(s * g for s, g in large) / gsum
    if large:
        return max(large, key=lambda x: x[1])[0]
    pin = gex.get("pin_strike")
    if pin is not None:
        return float(pin)
    return spot


def _price_fly(chain: dict, opt_type: str, body: int, lower: int,
               upper: int) -> tuple[float, float, float, float] | None:
    lo = _find(chain, lower, opt_type)
    bo = _find(chain, body, opt_type)
    up = _find(chain, upper, opt_type)
    if not all([lo, bo, up]):
        return None
    lm, bm, um = _mid(lo), _mid(bo), _mid(up)
    return round(lm + um - 2.0 * bm, 4), lm, bm, um


def _price_calendar(front_chain: dict, back_chain: dict, strike: int,
                    opt_type: str) -> tuple[float, float, float] | None:
    """(debit, front_mid, back_mid) for a calendar (sell front, buy back) at
    `strike`, or None if the strike is missing in either expiration."""
    f = _find(front_chain, strike, opt_type)
    b = _find(back_chain, strike, opt_type)
    if not (f and b):
        return None
    fm, bm = _mid(f), _mid(b)
    return round(bm - fm, 4), fm, bm


def build_pin_drift_combo_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> PinDriftComboSignal | None:
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return _reject(f"vix_too_high: vix={vix:.2f} max={MAX_VIX}")

    gex = front_chain.get("gex") or {}
    center = _pin_center(gex, spot)
    body = _nearest(_body_candidates(front_chain, "call"), round(center))
    if body is None:
        return _reject(f"no_body_strike: center={center:.2f}")

    atm_straddle = float(front_chain.get("atm_straddle_mid", 0))
    if atm_straddle <= 0:
        return _reject("missing_atm_straddle")
    sd_mult = float(config.get("sd_mult", 1.0))
    wing_distance = max(1, round(sd_mult * atm_straddle * 0.85))

    if config.get("use_gex_walls"):
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        if cw is not None and cw > body:
            wing_distance = min(wing_distance, int(round(cw)) - body)
        if pw is not None and pw < body:
            wing_distance = min(wing_distance, body - int(round(pw)))
        wing_distance = max(1, wing_distance)

    upper_strike = body + wing_distance
    lower_strike = body - wing_distance

    # --- butterfly: price both single-type flies on the front chain, keep cheaper ---
    call_fly = _price_fly(front_chain, "call", body, lower_strike, upper_strike)
    put_fly = _price_fly(front_chain, "put", body, lower_strike, upper_strike)
    fly_cands = []
    if call_fly is not None:
        fly_cands.append(("call", call_fly))
    if put_fly is not None:
        fly_cands.append(("put", put_fly))
    if not fly_cands:
        return _reject(f"fly_strike_missing: body={body} lower={lower_strike} upper={upper_strike}")
    option_type, (fly_debit, fly_lower_mid, fly_body_mid, fly_upper_mid) = min(
        fly_cands, key=lambda c: c[1][0]
    )
    if fly_debit <= 0:
        return _reject(f"non_positive_fly_debit: type={option_type} debit={fly_debit:.2f}")

    wing_width = upper_strike - body
    if wing_width <= 0:
        return _reject(f"degenerate_wings: lower={lower_strike} body={body} upper={upper_strike}")

    # --- calendars: drift offset either side of the body ---
    drift = int(config.get("drift_offset", DEFAULT_DRIFT))
    if drift <= 0:
        return _reject(f"non_positive_drift: drift={drift}")
    call_cal_strike = body + drift
    put_cal_strike = body - drift
    call_cal = _price_calendar(front_chain, back_chain, call_cal_strike, "call")
    put_cal = _price_calendar(front_chain, back_chain, put_cal_strike, "put")
    if call_cal is None or put_cal is None:
        return _reject(
            f"cal_strike_missing: call_cal={call_cal_strike} put_cal={put_cal_strike}"
        )
    call_cal_debit, cal_call_front_mid, cal_call_back_mid = call_cal
    put_cal_debit, cal_put_front_mid, cal_put_back_mid = put_cal
    # A calendar should be a (small) net debit — front sold, back bought.
    if call_cal_debit <= 0 or put_cal_debit <= 0:
        return _reject(
            f"non_positive_cal_debit: call={call_cal_debit:.2f} put={put_cal_debit:.2f}"
        )

    debit = round(fly_debit + call_cal_debit + put_cal_debit, 4)
    max_loss_per = debit * 100.0
    # Reference best-case: the butterfly's pin payoff (calendars add to upside).
    max_profit_per = (wing_width - fly_debit) * 100.0
    if max_profit_per <= 0:
        return _reject(f"non_positive_max_profit: wing={wing_width} fly_debit={fly_debit:.2f}")

    bp_pct = float(config.get("bp_pct", 0.10))
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

    pt_pct = float(config.get("pt_pct", 0.30))
    sl_pct = float(config.get("sl_pct", 0.50))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_loss_per * contracts

    return PinDriftComboSignal(
        ticker=front_chain.get("ticker", "SPY"),
        front_expiration=front_chain["expiration"],
        back_expiration=back_chain["expiration"],
        option_type=option_type,
        body_strike=body,
        lower_strike=lower_strike,
        upper_strike=upper_strike,
        call_cal_strike=call_cal_strike,
        put_cal_strike=put_cal_strike,
        fly_lower_mid=fly_lower_mid,
        fly_body_mid=fly_body_mid,
        fly_upper_mid=fly_upper_mid,
        cal_call_front_mid=cal_call_front_mid,
        cal_call_back_mid=cal_call_back_mid,
        cal_put_front_mid=cal_put_front_mid,
        cal_put_back_mid=cal_put_back_mid,
        fly_debit=fly_debit,
        call_cal_debit=call_cal_debit,
        put_cal_debit=put_cal_debit,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        drift_offset=drift,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
