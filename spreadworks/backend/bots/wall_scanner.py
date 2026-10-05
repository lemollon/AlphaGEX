"""Wall Scanner — descriptive-only GEX wall distances, MARKET-WIDE (2026-09-11).

CLOSED DECISION, do not relitigate: single-name flow-mix continuation FAILS
placebo (memory `flowmix-singlename-fails.md`, PREREG_FLOWMIX_SINGLENAME).
GEX walls are also not levels — SPY placebo-tested 5x, single names now
tested too, same conclusion. So this module makes NO directional call. It
reports, per ticker: spot, the nearest call wall above spot and put wall
below spot (by |net GEX|), the $ / % distance to each, ticker-wide open
interest / $-per-1%-move context, the 1-day options-implied expected move
(for "is this distance even plausible today" context), and — via the
history table below — whether OI/GEX at the closest wall has grown since
the last few captures. None of this is a verdict on whether the wall holds
or breaks; it is the raw ingredients so the viewer can judge that
themselves. If a future signal earns an actual directional call, it ships
as a separate, explicitly-validated surface — never bolted onto this one.

SCANNER, not a fixed basket (corrected 2026-09-11 — the original 8-ticker
list from the flowmix research was a dashboard, not a scanner). The
universe is TradingVolatility's own `/top-setups` cross-sectional roster:
that endpoint only carries names TV actively snapshots options structure
for, which is itself a liquid/optionable filter — "the whole stock market
that has options and is liquid" as far as any data vendor can define it.
Results are sorted by tightest $ gap to either wall first (the closest
thing to "scan for something notable" this descriptive-only page can do
without making a call).

Data source: TradingVolatility v2 `/top-setups` (universe),
`/tickers/{ticker}/curves/gex_by_strike` (per-ticker wall data), and
`/tickers/{ticker}/levels` (1-day expected-move bounds) — same base URL +
Bearer auth pattern as `tsunami/data/tv_client.py`.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_TIMEOUT = 20
# TV's documented max for /top-setups.
_UNIVERSE_LIMIT = 200
# Workers can be generous again (2026-09-11) because the real limiter is
# _pace() below, not thread count. Retry-with-backoff alone (first fix,
# same day) DID recover every ticker but took 135s for one scan -- reacting
# to a 429 after the fact is much slower than never sending the burst that
# triggers one. TV's actual rate limit isn't documented anywhere we have
# access to, so _MIN_REQUEST_INTERVAL is a conservative guess, not a known
# figure -- tighten it further if 429s reappear in the logs.
_MAX_WORKERS = 10
# A full scan is ~100 sequential-cost HTTP calls (gex_by_strike + levels per
# ticker) even with concurrency — cache it rather than pay that on every page
# load. Same lazy-refresh shape as routes_squeeze.py's _INTRADAY_CACHE. The
# scheduled capture job (backend/__init__.py) keeps this warm in practice;
# this TTL is the fallback for whenever that hasn't run yet.
_CACHE_TTL = 300
_cache: dict[str, Any] = {"ts": 0.0, "payload": None}

# ── ThetaData options-liquidity gate (2026-10-05) ────────────────────────
# TV's /top-setups roster is a liquid/optionable filter only in the sense
# that TV itself covers the name — it is NOT a tradable-chain-volume filter,
# and its payload has no volume/liquidity field at all. Confirmed live via
# ThetaData the day this gate was built: of TV's ~50-name roster, median
# single-day option volume (nearest listed expiration, summed across the
# whole chain) was only ~42 contracts, and 26 of 50 names had under 50
# contracts/day. Only a handful cleared 500+/day. Without this gate the
# scanner routinely surfaces walls built on markets nobody could actually
# trade into. Tune this threshold here if production experience says it's
# too tight or too loose — this exact number is a judgment call, not a
# measured edge.
MIN_LIQUID_VOLUME_PER_DAY = 500

# 2026-10-05: KILL SWITCH. Hard-disabled after this gate correlated with a
# production crash loop (spreadworks-backend 502s) even after the
# probe-first/short-TTL hotfix -- the scheduled wall_scanner_capture job
# appears to run once right at process startup, and a slow/hanging
# ThetaData probe at exactly that moment is suspected of delaying the
# app's readiness past Render's own health-check window. fetch_universe()
# falls back to TV's raw, unfiltered roster while this is False. Flip back
# to True only after the gate is hardened to run off the startup path
# (e.g. skip entirely on a job's first post-boot firing, or a hard
# wall-clock timeout independent of ThetaData's own retry logic).
LIQUIDITY_GATE_ENABLED = False

_THETA_BASE = "http://127.0.0.1:25510"  # NEVER localhost (::1 -> HTTP 476)
_THETA_HEADERS = {"Host": "127.0.0.1:25510", "Connection": "close"}
_THETA_TIMEOUT = 20

# ticker -> (volume or None, checked_at monotonic). 12h TTL: liquidity is a
# structural property of a name, not something that moves intraday, so
# there's no need to re-hit ThetaData every scan cycle.
_LIQUIDITY_CACHE_TTL = 12 * 3600
# A cached UNKNOWN (ThetaData was unreachable) gets a much shorter TTL --
# see _liquidity_ok()'s own docstring, 2026-10-05.
_LIQUIDITY_UNKNOWN_CACHE_TTL = 5 * 60
_liquidity_cache: dict[str, tuple[Optional[float], float]] = {}


def _theta_get(path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Single ThetaData Terminal call. Returns the parsed JSON body, or None
    for anything that is NOT a confirmed-empty 472/empty-response (i.e. a
    genuine connection failure, timeout, or malformed body) — the caller is
    responsible for telling "no data" (472 / empty response, handled inline
    at the call site) apart from "unknown" (this None)."""
    try:
        resp = requests.get(
            f"{_THETA_BASE}{path}",
            params=params,
            headers=_THETA_HEADERS,
            timeout=_THETA_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[wall_scanner] thetadata %s failed: %r", path, exc)
        return None

    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[wall_scanner] thetadata %s bad json: %r", path, exc)
            return None
    if resp.status_code == 472:
        # Documented Terminal convention: no data for THIS request. A real
        # fact (zero), not an error — the caller treats this as volume 0.0.
        return {"response": []}

    logger.debug("[wall_scanner] thetadata %s http %s", path, resp.status_code)
    return None


def _last_completed_session(today: Optional[datetime] = None) -> str:
    """Most recently completed trading session as YYYYMMDD. Simple weekday
    walk-back — exact holiday precision doesn't matter for a liquidity gate,
    this only needs to land on a day the chain plausibly traded."""
    now = today or datetime.now(dt_timezone.utc)
    d = now.date()
    # Before/at today's session is "in progress" or hasn't started -- step
    # back to the prior weekday regardless, then walk off weekends.
    from datetime import timedelta
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d = d - timedelta(days=1)
    return d.strftime("%Y%m%d")


def _thetadata_chain_volume(ticker: str) -> Optional[float]:
    """Total whole-chain contract volume on `ticker`'s nearest listed
    expiration, for the most recently completed trading session. None means
    genuinely unknown (ThetaData unreachable / malformed response) — never
    conflated with a confirmed 0.0 (no expirations listed, or a 472/empty
    volume response are both real, legitimately-illiquid zeros)."""
    exp_payload = _theta_get("/v2/list/expirations", {"root": ticker})
    if exp_payload is None:
        return None
    expirations = exp_payload.get("response") if isinstance(exp_payload, dict) else None
    if not expirations:
        return 0.0  # confirmed fact: no listed expirations at all

    today_int = int(datetime.now(dt_timezone.utc).strftime("%Y%m%d"))
    upcoming = sorted(e for e in expirations if isinstance(e, int) and e >= today_int)
    nearest_exp = upcoming[0] if upcoming else sorted(expirations)[-1]

    session = _last_completed_session()
    chain_payload = _theta_get(
        "/v2/bulk_hist/option/ohlc",
        {
            "root": ticker,
            "exp": nearest_exp,
            "start_date": session,
            "end_date": session,
            "ivl": 60000,
        },
    )
    if chain_payload is None:
        return None
    entries = chain_payload.get("response") if isinstance(chain_payload, dict) else None
    if not entries:
        return 0.0  # confirmed fact: 472/empty -- no chain volume that session

    total = 0.0
    for entry in entries:
        ticks = entry.get("ticks") if isinstance(entry, dict) else None
        if not ticks:
            continue
        for tick in ticks:
            try:
                total += float(tick[4])
            except (IndexError, TypeError, ValueError):
                continue
    return total


def _liquidity_ok(ticker: str) -> Optional[bool]:
    """Cached/fresh liquidity verdict for `ticker`. None propagates an
    unknown volume (ThetaData unreachable) rather than coercing it to False
    -- callers decide separately how to treat an unknown.

    A cached UNKNOWN (volume is None) uses a much shorter TTL
    (_LIQUIDITY_UNKNOWN_CACHE_TTL) than a cached real volume -- a confirmed
    liquid/illiquid verdict is stable for hours, but "ThetaData was
    unreachable a moment ago" must not block re-probing for the full 12h
    once the Terminal recovers, or this gate would keep believing it's still
    down long after it's back."""
    now = time.monotonic()
    cached = _liquidity_cache.get(ticker)
    if cached is not None:
        cached_volume, cached_at = cached
        ttl = _LIQUIDITY_UNKNOWN_CACHE_TTL if cached_volume is None else _LIQUIDITY_CACHE_TTL
        if (now - cached_at) < ttl:
            volume = cached_volume
        else:
            volume = _thetadata_chain_volume(ticker)
            _liquidity_cache[ticker] = (volume, now)
    else:
        volume = _thetadata_chain_volume(ticker)
        _liquidity_cache[ticker] = (volume, now)
    if volume is None:
        return None
    return volume >= MIN_LIQUID_VOLUME_PER_DAY

# ── History (for "is OI/GEX building at the wall") ──────────────────────
# One row per ticker per capture, for whichever wall was closest at that
# moment. A wall's STRIKE can itself change between captures (the tightest
# side can flip, or the strike with the biggest concentration can move) —
# when that happens there is simply no matching prior row for the new
# strike, and the delta reads as "no history yet" rather than a fabricated
# comparison across different strikes.
HISTORY_TABLE = "wall_scanner_snapshots"

_HISTORY_DDL = f"""
CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
    id           BIGSERIAL PRIMARY KEY,
    ticker       VARCHAR(16) NOT NULL,
    side         VARCHAR(4) NOT NULL,
    strike       DOUBLE PRECISION NOT NULL,
    net_gex      DOUBLE PRECISION,
    call_oi_sum  DOUBLE PRECISION,
    put_oi_sum   DOUBLE PRECISION,
    spot         DOUBLE PRECISION,
    captured_at  TIMESTAMPTZ NOT NULL
)
"""
_HISTORY_INDEX_DDL = (
    f"CREATE INDEX IF NOT EXISTS idx_{HISTORY_TABLE}_ticker_side_time "
    f"ON {HISTORY_TABLE} (ticker, side, captured_at)"
)


def ensure_history_table(engine: Engine) -> None:
    """Idempotent create. Safe to call every capture."""
    with engine.begin() as conn:
        conn.execute(text(_HISTORY_DDL))
        conn.execute(text(_HISTORY_INDEX_DDL))


def _base_url() -> str:
    return (
        os.environ.get("TRADING_VOLATILITY_V2_BASE_URL", "").strip()
        or "https://stocks.tradingvolatility.net/api/v2"
    )


def _token() -> str:
    return (
        os.environ.get("TRADING_VOLATILITY_API_TOKEN", "").strip()
        or os.environ.get("TRADING_VOLATILITY_API_KEY", "").strip()
    )


_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BASE_DELAY = 0.75  # seconds; doubles each retry (0.75, 1.5, 3, 6)

# ── Global pacer ─────────────────────────────────────────────────────────
# Proactive, not reactive: cap how often ANY thread may fire a TV request,
# regardless of _MAX_WORKERS. The retry-with-backoff below still exists as a
# safety net, but paced requests shouldn't need it in the normal case — a
# scan that recovers from a 429 storm one retry at a time (measured: 135s
# for 50 tickers) is much slower than a scan that never triggers the storm.
# ~6.7 req/sec is a conservative guess at TV's real limit, which isn't
# documented anywhere we have access to; tighten _MIN_REQUEST_INTERVAL if
# 429s show up in the logs again, loosen it if a scan ever feels too slow.
_MIN_REQUEST_INTERVAL = 0.15
_pace_lock = threading.Lock()
_last_request_at = [0.0]


def _pace() -> None:
    with _pace_lock:
        now = time.monotonic()
        wait = _last_request_at[0] + _MIN_REQUEST_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last_request_at[0] = time.monotonic()


def _get(path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    token = _token()
    if not token:
        logger.info("[wall_scanner] no TV token set — %s unavailable", path)
        return None
    delay = _RATE_LIMIT_BASE_DELAY
    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        _pace()
        try:
            resp = requests.get(
                f"{_base_url().rstrip('/')}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[wall_scanner] %s failed: %r", path, exc)
            return None

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429 and attempt < _RATE_LIMIT_RETRIES:
            # Honor a Retry-After header if TV sends one; otherwise our own
            # exponential backoff. This is what actually fixes the 2026-09-11
            # regression (dropping _MAX_WORKERS alone just makes it rarer).
            wait = float(resp.headers.get("Retry-After", delay))
            logger.info("[wall_scanner] %s 429, retry %d/%d after %.1fs", path, attempt + 1, _RATE_LIMIT_RETRIES, wait)
            time.sleep(wait)
            delay *= 2
            continue

        logger.warning("[wall_scanner] %s http %s", path, resp.status_code)
        return None
    return None


def fetch_universe(limit: int = _UNIVERSE_LIMIT) -> list[str]:
    """TV's covered, liquid, optionable universe — the scan target.

    /top-setups returns TV's most recent snapshot per ticker (36h recency
    window); we only want which tickers exist, not the opportunity ranking
    it computes (that's a different, directional feature this page does not
    make). min_score=0 + no other filters pulls the full roster it tracks.
    """
    payload = _get("/top-setups", {"limit": limit, "min_score": 0})
    if payload is None:
        return []
    data = payload.get("data", payload) if isinstance(payload, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        # Silent-empty is the failure mode a 200-with-unexpected-shape produces
        # (e.g. a tier/scope restriction returning an empty/different body
        # instead of an HTTP error) — log what we actually got instead of
        # guessing at the schema a second time.
        logger.warning(
            "[wall_scanner] /top-setups: no items[] found. top-level keys=%r, "
            "data type=%r, sample=%r",
            list(payload.keys()) if isinstance(payload, dict) else type(payload),
            type(data),
            str(payload)[:500],
        )
        return []
    tickers = [it.get("ticker") for it in items if isinstance(it, dict) and it.get("ticker")]
    if not tickers:
        logger.warning("[wall_scanner] /top-setups: items[] present but empty of tickers, len=%d", len(items))
        return []
    tickers = sorted(set(tickers))
    if not LIQUIDITY_GATE_ENABLED:
        return tickers
    return _filter_liquid_universe(tickers)


def _filter_liquid_universe(tickers: list[str]) -> list[str]:
    """Gate TV's raw roster through a real ThetaData chain-volume check,
    concurrently (same ThreadPoolExecutor/_MAX_WORKERS shape run_scan() uses
    -- one concurrency idiom in this file, not two). Infrastructure failure
    (ThetaData unreachable for every candidate) must never blank the
    scanner, so that case falls back to the unfiltered TV roster rather than
    returning an empty universe.

    2026-10-05: a SINGLE cheap probe runs FIRST, before the 10-way concurrent
    sweep over all 50 candidates. The in-memory _liquidity_cache resets on
    every process restart, and this gate runs inside the scheduled capture
    job -- during a real ThetaData outage, a restarting instance was piling
    10 concurrent fresh connection attempts onto an already-struggling
    Terminal on every single restart, which plausibly made the outage worse
    and contributed to a production incident (spreadworks-backend 502s).
    One failed probe now skips the other 49 calls entirely for this cycle.
    """
    if not tickers:
        return tickers
    probe_ticker = tickers[0]
    if _liquidity_ok(probe_ticker) is None:
        logger.warning(
            "[wall_scanner] liquidity gate: probe ticker %s unreachable, "
            "skipping the other %d candidates this cycle, falling back to "
            "unfiltered TV roster",
            probe_ticker, len(tickers) - 1,
        )
        return tickers

    verdicts: dict[str, Optional[bool]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_liquidity_ok, t): t for t in tickers}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                verdicts[t] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.debug("[wall_scanner] liquidity check %s raised: %r", t, exc)
                verdicts[t] = None

    if all(v is None for v in verdicts.values()):
        logger.warning(
            "[wall_scanner] liquidity gate: ThetaData unreachable for all %d candidates, "
            "falling back to unfiltered TV roster",
            len(tickers),
        )
        return tickers

    passed = [t for t in tickers if verdicts.get(t) is True]
    logger.info(
        "[wall_scanner] liquidity gate: %d of %d TV tickers passed (>= %d contracts/day)",
        len(passed), len(tickers), MIN_LIQUID_VOLUME_PER_DAY,
    )
    return passed


def _top_walls(points: list[dict[str, Any]], spot: float, side: str, n: int = 3) -> list[dict[str, Any]]:
    """Top-N strikes on `side` of spot, ranked by signed net GEX extremum.

    'Wall' = strikes with the largest |net GEX| — where dealer positioning
    currently concentrates, not a predicted turning point (see module
    docstring). Calls rank by largest POSITIVE net (descending); puts rank
    by largest NEGATIVE net (ascending) — same convention as the original
    single-wall pick, generalized to a top-N list so a second concentration
    building just past the primary wall is visible instead of discarded.
    """
    if side == "call":
        candidates = [p for p in points if p.get("strike") is not None and p.get("net") is not None and p["strike"] > spot]
        candidates.sort(key=lambda p: p["net"], reverse=True)
    else:
        candidates = [p for p in points if p.get("strike") is not None and p.get("net") is not None and p["strike"] < spot]
        candidates.sort(key=lambda p: p["net"])
    return candidates[:n]


def _fetch_levels(ticker: str) -> Optional[dict[str, float]]:
    """1-day options-implied expected-move bounds — context for "is the $
    distance to the wall even a plausible move today", not a forecast."""
    payload = _get(f"/tickers/{ticker}/levels", {})
    if payload is None:
        return None
    data = payload.get("data", payload) if isinstance(payload, dict) else None
    levels = data.get("levels") if isinstance(data, dict) else None
    if not isinstance(levels, list):
        return None
    by_name = {lv.get("name"): lv.get("price") for lv in levels if isinstance(lv, dict)}
    plus1, minus1 = by_name.get("plus_1s_1d"), by_name.get("minus_1s_1d")
    if plus1 is None or minus1 is None:
        return None
    return {"plus_1s_1d": plus1, "minus_1s_1d": minus1}


def scan_ticker(ticker: str) -> dict[str, Any]:
    # nearest, not combined (2026-09-11, Leron: "focus on weekly strikes") --
    # combined blends in far-dated OI/gamma that isn't relevant to near-term
    # price action. "first_weekly" is documented for the /curves/gamma
    # endpoint but NOT for /curves/gex_by_strike (only combined | nearest |
    # first_monthly are valid there -- confirmed the hard way: first_weekly
    # made every ticker come back empty). "nearest" is the front expiration,
    # i.e. the weekly for any liquid name that has one.
    payload = _get(f"/tickers/{ticker}/curves/gex_by_strike", {"exp": "nearest"})
    if payload is None:
        return {"ticker": ticker, "available": False}

    # Same cached value the universe gate (fetch_universe -> _liquidity_ok)
    # already populated for this scan cycle -- reuse it rather than paying a
    # second ThetaData round trip. A ticker that somehow reaches here without
    # a cache entry (shouldn't normally happen, the gate runs first) is
    # fetched fresh so this field is never silently null.
    cached = _liquidity_cache.get(ticker)
    near_exp_chain_volume = cached[0] if cached is not None else _thetadata_chain_volume(ticker)

    data = payload.get("data", payload) if isinstance(payload, dict) else None
    points = data.get("points") if isinstance(data, dict) else None
    spot = data.get("price") if isinstance(data, dict) else None
    asof = data.get("asof") if isinstance(data, dict) else None
    totals = data.get("totals") if isinstance(data, dict) else None
    totals = totals if isinstance(totals, dict) else {}

    if not spot or not points:
        return {"ticker": ticker, "available": False}

    def _fmt(p: dict[str, Any], is_call: bool) -> dict[str, Any]:
        dollars = (p["strike"] - spot) if is_call else (spot - p["strike"])
        return {
            "strike": p["strike"],
            "net_gex": p["net"],
            "dollars_to_break": round(dollars, 2),
            "pct_to_break": round(dollars / spot * 100, 2),
        }

    call_walls = [_fmt(p, True) for p in _top_walls(points, spot, "call")]
    put_walls = [_fmt(p, False) for p in _top_walls(points, spot, "put")]

    levels = _fetch_levels(ticker)
    expected_move_1d = (
        round((levels["plus_1s_1d"] - levels["minus_1s_1d"]) / 2, 2) if levels else None
    )

    # Gamma regime — TV's own deterministic classification (their
    # /agent/trade-setup docs: "positive when spot > flip, negative when
    # spot < flip"), computed from a field (gex_flip_price) already in the
    # totals we fetch for the wall calc. This is a FACT about current dealer
    # positioning, not a claim about what happens next.
    flip = totals.get("gex_flip_price")
    if flip is None:
        gamma_regime = None
    elif spot > flip:
        gamma_regime = "positive"
    elif spot < flip:
        gamma_regime = "negative"
    else:
        gamma_regime = "neutral"

    result: dict[str, Any] = {
        "ticker": ticker,
        "available": True,
        "spot": spot,
        "asof": asof,
        # Ticker-wide context, already in the payload we fetched for the wall
        # calc — free liquidity/size signal, no extra call. gex_value_per_1pct
        # is TV's own "$ notional per 1% underlying move" (the "money number"
        # requested 2026-09-11); *_oi_sum / put_call_oi are open interest, the
        # closest liquidity proxy available without a second, expiration-
        # specific call (options/volume requires a concrete expiration date
        # that exp=combined does not resolve to).
        "gex_value_per_1pct": totals.get("gex_value_per_1pct"),
        "call_oi_sum": totals.get("call_oi_sum"),
        "put_oi_sum": totals.get("put_oi_sum"),
        "put_call_oi": totals.get("put_call_oi"),
        # Real options-liquidity context (2026-10-05 gate) -- nearest-
        # expiration whole-chain volume for the most recent completed
        # session, from ThetaData, not TV (TV has no volume field).
        "near_exp_chain_volume": near_exp_chain_volume,
        "gamma_flip_price": flip,
        "gamma_regime": gamma_regime,
        # 1-day options-implied expected move, half-width in dollars — lets
        # the viewer judge "is $X to the wall a big or small move today"
        # without this module ever saying so itself.
        "expected_move_1d_dollars": expected_move_1d,
        "call_walls": call_walls,
        "put_walls": put_walls,
        "call_wall": call_walls[0] if call_walls else None,
        "put_wall": put_walls[0] if put_walls else None,
    }

    candidates = [
        (side, w) for side, w in (("call", result["call_wall"]), ("put", result["put_wall"]))
        if w is not None
    ]
    if candidates:
        side, w = min(candidates, key=lambda sw: sw[1]["pct_to_break"])
        vs_move = round(w["dollars_to_break"] / expected_move_1d, 2) if expected_move_1d else None
        result["closest_wall"] = {"side": side, **w, "vs_expected_move_1d": vs_move}
    else:
        result["closest_wall"] = None

    result["read"] = _composite_read(gamma_regime, result["closest_wall"], result["put_call_oi"])

    return result


def _composite_read(
    gamma_regime: Optional[str], closest_wall: Optional[dict[str, Any]], put_call_oi: Optional[float]
) -> dict[str, str]:
    """States the current facts (regime, wall proximity, OI skew) in plain
    English. Does NOT predict a behavior (no "pin-prone" / "amplified" —
    those claim a specific outcome that positive/negative gamma does not
    reliably produce; it's a secondary hedging-flow effect that trend, news,
    and real order flow routinely override, which is part of why
    wall-proximity signals failed testing in the first place —
    flowmix-singlename-fails.md, gex-walls-are-not-levels).

    NOT a validated edge, NOT a probability, NOT a forecast of what price
    does next. See handoff wall-scanner-gamma-regime-research.md for the
    real validation work if this is meant to become an actual signal.
    """
    if gamma_regime is None:
        return {"label": "UNKNOWN", "note": "gamma flip price unavailable for this ticker"}

    skew_word = None
    if put_call_oi is not None:
        if put_call_oi >= 1.3:
            skew_word = "put-heavy OI"
        elif put_call_oi <= 0.7:
            skew_word = "call-heavy OI"

    if gamma_regime == "positive":
        label = "POSITIVE GAMMA"
        note = "Spot is above the gamma flip — dealers are net long gamma here."
    elif gamma_regime == "negative":
        label = "NEGATIVE GAMMA"
        note = "Spot is below the gamma flip — dealers are net short gamma here."
    else:
        label = "AT FLIP"
        note = "Spot is sitting right at the gamma flip."

    if closest_wall is not None and closest_wall.get("vs_expected_move_1d") is not None:
        note += f" Closest wall is {closest_wall['vs_expected_move_1d']:.2f}x today's expected move away."
    if skew_word:
        note += f" OI skew: {skew_word}."

    return {"label": label, "note": note}


def _tightest_pct(row: dict[str, Any]) -> float:
    """Sort key: smallest % distance to EITHER wall. Missing data sorts last."""
    closest = row.get("closest_wall")
    return closest["pct_to_break"] if closest else float("inf")


def run_scan(limit: int = _UNIVERSE_LIMIT) -> dict[str, Any]:
    """Scan TV's covered universe, sorted tightest-gap-first."""
    started = time.monotonic()
    tickers = fetch_universe(limit)
    if not tickers:
        return {"tickers_scanned": 0, "data": [], "generated_at": None}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(scan_ticker, t): t for t in tickers}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                logger.warning("[wall_scanner] scan_ticker %s raised: %r", futures[fut], exc)
                results.append({"ticker": futures[fut], "available": False})

    available = [r for r in results if r.get("available")]
    unavailable = [r for r in results if not r.get("available")]
    available.sort(key=_tightest_pct)

    elapsed = round(time.monotonic() - started, 1)
    logger.info(
        "[wall_scanner] scanned %d tickers (%d available) in %ss",
        len(tickers), len(available), elapsed,
    )
    return {
        "tickers_scanned": len(tickers),
        "data": available + unavailable,
        "elapsed_sec": elapsed,
    }


def scan_all(limit: int = _UNIVERSE_LIMIT, force: bool = False) -> dict[str, Any]:
    """Cached market-wide scan — a full pass is ~100 external calls."""
    now = time.monotonic()
    if not force and _cache["payload"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["payload"]

    payload = run_scan(limit)
    _cache["payload"] = payload
    _cache["ts"] = now
    return payload


def capture_snapshot(engine: Optional[Engine], rows: list[dict[str, Any]]) -> None:
    """Write each available row's closest wall to history.

    Called by the scheduled capture job (backend/__init__.py), never inline
    in a request path — this is a write, and the request path only ever
    reads (see wall_history_delta). Never raises: a DB hiccup should not
    take the scan down, only skip that capture.
    """
    if engine is None:
        return
    now = datetime.now(dt_timezone.utc)
    try:
        ensure_history_table(engine)
        with engine.begin() as conn:
            for row in rows:
                closest = row.get("closest_wall")
                if not row.get("available") or not closest:
                    continue
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {HISTORY_TABLE}
                            (ticker, side, strike, net_gex, call_oi_sum, put_oi_sum, spot, captured_at)
                        VALUES (:ticker, :side, :strike, :net_gex, :call_oi, :put_oi, :spot, :ts)
                        """
                    ),
                    {
                        "ticker": row["ticker"],
                        "side": closest["side"],
                        "strike": closest["strike"],
                        "net_gex": closest.get("net_gex"),
                        "call_oi": row.get("call_oi_sum"),
                        "put_oi": row.get("put_oi_sum"),
                        "spot": row.get("spot"),
                        "ts": now,
                    },
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wall_scanner] history capture failed: %r", exc)


def capture_and_store() -> dict[str, Any]:
    """Scheduled entry point: scan, warm the request cache, write history."""
    from ..db import engine as _engine  # local import — avoid a hard dependency at module load

    payload = run_scan()
    _cache["payload"] = payload
    _cache["ts"] = time.monotonic()
    capture_snapshot(_engine, payload.get("data", []))
    return payload


def wall_history_delta(
    engine: Optional[Engine], ticker: str, side: str, strike: float, minutes_back: int = 60
) -> Optional[dict[str, Any]]:
    """Nearest snapshot at/before (now - minutes_back) for this exact
    ticker/side/strike. None if the wall wasn't at this strike back then (or
    the table has no history yet) — no fabricated cross-strike comparison.
    """
    if engine is None:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT net_gex, call_oi_sum, put_oi_sum, captured_at
                    FROM {HISTORY_TABLE}
                    WHERE ticker = :ticker AND side = :side AND strike = :strike
                      AND captured_at <= now() - (:mins * interval '1 minute')
                    ORDER BY captured_at DESC
                    LIMIT 1
                    """
                ),
                {"ticker": ticker, "side": side, "strike": strike, "mins": minutes_back},
            ).mappings().first()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wall_scanner] history lookup failed for %s: %r", ticker, exc)
        return None
    if not row:
        return None
    return {
        "net_gex": row["net_gex"],
        "call_oi_sum": row["call_oi_sum"],
        "put_oi_sum": row["put_oi_sum"],
        "captured_at": row["captured_at"].isoformat() if row["captured_at"] else None,
    }


def wall_history_series(
    engine: Optional[Engine], ticker: str, side: str, strike: float, days_back: int = 5
) -> list[dict[str, Any]]:
    """Every capture for this exact ticker/side/strike over the lookback
    window, oldest first — intraday points AND day-over-day in one series
    (the capture job runs every 5 min during market hours, so a few days of
    uptime is a few hundred points; nothing exists before this feature
    shipped, so a fresh deploy returns an empty or short series honestly
    rather than backfilling anything synthetic).
    """
    if engine is None:
        return []
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT net_gex, call_oi_sum, put_oi_sum, spot, captured_at
                    FROM {HISTORY_TABLE}
                    WHERE ticker = :ticker AND side = :side AND strike = :strike
                      AND captured_at >= now() - (:days * interval '1 day')
                    ORDER BY captured_at ASC
                    """
                ),
                {"ticker": ticker, "side": side, "strike": strike, "days": days_back},
            ).mappings().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wall_scanner] history series failed for %s: %r", ticker, exc)
        return []
    return [
        {
            "net_gex": r["net_gex"],
            "call_oi_sum": r["call_oi_sum"],
            "put_oi_sum": r["put_oi_sum"],
            "spot": r["spot"],
            "captured_at": r["captured_at"].isoformat() if r["captured_at"] else None,
        }
        for r in rows
    ]


def attach_history_deltas(engine: Optional[Engine], rows: list[dict[str, Any]], minutes_back: int = 60) -> None:
    """Mutates `rows` in place: adds closest_wall['delta'] = {net_gex_then,
    call_oi_then, put_oi_then, minutes_back} or None. Composed at the route
    layer (see routes_wall_scanner.py) so this module's core scan stays free
    of DB concerns beyond these explicit, opt-in capture/query functions.
    """
    if engine is None:
        return
    for row in rows:
        closest = row.get("closest_wall")
        if not row.get("available") or not closest:
            continue
        prior = wall_history_delta(engine, row["ticker"], closest["side"], closest["strike"], minutes_back)
        closest["delta"] = (
            {
                "minutes_back": minutes_back,
                "net_gex_then": prior["net_gex"],
                "call_oi_then": prior["call_oi_sum"],
                "put_oi_then": prior["put_oi_sum"],
                "captured_at": prior["captured_at"],
            }
            if prior
            else None
        )
