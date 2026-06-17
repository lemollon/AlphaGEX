"""RIVER — Long (debit) Butterfly 0DTE entry signal builder.

RIVER is the debit-paid sibling of BREEZE. It shares BREEZE's entire thesis —
the underlying is most likely to expire at the **gamma magnet**, so we want a
payoff that peaks there — but builds that tent with a single-type 1-2-1 long
butterfly paid for with a net DEBIT, rather than a four-legged credit iron fly.

Body / wing selection is identical to BREEZE (see `iron_butterfly.py`):
  - Body centers on the gamma-weighted midpoint of comparably-large magnets,
    else the single dominant magnet, else the predicted pin, else spot.
  - Wing distance = round(sd_mult * atm_straddle * 0.85), optionally clipped to
    the GEX walls when `use_gex_walls` is set.

The only real difference is the structure built at those strikes:

  long  1x  (body - wing)     <- lower wing
  short 2x  (body)            <- body, sold twice
  long  1x  (body + wing)     <- upper wing

all of the SAME option type. A call fly and a put fly on the same strikes have
an essentially identical at-expiration payoff (put-call parity), so the choice
of type is purely an execution one: the out-of-the-money side is cheaper and
trades tighter. We price BOTH and keep whichever costs the smaller debit
(`_pick_cheaper_side`), which is always the OTM side.

The structure is emitted as **four legs** (the body appears twice) so it reuses
the existing debit-aware MTM / close / payoff plumbing without changes — the
two body legs simply share a strike and type.

Economics (per contract):
  debit       = lower_mid + upper_mid - 2 * body_mid   (> 0 for a real long fly)
  max_loss    = debit * 100                            (you can't lose more)
  max_profit  = (wing_width - debit) * 100             (price pins the body)

Exits (set on the signal, consumed by the scanner/monitor):
  pt_target = pt_pct * max_profit * contracts          (% of best case)
  sl_target = sl_pct * debit      * contracts          (% of debit paid)

Pure function `build_long_butterfly_signal(chain, config, equity)` returns a
`LongButterflySignal` dataclass or `None` if no setup passes the gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_VIX = 28.0
# A magnet counts as "comparably large" (and therefore part of the pin zone the
# price gets caught between) when its |gamma| is at least this fraction of the
# single largest magnet's |gamma|. Mirrors BREEZE.
MAGNET_PARITY = 0.70


@dataclass
class LongButterflySignal:
    ticker: str
    expiration: str
    option_type: str        # 'call' or 'put' — the cheaper (OTM) side
    body_strike: int
    lower_strike: int
    upper_strike: int
    lower_mid: float
    body_mid: float
    upper_mid: float
    debit: float             # per contract, net debit paid (> 0)
    contracts: int
    max_profit: float        # per contract, $
    max_loss: float          # per contract, $  (== debit * 100)
    wing_width: int          # body to wing distance (symmetric)
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total

    def legs(self) -> list[dict[str, Any]]:
        # Body sold twice -> emitted as two identical short legs so the
        # debit-aware MTM/payoff engine (which scales unit legs by `contracts`)
        # accounts for the 2x body naturally.
        return [
            {"side": "long",  "type": self.option_type, "strike": self.lower_strike,
             "expiration": self.expiration, "entry_price": self.lower_mid},
            {"side": "short", "type": self.option_type, "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.body_mid},
            {"side": "short", "type": self.option_type, "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.body_mid},
            {"side": "long",  "type": self.option_type, "strike": self.upper_strike,
             "expiration": self.expiration, "entry_price": self.upper_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find_option(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _body_candidates(chain: dict, opt_type: str) -> list[int]:
    """Strikes that list the given option type — valid body candidates for a
    single-type butterfly."""
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


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
    """[(strike, |gamma|)] for magnets within MAGNET_PARITY of the top one."""
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
    """Resolve the price level the body should sit on. Identical priority to
    BREEZE: gamma-weighted midpoint of large magnets -> dominant magnet ->
    predicted pin -> spot."""
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


def _price_side(chain: dict, opt_type: str, body: int,
                lower: int, upper: int) -> tuple[float, float, float, float] | None:
    """Return (debit, lower_mid, body_mid, upper_mid) for the single-type fly,
    or None if any leg is missing from the chain."""
    lo = _find_option(chain, lower, opt_type)
    bo = _find_option(chain, body, opt_type)
    up = _find_option(chain, upper, opt_type)
    if not all([lo, bo, up]):
        return None
    lm, bm, um = _mid(lo), _mid(bo), _mid(up)
    debit = round(lm + um - 2.0 * bm, 4)
    return debit, lm, bm, um


def build_long_butterfly_signal(
    *,
    chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> LongButterflySignal | None:
    """Build a long-butterfly signal or return None.

    `diag` is an optional list that gets a single human-readable rejection
    reason appended when this function returns None (surfaced by the scanner
    into scan_activity.reason).
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
    # Same body resolution as BREEZE — center on the gamma magnet price is most
    # likely to be drawn toward into expiration. Snap to a strike that lists the
    # option type we'll use; both call and put grids list the same strikes here,
    # so resolve against calls for the body, then reuse for whichever side wins.
    center = _pin_center(gex, spot)
    body = _nearest(_body_candidates(chain, "call"), round(center))
    if body is None:
        return _reject(f"no_body_strike: center={center:.2f}")

    atm_straddle = float(chain.get("atm_straddle_mid", 0))
    sd_mult = float(config.get("sd_mult", 1.0))
    wing_distance = max(1, round(sd_mult * atm_straddle * 0.85))

    upper_strike = body + wing_distance
    lower_strike = body - wing_distance

    if config.get("use_gex_walls"):
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        if cw is not None and body < cw < upper_strike:
            upper_strike = int(round(cw))
        if pw is not None and lower_strike < pw < body:
            lower_strike = int(round(pw))

    # Price both single-type flies on these strikes; keep the cheaper (OTM) side.
    call_priced = _price_side(chain, "call", body, lower_strike, upper_strike)
    put_priced = _price_side(chain, "put", body, lower_strike, upper_strike)

    candidates: list[tuple[str, tuple[float, float, float, float]]] = []
    if call_priced is not None:
        candidates.append(("call", call_priced))
    if put_priced is not None:
        candidates.append(("put", put_priced))
    if not candidates:
        return _reject(
            f"strike_missing: body={body} lower={lower_strike} upper={upper_strike}"
        )

    # Cheaper debit wins; ties resolve to the call fly deterministically.
    option_type, (debit, lower_mid, body_mid, upper_mid) = min(
        candidates, key=lambda c: c[1][0]
    )

    # A long butterfly must be a net DEBIT. A non-positive debit means the
    # quoted mids are inverted/degenerate (e.g. a credit fly) — not our trade.
    if debit <= 0:
        return _reject(f"non_positive_debit: type={option_type} debit={debit:.2f}")

    # Symmetric wings by construction; use the realized distances for safety
    # (GEX-wall clipping can make them asymmetric).
    wing_width = min(upper_strike - body, body - lower_strike)
    if wing_width <= 0:
        return _reject(f"degenerate_wings: lower={lower_strike} body={body} upper={upper_strike}")

    max_loss_per = debit * 100.0                       # most you can lose
    max_profit_per = (wing_width - debit) * 100.0      # price pins the body
    if max_profit_per <= 0:
        return _reject(f"non_positive_max_profit: wing={wing_width} debit={debit:.2f}")

    bp_pct = float(config.get("bp_pct", 0.10))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    # max_contracts=0 means "no ceiling, size by BP alone" (matches BREEZE/FLOW).
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
    pt_target = pt_pct * max_profit_per * contracts     # % of best case
    sl_target = sl_pct * max_loss_per * contracts       # % of debit paid

    return LongButterflySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        option_type=option_type,
        body_strike=body,
        lower_strike=lower_strike,
        upper_strike=upper_strike,
        lower_mid=lower_mid,
        body_mid=body_mid,
        upper_mid=upper_mid,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
