#!/usr/bin/env python3
"""
PHASE 3: STRATEGY BACKTESTING — All Tickers
============================================
Replays every closed AGAPE-SPOT trade through candidate filter strategies
and calculates hypothetical P&L if that filter had been active.

Uses ACTUAL trade history (agape_spot_positions) — not simulated fills.
For each strategy we simply ask: "Would this trade have been TAKEN or SKIPPED?"
If skipped, its realized_pnl is removed from the total.

Strategies tested (all per-ticker):
  S1:  Time-of-day filter          — only trade profitable 2-hour windows
  S2:  Close-reason avoidance      — skip trades whose exit type is net-negative
  S3:  Chop index filter           — only trade favorable volatility regimes
  S4:  Oracle probability threshold — raise minimum oracle win probability
  S5:  Signal confidence filter    — only trade HIGH / VERY_HIGH confidence
  S6:  Funding regime filter       — skip toxic funding regimes
  S7:  Cooldown / anti-overtrade   — minimum minutes between entries
  S8:  Max concurrent positions    — cap simultaneous open positions
  S9:  Combined "best-of" filter   — per-ticker optimal combination
  S10: Ticker elimination          — disable negative-EV tickers entirely

Output: side-by-side comparison per ticker showing baseline vs each strategy.

Run:
  python scripts/phase3_strategy_simulation.py

Requires: DATABASE_URL environment variable or .env file.
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

TICKERS = ["ETH-USD", "BTC-USD", "DOGE-USD", "XRP-USD", "SHIB-USD"]

# Coinbase Advanced Trade taker fee (estimated round-trip)
FEE_RATE_RT = 0.008  # 0.4% per side × 2

# ---------------------------------------------------------------------------
# Database helpers (same pattern as Phase 1 / Phase 2)
# ---------------------------------------------------------------------------

def get_db_connection():
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        if not url:
            env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
            )
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                            url = line.split("=", 1)[1].strip()
                            break
        if not url:
            print("ERROR: DATABASE_URL not set. Export it or create .env file.")
            sys.exit(1)
        return psycopg2.connect(url, connect_timeout=30)
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)


def q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description] if cur.description else []
    cur.close()
    return rows, cols


def pnl(val):
    if val is None:
        return "N/A"
    v = float(val)
    return f"${'+' if v >= 0 else ''}{v:,.2f}"


def pct(val):
    if val is None:
        return "N/A"
    return f"{float(val):.1f}%"


def bar(val, scale=2, max_len=30):
    if val is None:
        return ""
    v = float(val)
    n = min(int(abs(v) / scale), max_len)
    return ("█" * n) if v >= 0 else ("░" * n)


# ---------------------------------------------------------------------------
# Load all closed trades into Python dicts for replay
# ---------------------------------------------------------------------------

def load_trades(conn):
    """Load all closed, non-fallback trades with relevant columns."""
    rows, cols = q(conn, """
        SELECT
            position_id,
            ticker,
            status,
            entry_price,
            close_price,
            quantity,
            realized_pnl,
            close_reason,
            open_time,
            close_time,
            funding_regime_at_entry,
            oracle_win_probability,
            signal_confidence,
            chop_index_at_entry,
            funding_rate_at_entry,
            account_label,
            entry_fee_usd,
            exit_fee_usd,
            high_water_mark
        FROM agape_spot_positions
        WHERE status = 'closed'
          AND account_label NOT LIKE '%%_fallback'
          AND account_label != 'paper'
          AND realized_pnl IS NOT NULL
        ORDER BY open_time ASC
    """)

    trades = []
    for row in rows:
        d = dict(zip(cols, row))
        # Pre-compute CT hour for time-of-day filters
        ot = d["open_time"]
        if ot is not None:
            ct = ot.astimezone(CENTRAL_TZ) if ot.tzinfo else ot
            d["ct_hour"] = ct.hour
            d["ct_bucket"] = (ct.hour // 2) * 2  # 0,2,4,...,22
        else:
            d["ct_hour"] = None
            d["ct_bucket"] = None
        # Estimated fee if not recorded
        ep = d["entry_price"] or 0
        qty = d["quantity"] or 0
        d["est_fee"] = ep * qty * FEE_RATE_RT
        trades.append(d)

    return trades


# ---------------------------------------------------------------------------
# Baseline stats helper
# ---------------------------------------------------------------------------

def calc_stats(trades):
    """Return summary dict for a list of trade dicts."""
    if not trades:
        return {
            "count": 0, "pnl": 0.0, "wins": 0, "losses": 0,
            "wr": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "ev": 0.0,
            "est_fees": 0.0, "net_pnl": 0.0,
        }
    total_pnl = sum(float(t["realized_pnl"] or 0) for t in trades)
    wins = [t for t in trades if float(t["realized_pnl"] or 0) > 0]
    losses = [t for t in trades if float(t["realized_pnl"] or 0) <= 0]
    avg_win = (sum(float(t["realized_pnl"]) for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(float(t["realized_pnl"]) for t in losses) / len(losses)) if losses else 0
    est_fees = sum(t["est_fee"] for t in trades)
    wr = len(wins) / len(trades) * 100 if trades else 0
    ev = total_pnl / len(trades) if trades else 0
    return {
        "count": len(trades),
        "pnl": total_pnl,
        "wins": len(wins),
        "losses": len(losses),
        "wr": wr,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "ev": ev,
        "est_fees": est_fees,
        "net_pnl": total_pnl - est_fees,
    }


# ---------------------------------------------------------------------------
# Strategy filter functions
#   Each returns True if the trade should be TAKEN, False if SKIPPED.
# ---------------------------------------------------------------------------

# S1: Time-of-day — per-ticker profitable 2-hour windows
# These will be computed dynamically from the data in s1_find_profitable_hours()
S1_PROFITABLE_HOURS = {}  # populated at runtime: {ticker: set of ct_bucket values}


def s1_time_filter(trade):
    ticker = trade["ticker"]
    if ticker not in S1_PROFITABLE_HOURS:
        return True  # no data, allow
    bucket = trade.get("ct_bucket")
    if bucket is None:
        return False
    return bucket in S1_PROFITABLE_HOURS[ticker]


# S2: Close-reason avoidance — skip trades whose exit type is net-negative EV
S2_BAD_REASONS = {}  # populated at runtime: {ticker: set of close_reasons}


def s2_close_reason_filter(trade):
    """Pre-filter: skip if the entry conditions match patterns that end in bad exits.
    NOTE: We can't know close_reason at entry time in production, but we CAN
    identify that certain ENTRY conditions (chop, funding, hour) reliably produce
    bad exit types. This section just removes the bad-exit trades to measure
    the ceiling of improvement. S9 combines actionable entry-time filters."""
    ticker = trade["ticker"]
    if ticker not in S2_BAD_REASONS:
        return True
    reason = trade.get("close_reason") or "UNKNOWN"
    return reason not in S2_BAD_REASONS[ticker]


# S3: Chop index filter — only trade in favorable regimes
S3_CHOP_RANGES = {
    # (min, max) — trades outside this range are skipped
    # Will be tuned per ticker; defaults allow everything
}


def s3_chop_filter(trade):
    ticker = trade["ticker"]
    if ticker not in S3_CHOP_RANGES:
        return True
    chop = trade.get("chop_index_at_entry")
    if chop is None:
        return True  # no data, allow
    lo, hi = S3_CHOP_RANGES[ticker]
    return lo <= float(chop) <= hi


# S4: Oracle win probability threshold
S4_MIN_PROB = {}  # {ticker: min_prob}


def s4_oracle_filter(trade):
    ticker = trade["ticker"]
    if ticker not in S4_MIN_PROB:
        return True
    prob = trade.get("oracle_win_probability")
    if prob is None:
        return True
    return float(prob) >= S4_MIN_PROB[ticker]


# S5: Signal confidence filter
S5_ALLOWED_CONF = {}  # {ticker: set of allowed confidence levels}


def s5_confidence_filter(trade):
    ticker = trade["ticker"]
    if ticker not in S5_ALLOWED_CONF:
        return True
    conf = (trade.get("signal_confidence") or "UNKNOWN").upper()
    return conf in S5_ALLOWED_CONF[ticker]


# S6: Funding regime filter
S6_BLOCKED_REGIMES = {}  # {ticker: set of blocked regimes}


def s6_funding_filter(trade):
    ticker = trade["ticker"]
    if ticker not in S6_BLOCKED_REGIMES:
        return True
    regime = (trade.get("funding_regime_at_entry") or "UNKNOWN").upper()
    return regime not in S6_BLOCKED_REGIMES[ticker]


# S7: Anti-overtrade cooldown (minimum minutes between entries per ticker)
S7_COOLDOWN_MIN = {}  # {ticker: minutes}


def s7_cooldown_filter(trades_by_ticker, trade, last_entry_time):
    """Stateful filter — needs the timestamp of the last accepted trade."""
    ticker = trade["ticker"]
    if ticker not in S7_COOLDOWN_MIN:
        return True, trade["open_time"]
    cd = S7_COOLDOWN_MIN[ticker]
    ot = trade["open_time"]
    if ot is None:
        return True, last_entry_time
    if last_entry_time is None:
        return True, ot
    if (ot - last_entry_time).total_seconds() < cd * 60:
        return False, last_entry_time  # too soon, skip
    return True, ot


# S8: Max concurrent positions
S8_MAX_POS = {}  # {ticker: max_positions}


def s8_max_pos_filter(trade, open_positions):
    """Stateful: needs current count of open (not yet closed) positions."""
    ticker = trade["ticker"]
    if ticker not in S8_MAX_POS:
        return True
    return open_positions < S8_MAX_POS[ticker]


# ---------------------------------------------------------------------------
# S1 auto-tuning: find profitable 2-hour buckets per ticker
# ---------------------------------------------------------------------------

def s1_find_profitable_hours(trades):
    """Compute which 2-hour CT buckets are net-profitable per ticker."""
    global S1_PROFITABLE_HOURS
    bucket_pnl = defaultdict(lambda: defaultdict(float))  # ticker -> bucket -> pnl
    for t in trades:
        bucket = t.get("ct_bucket")
        if bucket is not None:
            bucket_pnl[t["ticker"]][bucket] += float(t["realized_pnl"] or 0)

    for ticker in TICKERS:
        profitable = set()
        for bucket, total in bucket_pnl.get(ticker, {}).items():
            if total > 0:
                profitable.add(bucket)
        S1_PROFITABLE_HOURS[ticker] = profitable


# ---------------------------------------------------------------------------
# S2 auto-tuning: find net-negative close reasons per ticker
# ---------------------------------------------------------------------------

def s2_find_bad_reasons(trades):
    global S2_BAD_REASONS
    reason_pnl = defaultdict(lambda: defaultdict(float))
    reason_cnt = defaultdict(lambda: defaultdict(int))
    for t in trades:
        reason = (t.get("close_reason") or "UNKNOWN")
        reason_pnl[t["ticker"]][reason] += float(t["realized_pnl"] or 0)
        reason_cnt[t["ticker"]][reason] += 1

    for ticker in TICKERS:
        bad = set()
        for reason, total in reason_pnl.get(ticker, {}).items():
            count = reason_cnt[ticker][reason]
            # Only flag if it's a meaningful sample AND net negative
            if total < 0 and count >= 3:
                bad.add(reason)
        S2_BAD_REASONS[ticker] = bad


# ---------------------------------------------------------------------------
# S3 auto-tuning: find best chop range per ticker
# ---------------------------------------------------------------------------

def s3_find_chop_ranges(trades):
    """Test chop buckets and find which range is profitable per ticker."""
    global S3_CHOP_RANGES
    # Buckets: 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0
    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
    bucket_pnl = defaultdict(lambda: defaultdict(float))
    bucket_cnt = defaultdict(lambda: defaultdict(int))

    for t in trades:
        chop = t.get("chop_index_at_entry")
        if chop is None:
            continue
        chop = float(chop)
        for i in range(len(edges) - 1):
            if edges[i] <= chop < edges[i + 1]:
                label = f"{edges[i]:.1f}-{edges[i+1]:.2f}"
                bucket_pnl[t["ticker"]][label] += float(t["realized_pnl"] or 0)
                bucket_cnt[t["ticker"]][label] += 1
                break

    for ticker in TICKERS:
        # Find contiguous profitable range
        profitable_buckets = []
        for i in range(len(edges) - 1):
            label = f"{edges[i]:.1f}-{edges[i+1]:.2f}"
            if bucket_pnl.get(ticker, {}).get(label, 0) > 0:
                profitable_buckets.append((edges[i], edges[i + 1]))

        if profitable_buckets:
            lo = min(b[0] for b in profitable_buckets)
            hi = max(b[1] for b in profitable_buckets)
            S3_CHOP_RANGES[ticker] = (lo, hi)


# ---------------------------------------------------------------------------
# S4 auto-tuning: find best oracle threshold per ticker
# ---------------------------------------------------------------------------

def s4_find_oracle_thresholds(trades):
    global S4_MIN_PROB
    # Test thresholds: 0.45, 0.50, 0.55, 0.60, 0.65
    thresholds = [0.45, 0.50, 0.55, 0.60, 0.65]

    for ticker in TICKERS:
        ticker_trades = [t for t in trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        best_thresh = None
        best_improvement = 0

        for thresh in thresholds:
            filtered = [
                t for t in ticker_trades
                if t.get("oracle_win_probability") is None
                or float(t["oracle_win_probability"]) >= thresh
            ]
            if not filtered:
                continue
            filtered_pnl = sum(float(t["realized_pnl"] or 0) for t in filtered)
            improvement = filtered_pnl - baseline_pnl
            if improvement > best_improvement:
                best_improvement = improvement
                best_thresh = thresh

        if best_thresh is not None:
            S4_MIN_PROB[ticker] = best_thresh


# ---------------------------------------------------------------------------
# S5 auto-tuning: find best confidence levels per ticker
# ---------------------------------------------------------------------------

def s5_find_confidence_levels(trades):
    global S5_ALLOWED_CONF
    conf_pnl = defaultdict(lambda: defaultdict(float))

    for t in trades:
        conf = (t.get("signal_confidence") or "UNKNOWN").upper()
        conf_pnl[t["ticker"]][conf] += float(t["realized_pnl"] or 0)

    for ticker in TICKERS:
        allowed = set()
        for conf, total in conf_pnl.get(ticker, {}).items():
            if total > 0:
                allowed.add(conf)
        if allowed:
            S5_ALLOWED_CONF[ticker] = allowed


# ---------------------------------------------------------------------------
# S6 auto-tuning: find toxic funding regimes per ticker
# ---------------------------------------------------------------------------

def s6_find_blocked_regimes(trades):
    global S6_BLOCKED_REGIMES
    regime_pnl = defaultdict(lambda: defaultdict(float))
    regime_cnt = defaultdict(lambda: defaultdict(int))

    for t in trades:
        regime = (t.get("funding_regime_at_entry") or "UNKNOWN").upper()
        regime_pnl[t["ticker"]][regime] += float(t["realized_pnl"] or 0)
        regime_cnt[t["ticker"]][regime] += 1

    for ticker in TICKERS:
        blocked = set()
        for regime, total in regime_pnl.get(ticker, {}).items():
            count = regime_cnt[ticker][regime]
            if total < 0 and count >= 3:
                blocked.add(regime)
        S6_BLOCKED_REGIMES[ticker] = blocked


# ---------------------------------------------------------------------------
# S7 auto-tuning: find best cooldown per ticker
# ---------------------------------------------------------------------------

def s7_find_cooldowns(trades):
    """Test cooldowns and pick the one that improves P&L the most."""
    global S7_COOLDOWN_MIN
    candidates = [5, 10, 15, 30, 60]  # minutes

    for ticker in TICKERS:
        ticker_trades = [t for t in trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        best_cd = None
        best_pnl = baseline_pnl

        for cd in candidates:
            accepted = []
            last_time = None
            for t in ticker_trades:
                ot = t["open_time"]
                if ot is None:
                    accepted.append(t)
                    continue
                if last_time is None or (ot - last_time).total_seconds() >= cd * 60:
                    accepted.append(t)
                    last_time = ot

            filtered_pnl = sum(float(t["realized_pnl"] or 0) for t in accepted)
            if filtered_pnl > best_pnl:
                best_pnl = filtered_pnl
                best_cd = cd

        if best_cd is not None:
            S7_COOLDOWN_MIN[ticker] = best_cd


# ---------------------------------------------------------------------------
# S8 auto-tuning: find best max positions per ticker
# ---------------------------------------------------------------------------

def s8_find_max_positions(trades):
    global S8_MAX_POS
    candidates = [1, 2, 3, 5]

    for ticker in TICKERS:
        ticker_trades = [t for t in trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        best_max = None
        best_pnl = baseline_pnl

        for max_p in candidates:
            accepted = []
            # Track open positions with a simple simulation
            open_pos = []
            for t in ticker_trades:
                ot = t["open_time"]
                ct = t["close_time"]
                # Close positions that ended before this one opened
                if ot is not None:
                    open_pos = [p for p in open_pos if p["close_time"] and p["close_time"] > ot]
                if len(open_pos) < max_p:
                    accepted.append(t)
                    open_pos.append(t)

            filtered_pnl = sum(float(t["realized_pnl"] or 0) for t in accepted)
            if filtered_pnl > best_pnl:
                best_pnl = filtered_pnl
                best_max = max_p

        if best_max is not None:
            S8_MAX_POS[ticker] = best_max


# ---------------------------------------------------------------------------
# Apply a single filter to trades, return accepted trades
# ---------------------------------------------------------------------------

def apply_stateless_filter(trades, filter_fn):
    """Apply a stateless (per-trade) filter."""
    return [t for t in trades if filter_fn(t)]


def apply_cooldown_filter(trades):
    """Apply stateful cooldown filter (S7)."""
    by_ticker = defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append(t)

    accepted = []
    for ticker in TICKERS:
        last_time = None
        for t in by_ticker.get(ticker, []):
            ok, last_time = s7_cooldown_filter(by_ticker, t, last_time)
            if ok:
                accepted.append(t)

    # Re-sort by open_time
    accepted.sort(key=lambda t: t["open_time"] or datetime.min.replace(tzinfo=CENTRAL_TZ))
    return accepted


def apply_max_pos_filter(trades):
    """Apply stateful max-position filter (S8)."""
    by_ticker = defaultdict(list)
    for t in trades:
        by_ticker[t["ticker"]].append(t)

    accepted = []
    for ticker in TICKERS:
        open_pos = []
        for t in by_ticker.get(ticker, []):
            ot = t["open_time"]
            if ot is not None:
                open_pos = [p for p in open_pos if p["close_time"] and p["close_time"] > ot]
            if s8_max_pos_filter(t, len(open_pos)):
                accepted.append(t)
                open_pos.append(t)

    accepted.sort(key=lambda t: t["open_time"] or datetime.min.replace(tzinfo=CENTRAL_TZ))
    return accepted


# ---------------------------------------------------------------------------
# S9: Combined optimal — chain best filters per ticker
# ---------------------------------------------------------------------------

def apply_combined_filter(trades):
    """Apply all profitable filters in sequence."""
    result = trades
    result = apply_stateless_filter(result, s1_time_filter)
    result = apply_stateless_filter(result, s3_chop_filter)
    result = apply_stateless_filter(result, s4_oracle_filter)
    result = apply_stateless_filter(result, s5_confidence_filter)
    result = apply_stateless_filter(result, s6_funding_filter)
    result = apply_cooldown_filter(result)
    result = apply_max_pos_filter(result)
    return result


# ---------------------------------------------------------------------------
# S10: Ticker elimination — remove negative-EV tickers
# ---------------------------------------------------------------------------

def apply_ticker_elimination(trades):
    """Remove tickers where baseline P&L is negative."""
    by_ticker = defaultdict(float)
    for t in trades:
        by_ticker[t["ticker"]] += float(t["realized_pnl"] or 0)

    good_tickers = {tk for tk, p in by_ticker.items() if p > 0}
    return [t for t in trades if t["ticker"] in good_tickers]


# ===================================================================
# REPORTING
# ===================================================================

def print_section(title):
    print("\n" + "=" * 90)
    print(f"  {title}")
    print("=" * 90)


def print_strategy_comparison(label, baseline_by_tk, filtered_by_tk):
    """Print side-by-side baseline vs filtered for each ticker."""
    print(f"\n  {'Ticker':<12} {'Baseline':>38}  {'':>3} {'Filtered':>38}")
    print(f"  {'':12} {'Trades':>7} {'P&L':>10} {'WR':>7} {'EV/trade':>10}  {'→':>3} {'Trades':>7} {'P&L':>10} {'WR':>7} {'EV/trade':>10}  {'ΔP&L':>10}")
    print(f"  {'-'*105}")

    total_base_pnl = 0
    total_filt_pnl = 0

    for ticker in TICKERS:
        b = baseline_by_tk.get(ticker, calc_stats([]))
        f = filtered_by_tk.get(ticker, calc_stats([]))
        delta = f["pnl"] - b["pnl"]
        total_base_pnl += b["pnl"]
        total_filt_pnl += f["pnl"]

        sign = "+" if delta >= 0 else ""
        print(
            f"  {ticker:<12}"
            f" {b['count']:>7} {pnl(b['pnl']):>10} {pct(b['wr']):>7} {pnl(b['ev']):>10}"
            f"  {'→':>3}"
            f" {f['count']:>7} {pnl(f['pnl']):>10} {pct(f['wr']):>7} {pnl(f['ev']):>10}"
            f"  {sign}{pnl(delta)[1:] if delta >= 0 else pnl(delta):>10}"
        )

    total_delta = total_filt_pnl - total_base_pnl
    sign = "+" if total_delta >= 0 else ""
    print(f"  {'-'*105}")
    print(
        f"  {'TOTAL':<12}"
        f" {'':>7} {pnl(total_base_pnl):>10} {'':>7} {'':>10}"
        f"  {'→':>3}"
        f" {'':>7} {pnl(total_filt_pnl):>10} {'':>7} {'':>10}"
        f"  {sign}{pnl(total_delta)[1:] if total_delta >= 0 else pnl(total_delta):>10}"
    )


def compute_by_ticker(trades):
    by_tk = defaultdict(list)
    for t in trades:
        by_tk[t["ticker"]].append(t)
    return {tk: calc_stats(tl) for tk, tl in by_tk.items()}


# ===================================================================
# MAIN ANALYSIS SECTIONS
# ===================================================================

def show_baseline(all_trades):
    print_section("BASELINE — Current Performance (All Closed Trades, No Filters)")

    by_tk = compute_by_ticker(all_trades)
    overall = calc_stats(all_trades)

    print(f"\n  {'Ticker':<12} {'Trades':>7} {'Gross P&L':>10} {'Est Fees':>10} {'Net P&L':>10} "
          f"{'WR':>7} {'Avg Win':>9} {'Avg Loss':>9} {'EV/trade':>10}")
    print(f"  {'-'*95}")

    for ticker in TICKERS:
        s = by_tk.get(ticker, calc_stats([]))
        print(
            f"  {ticker:<12} {s['count']:>7} {pnl(s['pnl']):>10} {pnl(-s['est_fees']):>10} "
            f"{pnl(s['net_pnl']):>10} {pct(s['wr']):>7} {pnl(s['avg_win']):>9} "
            f"{pnl(s['avg_loss']):>9} {pnl(s['ev']):>10}"
        )

    print(f"  {'-'*95}")
    print(
        f"  {'TOTAL':<12} {overall['count']:>7} {pnl(overall['pnl']):>10} "
        f"{pnl(-overall['est_fees']):>10} {pnl(overall['net_pnl']):>10} "
        f"{pct(overall['wr']):>7} {pnl(overall['avg_win']):>9} "
        f"{pnl(overall['avg_loss']):>9} {pnl(overall['ev']):>10}"
    )
    return by_tk


def show_s1_time_details(all_trades):
    """Show the per-ticker time-of-day breakdown before filtering."""
    print_section("S1: TIME-OF-DAY FILTER — Profitable Hours per Ticker")
    print("  Only keep trades opened during net-profitable 2-hour CT windows.\n")

    bucket_pnl = defaultdict(lambda: defaultdict(float))
    bucket_cnt = defaultdict(lambda: defaultdict(int))
    for t in all_trades:
        bucket = t.get("ct_bucket")
        if bucket is not None:
            bucket_pnl[t["ticker"]][bucket] += float(t["realized_pnl"] or 0)
            bucket_cnt[t["ticker"]][bucket] += 1

    for ticker in TICKERS:
        buckets = sorted(bucket_pnl.get(ticker, {}).keys())
        if not buckets:
            continue
        print(f"  {ticker}:")
        print(f"    {'Window':>10} {'Trades':>7} {'P&L':>10} {'Status':>10}")
        print(f"    {'-'*42}")
        for b in buckets:
            p = bucket_pnl[ticker][b]
            c = bucket_cnt[ticker][b]
            status = "  KEEP" if b in S1_PROFITABLE_HOURS.get(ticker, set()) else "  SKIP"
            print(f"    {b:>02}:00-{b+2:>02}:00 {c:>7} {pnl(p):>10} {status:>10}")
        kept = S1_PROFITABLE_HOURS.get(ticker, set())
        print(f"    Keeping: {sorted(kept)} ({len(kept)} of {len(buckets)} windows)\n")


def show_s2_close_reason_details(all_trades):
    print_section("S2: CLOSE-REASON ANALYSIS — Net-Negative Exit Types")
    print("  Identifies which close_reason types are net P&L destroyers.\n")

    reason_pnl = defaultdict(lambda: defaultdict(float))
    reason_cnt = defaultdict(lambda: defaultdict(int))
    for t in all_trades:
        reason = (t.get("close_reason") or "UNKNOWN")
        reason_pnl[t["ticker"]][reason] += float(t["realized_pnl"] or 0)
        reason_cnt[t["ticker"]][reason] += 1

    for ticker in TICKERS:
        reasons = reason_pnl.get(ticker, {})
        if not reasons:
            continue
        print(f"  {ticker}:")
        print(f"    {'Close Reason':<30} {'Trades':>7} {'P&L':>10} {'Status':>10}")
        print(f"    {'-'*62}")
        for reason in sorted(reasons.keys(), key=lambda r: reasons[r]):
            p = reasons[reason]
            c = reason_cnt[ticker][reason]
            bad = S2_BAD_REASONS.get(ticker, set())
            status = "  SKIP" if reason in bad else "  KEEP"
            print(f"    {reason:<30} {c:>7} {pnl(p):>10} {status:>10}")
        print()


def show_s3_chop_details(all_trades):
    print_section("S3: CHOP INDEX FILTER — Favorable Volatility Regimes")
    print("  Trades bucketed by chop_index_at_entry.\n")

    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
    bucket_pnl = defaultdict(lambda: defaultdict(float))
    bucket_cnt = defaultdict(lambda: defaultdict(int))

    for t in all_trades:
        chop = t.get("chop_index_at_entry")
        if chop is None:
            continue
        chop = float(chop)
        for i in range(len(edges) - 1):
            if edges[i] <= chop < edges[i + 1]:
                label = f"{edges[i]:.1f}-{edges[i+1]:.2f}"
                bucket_pnl[t["ticker"]][label] += float(t["realized_pnl"] or 0)
                bucket_cnt[t["ticker"]][label] += 1
                break

    for ticker in TICKERS:
        buckets = bucket_pnl.get(ticker, {})
        if not buckets:
            continue
        print(f"  {ticker}:")
        rng = S3_CHOP_RANGES.get(ticker, None)
        rng_str = f"[{rng[0]:.1f}, {rng[1]:.2f}]" if rng else "ALL (no filter)"
        print(f"    Selected range: {rng_str}")
        print(f"    {'Chop Bucket':<15} {'Trades':>7} {'P&L':>10}")
        print(f"    {'-'*35}")
        for i in range(len(edges) - 1):
            label = f"{edges[i]:.1f}-{edges[i+1]:.2f}"
            p = buckets.get(label, 0)
            c = bucket_cnt[ticker].get(label, 0)
            if c > 0:
                print(f"    {label:<15} {c:>7} {pnl(p):>10}")
        print()


def show_s4_oracle_details(all_trades):
    print_section("S4: ORACLE WIN PROBABILITY THRESHOLD")
    print("  Sweeps thresholds 0.45–0.65 to find optimal minimum per ticker.\n")

    thresholds = [0.45, 0.50, 0.55, 0.60, 0.65]

    for ticker in TICKERS:
        ticker_trades = [t for t in all_trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        print(f"  {ticker} (baseline: {pnl(baseline_pnl)}):")
        print(f"    {'Threshold':>10} {'Trades':>7} {'P&L':>10} {'WR':>7} {'ΔP&L':>10}")
        print(f"    {'-'*48}")

        for thresh in thresholds:
            filtered = [
                t for t in ticker_trades
                if t.get("oracle_win_probability") is None
                or float(t["oracle_win_probability"]) >= thresh
            ]
            s = calc_stats(filtered)
            delta = s["pnl"] - baseline_pnl
            chosen = " ←" if S4_MIN_PROB.get(ticker) == thresh else ""
            print(f"    {thresh:>10.2f} {s['count']:>7} {pnl(s['pnl']):>10} {pct(s['wr']):>7} {pnl(delta):>10}{chosen}")

        selected = S4_MIN_PROB.get(ticker)
        print(f"    Selected: {selected if selected else 'NONE (no improvement)'}\n")


def show_s6_funding_details(all_trades):
    print_section("S6: FUNDING REGIME FILTER — Block Toxic Regimes")
    print("  Skip entries during funding regimes with net-negative P&L.\n")

    regime_pnl = defaultdict(lambda: defaultdict(float))
    regime_cnt = defaultdict(lambda: defaultdict(int))
    for t in all_trades:
        regime = (t.get("funding_regime_at_entry") or "UNKNOWN").upper()
        regime_pnl[t["ticker"]][regime] += float(t["realized_pnl"] or 0)
        regime_cnt[t["ticker"]][regime] += 1

    for ticker in TICKERS:
        regimes = regime_pnl.get(ticker, {})
        if not regimes:
            continue
        print(f"  {ticker}:")
        blocked = S6_BLOCKED_REGIMES.get(ticker, set())
        print(f"    {'Regime':<25} {'Trades':>7} {'P&L':>10} {'Status':>10}")
        print(f"    {'-'*57}")
        for regime in sorted(regimes.keys(), key=lambda r: regimes[r]):
            p = regimes[regime]
            c = regime_cnt[ticker][regime]
            status = "  BLOCK" if regime in blocked else "  ALLOW"
            print(f"    {regime:<25} {c:>7} {pnl(p):>10} {status:>10}")
        print()


def show_s7_cooldown_details(all_trades):
    print_section("S7: ANTI-OVERTRADE COOLDOWN")
    print("  Minimum minutes between consecutive entries per ticker.\n")

    candidates = [5, 10, 15, 30, 60]

    for ticker in TICKERS:
        ticker_trades = [t for t in all_trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        print(f"  {ticker} (baseline: {len(ticker_trades)} trades, {pnl(baseline_pnl)}):")
        print(f"    {'Cooldown':>10} {'Trades':>7} {'P&L':>10} {'ΔP&L':>10}")
        print(f"    {'-'*40}")

        for cd in candidates:
            accepted = []
            last_time = None
            for t in ticker_trades:
                ot = t["open_time"]
                if ot is None:
                    accepted.append(t)
                    continue
                if last_time is None or (ot - last_time).total_seconds() >= cd * 60:
                    accepted.append(t)
                    last_time = ot
            s = calc_stats(accepted)
            delta = s["pnl"] - baseline_pnl
            chosen = " ←" if S7_COOLDOWN_MIN.get(ticker) == cd else ""
            print(f"    {cd:>7} min {s['count']:>7} {pnl(s['pnl']):>10} {pnl(delta):>10}{chosen}")

        selected = S7_COOLDOWN_MIN.get(ticker)
        print(f"    Selected: {selected} min" if selected else "    Selected: NONE")
        print()


def show_s8_max_pos_details(all_trades):
    print_section("S8: MAX CONCURRENT POSITIONS")
    print("  Cap simultaneous open positions per ticker.\n")

    candidates = [1, 2, 3, 5]

    for ticker in TICKERS:
        ticker_trades = [t for t in all_trades if t["ticker"] == ticker]
        if not ticker_trades:
            continue

        baseline_pnl = sum(float(t["realized_pnl"] or 0) for t in ticker_trades)
        print(f"  {ticker} (baseline: {len(ticker_trades)} trades, {pnl(baseline_pnl)}):")
        print(f"    {'Max Pos':>10} {'Trades':>7} {'P&L':>10} {'ΔP&L':>10}")
        print(f"    {'-'*40}")

        for max_p in candidates:
            accepted = []
            open_pos = []
            for t in ticker_trades:
                ot = t["open_time"]
                if ot is not None:
                    open_pos = [p for p in open_pos if p["close_time"] and p["close_time"] > ot]
                if len(open_pos) < max_p:
                    accepted.append(t)
                    open_pos.append(t)
            s = calc_stats(accepted)
            delta = s["pnl"] - baseline_pnl
            chosen = " ←" if S8_MAX_POS.get(ticker) == max_p else ""
            print(f"    {max_p:>10} {s['count']:>7} {pnl(s['pnl']):>10} {pnl(delta):>10}{chosen}")

        selected = S8_MAX_POS.get(ticker)
        print(f"    Selected: {selected}" if selected else "    Selected: NONE")
        print()


def show_summary(baseline_by_tk, results):
    """Final comparison table — all strategies side by side."""
    print_section("FINAL COMPARISON — All Strategies vs Baseline (ΔP&L)")

    print(f"\n  {'Ticker':<12}", end="")
    for label in results:
        print(f" {label:>12}", end="")
    print()
    print(f"  {'-' * (12 + 13 * len(results))}")

    totals = defaultdict(float)

    for ticker in TICKERS:
        base_pnl = baseline_by_tk.get(ticker, calc_stats([]))["pnl"]
        print(f"  {ticker:<12}", end="")
        for label, by_tk in results.items():
            filt_pnl = by_tk.get(ticker, calc_stats([]))["pnl"]
            delta = filt_pnl - base_pnl
            totals[label] += delta
            sign = "+" if delta >= 0 else ""
            print(f" {sign}${abs(delta):>9,.2f}", end="")
        print()

    print(f"  {'-' * (12 + 13 * len(results))}")
    print(f"  {'TOTAL':<12}", end="")
    for label in results:
        d = totals[label]
        sign = "+" if d >= 0 else ""
        print(f" {sign}${abs(d):>9,.2f}", end="")
    print()

    # Best strategy
    if totals:
        best = max(totals.items(), key=lambda x: x[1])
        print(f"\n  BEST SINGLE STRATEGY: {best[0]} ({'+' if best[1] >= 0 else ''}${abs(best[1]):,.2f} vs baseline)")


def show_per_ticker_recommendation(baseline_by_tk, results):
    """Per-ticker: which strategy is best?"""
    print_section("PER-TICKER BEST STRATEGY RECOMMENDATION")

    for ticker in TICKERS:
        base_pnl = baseline_by_tk.get(ticker, calc_stats([]))["pnl"]
        best_label = "BASELINE"
        best_delta = 0
        best_pnl = base_pnl

        for label, by_tk in results.items():
            filt_pnl = by_tk.get(ticker, calc_stats([]))["pnl"]
            delta = filt_pnl - base_pnl
            if delta > best_delta:
                best_delta = delta
                best_label = label
                best_pnl = filt_pnl

        improvement = (best_delta / abs(base_pnl) * 100) if base_pnl != 0 else 0
        filt_stats = results.get(best_label, {}).get(ticker, calc_stats([]))

        print(f"\n  {ticker}:")
        print(f"    Baseline:       {pnl(base_pnl)}")
        print(f"    Best strategy:  {best_label}")
        print(f"    Filtered P&L:   {pnl(best_pnl)} ({'+' if best_delta >= 0 else ''}{pnl(best_delta)} / {improvement:+.1f}%)")

        # Show tuned parameters for this ticker
        params = []
        if ticker in S1_PROFITABLE_HOURS:
            hours = sorted(S1_PROFITABLE_HOURS[ticker])
            params.append(f"Hours(CT): {hours}")
        if ticker in S3_CHOP_RANGES:
            lo, hi = S3_CHOP_RANGES[ticker]
            params.append(f"Chop: [{lo:.1f}, {hi:.2f}]")
        if ticker in S4_MIN_PROB:
            params.append(f"Oracle >= {S4_MIN_PROB[ticker]:.2f}")
        if ticker in S6_BLOCKED_REGIMES and S6_BLOCKED_REGIMES[ticker]:
            params.append(f"Block funding: {S6_BLOCKED_REGIMES[ticker]}")
        if ticker in S7_COOLDOWN_MIN:
            params.append(f"Cooldown: {S7_COOLDOWN_MIN[ticker]} min")
        if ticker in S8_MAX_POS:
            params.append(f"Max pos: {S8_MAX_POS[ticker]}")

        if params:
            print(f"    Tuned params:")
            for p in params:
                print(f"      - {p}")


def show_fee_adjusted_summary(baseline_by_tk, results):
    """Show net P&L after estimated fees for baseline and best strategies."""
    print_section("FEE-ADJUSTED NET P&L (After Estimated 0.8% Round-Trip Fees)")

    print(f"\n  {'Ticker':<12} {'Gross Base':>11} {'Base Fees':>11} {'Net Base':>11}"
          f" {'':>3} {'Gross Best':>11} {'Best Fees':>11} {'Net Best':>11} {'Strategy':<12}")
    print(f"  {'-'*100}")

    for ticker in TICKERS:
        base = baseline_by_tk.get(ticker, calc_stats([]))
        best_label = "BASELINE"
        best_net = base["net_pnl"]

        for label, by_tk in results.items():
            s = by_tk.get(ticker, calc_stats([]))
            if s["net_pnl"] > best_net:
                best_net = s["net_pnl"]
                best_label = label
                best_stats = s

        if best_label == "BASELINE":
            best_stats = base

        print(
            f"  {ticker:<12}"
            f" {pnl(base['pnl']):>11} {pnl(-base['est_fees']):>11} {pnl(base['net_pnl']):>11}"
            f" {'→':>3}"
            f" {pnl(best_stats['pnl']):>11} {pnl(-best_stats['est_fees']):>11} {pnl(best_stats['net_pnl']):>11}"
            f" {best_label:<12}"
        )


# ===================================================================
# MAIN
# ===================================================================

def main():
    print("=" * 90)
    print("  PHASE 3: STRATEGY BACKTESTING — All Tickers")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("  Replays closed trades through candidate filters to find optimal settings.")
    print("=" * 90)

    conn = get_db_connection()

    # ------------------------------------------------------------------
    # Load all trades
    # ------------------------------------------------------------------
    all_trades = load_trades(conn)
    conn.close()

    if not all_trades:
        print("\n  ERROR: No closed trades found. Nothing to backtest.")
        return

    trade_counts = defaultdict(int)
    for t in all_trades:
        trade_counts[t["ticker"]] += 1

    print(f"\n  Loaded {len(all_trades)} closed trades:")
    for ticker in TICKERS:
        c = trade_counts.get(ticker, 0)
        if c > 0:
            print(f"    {ticker}: {c} trades")

    date_range = [t["open_time"] for t in all_trades if t["open_time"]]
    if date_range:
        print(f"  Date range: {min(date_range).strftime('%Y-%m-%d')} to {max(date_range).strftime('%Y-%m-%d')}")

    # ------------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------------
    baseline_by_tk = show_baseline(all_trades)

    # ------------------------------------------------------------------
    # Auto-tune all filters
    # ------------------------------------------------------------------
    print_section("AUTO-TUNING FILTERS (finding optimal parameters per ticker)")
    print("  Scanning trade history to find best filter settings...\n")

    s1_find_profitable_hours(all_trades)
    print("  S1 Time-of-day:    done")

    s2_find_bad_reasons(all_trades)
    print("  S2 Close-reason:   done")

    s3_find_chop_ranges(all_trades)
    print("  S3 Chop index:     done")

    s4_find_oracle_thresholds(all_trades)
    print("  S4 Oracle prob:    done")

    s5_find_confidence_levels(all_trades)
    print("  S5 Confidence:     done")

    s6_find_blocked_regimes(all_trades)
    print("  S6 Funding regime: done")

    s7_find_cooldowns(all_trades)
    print("  S7 Cooldown:       done")

    s8_find_max_positions(all_trades)
    print("  S8 Max positions:  done")

    # ------------------------------------------------------------------
    # Show detailed filter analysis
    # ------------------------------------------------------------------
    show_s1_time_details(all_trades)
    show_s2_close_reason_details(all_trades)
    show_s3_chop_details(all_trades)
    show_s4_oracle_details(all_trades)
    show_s6_funding_details(all_trades)
    show_s7_cooldown_details(all_trades)
    show_s8_max_pos_details(all_trades)

    # ------------------------------------------------------------------
    # Apply each strategy and collect results
    # ------------------------------------------------------------------
    print_section("STRATEGY RESULTS — Filtered vs Baseline")

    strategies = {}

    # S1: Time filter
    s1_filtered = apply_stateless_filter(all_trades, s1_time_filter)
    strategies["S1:Time"] = compute_by_ticker(s1_filtered)
    print_strategy_comparison("S1: Time-of-Day Filter", baseline_by_tk, strategies["S1:Time"])

    # S2: Close-reason filter (ceiling estimate)
    s2_filtered = apply_stateless_filter(all_trades, s2_close_reason_filter)
    strategies["S2:ExitType"] = compute_by_ticker(s2_filtered)
    print_strategy_comparison("S2: Close-Reason Filter (ceiling — not actionable at entry)", baseline_by_tk, strategies["S2:ExitType"])

    # S3: Chop index filter
    s3_filtered = apply_stateless_filter(all_trades, s3_chop_filter)
    strategies["S3:Chop"] = compute_by_ticker(s3_filtered)
    print_strategy_comparison("S3: Chop Index Filter", baseline_by_tk, strategies["S3:Chop"])

    # S4: Oracle probability filter
    s4_filtered = apply_stateless_filter(all_trades, s4_oracle_filter)
    strategies["S4:Oracle"] = compute_by_ticker(s4_filtered)
    print_strategy_comparison("S4: Oracle Probability Filter", baseline_by_tk, strategies["S4:Oracle"])

    # S5: Signal confidence filter
    s5_filtered = apply_stateless_filter(all_trades, s5_confidence_filter)
    strategies["S5:Conf"] = compute_by_ticker(s5_filtered)
    print_strategy_comparison("S5: Signal Confidence Filter", baseline_by_tk, strategies["S5:Conf"])

    # S6: Funding regime filter
    s6_filtered = apply_stateless_filter(all_trades, s6_funding_filter)
    strategies["S6:Funding"] = compute_by_ticker(s6_filtered)
    print_strategy_comparison("S6: Funding Regime Filter", baseline_by_tk, strategies["S6:Funding"])

    # S7: Cooldown filter
    s7_filtered = apply_cooldown_filter(all_trades)
    strategies["S7:Cooldown"] = compute_by_ticker(s7_filtered)
    print_strategy_comparison("S7: Anti-Overtrade Cooldown", baseline_by_tk, strategies["S7:Cooldown"])

    # S8: Max positions filter
    s8_filtered = apply_max_pos_filter(all_trades)
    strategies["S8:MaxPos"] = compute_by_ticker(s8_filtered)
    print_strategy_comparison("S8: Max Concurrent Positions", baseline_by_tk, strategies["S8:MaxPos"])

    # S9: Combined optimal
    s9_filtered = apply_combined_filter(all_trades)
    strategies["S9:Combined"] = compute_by_ticker(s9_filtered)
    print_strategy_comparison("S9: Combined Optimal Filters", baseline_by_tk, strategies["S9:Combined"])

    # S10: Ticker elimination
    s10_filtered = apply_ticker_elimination(all_trades)
    strategies["S10:TickerKill"] = compute_by_ticker(s10_filtered)
    print_strategy_comparison("S10: Disable Negative-EV Tickers", baseline_by_tk, strategies["S10:TickerKill"])

    # ------------------------------------------------------------------
    # Summary tables
    # ------------------------------------------------------------------
    show_summary(baseline_by_tk, strategies)
    show_per_ticker_recommendation(baseline_by_tk, strategies)
    show_fee_adjusted_summary(baseline_by_tk, strategies)

    # ------------------------------------------------------------------
    # Actionable implementation guide
    # ------------------------------------------------------------------
    print_section("IMPLEMENTATION GUIDE — What to Change in Production")

    print("""
  Priority 1: IMMEDIATE (no downside risk)
  ─────────────────────────────────────────""")

    for ticker in TICKERS:
        base = baseline_by_tk.get(ticker, calc_stats([]))
        if base["pnl"] < 0 and base["count"] >= 10:
            print(f"    DISABLE {ticker}: Net negative P&L ({pnl(base['pnl'])} over {base['count']} trades)")

    for ticker in TICKERS:
        if ticker in S7_COOLDOWN_MIN:
            print(f"    {ticker}: Add {S7_COOLDOWN_MIN[ticker]}-min cooldown between entries")

    for ticker in TICKERS:
        if ticker in S8_MAX_POS:
            print(f"    {ticker}: Cap max concurrent positions at {S8_MAX_POS[ticker]}")

    print("""
  Priority 2: SIGNAL QUALITY (implement in signals.py)
  ─────────────────────────────────────────────────────""")

    for ticker in TICKERS:
        if ticker in S1_PROFITABLE_HOURS:
            hours = sorted(S1_PROFITABLE_HOURS[ticker])
            if len(hours) < 12:
                windows = [f"{h:02d}:00-{h+2:02d}:00" for h in hours]
                print(f"    {ticker}: Only trade during CT windows: {', '.join(windows)}")

    for ticker in TICKERS:
        if ticker in S4_MIN_PROB:
            print(f"    {ticker}: Require oracle_win_probability >= {S4_MIN_PROB[ticker]:.2f}")

    for ticker in TICKERS:
        if ticker in S3_CHOP_RANGES:
            lo, hi = S3_CHOP_RANGES[ticker]
            print(f"    {ticker}: Only trade when chop_index in [{lo:.1f}, {hi:.2f}]")

    for ticker in TICKERS:
        blocked = S6_BLOCKED_REGIMES.get(ticker, set())
        if blocked:
            print(f"    {ticker}: Block entries during funding regimes: {blocked}")

    print("""
  Priority 3: MONITORING (verify post-deployment)
  ────────────────────────────────────────────────
    Run phase3 again after 7 days of filtered trading.
    Compare actual vs predicted improvement.
    If actual improvement < 50%% of predicted, review for overfitting.
""")

    overall_base = calc_stats(all_trades)
    overall_combined = calc_stats(s9_filtered)
    delta = overall_combined["pnl"] - overall_base["pnl"]
    print(f"  PROJECTED IMPROVEMENT (Combined S9):")
    print(f"    Baseline total P&L:   {pnl(overall_base['pnl'])} ({overall_base['count']} trades)")
    print(f"    Filtered total P&L:   {pnl(overall_combined['pnl'])} ({overall_combined['count']} trades)")
    print(f"    Improvement:          {'+' if delta >= 0 else ''}{pnl(delta)}")
    print(f"    Trades removed:       {overall_base['count'] - overall_combined['count']}")

    fee_delta = overall_combined["net_pnl"] - overall_base["net_pnl"]
    print(f"\n  FEE-ADJUSTED PROJECTION:")
    print(f"    Baseline net P&L:     {pnl(overall_base['net_pnl'])}")
    print(f"    Filtered net P&L:     {pnl(overall_combined['net_pnl'])}")
    print(f"    Net improvement:      {'+' if fee_delta >= 0 else ''}{pnl(fee_delta)}")

    print("\n" + "=" * 90)
    print("  PHASE 3 COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
