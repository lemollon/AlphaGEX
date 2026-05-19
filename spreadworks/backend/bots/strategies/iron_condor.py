"""FLOW — Iron Condor 1DTE entry signal builder.

Port of IronForge SPARK criteria into the SpreadWorks paper-bot architecture.
SPARK trades SPY 1DTE Iron Condors with symmetric wings sized by std-dev mult
times the ATM straddle. Same gate stack:

  - VIX <= 32
  - Credit >= $0.25 per contract
  - $5 wings (long strikes are $5 outside the shorts)
  - 1DTE expiration
  - Skip when underlying sits within MIN_FLIP_DIST of the GEX flip point
  - PT = 30% of max profit; SL = 50% of max profit (matches current SPARK prod)

Sizing mirrors `iron_butterfly.py`: contracts = floor((equity * bp_pct) /
max_loss_per_contract), clamped to max_contracts when > 0. `max_contracts=0`
means "unlimited" (size only by buying power).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Match SPARK's hardcoded scanner defaults (ironforge/webapp/src/lib/scanner.ts).
MIN_CREDIT = 0.25
MAX_VIX = 32.0
MIN_FLIP_DIST = 1.0
SPREAD_WIDTH = 5  # $5 wings — symmetric IC


@dataclass
class IronCondorSignal:
    ticker: str
    expiration: str
    # Strikes ordered low → high for clarity.
    long_put_strike: int
    short_put_strike: int
    short_call_strike: int
    long_call_strike: int
    short_put_mid: float
    long_put_mid: float
    short_call_mid: float
    long_call_mid: float
    credit: float            # per contract, $
    contracts: int
    max_profit: float        # per contract, $
    max_loss: float          # per contract, $
    wing_width: int          # $ — uniform left/right wings
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "put",  "strike": self.short_put_strike,
             "expiration": self.expiration, "entry_price": self.short_put_mid},
            {"side": "short", "type": "call", "strike": self.short_call_strike,
             "expiration": self.expiration, "entry_price": self.short_call_mid},
            {"side": "long",  "type": "put",  "strike": self.long_put_strike,
             "expiration": self.expiration, "entry_price": self.long_put_mid},
            {"side": "long",  "type": "call", "strike": self.long_call_strike,
             "expiration": self.expiration, "entry_price": self.long_call_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find_option(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _available_strikes(chain: dict, opt_type: str) -> list[int]:
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


def _nearest_strike(strikes: list[int], target: int) -> int | None:
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def build_iron_condor_signal(
    *,
    chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> IronCondorSignal | None:
    """Build a 1DTE Iron Condor signal or return None.

    `diag` (optional) collects a single human-readable rejection reason
    when this function returns None, so the scanner can surface it on
    scan_activity.reason.
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
    if atm_straddle <= 0:
        return _reject("missing_atm_straddle")

    # SPARK's strike selection: shorts at (spot ± sd_mult * ATM straddle),
    # longs $5 further out symmetric.
    sd_mult = float(config.get("sd_mult", 1.2))
    sd_distance = sd_mult * atm_straddle
    spread_width = int(config.get("spread_width", SPREAD_WIDTH) or SPREAD_WIDTH)

    target_short_put = round(spot - sd_distance)
    target_short_call = round(spot + sd_distance)

    put_strikes = _available_strikes(chain, "put")
    call_strikes = _available_strikes(chain, "call")
    short_put_strike = _nearest_strike(put_strikes, target_short_put)
    short_call_strike = _nearest_strike(call_strikes, target_short_call)
    if short_put_strike is None or short_call_strike is None:
        return _reject(
            f"strike_missing_shorts: target_put={target_short_put} "
            f"target_call={target_short_call}"
        )
    if short_call_strike <= short_put_strike:
        return _reject(
            f"shorts_crossed: sp={short_put_strike} sc={short_call_strike}"
        )

    long_put_strike = short_put_strike - spread_width
    long_call_strike = short_call_strike + spread_width

    short_put = _find_option(chain, short_put_strike, "put")
    short_call = _find_option(chain, short_call_strike, "call")
    long_put = _find_option(chain, long_put_strike, "put")
    long_call = _find_option(chain, long_call_strike, "call")
    if not all([short_put, short_call, long_put, long_call]):
        return _reject(
            f"strike_missing_legs: sp={short_put_strike} sc={short_call_strike} "
            f"lp={long_put_strike} lc={long_call_strike}"
        )

    sp_mid, sc_mid = _mid(short_put), _mid(short_call)
    lp_mid, lc_mid = _mid(long_put), _mid(long_call)
    # IC credit = (sell shorts at bid, buy longs at ask) approx via mids.
    credit = round(sp_mid + sc_mid - lp_mid - lc_mid, 4)
    if credit < MIN_CREDIT:
        return _reject(f"credit_too_low: credit={credit:.2f} min={MIN_CREDIT}")

    wing_width = spread_width
    max_profit_per = credit * 100.0
    max_loss_per = (wing_width - credit) * 100.0
    if max_loss_per <= 0:
        return _reject(f"negative_max_loss: wing={wing_width} credit={credit:.2f}")

    bp_pct = float(config.get("bp_pct", 0.50))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    # max_contracts=0 means "no ceiling, size by BP alone" (matches SPARK).
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

    # PT/SL are stored as $ totals (matches monitor.decide_exit). FLOW config
    # defaults: pt_pct=0.30 → close on +30% of max profit;
    # sl_pct=0.50 → close on -50% of max profit (= 150% cost-to-close,
    # matches current SPARK prod stop_loss_pct=150).
    pt_pct = float(config.get("pt_pct", 0.30))
    sl_pct = float(config.get("sl_pct", 0.50))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_profit_per * contracts

    return IronCondorSignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        long_put_strike=long_put_strike,
        short_put_strike=short_put_strike,
        short_call_strike=short_call_strike,
        long_call_strike=long_call_strike,
        short_put_mid=sp_mid,
        long_put_mid=lp_mid,
        short_call_mid=sc_mid,
        long_call_mid=lc_mid,
        credit=credit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
