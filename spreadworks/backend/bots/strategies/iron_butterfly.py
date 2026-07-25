"""BREEZE — Iron Butterfly 0DTE entry signal builder.

An iron butterfly's payoff is a tent that peaks — maximum profit — exactly at
the BODY strike (the shared short call / short put strike). The trade is most
profitable when the underlying *expires at that body*. So instead of anchoring
the body to current spot, we center it on the **gamma magnet** the price is
most likely to be drawn toward into expiration.

The magnet is NOT the GEX flip point. The flip is just the gamma zero-crossing;
price does not always gravitate there. The magnet structure also depends on the
days to expiration, because the gamma profile differs every day and across
DTEs — so it is resolved per-expiration upstream and passed in on the chain.

Body selection (see `gamma_pin_center`):
  - When *comparably large* magnets (within `MAGNET_PARITY` of the top one by
    |gamma|) BRACKET spot — a call-side wall at/above spot and a put-side wall
    below it — price tends to pin inside that corridor, so the body is centered
    on the gamma-weighted midpoint of that bracketing pair.
  - Otherwise (one dominant magnet, or several clustered on the same side)
    center on the single largest gamma magnet.
  - Fall back to the predicted pin (`pin_strike`) when no magnets are present,
    then to the call_wall/put_wall corridor midpoint, then to spot.

There is intentionally **no minimum-credit gate**. The butterfly's edge is the
underlying expiring at the body, not the thickness of the entry credit, so a
thin credit is allowed. The only credit-side guard left is the structural
`max_loss > 0` sanity check (credit must not exceed the wing width).

Pure function `build_iron_butterfly_signal(chain, config, equity)` returns an
`IronButterflySignal` dataclass or `None` if no setup passes the gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_VIX = 28.0
# A magnet counts as "comparably large" (and therefore part of the pin zone the
# price gets caught between) when its |gamma| is at least this fraction of the
# single largest magnet's |gamma|.
MAGNET_PARITY = 0.70


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
    wing_width: int          # symmetric wing distance (body to either long strike)
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


def _body_candidates(chain: dict) -> list[int]:
    """Strikes that list BOTH a call and a put — the only valid butterfly
    bodies, since the body sells one of each."""
    calls = {int(o["strike"]) for o in chain["options"] if o["type"] == "call"}
    puts = {int(o["strike"]) for o in chain["options"] if o["type"] == "put"}
    return sorted(calls & puts)


def _nearest(strikes: list[int], target: float) -> int | None:
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def _magnet_gamma(m: dict[str, Any]) -> float:
    """A magnet's gamma magnitude, tolerant of the upstream key name.

    The WATCHTOWER gamma engine emits each magnet as
    `{"strike", "net_gamma", "probability"}` (see
    `core/watchtower_engine.identify_magnets`), while older callers/tests use
    a plain `"gamma"` key. Read whichever is present — otherwise every magnet
    silently reads as 0 gamma, gets dropped, and the body falls back to spot."""
    g = m.get("gamma")
    if g is None:
        g = m.get("net_gamma", 0)
    return abs(float(g or 0))


def _large_magnets(gex: dict[str, Any]) -> list[tuple[float, float]]:
    """Return [(strike, |gamma|)] for the magnets that are comparably large —
    within `MAGNET_PARITY` of the top magnet's |gamma|. The chain carries the
    top-N magnets (highest |gamma|) from the gamma engine."""
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


def gamma_pin_center(gex: dict[str, Any], spot: float) -> float:
    """Resolve the price level the body should sit on.

    Priority:
      1. **Pin BETWEEN the walls.** When the comparably-large magnets *bracket*
         spot — i.e. there is a call-side wall at/above spot AND a put-side wall
         below it — price tends to pin inside that corridor. Center on the
         gamma-weighted midpoint of that bracketing pair (the dominant magnet on
         each side). This mirrors the classic call-wall / put-wall framing:
         price gets caught between the two walls dealers defend.
      2. Otherwise center on the single largest gamma magnet (one dominant
         magnet, or several clustered on the same side of spot — there is no
         corridor to pin inside, so price is drawn to the heaviest strike).
      3. Otherwise (no magnets) fall back to the predicted pin (`pin_strike`).
      4. Otherwise, if the explicit call_wall / put_wall bracket spot, use the
         midpoint of that corridor (no per-strike gamma to weight by, so it's a
         plain midpoint). Lets callers that only carry the named walls — e.g.
         the gex-suggest builder — reuse this same logic.
      5. Otherwise fall back to spot.
    """
    large = _large_magnets(gex)
    if large:
        above = [(s, g) for s, g in large if s >= spot]  # call-side walls
        below = [(s, g) for s, g in large if s < spot]   # put-side walls
        if above and below:
            cw = max(above, key=lambda x: x[1])  # heaviest call-side wall
            pw = max(below, key=lambda x: x[1])  # heaviest put-side wall
            gsum = cw[1] + pw[1]
            if gsum > 0:
                return (cw[0] * cw[1] + pw[0] * pw[1]) / gsum
        # No bracketing pair (all magnets on one side) -> dominant magnet.
        return max(large, key=lambda x: x[1])[0]
    pin = gex.get("pin_strike")
    if pin is not None:
        return float(pin)
    call_wall = gex.get("call_wall")
    put_wall = gex.get("put_wall")
    if call_wall is not None and put_wall is not None:
        cw, pw = float(call_wall), float(put_wall)
        if pw < spot <= cw:  # walls bracket spot -> pin in the corridor
            return (cw + pw) / 2.0
    return spot


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
    # Center the body (the payoff apex / max-profit strike) on the gamma magnet
    # price is most likely to be drawn toward: the gamma-weighted midpoint of
    # comparably-large magnets when more than one exists, else the single
    # largest magnet, else the predicted pin, else spot (see gamma_pin_center).
    # This is per-expiration GEX structure — NOT the static flip point. Snap to
    # the nearest strike that lists BOTH a call and a put (body sells one each).
    center = gamma_pin_center(gex, spot)
    body = _nearest(_body_candidates(chain), round(center))
    if body is None:
        return _reject(f"no_body_strike: center={center:.2f}")

    atm_straddle = float(chain.get("atm_straddle_mid", 0))
    if atm_straddle <= 0:
        # No ATM straddle => can't size the wings; mirrors the iron condor's
        # guard. Without this the wings collapse to the $1 floor on missing data.
        return _reject("missing_atm_straddle")
    sd_mult = float(config.get("sd_mult", 1.0))
    wing_distance = max(1, round(sd_mult * atm_straddle * 0.85))

    if config.get("use_gex_walls"):
        # Walls cap how far the protective wings sit, but the fly must stay a
        # SYMMETRIC tent or the defined-risk math below (max_loss = wing -
        # credit) breaks: clipping only one side makes a broken-wing fly whose
        # true max loss is the WIDER wing minus credit, which would silently
        # under-size risk. So pull BOTH wings in to the nearer wall distance.
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        if cw is not None and cw > body:
            wing_distance = min(wing_distance, int(round(cw)) - body)
        if pw is not None and pw < body:
            wing_distance = min(wing_distance, body - int(round(pw)))
        wing_distance = max(1, wing_distance)

    long_call_strike = body + wing_distance
    long_put_strike = body - wing_distance

    short_call = _find_option(chain, body, "call")
    short_put = _find_option(chain, body, "put")
    long_call = _find_option(chain, long_call_strike, "call")
    long_put = _find_option(chain, long_put_strike, "put")
    if not all([short_call, short_put, long_call, long_put]):
        return _reject(f"strike_missing: body={body} put_wing={long_put_strike} call_wing={long_call_strike}")

    sc_mid, sp_mid = _mid(short_call), _mid(short_put)
    lc_mid, lp_mid = _mid(long_call), _mid(long_put)
    # No minimum-credit floor — a thin credit is acceptable for this strategy.
    credit = round(sc_mid + sp_mid - lc_mid - lp_mid, 4)

    # Wings are symmetric by construction (wall clipping above pulls BOTH in
    # equally), so a single wing width drives the defined-risk math.
    wing_width = long_call_strike - body
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
    sl_pct = float(config.get("sl_pct", 0.50))
    pt_target = pt_pct * max_profit_per * contracts
    # SL is a fraction of MAX LOSS (defined risk), mirroring RIVER. Basing it on
    # max_profit (the credit) made the stop unreachable for an iron fly: the
    # rich ATM credit is a large fraction of the wing, so the max loss
    # (wing - credit) can never reach 2x the credit and the stop never fired.
    sl_target = sl_pct * max_loss_per * contracts

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
