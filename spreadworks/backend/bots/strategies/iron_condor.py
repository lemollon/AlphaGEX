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
# 🚨 A CEILING, NOT JUST A FLOOR. RE-TIGHTENED 2026-08-21 from 0.40 to 0.25:
# 0.40 was calibrated to the worst known case (56%) and a THIRD phantom walked
# through it at 30.2% the very next session — 760 put quoted 1.46 with spot at
# 765.98, six points OTM on a 1DTE and dearer than a 3.45-OTM put from a
# comparable day. Two populations, cleanly separated:
#     8 clean fills : 10.4% - 17.7%
#     3 phantoms    : 28.8%, 30.2%, 56.2%
# 0.22 sits 4.3 points above the worst real fill and 6.8 below the nearest
# phantom. Erring TIGHT on purpose: a rejected real trade costs an
# opportunity on a marginal paper bot, an accepted phantom corrupts the
# ledger - which is the thing this exists to protect.
# The only upper bound used to be
# `credit < wing_width` (otherwise max loss goes negative), which on a $5 wing
# admits anything up to $4.99. That is nowhere near tight enough to catch a bad
# quote: on 2026-08-18 FLOW booked a 2.81 credit on a $5 wing - 56% of the width
# - because the 763 put came back at 2.75 when the 764 put two minutes later was
# 0.695. A lower-strike put cannot cost 4x a higher-strike one; the quote was
# garbage, and the phantom credit made the position look instantly profitable,
# so the profit-target logic closed it ONE MINUTE after entry and booked +$5,319
# on a trade that was really about -$500.
#
# Real 1DTE condors at sd_mult 1.2 collect 13-18% of the width (measured across
# every other FLOW fill). 40% is far above anything legitimate and far below the
# 56% that got through, so it rejects the data error without touching a real
# signal. A rejection is logged and surfaced, never silent.
MAX_CREDIT_FRAC_OF_WIDTH = 0.22

# 🚨 08:30:00 IS THE CAUSE, NOT A COINCIDENCE. All three phantom fills entered
# at exactly 13:30:00 UTC — the first scan of the session, on the opening
# auction print. Quotes there are wide, one-sided and frequently stale, and the
# inflated credit then trips the profit target within minutes. No legitimate
# FLOW fill has ever come from that scan. Skipping the first few minutes removes
# the source instead of filtering its output.
OPENING_BELL_SKIP_MIN = 5
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
    now_ct=None,
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

    # ⛔ SKIP THE OPENING AUCTION. Passed in rather than read from a clock
    # inside here, so the rule is testable and the caller stays honest about
    # what time it thinks it is. Omitted (None) = no time gate, which keeps the
    # preview/backtest callers working unchanged.
    if now_ct is not None:
        mins = now_ct.hour * 60 + now_ct.minute
        if 8 * 60 + 30 <= mins < 8 * 60 + 30 + OPENING_BELL_SKIP_MIN:
            return _reject(
                f"opening_auction: {now_ct:%H:%M} CT is inside the first "
                f"{OPENING_BELL_SKIP_MIN} min. Every phantom fill this bot has "
                f"booked came from the 08:30 scan on opening-auction quotes."
            )

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
    # ⛔ CHECKED BEFORE SIZING. An inflated credit does not just misprice the
    # trade, it inflates max_profit and shrinks max_loss, which feeds straight
    # into the contract count - so a bad quote buys MORE of the bad trade.
    if credit > MAX_CREDIT_FRAC_OF_WIDTH * wing_width:
        return _reject(
            f"credit_implausible: credit={credit:.2f} is "
            f"{100 * credit / wing_width:.0f}% of the {wing_width:.0f}-wide wing "
            f"(max {100 * MAX_CREDIT_FRAC_OF_WIDTH:.0f}%). Legs: "
            f"sp={sp_mid:.2f} sc={sc_mid:.2f} lp={lp_mid:.2f} lc={lc_mid:.2f} "
            f"— almost certainly a bad quote, not an opportunity."
        )
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
