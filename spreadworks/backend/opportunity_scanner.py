"""Opportunity Scanner — THE RULE, pure and network-free.

Architecture (2026-09-14 pivot, Leron): market-data pulls (ThetaData/Polygon/
yfinance) cannot run on Render — ThetaData is a local terminal on Leron's
laptop (http://127.0.0.1:25510), unreachable from the deployed backend. So
computation moved entirely to a laptop script:
    C:\\Users\\lemol\\dev\\meltup\\opportunity\\build_opportunity_snapshot.py
which imports THIS module (by file path, via importlib — never through the
`backend` package, whose __init__.py boots a whole FastAPI app) purely for
the pieces that never change no matter where the numbers come from: THE RULE
itself, the eligibility thresholds, the VIX-gate ratio math, the planned
entry/exit date logic, and the FilingSense wording. This module has ZERO
network calls and ZERO FastAPI imports — every function here is a plain,
directly-unit-testable transformation of numbers someone else fetched.

The SpreadWorks backend (routes_opportunity.py) now only stores and serves
whatever snapshot the laptop last pushed — it does not compute anything.

  1. DIVIDEND RAISE — THE RULE (median_ratio_rule / eligible_entry / the
     RATIO_MIN etc. constants) is copied VERBATIM from the live laptop bot,
     never re-derived:
       C:\\Users\\lemol\\dev\\meltup\\divhike\\run_divhike.py, lines 130-137
       (constants) and 227-256 (median_ratio_rule / eligible_entry).
     HALF2 passed all 5 clauses (39.6%/yr, DD 45%, t 2.98, beats 95.5% of
     placebo); HALF1 failed on missing declaration-date coverage. Armed by
     Leron 2026-09-11 at $100/pos, max 3.

  2. SAME-DAY SPY 0DTE PUT SPREAD — constants ported from
       C:\\Users\\lemol\\dev\\Dealers-Edge-dashboard\\hike_scanner.py
     (SAME_DAY_* constants — GATE_75 / the honest engine, 2022-2026).

  3. FILINGSENSE — wording ported verbatim from hike_scanner.py's
     _fs_instruction / _fs_scorecard / _fs_hit_rate_label.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
UTC = timezone.utc

# ============================================================================
# 1. DIVIDEND RAISE — THE RULE, copied verbatim from run_divhike.py
#    (C:\Users\lemol\dev\meltup\divhike\run_divhike.py, lines 130-137 + 227-256)
# ============================================================================
RATIO_MIN = 2.0                 # event: amount > 2.0x the median denominator
PREV_LOOKBACK_MONTHS = 24       # prior dividends must have an ex-date in this window
MEDIAN_WINDOW_N = 4              # median of up to 4 previous dividends
MEDIAN_MIN_N = 2                 # at least 2 prior dividends required, else no event
PRICE_MIN = 2.0                  # eligibility: close >= $2.00 at entry
DOLVOL_MIN = 1_000_000.0         # eligibility: trailing-63-session median $ volume >= $1M
DOLVOL_LOOKBACK = 63

# Polygon /v3/reference/tickers "primary_exchange" values that count as a US
# exchange. Source: gate_63_divhike_book.py's US_EXCHANGES. Used by the
# laptop script's Polygon-only CS/US-exchange check (ThetaData has no
# equivalent metadata endpoint in this codebase's existing usage).
US_EXCHANGES = {"XNYS", "XNAS", "XASE", "ARCX", "BATS"}

DIVIDEND_ECONOMICS_TEXT = "~+1.0\u20131.4% per event net, ~10 sessions (GATE_69 HALF2)"


def median_ratio_rule(amount: float, own_type: str | None, prior_amounts: list[float]) -> dict:
    """VERBATIM from run_divhike.py lines 227-245 (the AMENDMENT rule). prior_amounts: the
    ticker's dividend amounts (ANY type, SC included) with an ex-date strictly before the
    candidate's own ex-date and within PREV_LOOKBACK_MONTHS, already sorted ASCENDING by
    ex-date (oldest first) by the caller -- this function only takes the trailing
    MEDIAN_WINDOW_N of that list and never re-sorts by date itself. A record whose own
    dividend_type is 'SC' can never be the event -- checked first, unconditionally. SC priors
    are NEVER excluded from the median (SC is barred from being the event, not from being part
    of the denominator). own_type is Polygon's dividend_type field -- ThetaData's dividend
    endpoint carries no such field, so a candidate whose own_type is unknown (ThetaData-only
    data) is treated as non-SC (own_type is None here, and only the literal string 'SC' bars
    the event)."""
    import numpy as np

    if own_type == "SC":
        return dict(event=False, reason="own_type_SC")
    last_n = prior_amounts[-MEDIAN_WINDOW_N:]
    n_used = len(last_n)
    if n_used < MEDIAN_MIN_N:
        return dict(event=False, reason="insufficient_prior_dividends", n_used=n_used)
    median = float(np.median(last_n))
    ratio = (amount / median) if median else float("nan")
    if not (ratio > RATIO_MIN):
        return dict(event=False, reason="ratio_below_2x", ratio=ratio, median=median, n_used=n_used)
    return dict(event=True, reason="SURVIVES", ratio=ratio, median=median, n_used=n_used)


def eligible_entry(close_px: float | None, trailing_dolvol_median: float | None) -> tuple[bool, str]:
    """VERBATIM from run_divhike.py lines 248-256: close >= $2.00 and trailing-63-session
    median dollar volume >= $1,000,000, both at entry."""
    if close_px is None or not (close_px == close_px) or close_px < PRICE_MIN:
        return False, f"close {close_px} < ${PRICE_MIN:.2f}"
    if trailing_dolvol_median is None or not (trailing_dolvol_median == trailing_dolvol_median) \
            or trailing_dolvol_median < DOLVOL_MIN:
        return False, (f"trailing-{DOLVOL_LOOKBACK}-session median $ volume "
                        f"{trailing_dolvol_median} < ${DOLVOL_MIN:,.0f}")
    return True, "eligible"


def planned_entry_date(decl_date: date) -> date:
    """First session strictly AFTER declaration_date (or ThetaData's ann_date, which replaces
    it as the data source of truth when available). Weekday calendar only (no NYSE holiday
    table) -- same documented limitation as run_divhike.py's own _planned_dates() fallback
    path (lines 580-581), used here unconditionally since production has no cached price
    history to project a real session from."""
    import numpy as np
    return np.busday_offset(decl_date, 1, roll="forward").astype("datetime64[D]").astype(object)


def planned_exit_date(ex_date: date) -> date:
    """T-1: the session immediately before ex_date. Weekday calendar only -- mirrors
    run_divhike.py's _planned_dates() fallback path (line 581/592)."""
    import numpy as np
    return np.busday_offset(ex_date, -1, roll="preceding").astype("datetime64[D]").astype(object)


def weekday_session_count(start: date, end: date) -> int:
    """Number of weekday sessions between start (exclusive) and end (exclusive) -- used only to
    report 'N sessions late', same np.busday_count() call hike_scanner.py uses."""
    import numpy as np
    return int(np.busday_count(start, end))


# ============================================================================
# 2. SAME-DAY SPY 0DTE PUT SPREAD
#    Rule + constants ported from hike_scanner.py (Dealers-Edge-dashboard):
#    SAME_DAY_* constants -- honest engine, GATE_75, 2022-2026.
# ============================================================================
VIX_GATE_MAX_RATIO = 0.80
VIX_GATE_LOOKBACK = 20

SAME_DAY_SHORT_OFFSET = 1.0
SAME_DAY_WING = 2.0
SAME_DAY_ENTRY_TIME_CT = dtime(13, 5)
SAME_DAY_EXIT_TIME_CT = dtime(14, 57)
SAME_DAY_EXIT_PROXIMITY = 0.50

SAME_DAY_INSTRUCTION_TEXT = (
    "At 1:05 PM CT: sell the SPY put $1 below spot, buy the put $2 below "
    "that, expiring today; exit 2:57 PM CT if SPY is within $0.50 of the "
    "short strike."
)
SAME_DAY_ECONOMICS_TEXT = (
    "~$8.47 per trade avg, $2,101/yr per contract, worst \u2212$181, "
    "329 trades (honest engine 2022-2026)"
)
SAME_DAY_NOTE_TEXT = "Fridays carry most of the edge; Thursdays the least (GATE_75)"


def compute_vix_gate(vix_prev: float, vix_20d_max: float) -> dict:
    """Pure: ratio = VIX close(T-1) / max VIX close over the 20 sessions before T-1. Gate OPEN
    if ratio <= VIX_GATE_MAX_RATIO. Source rule: hike_scanner.py's _vix_gate / GATE_75."""
    ratio = (vix_prev / vix_20d_max) if vix_20d_max else float("nan")
    gate_status = "OPEN" if ratio <= VIX_GATE_MAX_RATIO else "CLOSED"
    return {"ratio": ratio, "gate_status": gate_status}


# ============================================================================
# 3. FILINGSENSE -- wording ported verbatim from hike_scanner.py
#    (_fs_source / _fs_is_cluster / _fs_instruction / _fs_scorecard /
#    _fs_hit_rate_label).
# ============================================================================
FS_WINDOW_DAYS = 3
FS_STALE_HOURS = 24.0


def _fmt_ct(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M:%S CT")


def parse_any_iso_to_ct(iso_str) -> datetime | None:
    """Parse an ISO timestamp (naive treated as UTC) and return it in CT."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(CT)


def _fs_source(row: dict) -> str:
    """Insider rows carry insider_buyers/insider_rule; SEC ownership-stake filings (13D/13G) are
    'stake'; everything else (8-K, 8-K/A, ...) is a plain 'filing'."""
    if row.get("insider_buyers") is not None or row.get("insider_rule") is not None:
        return "insider"
    form = str(row.get("form") or "")
    if "13D" in form or "13G" in form:
        return "stake"
    return "filing"


def _fs_is_cluster(row: dict) -> bool:
    rule = row.get("insider_rule")
    if rule:
        return rule == "cluster"
    return (row.get("insider_buyers") or 0) >= 2


def _fs_instruction(row: dict, posted_ct: datetime) -> str:
    ticker = row.get("ticker", "?")
    signal = row.get("signal")
    source = _fs_source(row)
    ct_str = _fmt_ct(posted_ct)
    conf = row.get("confidence")
    conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"

    if signal == "bullish" and source == "insider":
        if _fs_is_cluster(row):
            rule_label = row.get("insider_rule") or "cluster"
            return (f"WATCH TO BUY {ticker} \u2014 2+ insiders bought on the open market "
                    f"({rule_label}), posted {ct_str}")
        return f"WATCH TO BUY {ticker} \u2014 one insider bought \u2265 a quarter-day of volume, posted {ct_str}"
    if signal == "bullish" and source == "filing":
        return f"WATCH TO BUY {ticker} \u2014 bullish SEC filing, confidence {conf_str}, posted {ct_str}"
    if signal == "bearish":
        return f"AVOID / SHORT CANDIDATE {ticker} \u2014 bearish {source}, confidence {conf_str}, posted {ct_str}"
    return f"WATCH {ticker} \u2014 {signal} {source}, confidence {conf_str}, posted {ct_str}"


def _fs_scorecard(rows: list[dict]) -> dict | None:
    """All-time scorecard over every non-backfilled row with a filled 1-day forward return."""
    scored = []
    for row in rows:
        ret_1d = row.get("ret_1d")
        if ret_1d is None:
            continue
        signal = row.get("signal")
        signed = float(ret_1d) if signal == "bullish" else -float(ret_1d)
        scored.append({"row": row, "signal": signal, "signed": signed, "source": _fs_source(row)})

    if not scored:
        return None

    def _bucket(items):
        n = len(items)
        right = sum(1 for it in items if it["signed"] > 0)
        avg = sum(it["signed"] for it in items) / n
        return {"n": n, "right": right, "avg": avg}

    out = {"all": _bucket(scored)}
    bullish = [s for s in scored if s["signal"] == "bullish"]
    bearish = [s for s in scored if s["signal"] == "bearish"]
    if bullish:
        out["bullish"] = _bucket(bullish)
    if bearish:
        out["bearish"] = _bucket(bearish)

    insider = [s for s in scored if s["source"] == "insider"]
    by_rule: dict[str, list] = {}
    for s in insider:
        rule = s["row"].get("insider_rule") or ("cluster" if _fs_is_cluster(s["row"]) else "size")
        by_rule.setdefault(rule, []).append(s)
    if by_rule:
        out["insider_by_rule"] = {rule: _bucket(items) for rule, items in sorted(by_rule.items())}

    return out


def _fs_hit_rate_label(row: dict, scorecard: dict | None) -> str:
    if scorecard is None:
        return "no validated number"
    if _fs_source(row) == "insider":
        rule = row.get("insider_rule") or ("cluster" if _fs_is_cluster(row) else "size")
        bucket = scorecard.get("insider_by_rule", {}).get(rule)
        if bucket:
            return f"{bucket['right']}/{bucket['n']} next-day ({bucket['right'] / bucket['n'] * 100:.0f}%)"
    bucket = scorecard.get(row.get("signal"))
    if bucket:
        return f"{bucket['right']}/{bucket['n']} next-day ({bucket['right'] / bucket['n'] * 100:.0f}%)"
    return "no validated number"


def filingsense_snapshot(rows: list[dict], now_ct: datetime) -> dict:
    """rows: every pushed ledger row (verbatim dicts). Returns the last FS_WINDOW_DAYS days'
    calls plus the all-time scorecard, newest first."""
    live_rows = [r for r in rows if not r.get("stale_backfill")]
    scorecard = _fs_scorecard(live_rows)

    window_start_date = now_ct.date() - timedelta(days=FS_WINDOW_DAYS - 1)
    windowed = []
    for row in live_rows:
        posted_ct = parse_any_iso_to_ct(row.get("posted_utc"))
        if posted_ct is None or posted_ct.date() < window_start_date:
            continue
        windowed.append((posted_ct, row))
    windowed.sort(key=lambda t: t[0], reverse=True)

    out_rows = []
    for posted_ct, row in windowed:
        age_hours = (now_ct - posted_ct).total_seconds() / 3600.0
        out_rows.append({
            "ticker": row.get("ticker"),
            "instruction": _fs_instruction(row, posted_ct),
            "posted_ct": posted_ct.isoformat(timespec="seconds"),
            "ret_1d": row.get("ret_1d"),
            "hit_rate": _fs_hit_rate_label(row, scorecard),
            "stale": age_hours > FS_STALE_HOURS,
        })

    return {"rows": out_rows, "scorecard": scorecard, "n_live_total": len(live_rows),
            "window_days": FS_WINDOW_DAYS}
