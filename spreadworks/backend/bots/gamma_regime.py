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

from sqlalchemy import bindparam, text
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
    dollar_vol   DOUBLE PRECISION,
    n_contracts  INTEGER,
    updated_at   TIMESTAMP NOT NULL
)
"""


def ensure_gamma_table(engine: Engine) -> None:
    """Idempotent create. Safe to call every cycle.

    dollar_vol was added after the table shipped, so ADD COLUMN IF NOT EXISTS
    runs too — Postgres only; SQLite tolerates the failure and is dev-only.
    """
    with engine.begin() as conn:
        conn.execute(text(_GAMMA_DDL))
        if engine.dialect.name != "sqlite":
            conn.execute(text(
                f"ALTER TABLE {GAMMA_DAILY_TABLE} "
                "ADD COLUMN IF NOT EXISTS dollar_vol DOUBLE PRECISION"))


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
                 spot: float | None = None, n_contracts: int | None = None,
                 dollar_vol: float | None = None) -> None:
    """Upsert one session's reading, keyed on the date whose CLOSE produced it."""
    if net_gex is None:
        return
    params = {"d": trade_date, "g": float(net_gex),
              "s": float(spot) if spot else None,
              "n": int(n_contracts) if n_contracts else None,
              "v": float(dollar_vol) if dollar_vol else None}
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, dollar_vol, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, :v, :n, CURRENT_TIMESTAMP) "
                "ON CONFLICT(trade_date) DO UPDATE SET net_gex = excluded.net_gex, "
                "spot = excluded.spot, dollar_vol = excluded.dollar_vol, "
                "n_contracts = excluded.n_contracts, updated_at = CURRENT_TIMESTAMP"
            ), params)
        else:
            conn.execute(text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, dollar_vol, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, :v, :n, NOW()) "
                "ON CONFLICT (trade_date) DO UPDATE SET net_gex = EXCLUDED.net_gex, "
                "spot = EXCLUDED.spot, dollar_vol = EXCLUDED.dollar_vol, "
                "n_contracts = EXCLUDED.n_contracts, updated_at = NOW()"
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


# ---------------------------------------------------------------------------
# Intraday break probability by regime cell — P(>1% intraday move), measured
# 2020-01-02 through 2026-08-11 (1,646 sessions). Cells are net_gex sign +
# spot vs the re-solved flip; the two collapse to the SAME variable here (net
# gamma < 0 and spot below flip agree 96.1% of the time — see the module
# docstring), so the sign of net_gex_b alone selects a cell.
# ---------------------------------------------------------------------------
BREAK_CELLS = {
    "short_below_flip": 0.275,   # short gamma, spot below flip
    "long_above_flip": 0.096,    # long gamma, spot above flip
    "deep_short_gamma": 0.333,   # net gamma below -$10B — a subset of short_below_flip
    "sample": "1,646 sessions, 2020-2026",
}


def break_probability(net_gex_b: float | None) -> tuple[float | None, str]:
    """P(SPY moves >1% intraday) for today's regime cell, or (None, "no cell").

    Checked most-specific first: deep short gamma is a SUBSET of "short gamma,
    spot below flip", so it has to win the match rather than the broader cell.
    """
    if net_gex_b is None:
        return None, "no cell"
    if net_gex_b <= DEEP_SHORT_B:
        return BREAK_CELLS["deep_short_gamma"], "deep_short_gamma"
    if net_gex_b < 0:
        return BREAK_CELLS["short_below_flip"], "short_below_flip"
    if net_gex_b > 0:
        return BREAK_CELLS["long_above_flip"], "long_above_flip"
    return None, "no cell"


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
    break_prob, break_cell = break_probability(b)

    out = {"verdict": "UNKNOWN", "gamma_pct": pct, "net_gex_b": b,
           "vix_ratio": ratio, "prior_date": gp.get("prior_date"),
           "break_prob": break_prob, "break_cell": break_cell,
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


def calendar_flags(asof: date) -> dict[str, Any]:
    """Scheduled flow, knowable in advance forever. No news feed required.

    The trigger for a squeeze is not forecastable as NEWS, but a large part of
    it is forecastable as CALENDAR. Measured on oversold days only (base 10.08%
    squeeze rate over 397 sessions):

        month end (>=26th)   25.35%   2.52x   n=71    <- the standout
        quarter end          22.22%   2.21x   n=27
        payrolls Friday      20.00%   1.99x   n=20
        opex week             6.00%   0.60x   n=100   <- SUPPRESSES
        monthly opex day      4.35%   0.43x   n=23    <- SUPPRESSES

    Month-end survives Bonferroni across the 14 catalyst tests run
    (binomial p=0.00018 vs a 0.00357 bar) and beats its own year's oversold
    base in 5 of 7 years. It is NOT uniform: 2024 was 0 of 9 and 2025 was 0 of
    9, against 62.5% in 2020 and 50% in 2026. Treat it as a tilt on top of an
    existing setup, never as a trigger on its own.

    Mechanism, which is why it is plausible rather than mined: month-end forces
    real rebalancing flow (pension and target-date mandates buying equities
    back to weight). Into a beaten-down tape with dealers short gamma, that is
    the match. Opex runs the other way for the same kind of reason — expiry
    removes the gamma, so the accelerant is switched off.
    """
    dom, dow, mon = asof.day, asof.weekday(), asof.month
    is_opex = dow == 4 and 15 <= dom <= 21
    # the Mon-Fri run into monthly opex
    opex_week = dow <= 4 and any(
        (asof + timedelta(days=k)).day >= 15 and (asof + timedelta(days=k)).day <= 21
        and (asof + timedelta(days=k)).weekday() == 4 for k in range(0, 5))
    return {
        "month_end": dom >= 26,
        "quarter_end": dom >= 26 and mon in (3, 6, 9, 12),
        "payrolls_friday": dow == 4 and dom <= 7,
        "opex_day": is_opex,
        "opex_week": opex_week,
    }


def fuel_ratio(engine: Engine, asof: date, window: int = 20) -> dict[str, Any]:
    """Forced dealer hedging per 1% move, as a share of a normal day's volume.

    net_gex IS dollars-per-1%-move, so its MAGNITUDE against SPY's own liquidity
    says whether dealer flow can actually dominate the tape. $17B of forced
    hedging means one thing when SPY trades $33B/day and another at $80B.

    Median across the sample: 9.4% of a normal day. Top sextile: 17.5-56.8%.
    Squeeze rate by fuel sextile runs 0.00 / 0.00 / 0.75 / 2.25 / 7.89 / 9.36%
    — monotone, and the top-quintile-plus-VIX-high cell reaches 16.49% versus
    15.13% for the percentile version that shipped first. Better mechanism,
    slightly better numbers; kept alongside the percentile rather than replacing
    it until it has been watched forward.

    fuel is SIGNED: positive = short gamma = accelerant.
    """
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT net_gex, dollar_vol FROM {GAMMA_DAILY_TABLE} "
            "WHERE trade_date < :d AND dollar_vol IS NOT NULL "
            "ORDER BY trade_date DESC LIMIT :n"
        ), {"d": asof, "n": window}).fetchall()
    if len(rows) < window:
        return {"fuel": None, "adv_b": None,
                "reason": f"insufficient_volume_history: have={len(rows)} need={window}"}
    advs = [float(r[1]) for r in rows if r[1]]
    if not advs:
        return {"fuel": None, "adv_b": None, "reason": "no_volume_data"}
    adv = sum(advs) / len(advs)
    if adv <= 0:
        return {"fuel": None, "adv_b": None, "reason": "bad_adv"}
    return {"fuel": -float(rows[0][0]) / adv, "adv_b": adv / 1e9, "reason": None}


def squeeze_outlook(engine: Engine, asof: date,
                    window: int = PCT_WINDOW,
                    live_gex_b: float | None = None,
                    live_vix_ratio: float | None = None) -> dict[str, Any]:
    """Where the triggers actually sit, so you can watch a LEVEL not a verdict.

    A verdict alone tells you nothing until the day it flips. What is useful
    before then is: what would gamma have to print to cross, how far is it, is
    it travelling toward the trigger or away, and — for SQUEEZE_WATCH, which
    needs two legs — WHICH leg is missing.

    Returns trigger levels in $bn plus the gap from the current reading, a
    5-session percentile trend, a proximity label, and a per-leg breakdown.
    All None-safe: missing history yields Nones, never a misleading zero.

    🚨 LIVE MODE. Pass live_gex_b / live_vix_ratio to recompute the whole card
    from THIS MINUTE instead of the last stored close. Everything here except
    the calendar is a function of the current gamma reading, so there was no
    reason for the panel to sit frozen from 15:05 to 15:05 — the gaps to the
    triggers, which leg is short, the pin band, all of it moves during the
    session and the reader could not see it.

    ⛔ THE TRIGGER LEVELS THEMSELVES STAY HISTORICAL. They are the 20th and 80th
    percentiles of the trailing window, which is by definition made of closes.
    Only the CURRENT reading is swapped. And live mode never writes anything:
    the verdict is still the 15:05 capture, because that is what the backtest
    measured.
    """
    live = live_gex_b is not None
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

    cur = float(live_gex_b) if live else float(rows[0][1]) / 1e9
    hist = sorted(float(r[1]) / 1e9 for r in rows)
    # the value that WOULD sit at each threshold in the current window
    lo_i = max(0, int(OVERSOLD_PCT * len(hist)) - 1)
    hi_i = min(len(hist) - 1, int(OVERBOUGHT_PCT * len(hist)))
    lo_trig, hi_trig = hist[lo_i], hist[hi_i]
    out["oversold_trigger_b"] = lo_trig
    out["overbought_trigger_b"] = hi_trig
    out["gap_to_oversold_b"] = cur - lo_trig       # negative once through it
    out["gap_to_overbought_b"] = hi_trig - cur

    if live:
        # Rank the live reading against the same window the stored one uses.
        pct = sum(1 for v in hist if cur > v) / len(hist)
    else:
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
    vr = (live_vix_ratio if live_vix_ratio is not None
          else vix_decay_ratio(engine, asof).get("ratio"))
    out["legs"] = {
        "gamma_oversold": None if pct is None else bool(pct <= OVERSOLD_PCT),
        "vix_at_highs": None if vr is None else bool(vr > VIX_AT_HIGHS),
        "vix_ratio": vr,
        "vix_gap": None if vr is None else VIX_AT_HIGHS - vr,
    }

    # Fuel: can dealer flow actually dominate the tape today?
    fr = fuel_ratio(engine, asof)
    out["fuel"] = fr.get("fuel")
    out["adv_b"] = fr.get("adv_b")
    out["fuel_reason"] = fr.get("reason")

    # Scheduled flow — the forecastable half of "the match".
    out["calendar"] = calendar_flags(asof)
    out["live"] = live

    # PIN proximity is the mirror question and shares the same number: the
    # higher the percentile, the more dealer hedging damps the tape. Zero
    # squeezes have ever started in the top quartile of the range.
    #
    # The bands must not collide with the verdict. An earlier version called
    # >=0.80 "building", which IS the overbought threshold — so an "approaching
    # pin" alert could only fire once SELL_PREMIUM had already fired, and it
    # duplicated the verdict every time. Caught in test. The approach band is
    # strictly BELOW the trigger:
    #
    #   >= 0.90        strong        deep pin, tape heavily damped
    #   >= 0.80        active        the SELL_PREMIUM zone itself
    #   0.60 - 0.80    approaching   heading toward it, alert-worthy
    #   < 0.60         none
    if pct is not None:
        out["pin_strength"] = (
            "strong" if pct >= 0.90 else
            "active" if pct >= OVERBOUGHT_PCT else
            "approaching" if pct >= 0.60 else "none")
    else:
        out["pin_strength"] = None
    return out


# ---------------------------------------------------------------------------
# Freshness. A verdict is only as current as the row underneath it.
# ---------------------------------------------------------------------------
# gamma_state / gamma_percentile take `ORDER BY trade_date DESC LIMIT 1` and
# use whatever is there, however old. That is correct for the query and wrong
# for the caller: a table that stopped updating a month ago still yields a
# confident SELL_PREMIUM, which contradicts this module's own doctrine that
# UNKNOWN is a block rather than a pass. Staleness is not "no data", so it does
# not become UNKNOWN — but it must never be invisible either.
#
# The two legs are stored separately (sw_gamma_daily, sw_vix_daily) and are
# seeded and captured by different code paths, so they can and do drift apart.
# A two-leg gate reading its legs off different dates is a real defect, not a
# cosmetic one, and `legs_mismatch` is what surfaces it.
MAX_STALE_SESSIONS = 1   # the prior session is fresh; anything older is stale


def sessions_between(a: date, b: date) -> int:
    """Weekdays strictly after `a` through `b` inclusive. 0 if b <= a.

    Market holidays are NOT modelled — there is no holiday calendar in this
    service, so a holiday reads as one session of staleness. That errs toward
    claiming stale when fresh, which is the safe direction for this use.
    """
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def data_freshness(engine: Engine, asof: date) -> dict[str, Any]:
    """How old is the data actually driving the verdict on `asof`?

    Returns the newest stored date for each leg, how many sessions behind the
    expected prior session each one is, and whether the two legs disagree.
    Never raises — a missing table reports as unknown, not as fresh.
    """
    out: dict[str, Any] = {
        "gamma_date": None, "vix_date": None,
        "gamma_stale_sessions": None, "vix_stale_sessions": None,
        "expected_date": None, "stale": None, "legs_mismatch": None,
        "reason": None,
    }

    # The most recent session that SHOULD be stored: the last weekday before
    # asof. Same holiday caveat as sessions_between.
    expected = asof - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    out["expected_date"] = expected

    def _latest(table: str) -> date | None:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT MAX(trade_date) FROM {table}")).fetchone()
        if row is None or row[0] is None:
            return None
        d = row[0]
        return d if isinstance(d, date) else date.fromisoformat(str(d))

    try:
        from backend.bots.vix_regime import VIX_DAILY_TABLE
        g = _latest(GAMMA_DAILY_TABLE)
        v = _latest(VIX_DAILY_TABLE)
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"freshness query error: {e}"
        return out

    out["gamma_date"], out["vix_date"] = g, v
    if g is not None:
        out["gamma_stale_sessions"] = sessions_between(g, expected)
    if v is not None:
        out["vix_stale_sessions"] = sessions_between(v, expected)
    if g is not None and v is not None:
        out["legs_mismatch"] = g != v
    staleness = [s for s in (out["gamma_stale_sessions"],
                             out["vix_stale_sessions"]) if s is not None]
    out["stale"] = bool(staleness and max(staleness) >= MAX_STALE_SESSIONS)

    # PROVENANCE. Rows arrive by two very different routes: the 15:05 capture
    # (a live chain pull) and _auto_seed_from_csv (the committed baseline). The
    # seed leaves n_contracts NULL and the capture sets it, so that column is
    # the discriminator — and it is the only way to answer "has the capture job
    # ever actually run?", which as of this writing is still "no". A page that
    # says "next capture 15:05 CT" while every row it displays came from a CSV
    # is claiming a liveness it does not have.
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                f"SELECT COUNT(*), MAX(trade_date) FROM {GAMMA_DAILY_TABLE} "
                "WHERE n_contracts IS NOT NULL")).fetchone()
        out["captured_sessions"] = int(row[0]) if row and row[0] is not None else 0
        cd = row[1] if row else None
        if cd is not None and not isinstance(cd, date):
            cd = date.fromisoformat(str(cd))
        out["last_capture_date"] = cd
        out["latest_is_capture"] = bool(cd is not None and g is not None and cd == g)
    except Exception as e:  # noqa: BLE001
        out["captured_sessions"] = None
        out["last_capture_date"] = None
        out["latest_is_capture"] = None
        out["provenance_reason"] = f"provenance query error: {e}"

    # WINDOW COMPLETENESS. A hole in the trailing PCT_WINDOW silently distorts
    # every percentile on the page, and the page could not previously tell you
    # whether the CURRENT window had one. Missing sessions are found by
    # differencing against sw_vix_daily rather than by counting weekdays: VIX
    # is an independent series over the same NYSE calendar, so holidays cancel
    # out instead of reading as false gaps.
    try:
        with engine.begin() as conn:
            grows = conn.execute(text(
                f"SELECT trade_date FROM {GAMMA_DAILY_TABLE} "
                "ORDER BY trade_date DESC LIMIT :n"), {"n": PCT_WINDOW}).fetchall()
            gdates = {r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0]))
                      for r in grows}
            if gdates:
                vrows = conn.execute(text(
                    f"SELECT trade_date FROM {VIX_DAILY_TABLE} "
                    "WHERE trade_date >= :lo AND trade_date <= :hi"),
                    {"lo": min(gdates), "hi": max(gdates)}).fetchall()
                vdates = {r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0]))
                          for r in vrows}
                missing = sorted(vdates - gdates)
            else:
                missing = []
        out["window_sessions"] = len(gdates)
        out["window_needed"] = PCT_WINDOW
        out["window_missing"] = missing
        out["window_complete"] = bool(len(gdates) >= PCT_WINDOW and not missing)

        # SOURCE MIXING. The 1,663-row baseline is ORATS/ThetaData-derived:
        # gamma solved locally by Black-Scholes with a parity-implied carry.
        # The 15:05 capture reads Tradier's OWN vendor greeks. The arithmetic
        # is identical on both sides (gamma*OI*100*spot^2*0.01), so any
        # disagreement is in the greeks themselves -- and the one paired
        # observation available reads 6.30B live against 3.50B stored for
        # 2026-08-14, with spot matching to the cent.
        #
        # A percentile is a rank of a value against its own history. Rank a
        # Tradier-derived reading inside a window of ORATS-derived ones and the
        # comparison is between two different measurements of the same thing.
        # This does not block -- one paired reading on a closed market is weak
        # evidence and the capture may well agree once it runs live -- but the
        # moment the window stops being homogeneous, the page and the alert
        # have to say so rather than quietly serving a percentile built on it.
        with engine.begin() as conn:
            srcs = conn.execute(text(
                f"SELECT COUNT(*) FILTER (WHERE n_contracts IS NOT NULL), COUNT(*) "
                f"FROM (SELECT n_contracts FROM {GAMMA_DAILY_TABLE} "
                "ORDER BY trade_date DESC LIMIT :n) t"
                if engine.dialect.name != "sqlite" else
                f"SELECT SUM(CASE WHEN n_contracts IS NOT NULL THEN 1 ELSE 0 END), "
                f"COUNT(*) FROM (SELECT n_contracts FROM {GAMMA_DAILY_TABLE} "
                "ORDER BY trade_date DESC LIMIT :n)"),
                {"n": PCT_WINDOW}).fetchone()
        cap_n = int(srcs[0] or 0)
        tot_n = int(srcs[1] or 0)
        out["window_captured"] = cap_n
        out["window_seeded"] = tot_n - cap_n
        out["window_source_mixed"] = bool(cap_n > 0 and cap_n < tot_n)
    except Exception as e:  # noqa: BLE001
        out["window_sessions"] = None
        out["window_missing"] = None
        out["window_complete"] = None
        out["window_source_mixed"] = None
        out["window_reason"] = f"window query error: {e}"
    return out


# Alert bookkeeping lives in discord_post_log (models.py), keyed by the same
# strings gamma_alerts.py passes to _dedup_ok.
ALERT_KEYS = {
    "gamma_capture": "capture",
    "squeeze_signal": "verdict alert",
    "squeeze_proximity_watch": "approaching-squeeze alert",
    "squeeze_proximity_pin": "approaching-pin alert",
}


def job_status(engine: Engine) -> dict[str, Any]:
    """When each scheduled job last actually fired.

    The page advertises "next capture 15:05 CT" and "next alert 08:05 CT" with
    no way to see whether either has ever run — precisely the blind spot the
    freshness work exists to close. Reads the dedup ledger the jobs already
    write, so it needs no new bookkeeping.

    Never raises: a missing table reports as unknown, which must not read the
    same as "ran fine".
    """
    out: dict[str, Any] = {"last": {}, "reason": None}
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT message_key, MAX(fire_date) FROM discord_post_log "
                "WHERE message_key IN :keys GROUP BY message_key"
            ).bindparams(bindparam("keys", expanding=True)),
                {"keys": list(ALERT_KEYS)}).fetchall()
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"job_status query error: {e}"
        return out
    for k, d in rows:
        if d is not None and not isinstance(d, date):
            d = date.fromisoformat(str(d))
        out["last"][k] = d
    return out


SPREAD_WIDTH = 2.0        # $2 wide, the width the sell side was validated at
SHORT_OFFSET = 2.0        # short strike sits round(spot) - 2
BUY_DELTA = 0.25          # NOT at-the-money: 0.50 delta LOSES $43/trade
BUY_DTE_MIN, BUY_DTE_MAX = 5, 9


def trade_ticket(engine: Engine, asof: date,
                 live_spot: float | None = None) -> dict[str, Any]:
    """The actual strikes, not the formula.

    "short strike round(spot) - 2, $2 wide" is a rule, and a rule is not a
    ticket -- it still leaves arithmetic between the page and the order. This
    resolves it to numbers.

    The strike is a function of spot, and spot moves, so the honest version
    carries WHICH spot it used and when that stops being true: the entry is
    11:05 ET and the real strike derives from spot at that moment. A ticket
    computed off the prior close is indicative, and says so.

    Never raises -- a missing spot yields nulls, never a plausible-looking
    strike computed from nothing.
    """
    out: dict[str, Any] = {"spot": None, "spot_source": None, "sell": None,
                           "buy": None, "reason": None}
    spot, source = live_spot, "live"
    if spot is None:
        try:
            with engine.begin() as conn:
                row = conn.execute(text(
                    f"SELECT trade_date, spot FROM {GAMMA_DAILY_TABLE} "
                    "WHERE spot IS NOT NULL ORDER BY trade_date DESC LIMIT 1"
                )).fetchone()
            if row is not None and row[1] is not None:
                spot = float(row[1])
                source = f"{_isodate(row[0])} close"
        except Exception as e:  # noqa: BLE001
            out["reason"] = f"spot lookup error: {e}"
            return out
    if not spot or spot <= 0:
        out["reason"] = "no spot available"
        return out

    short_put = round(spot) - SHORT_OFFSET
    out["spot"] = round(float(spot), 2)
    out["spot_source"] = source
    out["sell"] = {
        "structure": "SPY 0DTE put spread",
        "short_put": short_put,
        "long_put": short_put - SPREAD_WIDTH,
        "width": SPREAD_WIDTH,
        "entry_ct": "10:05",          # 11:05 ET
        "exit": "hold to settlement, no stop",
    }
    out["buy"] = {
        "structure": "SPY call, long",
        "target_delta": BUY_DELTA,
        "dte_min": BUY_DTE_MIN,
        "dte_max": BUY_DTE_MAX,
        "hold_sessions": 5,
        # The strike is a DELTA, not an offset, so it cannot be derived from
        # spot alone -- it needs the chain. Naming the qualifying expiries is
        # the part that IS knowable in advance.
        "expiries": [(asof + timedelta(days=d)).isoformat()
                     for d in range(BUY_DTE_MIN, BUY_DTE_MAX + 1)
                     if (asof + timedelta(days=d)).weekday() < 5],
    }
    return out


def _isodate(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def capture_health(freshness: dict[str, Any], jobs: dict[str, Any]) -> dict[str, Any]:
    """Did the capture job CLAIM a slot without STORING anything?

    `_dedup_ok` is called at the TOP of capture_gamma, before the chain pull
    is attempted, because its job is to stop two replicas doing the same work.
    That makes the ledger a record of "this job claimed today", NOT of "this
    job succeeded" — so a capture that claims the slot and then dies on a
    Tradier error leaves a ledger entry and no row, and a naive "last fired"
    readout would report it as healthy.

    Comparing the claim against sw_gamma_daily's own newest CAPTURED row is
    what separates the two. This is the exact silent-failure shape that let a
    four-session-stale reading sit on the page wearing today's date.

    Returns {"state", "claimed", "stored", "detail"} where state is one of
    never_run | ok | claimed_but_not_stored | unknown.
    """
    claimed = (jobs or {}).get("last", {}).get("gamma_capture")
    stored = (freshness or {}).get("last_capture_date")
    if (jobs or {}).get("reason") or freshness.get("provenance_reason"):
        return {"state": "unknown", "claimed": claimed, "stored": stored,
                "detail": "Job or provenance lookup failed — not a clean bill."}
    if claimed is None:
        return {"state": "never_run", "claimed": None, "stored": stored,
                "detail": "The capture job has never claimed a session."}
    if stored is not None and str(stored) >= str(claimed):
        return {"state": "ok", "claimed": claimed, "stored": stored,
                "detail": None}
    return {"state": "claimed_but_not_stored", "claimed": claimed, "stored": stored,
            "detail": (f"Capture claimed {claimed} but the newest stored reading "
                       f"is {stored or 'none'} — the job ran and wrote nothing.")}


# ---------------------------------------------------------------------------
# Signal history — the verdict this signal WOULD have printed, session by
# session, so the page can show a track record rather than only today's state.
# ---------------------------------------------------------------------------
def signal_history(engine: Engine, n: int = 90,
                   window: int = PCT_WINDOW) -> list[dict[str, Any]]:
    """Per-session verdict for the last `n` stored sessions.

    Each row is keyed by the gamma session's OWN trade_date and carries the
    verdict that session's close produced — i.e. the verdict that was
    actionable the NEXT morning, which is exactly how gamma_alerts.py consumes
    it (15:05 CT capture, 08:05 CT alert). It is NOT the verdict in force
    during that session.

    Verdict logic is not re-implemented here; it is the same ladder as
    squeeze_signal, applied to a stored row instead of the latest one. If that
    ladder ever changes, change it in both places or this chart starts lying
    about its own history.
    """
    from backend.bots.vix_regime import MIN_HISTORY, VIX_DAILY_TABLE, WINDOW

    with engine.begin() as conn:
        grows = conn.execute(text(
            f"SELECT trade_date, net_gex FROM {GAMMA_DAILY_TABLE} "
            "ORDER BY trade_date DESC LIMIT :n"
        ), {"n": n + window}).fetchall()
        vrows = conn.execute(text(
            f"SELECT trade_date, vix FROM {VIX_DAILY_TABLE} "
            "ORDER BY trade_date DESC LIMIT :n"
        ), {"n": n + MIN_HISTORY}).fetchall()

    g = sorted(((r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])),
                 float(r[1])) for r in grows), key=lambda t: t[0])
    v = sorted(((r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])),
                 float(r[1])) for r in vrows), key=lambda t: t[0])
    vix_by_date = {d: x for d, x in v}
    vix_dates = [d for d, _ in v]
    # position index, so the per-session lookup below is O(1) rather than a
    # list scan inside the loop
    vix_pos = {d: i for i, d in enumerate(vix_dates)}

    out: list[dict[str, Any]] = []
    for i, (d, net_gex) in enumerate(g):
        if i + 1 < window:
            continue                                  # percentile undefined
        hist = [x for _, x in g[i - window + 1:i + 1]]
        pct = sum(1 for x in hist if net_gex > x) / len(hist)
        b = net_gex / 1e9

        # VIX ratio for this same session: vix(d) / max(vix over the WINDOW
        # sessions before d) — the definition vix_decay_ratio uses, one day
        # shifted because there the "prior session" IS this row.
        ratio = None
        if d in vix_by_date:
            j = vix_pos[d]
            if j >= WINDOW:
                wmax = max(vix_by_date[x] for x in vix_dates[j - WINDOW:j])
                if wmax > 0:
                    ratio = vix_by_date[d] / wmax

        if ratio is None:
            verdict = "UNKNOWN"
        elif pct <= OVERSOLD_PCT and ratio > VIX_AT_HIGHS:
            verdict = "SQUEEZE_WATCH"
        elif b <= DEEP_SHORT_B:
            verdict = "NO_SELL"
        elif pct >= OVERBOUGHT_PCT:
            verdict = "SELL_PREMIUM"
        else:
            verdict = "NEUTRAL"

        out.append({"trade_date": d, "net_gex_b": b, "pct": pct,
                    "vix_ratio": ratio, "verdict": verdict})
    return out[-n:]


SPY_DAILY_TABLE = "sw_spy_daily"
# Widest calendar gap that can still be ONE session: Friday to the Tuesday
# after a Monday holiday, or Thursday to the Monday after Good Friday.
MAX_NEXT_SESSION_GAP_DAYS = 4


def attach_forward_returns(engine: Engine, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Tag each `signal_history` row with `fwd1_pct`: the NEXT session's SPY
    close over THIS session's close, minus 1. Read from sw_spy_daily's own
    closes only.

    🚨 NEVER sw_gamma_daily.spot or the ORAT baseline's `spot` column — see the
    module docstring: those are a forward mark solved off the option chain,
    not a settle, and using them here would silently swap in a different
    number under the same name.

    Mutates `rows` in place (adds "fwd1_pct", float or None) and returns the
    coverage the page prints alongside the strip. sw_spy_daily is populated
    live from Tradier in a trailing window (see routes_calls._refresh_spy), so
    a wide range routinely has sessions with no close on file yet — those are
    left as None, never zero-filled, and the caller omits them from the strip
    rather than plotting a manufactured "no move".
    """
    coverage: dict[str, Any] = {"sessions_with_fwd": 0, "sessions_total": len(rows),
                                "first_date": None, "last_date": None}
    if not rows:
        return coverage

    def _d(x: Any) -> date:
        return x if isinstance(x, date) else date.fromisoformat(str(x))

    dates = [_d(r["trade_date"]) for r in rows]
    lo, hi = min(dates), max(dates)
    with engine.begin() as conn:
        spy_rows = conn.execute(text(
            f"SELECT trade_date, close FROM {SPY_DAILY_TABLE} "
            "WHERE trade_date >= :lo AND trade_date <= :hi AND close IS NOT NULL "
            "ORDER BY trade_date"
        ), {"lo": lo, "hi": hi + timedelta(days=10)}).fetchall()
    spy = sorted((_d(r[0]), float(r[1])) for r in spy_rows)
    close_by_date = dict(spy)
    ordered_dates = [d for d, _ in spy]
    pos = {d: i for i, d in enumerate(ordered_dates)}

    # What counts as "the next session" is decided by TWO calendars agreeing:
    # the next row in sw_spy_daily and the next row in the signal history
    # itself (which is the gamma table's own session list). A hole in either
    # table would otherwise turn this into a two-session return wearing the
    # same name. When both tables skip the same weekday it is treated as a
    # holiday — there is no holiday calendar in this service and that is the
    # only evidence available. The calendar-gap cap is belt and braces on top:
    # Fri -> Tue across a Monday holiday is the widest real gap there is.
    row_dates = sorted(set(dates))
    next_row = {a: b for a, b in zip(row_dates, row_dates[1:])}

    n_fwd = 0
    covered: list[date] = []
    for r, d in zip(rows, dates):
        fwd = None
        c0 = close_by_date.get(d)
        i = pos.get(d)
        if c0 and i is not None and i + 1 < len(ordered_dates):
            d1 = ordered_dates[i + 1]
            c1 = close_by_date[d1]
            if (c1 and next_row.get(d) == d1
                    and (d1 - d).days <= MAX_NEXT_SESSION_GAP_DAYS):
                fwd = (c1 / c0) - 1
        r["fwd1_pct"] = fwd
        if fwd is not None:
            n_fwd += 1
            covered.append(d)

    coverage["sessions_with_fwd"] = n_fwd
    if covered:
        coverage["first_date"] = min(covered)
        coverage["last_date"] = max(covered)
    return coverage


def signal_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Track-record roll-up over `signal_history` rows.

    `sessions_in_state` counts the CURRENT unbroken run, so a page can say
    "11 sessions in SELL_PREMIUM" instead of only naming the state.
    """
    out: dict[str, Any] = {
        "counts": {}, "last_squeeze_watch": None, "last_no_sell": None,
        "sessions_in_state": None, "current": None, "n": len(rows),
        "first_date": None, "last_date": None,
    }
    if not rows:
        return out
    for r in rows:
        out["counts"][r["verdict"]] = out["counts"].get(r["verdict"], 0) + 1
    for r in reversed(rows):
        if out["last_squeeze_watch"] is None and r["verdict"] == "SQUEEZE_WATCH":
            out["last_squeeze_watch"] = r["trade_date"]
        if out["last_no_sell"] is None and r["verdict"] == "NO_SELL":
            out["last_no_sell"] = r["trade_date"]
    cur = rows[-1]["verdict"]
    run = 0
    for r in reversed(rows):
        if r["verdict"] != cur:
            break
        run += 1
    out["current"] = cur
    out["sessions_in_state"] = run
    out["first_date"] = rows[0]["trade_date"]
    out["last_date"] = rows[-1]["trade_date"]
    return out


def vix_history(engine: Engine, n: int = 90) -> list[dict[str, Any]]:
    """Last `n` sessions of VIX with each session's own decay ratio.

    The VIX leg has been a bare number on the page with no history behind it
    while the gamma leg got a 90-session chart. Same series, same shape, so
    the missing leg can be seen rather than asserted.
    """
    from backend.bots.vix_regime import VIX_DAILY_TABLE, WINDOW

    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT trade_date, vix FROM {VIX_DAILY_TABLE} "
            "ORDER BY trade_date DESC LIMIT :n"
        ), {"n": n + WINDOW}).fetchall()

    v = sorted(((r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])),
                 float(r[1])) for r in rows), key=lambda t: t[0])
    out: list[dict[str, Any]] = []
    for i, (d, vix) in enumerate(v):
        ratio = None
        if i >= WINDOW:
            wmax = max(x for _, x in v[i - WINDOW:i])
            if wmax > 0:
                ratio = vix / wmax
        out.append({"trade_date": d, "vix": vix, "ratio": ratio})
    return out[-n:]


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
