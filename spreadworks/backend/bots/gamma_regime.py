"""Net dealer gamma — the state variable behind every SPY squeeze since 2020.

WHAT IT MEASURES
----------------
    net_gex = [ SUM_calls (gamma * OI * 100) - SUM_puts (gamma * OI * 100) ]
              * spot^2 * 0.01                              # $ per 1% move

Negative means dealers are short gamma and hedge WITH the move (amplifying).
Positive means they hedge AGAINST it (pinning). Computed over dte 0-365 with NO
implied-vol filter — that exact contract set reproduces the research warehouse
series to corr 1.0000 (residual sd 0.000 over 903 overlapping sessions). Narrowing
the dte band or filtering on iv breaks the reconciliation, so do not "clean" it.

WHY WE COMPUTE IT INSTEAD OF READING THE VENDOR FLIP
----------------------------------------------------
The obvious shortcut is `spot < vendor_flip_point`, which the GEX proxy already
serves. It does not work. Against the research series the vendor flip correlates
+0.98 and is still only ~10 points off on average — but spot usually sits within
1-2% of the flip, so a 10-point error flips the SIGN. Measured agreement of
`spot < vendor_flip` with `net_gex < 0`:

    gamma_history.flip_point (watchtower feed)     52.4%   <- a coin flip
    spy_intraday_gex.igex_flip                     45.0%
    our own re-solved flip                         95.1%

52% is not a signal. That is why this module pulls the chain and does the sum.

WHY THE LAG IS NOT OPTIONAL
---------------------------
A reading is stored under the session whose CLOSING chain produced it, and
`gamma_state(asof)` only ever reads sessions STRICTLY BEFORE `asof`. This mirrors
the research construction exactly (bt_spy.net_gex for date t is built from t-1's
close). Reading today's own chain to judge today is conditioning on the day's
outcome.

WHAT IT IS AND IS NOT
---------------------
It is NOT directional. Deep short gamma roughly DOUBLES the odds of a big move in
BOTH directions — read as "get long" it was wrong 16 times out of 22. What it is:

    every SPY squeeze since 2020 began in short gamma      33 of 33 (base rate 58%)
    ...but precision is only                               3.4%   (929 false alarms)
    P(-4% within 5 sessions), net_gex > +5B                1.89%  (vs 10.16% base)
    P(>1% intraday break), short gamma vs long             28.2% vs 10.1%

So: a prerequisite for a squeeze, a strong veto for short premium, and useless as
a direction call.

UNKNOWN IS NOT "SAFE"
---------------------
With no prior session on file `gamma_state` returns None. Callers must treat None
as BLOCK, not as pass — the days data goes missing are not randomly chosen.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# The contract set that reconciles to the research series. Do not narrow.
MAX_DTE = 365

# Regime thresholds, in $bn of gamma per 1% move.
DEEP_LONG_B = 5.0     # P(-4% in 5d) = 1.89% vs a 10.16% base rate
DEEP_SHORT_B = -10.0  # the short-premium veto; fires on ~9% of sessions

# --- the normalised view, which beats the raw sign -------------------------------
# Percentile rank of net_gex within its own trailing window. The LEVEL of gamma is
# a weaker signal than where gamma sits in its own recent range, exactly as VIX's
# level is weaker than VIX/20d-max. Squeeze rate by 60-session percentile:
#
#     0-10  (most oversold)   10.80%        50-75                    0.80%
#     10-25                    8.54%        75-90                    0.00%
#     25-50                    2.03%        90-100 (overbought)      0.00%
#
# Monotone, and ZERO squeezes in the top quartile across 429 sessions. Base 3.38%.
# Combined with VIX at its 20-day high the oversold cell reaches 15.13% — better
# than 9.95% for the raw sign, i.e. the normalisation is worth ~50% of precision.
#
# The overbought end is NOT a crash signal. P(crash) there is 4.30% against a 3.63%
# base (nothing), and its downside tail is the SMALLEST on the board (5.38% vs
# 8.76%). Overbought gamma means stand down and sell premium — never buy puts.
PCT_WINDOW = 60
OVERSOLD_PCT = 0.20
OVERBOUGHT_PCT = 0.80
VIX_AT_HIGHS = 0.95   # vix_decay_ratio above this = fear peaking, not decaying

GAMMA_DAILY_TABLE = "sw_gamma_daily"

_GAMMA_DDL = f"""
CREATE TABLE IF NOT EXISTS {GAMMA_DAILY_TABLE} (
    trade_date   DATE PRIMARY KEY,
    net_gex      DOUBLE PRECISION NOT NULL,
    spot         NUMERIC(10,2),
    n_contracts  INTEGER,
    updated_at   TIMESTAMP NOT NULL
)
"""


def ensure_gamma_table(engine: Engine) -> None:
    """Idempotent create. Safe to call every cycle."""
    with engine.begin() as conn:
        conn.execute(text(_GAMMA_DDL))


def compute_net_gex(options: list[dict], spot: float) -> dict[str, Any]:
    """Sum a full option chain into one net-gamma number.

    `options` is a flat list of Tradier chain rows across expirations, each with
    a `greeks.gamma`, an `open_interest` and an `option_type`. Rows missing either
    input contribute nothing rather than raising — a vendor gap should shrink the
    estimate, not crash the job. `n_contracts` is returned so a caller can tell a
    thin pull from a full one.
    """
    if not spot or spot <= 0:
        return {"net_gex": None, "n_contracts": 0, "reason": "bad_spot"}

    call_g = 0.0
    put_g = 0.0
    n = 0
    for o in options:
        g = (o.get("greeks") or {}).get("gamma")
        oi = o.get("open_interest")
        if g is None or oi is None:
            continue
        try:
            g = float(g)
            oi = float(oi)
        except (TypeError, ValueError):
            continue
        if oi <= 0 or g <= 0:
            continue
        w = g * oi * 100.0
        if str(o.get("option_type", "")).lower().startswith("c"):
            call_g += w
        else:
            put_g += w
        n += 1

    if n == 0:
        return {"net_gex": None, "n_contracts": 0, "reason": "no_usable_greeks"}

    net = (call_g - put_g) * (spot ** 2) * 0.01
    return {"net_gex": net, "n_contracts": n, "reason": None}


def fetch_net_gex(client: Any, ticker: str = "SPY", *, today: date | None = None,
                  max_dte: int = MAX_DTE) -> dict[str, Any]:
    """Pull every expiration out to `max_dte` and reduce it to one number.

    `client` is a routes_helpers.TradierClient. This is ~40 chain calls for SPY,
    which is why it runs once a session and never inside the scan loop.
    """
    today = today or date.today()
    spot = client._spot(ticker)
    if not spot:
        return {"net_gex": None, "spot": None, "n_contracts": 0, "reason": "no_spot"}

    try:
        exps = client._all_expirations(ticker)
    except AttributeError:
        exps = _expirations(client, ticker)
    if not exps:
        return {"net_gex": None, "spot": spot, "n_contracts": 0, "reason": "no_expirations"}

    horizon = (today + timedelta(days=max_dte)).isoformat()
    rows: list[dict] = []
    for exp in exps:
        if exp > horizon:
            break
        try:
            r = client._client.get(
                f"{_base()}/markets/options/chains",
                params={"symbol": ticker, "expiration": exp, "greeks": "true"},
                headers=_hdrs(),
            )
            if r.status_code != 200:
                logger.warning("gamma_regime: chain %s %s -> %s", ticker, exp, r.status_code)
                continue
            data = (r.json().get("options") or {}).get("option") or []
            if isinstance(data, dict):
                data = [data]
            rows.extend(data)
        except Exception as e:                                    # noqa: BLE001
            logger.warning("gamma_regime: chain %s %s failed: %s", ticker, exp, e)
            continue

    out = compute_net_gex(rows, float(spot))
    out["spot"] = float(spot)
    out["n_expirations"] = len([e for e in exps if e <= horizon])
    return out


def record_gamma(engine: Engine, trade_date: date, net_gex: float,
                 spot: float | None = None, n_contracts: int | None = None) -> None:
    """Upsert one session's reading, keyed on the date whose CLOSE produced it."""
    if net_gex is None:
        return
    params = {"d": trade_date, "g": float(net_gex),
              "s": float(spot) if spot else None,
              "n": int(n_contracts) if n_contracts else None}
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, :n, CURRENT_TIMESTAMP) "
                "ON CONFLICT(trade_date) DO UPDATE SET net_gex = excluded.net_gex, "
                "spot = excluded.spot, n_contracts = excluded.n_contracts, "
                "updated_at = CURRENT_TIMESTAMP"
            ), params)
        else:
            conn.execute(text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, :n, NOW()) "
                "ON CONFLICT (trade_date) DO UPDATE SET net_gex = EXCLUDED.net_gex, "
                "spot = EXCLUDED.spot, n_contracts = EXCLUDED.n_contracts, "
                "updated_at = NOW()"
            ), params)


def gamma_state(engine: Engine, asof: date) -> dict[str, Any]:
    """Prior session's gamma, for a decision being made ON `asof`.

    Returns {"net_gex_b": float|None, "regime": str|None, "prior_date", "spot",
             "reason": str|None}. net_gex_b is in $bn. None means BLOCK.
    """
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT trade_date, net_gex, spot FROM {GAMMA_DAILY_TABLE} "
            "WHERE trade_date < :d ORDER BY trade_date DESC LIMIT 1"
        ), {"d": asof}).fetchone()

    if row is None:
        return {"net_gex_b": None, "regime": None, "prior_date": None, "spot": None,
                "reason": "no_gamma_history"}

    prior_date, net_gex, spot = row[0], float(row[1]), row[2]
    b = net_gex / 1e9
    if b >= DEEP_LONG_B:
        regime = "deep_long_gamma"
    elif b > 0:
        regime = "long_gamma"
    elif b > DEEP_SHORT_B:
        regime = "short_gamma"
    else:
        regime = "deep_short_gamma"

    return {"net_gex_b": b, "regime": regime, "prior_date": prior_date,
            "spot": float(spot) if spot is not None else None, "reason": None}


def gamma_percentile(engine: Engine, asof: date,
                     window: int = PCT_WINDOW) -> dict[str, Any]:
    """Where the PRIOR session's gamma sits in its own trailing range.

    Returns {"pct": float|None, "net_gex_b", "prior_date", "n_history", "reason"}.
    pct is the fraction of the trailing window the prior reading exceeds, so 0.0 is
    the most oversold reading in `window` sessions and 1.0 the most overbought.
    None means BLOCK — a percentile computed off a short history is not a percentile.
    """
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT trade_date, net_gex FROM {GAMMA_DAILY_TABLE} "
            "WHERE trade_date < :d ORDER BY trade_date DESC LIMIT :n"
        ), {"d": asof, "n": window}).fetchall()

    if len(rows) < window:
        return {"pct": None, "net_gex_b": None, "prior_date": None,
                "n_history": len(rows),
                "reason": f"insufficient_gamma_history: have={len(rows)} need={window}"}

    prior_date, prior = rows[0][0], float(rows[0][1])
    hist = [float(r[1]) for r in rows]              # includes the prior reading
    pct = sum(1 for v in hist if prior > v) / len(hist)
    return {"pct": pct, "net_gex_b": prior / 1e9, "prior_date": prior_date,
            "n_history": len(rows), "reason": None}


def squeeze_signal(engine: Engine, asof: date) -> dict[str, Any]:
    """The full verdict for a decision being made ON `asof`. Prior sessions only.

    verdict is one of:
      SQUEEZE_WATCH  gamma oversold AND VIX at its highs. 15.13% of these started a
                     squeeze (base 3.38%) and ZERO were crashes-from-highs. This is
                     where the long-convexity trade goes and where selling stands down.
      NO_SELL        gamma below -$10B. The short-premium veto, ~9% of sessions.
      SELL_PREMIUM   gamma overbought. Zero squeezes in 387 sessions, smallest
                     downside tail on the board.
      NEUTRAL        everything else. Trade the sell side normally.
      UNKNOWN        missing history. BLOCK — do not read this as NEUTRAL.

    The VIX leg reuses vix_regime.vix_decay_ratio, which is already prior-session
    lagged. Note one definitional difference from the research: research used
    VIX / max(VIX including today), which caps at 1.0; this uses VIX(prior) / max(20
    sessions BEFORE prior), which exceeds 1.0 when the prior session set a new high.
    Both are "is fear still building", the live one is slightly stricter, and the
    0.95 threshold captures the same regime. Worth confirming on live readings
    before this gates anything that trades.
    """
    from backend.bots.vix_regime import vix_decay_ratio

    gp = gamma_percentile(engine, asof)
    vr = vix_decay_ratio(engine, asof)
    pct, ratio = gp.get("pct"), vr.get("ratio")
    b = gp.get("net_gex_b")

    out = {"verdict": "UNKNOWN", "gamma_pct": pct, "net_gex_b": b,
           "vix_ratio": ratio, "prior_date": gp.get("prior_date"),
           "reason": gp.get("reason") or vr.get("reason")}

    if pct is None or ratio is None:
        return out                                   # UNKNOWN is a block, not a pass

    out["reason"] = None
    if pct <= OVERSOLD_PCT and ratio > VIX_AT_HIGHS:
        out["verdict"] = "SQUEEZE_WATCH"
    elif b is not None and b <= DEEP_SHORT_B:
        out["verdict"] = "NO_SELL"
    elif pct >= OVERBOUGHT_PCT:
        out["verdict"] = "SELL_PREMIUM"
    else:
        out["verdict"] = "NEUTRAL"
    return out


def squeeze_outlook(engine: Engine, asof: date,
                    window: int = PCT_WINDOW) -> dict[str, Any]:
    """Where the triggers actually sit, so you can watch a LEVEL not a verdict.

    A verdict alone tells you nothing until the day it flips. What is useful
    before then is: what would gamma have to print to cross, how far is it, is
    it travelling toward the trigger or away, and — for SQUEEZE_WATCH, which
    needs two legs — WHICH leg is missing.

    Returns trigger levels in $bn plus the gap from the current reading, a
    5-session percentile trend, a proximity label, and a per-leg breakdown.
    All None-safe: missing history yields Nones, never a misleading zero.
    """
    from backend.bots.vix_regime import vix_decay_ratio

    out: dict[str, Any] = {
        "oversold_trigger_b": None, "overbought_trigger_b": None,
        "gap_to_oversold_b": None, "gap_to_overbought_b": None,
        "pct_trend_5d": None, "proximity": None,
        "legs": {}, "reason": None,
    }

    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT trade_date, net_gex FROM {GAMMA_DAILY_TABLE} "
            "WHERE trade_date < :d ORDER BY trade_date DESC LIMIT :n"
        ), {"d": asof, "n": window}).fetchall()

    if len(rows) < window:
        out["reason"] = f"insufficient_gamma_history: have={len(rows)} need={window}"
        return out

    cur = float(rows[0][1]) / 1e9
    hist = sorted(float(r[1]) / 1e9 for r in rows)
    # the value that WOULD sit at each threshold in the current window
    lo_i = max(0, int(OVERSOLD_PCT * len(hist)) - 1)
    hi_i = min(len(hist) - 1, int(OVERBOUGHT_PCT * len(hist)))
    lo_trig, hi_trig = hist[lo_i], hist[hi_i]
    out["oversold_trigger_b"] = lo_trig
    out["overbought_trigger_b"] = hi_trig
    out["gap_to_oversold_b"] = cur - lo_trig       # negative once through it
    out["gap_to_overbought_b"] = hi_trig - cur

    gp = gamma_percentile(engine, asof, window)
    pct = gp.get("pct")
    if pct is not None and len(rows) > 5:
        prior5 = [float(r[1]) for r in rows[5:]][:window]
        if len(prior5) >= 20:
            p5 = sum(1 for v in prior5 if float(rows[5][1]) > v) / len(prior5)
            out["pct_trend_5d"] = pct - p5

    if pct is not None:
        if pct <= OVERSOLD_PCT:
            out["proximity"] = "OVERSOLD"
        elif pct <= OVERSOLD_PCT + 0.15:
            out["proximity"] = "APPROACHING_OVERSOLD"
        elif pct >= OVERBOUGHT_PCT:
            out["proximity"] = "OVERBOUGHT"
        elif pct >= OVERBOUGHT_PCT - 0.15:
            out["proximity"] = "APPROACHING_OVERBOUGHT"
        else:
            out["proximity"] = "MID_RANGE"

    # SQUEEZE_WATCH needs BOTH legs. Say which one is short.
    vr = vix_decay_ratio(engine, asof).get("ratio")
    out["legs"] = {
        "gamma_oversold": None if pct is None else bool(pct <= OVERSOLD_PCT),
        "vix_at_highs": None if vr is None else bool(vr > VIX_AT_HIGHS),
        "vix_ratio": vr,
        "vix_gap": None if vr is None else VIX_AT_HIGHS - vr,
    }
    return out


# ---- small shims so this module does not hard-depend on TradierClient internals ----

def _base() -> str:
    from backend.bots.routes_helpers import TRADIER_BASE
    return TRADIER_BASE


def _hdrs() -> dict:
    from backend.bots.routes_helpers import _headers
    return _headers()


def _expirations(client: Any, ticker: str) -> list[str]:
    r = client._client.get(
        f"{_base()}/markets/options/expirations",
        params={"symbol": ticker, "includeAllRoots": "true"},
        headers=_hdrs(),
    )
    if r.status_code != 200:
        return []
    dates = (r.json().get("expirations") or {}).get("date") or []
    if isinstance(dates, str):
        dates = [dates]
    return sorted(dates)
