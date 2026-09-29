"""PAPER-ONLY forward logger for two XSP 0DTE call-vertical leads
(``PREREG_XSP_OTM_VOL_PLAYS.md`` / ``RESULT_XSP_OTM_VOL_PLAYS_500.md``).

WHY THIS EXISTS
----------------
The holdout study found every one of 5 OTM-debit-vertical structures
INCONCLUSIVE (n=13-46, below the pre-declared n>=90 power floor) and its
explicit bottom line is: do not build or arm any of them, but Track A
(``igex_call`` rally signal) and Track C2 (VIX-tercile spike) are "worth
continued FORWARD-ONLY logging" given their placebo percentile, R:R, and
(for A) an independently-replicated dealer-gamma mechanism. This module is
that forward log -- one row per (trade_date, lead), NEVER an order.

🚨 LOGGING NEVER DEPENDS ON ARMING. Nothing in this module reads any
``*_LIVE`` flag. It is registered in ``ember.runtime.register()`` as its own
scheduler jobs, gated only on ``EMBER_XSP_VERTICAL_LEADS_ENABLED``.

NO ORDERS, NO AGENT, NO BROKER LOCK. Same discipline as ``xsp_paper_ledger``
(PR #3112, the model for this file): never launches the Robinhood-Agentic
subprocess, never calls the runtime's advisory-lock acquisition, never
imports anything from the live executor's order-tool allowlist. It prices
XSP legs with the SAME read-only Tradier chain client ``xsp_paper_ledger``
uses (``bots/tsunami/data/tradier_client``) -- ``get_quote``/
``get_chain_contracts``/``get_daily_history``, all pure market-data GETs.

WHY THIS DOES NOT IMPORT ``xsp_flow_live``'s geometry/settlement helpers:
that module's ``strike_geometry`` is frozen to XSP Flow's own UP/DOWN,
base+/-2 long, base+/-3 short ($1-wide) geometry, and its
``settlement_payout`` hardcodes the module-level ``WIDTH = 1`` constant.
Leads A and C2 use a DIFFERENT frozen geometry from the prereg's selected
champions -- both are call-only, long strike = spot x 1.01 (1% OTM, nearest
quoted strike), short = long + $5 (nearest quoted strike), never a fixed
point offset. Forcing that through helpers whose constants don't match
would silently misprice the trade, so the equivalent debit/payout math is
reimplemented locally below under the identical conventions (buy the ask,
sell the bid, clip payout to [0, width], no look-ahead) -- see
``_select_strikes_and_quote`` and ``_settlement_payout``.

FROZEN RULES (copied from the prereg, not re-derived)
------------------------------------------------------
Lead A  -- 12:00 ET: if ``igex_call`` (SPY-side dealer call-gamma composite)
           is below its own trailing-20-session 40th percentile (PIT,
           computed only from the trailing 20 prior sessions of the SAME
           12:00 ET bucket), buy the 1%-OTM/$5-wide XSP 0DTE call vertical.
Lead C2 -- 10:30 ET: if ``vix_l`` (LAGGED prior trading day's VIX close,
           PIT-safe by construction) is above its own trailing-20-session
           67th percentile (top tercile) AND today is not a monthly OPEX
           day (3rd Friday), buy the same 1%-OTM/$5-wide XSP 0DTE call
           vertical.
Both hold to cash settlement. Strike selection: long = nearest ACTUALLY
QUOTED call strike to spot*(1+1%); short = nearest actually quoted call
strike to long+$5; skip (logged) if no quoted strike is within $0.50 of
either target -- identical to the prereg's frozen strike-selection rule.
The first ~20 sessions of each lead have no valid trailing signal (logged
as ``warming_up``, never treated as a meaningful non-fire) -- same
disclosed warm-up the prereg itself carries.

LIVE ``igex_call`` SOURCE -- DOCUMENTED DEFINITIONAL MISMATCH
----------------------------------------------------------------
``bt_spy.igex_call`` (the backtest's frozen SPY dealer call-gamma column) is
a historical-warehouse composite built from an ORAT/ThetaData intraday-GEX
pipeline; it is not reproduced live anywhere in this repo. The closest LIVE
analogs found:
  - This same Python backend's OWN ``market_structure.py`` computes a live
    SPY gamma snapshot, but from the ORATS one-minute chain, and it only
    returns a NETTED total (``net_gex_b`` = call exposure minus put
    exposure), never an isolated call-side figure -- and ORATS_API_TOKEN
    is a known-flaky live credential in this program (see memory:
    "ORAT tables frozen since 2026-08-11, no ORATS_TOKEN").
  - The ironforge webapp (a SEPARATE TypeScript/Node service, not
    importable here) computes ``FLINT_FAVORABLE_UPSIZE``'s call_gamma via
    ``getGammaExposureComponents('SPY', spot, 60)``, logged with
    ``gamma_source = 'tradier_chain_dollar_gex_dte0-60'`` -- a live
    Tradier-chain dollar-gamma-exposure sum over SPY's 0-60 DTE calls.
This module computes a Python-native proxy using the SAME formula
(``gamma * open_interest * 100 * spot**2 * 0.01`` per contract, summed over
calls only, across SPY expirations 0-60 calendar days out) sourced from
Tradier (the one credential guaranteed present in this codepath already,
unlike ORATS) -- definitionally the closest live match to the ironforge
FLINT composite's own DTE window and construction, and mechanically
IDENTICAL to the per-row formula this backend's own
``market_structure._gex_for_row`` already uses for SPY. It is NOT validated
as numerically equivalent to ``bt_spy.igex_call``'s frozen backtest
construction -- no reconciliation study has been run. Every Lead A row
therefore carries ``igex_call_definition_mismatch = TRUE`` and an
``igex_call_note`` explaining this, per instruction: log the live value
alongside and flag the mismatch, never silently substitute.

LIVE SETTLEMENT SOURCE -- ALSO A DOCUMENTED PROXY
-----------------------------------------------------
The frozen backtest settles on ``xsp_spot_minute``'s last snap >=15:55 ET
(a raw spot print, explicitly NOT an official settlement value). This
module's live equivalent is the last Tradier XSP quote fetched during the
scheduled 14:57 CT (~15:57 ET) settle sweep -- the same convention, not an
official Cboe/OCC settlement print (no such live feed is wired into this
backend). Settlement only runs same-day, for rows captured that trade_date;
a day the sweep never runs (outage) stays ``settled_at IS NULL`` forever --
disclosed, not silently worked around, since no live source can retroactively
reproduce a past day's 15:55 ET print.

NO COMMISSION MODELED. Same simplification ``xsp_paper_ledger.py`` already
uses for this program's live paper ledgers (its own ``pnl`` calc has no fee
term) -- disclosed here explicitly since the frozen backtest itself DOES
charge $0.70/contract/leg-side entry commission. This ledger's ``pnl`` is
therefore a slightly optimistic (fee-free) read versus the frozen backtest
number; the debit/payout math is otherwise identical.

NEVER RAISES. ``record_tick``/``settle_pending`` catch every exception, log
a warning, and return -- a paper-logging failure must never take the real
scheduler tick down with it.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..bots.tsunami.data import tradier_client as _tradier

logger = logging.getLogger("spreadworks.ember.xsp_vertical_leads_paper")

CT = ZoneInfo("America/Chicago")
UTC = timezone.utc
TABLE = "ember_xsp_vertical_leads_paper"

ENABLED_ENV = "EMBER_XSP_VERTICAL_LEADS_ENABLED"

# Frozen champion geometry (PREREG_XSP_OTM_VOL_PLAYS.md, both Track A and
# Track C2's selected champions): 1% OTM distance, $5-wide, calls only.
OTM_DISTANCE = 0.01
WIDTH = 5.0
STRIKE_TOLERANCE = 0.50  # prereg: skip the leg if no quoted strike within $0.50 of target

# Prereg entry times are ET; US Central is always exactly 1 hour behind US
# Eastern (both follow the same DST calendar), so these CT times are exact.
LEAD_A_DECISION_CT = time(11, 0)    # 12:00 ET
LEAD_C2_DECISION_CT = time(9, 30)   # 10:30 ET
CAPTURE_TOLERANCE_MINUTES = 7       # same NBBO-quote tolerance frozen in the prereg's fill convention
SETTLE_HOUR_CT, SETTLE_MINUTE_CT = 14, 57   # ~15:57 ET, safely after the >=15:55 ET settlement snap

TRAILING_N = 20   # prereg: trailing 20 prior sessions of the same entry-time bucket
A_PCTILE = 40.0
C2_PCTILE = 67.0

_TRADIER_BASE = "https://api.tradier.com/v1"

IGEX_CALL_LIVE_PROXY_NOTE = (
    "live proxy, NOT bt_spy.igex_call: dollar call-gamma exposure summed over "
    "SPY's live Tradier 0-60 DTE chain (gamma*open_interest*100*spot^2*0.01 per "
    "contract -- the same per-row formula this backend's own market_structure.py "
    "uses for its SPY gamma snapshot, and definitionally the closest match to "
    "ironforge webapp's FLINT_FAVORABLE_UPSIZE 'tradier_chain_dollar_gex_dte0-60' "
    "composite, which lives in a separate Node service and was not imported). "
    "bt_spy.igex_call is a frozen backtest-warehouse column from a different "
    "historical ORAT/ThetaData pipeline; no reconciliation study has run between "
    "the two. Read this column as a live proxy under test, not a verified "
    "reproduction of the frozen backtest signal."
)

_COLUMNS_SQL = """
    trade_date                    DATE NOT NULL,
    lead                          TEXT NOT NULL,
    run_ts_utc                    TIMESTAMP NOT NULL,
    run_ts_ct                     TIMESTAMP NOT NULL,
    decision_time_ct               TEXT,
    spot                           DOUBLE PRECISION,
    live_call_gex                  DOUBLE PRECISION,
    call_gex_trailing_p40           DOUBLE PRECISION,
    call_gex_trailing_n             INTEGER,
    igex_call_definition_mismatch   BOOLEAN,
    igex_call_note                  TEXT,
    vix_value                       DOUBLE PRECISION,
    vix_trailing_p67                 DOUBLE PRECISION,
    vix_trailing_n                   INTEGER,
    is_opex                          BOOLEAN,
    fired                            BOOLEAN NOT NULL DEFAULT FALSE,
    reason                           TEXT,
    option_type                      TEXT,
    long_strike                      DOUBLE PRECISION,
    short_strike                     DOUBLE PRECISION,
    expiry                           TEXT,
    long_ask                         DOUBLE PRECISION,
    short_bid                        DOUBLE PRECISION,
    quote_ts_utc                     TIMESTAMP,
    debit                            DOUBLE PRECISION,
    captured_at                      TIMESTAMP,
    settlement_spot                  DOUBLE PRECISION,
    payout                           DOUBLE PRECISION,
    pnl                              DOUBLE PRECISION,
    settled_at                       TIMESTAMP,
    created_at                       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, lead)
"""


def _ddl() -> str:
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id BIGSERIAL PRIMARY KEY,\n{_COLUMNS_SQL}\n)"


def _ddl_sqlite() -> str:
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n{_COLUMNS_SQL}\n)"


def ensure_table(engine: Optional[Engine]) -> None:
    """Idempotent create. Never raises."""
    if engine is None:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(_ddl_sqlite() if engine.dialect.name == "sqlite" else _ddl()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] table create failed: %r", exc)


def _now_utc_ct() -> tuple[datetime, datetime]:
    now_utc = datetime.now(UTC)
    return now_utc.replace(tzinfo=None), now_utc.astimezone(CT).replace(tzinfo=None)


def _fetch_existing(engine: Engine, trade_date: date, lead: str) -> Optional[dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT * FROM {TABLE} WHERE trade_date = :d AND lead = :l"),
            {"d": trade_date, "l": lead},
        ).mappings().first()
    return dict(row) if row else None


_INSERT_COLUMNS = [
    "trade_date", "lead", "run_ts_utc", "run_ts_ct", "decision_time_ct", "spot",
    "live_call_gex", "call_gex_trailing_p40", "call_gex_trailing_n",
    "igex_call_definition_mismatch", "igex_call_note",
    "vix_value", "vix_trailing_p67", "vix_trailing_n", "is_opex",
    "fired", "reason", "option_type", "long_strike", "short_strike", "expiry",
    "long_ask", "short_bid", "quote_ts_utc", "debit", "captured_at",
]

_UPSERT_SQL = f"""
    INSERT INTO {TABLE} ({', '.join(_INSERT_COLUMNS)})
    VALUES ({', '.join(':' + c for c in _INSERT_COLUMNS)})
    ON CONFLICT (trade_date, lead) DO UPDATE SET
        {', '.join(f"{c} = EXCLUDED.{c}" for c in _INSERT_COLUMNS if c not in ("trade_date", "lead"))}
"""


def _upsert(engine: Engine, params: dict[str, Any]) -> None:
    ensure_table(engine)
    row = {k: params.get(k) for k in _INSERT_COLUMNS}
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), row)


def _base_row(lead: str, trade_date: date, run_ts_utc: datetime, run_ts_ct: datetime) -> dict[str, Any]:
    decision_ct = LEAD_A_DECISION_CT if lead == "A" else LEAD_C2_DECISION_CT
    return {
        "trade_date": trade_date, "lead": lead, "run_ts_utc": run_ts_utc, "run_ts_ct": run_ts_ct,
        "decision_time_ct": decision_ct.isoformat(timespec="minutes"),
        "spot": None, "live_call_gex": None, "call_gex_trailing_p40": None, "call_gex_trailing_n": None,
        "igex_call_definition_mismatch": None, "igex_call_note": None,
        "vix_value": None, "vix_trailing_p67": None, "vix_trailing_n": None, "is_opex": None,
        "fired": False, "reason": None,
        "option_type": None, "long_strike": None, "short_strike": None, "expiry": None,
        "long_ask": None, "short_bid": None, "quote_ts_utc": None, "debit": None,
        "captured_at": None,
    }


# ---------------------------------------------------------------- pure math


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile, standard convention."""
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (pct / 100.0) * (len(s) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def _is_opex_day(d: date) -> bool:
    """3rd Friday of the month, computed directly -- same convention the
    prereg's own loss-attribution/optimization section uses (no vendor
    macro-calendar table exists locally)."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def _decide_lead_a(
    spy_spot: Optional[float], live_call_gex: Optional[float], gex_note: str, trailing: list[float]
) -> dict[str, Any]:
    if spy_spot is None:
        return {"fired": False, "reason": "no_spy_spot",
                "call_gex_trailing_p40": None, "call_gex_trailing_n": len(trailing)}
    if live_call_gex is None:
        return {"fired": False, "reason": f"no_live_call_gex: {gex_note}",
                "call_gex_trailing_p40": None, "call_gex_trailing_n": len(trailing)}
    if len(trailing) < TRAILING_N:
        return {"fired": False,
                "reason": f"warming_up: trailing_n={len(trailing)} < {TRAILING_N} sessions",
                "call_gex_trailing_p40": None, "call_gex_trailing_n": len(trailing)}
    p40 = _percentile(trailing, A_PCTILE)
    fired = live_call_gex < p40
    reason = (
        f"trigger {'fired' if fired else 'no_fire'}: live_call_gex={live_call_gex:.4g} "
        f"{'<' if fired else '>='} trailing_p40={p40:.4g} (n={len(trailing)})"
    )
    return {"fired": fired, "reason": reason, "call_gex_trailing_p40": p40,
            "call_gex_trailing_n": len(trailing)}


def _decide_lead_c2(vix_value: Optional[float], trailing: list[float], is_opex: bool) -> dict[str, Any]:
    if vix_value is None:
        return {"fired": False, "reason": "no_prior_day_vix_close",
                "vix_trailing_p67": None, "vix_trailing_n": len(trailing), "is_opex": is_opex}
    if len(trailing) < TRAILING_N:
        return {"fired": False,
                "reason": f"warming_up: trailing_n={len(trailing)} < {TRAILING_N} sessions",
                "vix_trailing_p67": None, "vix_trailing_n": len(trailing), "is_opex": is_opex}
    p67 = _percentile(trailing, C2_PCTILE)
    tercile_hit = vix_value > p67
    if tercile_hit and is_opex:
        return {"fired": False,
                "reason": f"skip: vix_top_tercile_true (vix={vix_value:.2f} > p67={p67:.2f}) but is_opex",
                "vix_trailing_p67": p67, "vix_trailing_n": len(trailing), "is_opex": is_opex}
    fired = tercile_hit and not is_opex
    reason = (
        f"trigger {'fired' if fired else 'no_fire'}: vix_l={vix_value:.2f} "
        f"{'>' if tercile_hit else '<='} trailing_p67={p67:.2f} (n={len(trailing)}), is_opex={is_opex}"
    )
    return {"fired": fired, "reason": reason, "vix_trailing_p67": p67,
            "vix_trailing_n": len(trailing), "is_opex": is_opex}


def _nearest_call(contracts: list[dict[str, Any]], target: float) -> Optional[dict[str, Any]]:
    calls = [c for c in contracts if str(c.get("option_type", "")).lower() == "call"]
    if not calls:
        return None
    best = min(calls, key=lambda c: abs(float(c.get("strike", 0)) - target))
    if abs(float(best["strike"]) - target) > STRIKE_TOLERANCE:
        return None
    return best


def _select_strikes_and_quote(contracts: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    """Prereg strike-selection rule: long = nearest quoted call to
    spot*(1+1%); short = nearest quoted call to long+$5; skip (logged) if no
    quoted strike is within $0.50 of either target."""
    long_target = spot * (1.0 + OTM_DISTANCE)
    long_c = _nearest_call(contracts, long_target)
    if long_c is None:
        return {"note": "no_long_strike_within_tolerance"}
    short_target = float(long_c["strike"]) + WIDTH
    short_c = _nearest_call(contracts, short_target)
    if short_c is None:
        return {"note": "no_short_strike_within_tolerance", "long_strike": float(long_c["strike"])}
    long_ask = float(long_c.get("ask") or 0)
    short_bid = float(short_c.get("bid") or 0)
    if long_ask <= 0 or short_bid <= 0:
        return {"note": "missing_quote", "long_strike": float(long_c["strike"]),
                "short_strike": float(short_c["strike"])}
    return {"long_strike": float(long_c["strike"]), "short_strike": float(short_c["strike"]),
            "long_ask": long_ask, "short_bid": short_bid}


def _settlement_payout(settlement_spot: float, long_strike: float, short_strike: float,
                        debit: float) -> tuple[float, float]:
    """Same call-vertical payoff formula as xsp_flow_live.settlement_payout's
    UP branch, generalized past that module's hardcoded WIDTH=1."""
    points = max(settlement_spot - long_strike, 0.0) - max(settlement_spot - short_strike, 0.0)
    payout = round(max(0.0, min(WIDTH, points)) * 100.0, 2)
    pnl = round(payout - float(debit or 0.0) * 100.0, 2)
    return payout, pnl


def _call_gex_for_chain(contracts: list[dict[str, Any]], spot: float) -> float:
    """Dollar call-gamma exposure for one expiration's chain: sum over calls
    of gamma*open_interest*100*spot^2*0.01 -- identical per-row formula to
    this backend's own market_structure.py (_gex_for_row)."""
    total = 0.0
    factor = 100.0 * spot * spot * 0.01
    for c in contracts:
        if str(c.get("option_type", "")).lower() != "call":
            continue
        gamma = float(c.get("gamma") or 0.0)
        oi = float(c.get("open_interest") or 0.0)
        if gamma <= 0 or oi <= 0:
            continue
        total += gamma * oi * factor
    return total


def _fetch_live_call_gex(
    spot: float,
    expirations_fn: Callable[[], list[str]],
    chain_fn: Callable[[str], list[dict[str, Any]]],
) -> tuple[Optional[float], str]:
    try:
        expirations = expirations_fn() or []
    except Exception as exc:  # noqa: BLE001
        return None, f"expirations_fetch_failed:{type(exc).__name__}"
    if not expirations:
        return None, "no_expirations_0_60dte"
    total = 0.0
    n = 0
    for exp in expirations:
        try:
            contracts = chain_fn(exp) or []
        except Exception:  # noqa: BLE001
            continue
        if not contracts:
            continue
        total += _call_gex_for_chain(contracts, spot)
        n += 1
    if n == 0:
        return None, "no_usable_chain_rows"
    return total, "ok"


def _prior_day_close(history_fn: Callable[[], list[dict[str, Any]]], trade_date: date) -> Optional[float]:
    """Lagged prior trading day's close -- PIT-safe by construction, same
    'vix_l' the prereg's Track C2 trigger uses."""
    try:
        bars = history_fn() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] VIX history fetch failed: %r", exc)
        return None
    prior = [b for b in bars if isinstance(b, dict) and b.get("date")
             and str(b["date"]) < trade_date.isoformat()]
    if not prior:
        return None
    prior.sort(key=lambda b: str(b["date"]))
    try:
        return float(prior[-1]["close"])
    except (TypeError, ValueError, KeyError):
        return None


def _trailing_values(engine: Engine, lead: str, column: str, before_date: date,
                      limit: int = TRAILING_N) -> list[float]:
    """Trailing N prior sessions of the SAME lead's own captured history --
    self-referential, matching the prereg's PIT trailing-percentile method
    (no same-day value in its own trailing window)."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"SELECT {column} FROM {TABLE} WHERE lead = :lead AND {column} IS NOT NULL "
                f"AND trade_date < :d ORDER BY trade_date DESC LIMIT :n"
            ),
            {"lead": lead, "d": before_date, "n": limit},
        ).scalars().all()
    return [float(v) for v in rows if v is not None]


# ---------------------------------------------------------------- IO (Tradier)


def _tradier_token() -> str:
    return (os.environ.get("TRADIER_TOKEN", "").strip()
            or os.environ.get("TRADIER_API_KEY", "").strip())


def _default_spy_spot() -> Optional[float]:
    q = _tradier.get_quote("SPY")
    return float(q["last"]) if q and q.get("last") is not None else None


def _default_xsp_spot() -> Optional[float]:
    q = _tradier.get_quote("XSP")
    return float(q["last"]) if q and q.get("last") is not None else None


def _default_vix_history() -> list[dict[str, Any]]:
    return _tradier.get_daily_history("VIX", days=40)


def _default_spy_chain(expiry: str) -> list[dict[str, Any]]:
    return _tradier.get_chain_contracts("SPY", expiration=expiry)


def _default_xsp_chain(expiry: str) -> list[dict[str, Any]]:
    return _tradier.get_chain_contracts("XSP", expiration=expiry)


def _spy_expirations_within(max_dte: int, today: Optional[date] = None) -> list[str]:
    """SPY option expirations 0-max_dte calendar days out, via Tradier's
    expirations endpoint -- same minimal self-contained request pattern
    market_structure.py and tsunami's tradier_client both already use; no
    new SDK, no new token."""
    token = _tradier_token()
    if not token:
        return []
    today = today or date.today()
    try:
        r = requests.get(
            f"{_TRADIER_BASE}/markets/options/expirations",
            params={"symbol": "SPY"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        dates = (r.json().get("expirations") or {}).get("date") or []
        if isinstance(dates, str):
            dates = [dates]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] SPY expirations fetch failed: %r", exc)
        return []
    out = []
    for d in dates:
        try:
            dte = (date.fromisoformat(d) - today).days
        except ValueError:
            continue
        if 0 <= dte <= max_dte:
            out.append(d)
    return sorted(out)


def _default_spy_expirations_0_60() -> list[str]:
    return _spy_expirations_within(60)


def _safe_call(fn: Callable[[], Optional[float]]) -> Optional[float]:
    try:
        v = fn()
        return float(v) if v is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] spot fetch failed: %r", exc)
        return None


# ---------------------------------------------------------------- capture


def _attach_entry(row: dict[str, Any], xsp_spot: float,
                   xsp_chain_fn: Callable[[str], list[dict[str, Any]]],
                   trade_date: date, now_utc: datetime) -> None:
    try:
        contracts = xsp_chain_fn(trade_date.isoformat()) or []
    except Exception as exc:  # noqa: BLE001
        row["fired"] = False
        row["reason"] = f"signal_fired_no_entry: chain_fetch_failed ({type(exc).__name__})"
        return
    if not contracts:
        row["fired"] = False
        row["reason"] = "signal_fired_no_entry: no_0dte_xsp_chain"
        return
    sel = _select_strikes_and_quote(contracts, xsp_spot)
    if "note" in sel:
        row["fired"] = False
        row["reason"] = f"signal_fired_no_entry: {sel['note']}"
        row["long_strike"] = sel.get("long_strike")
        row["short_strike"] = sel.get("short_strike")
        return
    debit = round(sel["long_ask"] - sel["short_bid"], 2)
    row.update({
        "option_type": "C", "expiry": trade_date.isoformat(),
        "long_strike": sel["long_strike"], "short_strike": sel["short_strike"],
        "long_ask": sel["long_ask"], "short_bid": sel["short_bid"],
        "quote_ts_utc": now_utc, "debit": debit,
    })
    if debit <= 0:
        row["fired"] = False
        row["reason"] = f"signal_fired_no_entry: non-positive debit ({debit}) -- credit, out of scope"
    else:
        row["reason"] = f"{row['reason']} | entered: 1% OTM $5-wide XSP call vertical, debit={debit:.2f}"


def _capture_lead_a(
    engine: Engine, trade_date: date, now_utc: datetime, now_ct: datetime,
    spy_spot_fn: Callable[[], Optional[float]], xsp_spot_fn: Callable[[], Optional[float]],
    expirations_fn: Callable[[], list[str]], spy_chain_fn: Callable[[str], list[dict[str, Any]]],
    xsp_chain_fn: Callable[[str], list[dict[str, Any]]],
) -> dict[str, Any]:
    row = _base_row("A", trade_date, now_utc, now_ct)
    spy_spot = _safe_call(spy_spot_fn)
    xsp_spot = _safe_call(xsp_spot_fn)
    row["spot"] = xsp_spot
    live_call_gex: Optional[float] = None
    gex_note = "no_spy_spot"
    if spy_spot is not None:
        live_call_gex, gex_note = _fetch_live_call_gex(spy_spot, expirations_fn, spy_chain_fn)
    row["live_call_gex"] = live_call_gex
    row["igex_call_definition_mismatch"] = True
    row["igex_call_note"] = IGEX_CALL_LIVE_PROXY_NOTE
    trailing = _trailing_values(engine, "A", "live_call_gex", trade_date)
    row.update(_decide_lead_a(spy_spot, live_call_gex, gex_note, trailing))
    if row["fired"]:
        if xsp_spot is None:
            row["fired"] = False
            row["reason"] = "signal_fired_no_entry: no_xsp_spot_for_strikes"
        else:
            _attach_entry(row, xsp_spot, xsp_chain_fn, trade_date, now_utc)
    row["captured_at"] = now_utc
    return row


def _capture_lead_c2(
    engine: Engine, trade_date: date, now_utc: datetime, now_ct: datetime,
    xsp_spot_fn: Callable[[], Optional[float]], vix_history_fn: Callable[[], list[dict[str, Any]]],
    xsp_chain_fn: Callable[[str], list[dict[str, Any]]],
) -> dict[str, Any]:
    row = _base_row("C2", trade_date, now_utc, now_ct)
    xsp_spot = _safe_call(xsp_spot_fn)
    row["spot"] = xsp_spot
    vix_value = _prior_day_close(vix_history_fn, trade_date)
    row["vix_value"] = vix_value
    is_opex = _is_opex_day(trade_date)
    trailing = _trailing_values(engine, "C2", "vix_value", trade_date)
    row.update(_decide_lead_c2(vix_value, trailing, is_opex))
    if row["fired"]:
        if xsp_spot is None:
            row["fired"] = False
            row["reason"] = "signal_fired_no_entry: no_xsp_spot_for_strikes"
        else:
            _attach_entry(row, xsp_spot, xsp_chain_fn, trade_date, now_utc)
    row["captured_at"] = now_utc
    return row


def _within_market_window(now_ct: datetime) -> bool:
    return now_ct.weekday() < 5 and time(8, 30) <= now_ct.time().replace(tzinfo=None) <= time(15, 5)


def record_tick(
    engine: Optional[Engine],
    now_ct: datetime,
    *,
    spy_spot_fn: Optional[Callable[[], Optional[float]]] = None,
    xsp_spot_fn: Optional[Callable[[], Optional[float]]] = None,
    vix_history_fn: Optional[Callable[[], list[dict[str, Any]]]] = None,
    expirations_fn: Optional[Callable[[], list[str]]] = None,
    spy_chain_fn: Optional[Callable[[str], list[dict[str, Any]]]] = None,
    xsp_chain_fn: Optional[Callable[[str], list[dict[str, Any]]]] = None,
) -> bool:
    """One paper-logging tick for BOTH leads. Never raises -- returns False
    (and logs) on any failure."""
    if engine is None:
        return False
    if not _within_market_window(now_ct):
        return False
    spy_spot_fn = spy_spot_fn or _default_spy_spot
    xsp_spot_fn = xsp_spot_fn or _default_xsp_spot
    vix_history_fn = vix_history_fn or _default_vix_history
    expirations_fn = expirations_fn or _default_spy_expirations_0_60
    spy_chain_fn = spy_chain_fn or _default_spy_chain
    xsp_chain_fn = xsp_chain_fn or _default_xsp_chain
    try:
        ensure_table(engine)
        trade_date = now_ct.date()
        now_utc, now_ct_naive = _now_utc_ct()
        now_time = now_ct.time().replace(tzinfo=None)
        for lead, decision_time in (("A", LEAD_A_DECISION_CT), ("C2", LEAD_C2_DECISION_CT)):
            existing = _fetch_existing(engine, trade_date, lead)
            if existing and existing.get("captured_at") is not None:
                continue
            if now_time < decision_time:
                continue
            window_end = (
                datetime.combine(trade_date, decision_time) + timedelta(minutes=CAPTURE_TOLERANCE_MINUTES)
            ).time()
            if now_time > window_end:
                row = _base_row(lead, trade_date, now_utc, now_ct_naive)
                row["fired"] = False
                row["reason"] = f"missed: no tick within {CAPTURE_TOLERANCE_MINUTES}min capture window"
                row["captured_at"] = now_utc
                _upsert(engine, row)
                continue
            if lead == "A":
                row = _capture_lead_a(
                    engine, trade_date, now_utc, now_ct_naive, spy_spot_fn, xsp_spot_fn,
                    expirations_fn, spy_chain_fn, xsp_chain_fn,
                )
            else:
                row = _capture_lead_c2(
                    engine, trade_date, now_utc, now_ct_naive, xsp_spot_fn, vix_history_fn, xsp_chain_fn,
                )
            _upsert(engine, row)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] record_tick failed: %r", exc)
        return False


def settle_pending(
    engine: Optional[Engine],
    now_ct: Optional[datetime] = None,
    *,
    xsp_spot_fn: Optional[Callable[[], Optional[float]]] = None,
) -> int:
    """Settle every fired=True row captured TODAY still missing settled_at,
    using one fresh XSP quote for all of them (the live equivalent of the
    frozen backtest's xsp_spot_minute >=15:55 ET last snap). Never raises;
    returns the count settled. Rows from a prior day that never settled
    (e.g. an outage) are logged, not retroactively guessed."""
    if engine is None:
        return 0
    xsp_spot_fn = xsp_spot_fn or _default_xsp_spot
    today = (now_ct or datetime.now(CT)).date()
    n = 0
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            pending = conn.execute(
                text(
                    f"SELECT trade_date, lead, long_strike, short_strike, debit FROM {TABLE} "
                    "WHERE fired = TRUE AND settled_at IS NULL AND trade_date = :today"
                ),
                {"today": today},
            ).mappings().all()
            stale = conn.execute(
                text(
                    f"SELECT count(*) FROM {TABLE} WHERE fired = TRUE AND settled_at IS NULL "
                    "AND trade_date < :today"
                ),
                {"today": today},
            ).scalar_one()
        if stale:
            logger.warning(
                "[xsp_vertical_leads_paper] %d prior-day fired row(s) remain unsettled "
                "(no live spot source can reproduce a past day's settlement snap)", stale,
            )
        if not pending:
            return 0
        settlement_spot = _safe_call(xsp_spot_fn)
        if settlement_spot is None:
            logger.warning("[xsp_vertical_leads_paper] settle_pending: no XSP spot available")
            return 0
        now_utc, _ = _now_utc_ct()
        for row in pending:
            payout, pnl = _settlement_payout(
                settlement_spot, row["long_strike"], row["short_strike"], row["debit"] or 0.0
            )
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"UPDATE {TABLE} SET settlement_spot = :sv, payout = :payout, pnl = :pnl, "
                        "settled_at = :settled_at WHERE trade_date = :d AND lead = :lead"
                    ),
                    {"sv": settlement_spot, "payout": payout, "pnl": pnl, "settled_at": now_utc,
                     "d": row["trade_date"], "lead": row["lead"]},
                )
            n += 1
        return n
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] settle_pending failed: %r", exc)
        return n


def export_csv(engine: Optional[Engine], out_path: str, *, days: int = 60) -> int:
    """Read-only export used by scripts/export_xsp_vertical_leads_paper.py.
    Returns the row count written; 0 on any failure. Never raises."""
    if engine is None:
        logger.warning("[xsp_vertical_leads_paper] export skipped: no engine")
        return 0
    import csv

    try:
        ensure_table(engine)
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"SELECT * FROM {TABLE} WHERE trade_date >= CURRENT_DATE - :days "
                    "ORDER BY trade_date DESC, lead"
                    if engine.dialect.name != "sqlite" else
                    f"SELECT * FROM {TABLE} WHERE date(trade_date) >= date('now', '-' || :days || ' days') "
                    "ORDER BY trade_date DESC, lead"
                ),
                {"days": days},
            ).mappings().all()
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            if not rows:
                return 0
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_vertical_leads_paper] export failed: %r", exc)
        return 0


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_eval_tick() -> None:
    from .. import db
    record_tick(db.engine, datetime.now(CT))


def _run_settle_tick() -> None:
    from .. import db
    settle_pending(db.engine)


def register(scheduler: Any) -> None:
    """Register the two paper-ledger jobs. Gated ONLY on
    EMBER_XSP_VERTICAL_LEADS_ENABLED -- never on any *_LIVE flag. Independent
    scheduler jobs: no shared lock, no shared state file, no dependency on
    any live/dry-run agent flow."""
    if not _env_bool(ENABLED_ENV):
        return
    scheduler.add_job(
        _run_eval_tick,
        "cron",
        day_of_week="mon-fri",
        hour="8-15",
        minute="*",
        second="25",
        timezone="America/Chicago",
        id="ember_xsp_vertical_leads_eval",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        _run_settle_tick,
        "cron",
        day_of_week="mon-fri",
        hour=SETTLE_HOUR_CT,
        minute=SETTLE_MINUTE_CT,
        timezone="America/Chicago",
        id="ember_xsp_vertical_leads_settle",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    logger.info("[xsp_vertical_leads_paper] registered paper-only Lead A/C2 evaluation + settlement jobs")
