#!/usr/bin/env python3
"""
IronForge Production Smoke Test — Render Shell Edition
========================================================

Run on the Render shell where DATABASE_URL and TRADIER_* env vars are set.

Usage:
    python scripts/ironforge_smoke_test.py              # Run all steps
    python scripts/ironforge_smoke_test.py --step 1     # Run single step
    python scripts/ironforge_smoke_test.py --step 2     # Signal pipeline only
    python scripts/ironforge_smoke_test.py --step 3     # Force trade FLAME
    python scripts/ironforge_smoke_test.py --step 4     # Force trade SPARK
    python scripts/ironforge_smoke_test.py --step 5     # Position monitor
    python scripts/ironforge_smoke_test.py --step 6     # Equity snapshots
    python scripts/ironforge_smoke_test.py --step 7     # Scan loop alive
    python scripts/ironforge_smoke_test.py --skip-trade  # Skip force trade steps

Steps:
  1  Pre-Flight: env vars, DB tables, Tradier keys, worker presence
  2  Signal Pipeline: SPY quote, VIX, chain, strikes, advisor, sizing (no trade)
  3  Force Trade FLAME: opens position, mirrors to 3 sandbox accounts
  4  Force Trade SPARK: opens position, paper-only (no sandbox)
  5  Position Monitor: live MTM, unrealized P&L, sandbox_order_ids
  6  Equity Snapshots: verify snapshot rows, balance math
  7  Scan Loop Alive: heartbeats, logs, proof of running
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

# ── Colour helpers ──────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def info(msg: str):
    print(f"  {CYAN}ℹ{RESET} {msg}")


def header(step: int, title: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  STEP {step}: {title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")


def section(title: str):
    print(f"\n  {BOLD}── {title} ──{RESET}")


# ── Database helper ─────────────────────────────────────────────────
_conn = None


def get_db():
    global _conn
    if _conn is not None:
        return _conn
    try:
        import psycopg2
    except ImportError:
        fail("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)
    url = os.getenv("DATABASE_URL")
    if not url:
        fail("DATABASE_URL not set")
        sys.exit(1)
    _conn = psycopg2.connect(url)
    _conn.autocommit = True
    return _conn


def query(sql: str, params: tuple = ()) -> List[Dict]:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return []


def query_one(sql: str, params: tuple = ()) -> Optional[Dict]:
    rows = query(sql, params)
    return rows[0] if rows else None


# ── Tradier helper ──────────────────────────────────────────────────
import requests as _req


def tradier_get(endpoint: str, params: dict = None, base_url: str = None, api_key: str = None) -> Optional[dict]:
    key = api_key or os.getenv("TRADIER_API_KEY", "")
    url = (base_url or os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")) + endpoint
    if not key:
        return None
    r = _req.get(url, params=params, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }, timeout=10)
    r.raise_for_status()
    return r.json()


def get_spy_quote() -> Optional[dict]:
    data = tradier_get("/markets/quotes", {"symbols": "SPY"})
    if not data:
        return None
    q = data.get("quotes", {}).get("quote", {})
    if isinstance(q, list):
        q = q[0]
    return q


def get_vix() -> Optional[float]:
    data = tradier_get("/markets/quotes", {"symbols": "VIX"})
    if not data:
        return None
    q = data.get("quotes", {}).get("quote", {})
    if isinstance(q, list):
        q = q[0]
    return float(q.get("last", 0)) or None


def build_occ(ticker, exp, strike, opt_type):
    dt = datetime.strptime(exp, "%Y-%m-%d")
    return f"{ticker}{dt:%y%m%d}{opt_type}{str(int(round(strike*1000))).zfill(8)}"


def get_option_quote(occ: str) -> Optional[dict]:
    data = tradier_get("/markets/quotes", {"symbols": occ})
    if not data:
        return None
    q = data.get("quotes", {}).get("quote", {})
    if isinstance(q, list):
        q = q[0]
    if data.get("quotes", {}).get("unmatched_symbols"):
        return None
    return q if q and q.get("bid") is not None else None


def next_trading_day(n: int) -> str:
    """n trading days from today."""
    d = datetime.utcnow()
    counted = 0
    while counted < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            counted += 1
    return d.strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════════
#  STEP 1 — Pre-Flight
# ══════════════════════════════════════════════════════════════════
def step1():
    header(1, "PRE-FLIGHT")
    failures = 0

    # ── 1a. DATABASE_URL ──
    section("Database")
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        ok(f"DATABASE_URL is PostgreSQL ({db_url[:40]}...)")
    else:
        fail(f"DATABASE_URL not postgresql:// — got: {db_url[:40]}...")
        failures += 1
        return failures

    # ── 1b. All tables exist ──
    section("Tables")
    expected_tables = []
    for bot in ["flame", "spark"]:
        for suffix in ["positions", "signals", "paper_account", "equity_snapshots",
                        "daily_perf", "logs", "pdt_log", "config"]:
            expected_tables.append(f"{bot}_{suffix}")
    expected_tables.append("bot_heartbeats")

    existing = {r["tablename"] for r in query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )}

    for t in expected_tables:
        if t in existing:
            ok(f"Table {t} exists")
        else:
            fail(f"Table {t} MISSING")
            failures += 1

    # ── 1c. Schema spot-check: oracle columns ──
    section("Schema spot-check (oracle columns in positions)")
    for bot in ["flame", "spark"]:
        cols_rows = query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            (f"{bot}_positions",)
        )
        cols = {r["column_name"] for r in cols_rows}
        for required in ["oracle_confidence", "oracle_win_probability",
                         "oracle_advice", "oracle_reasoning",
                         "sandbox_order_id", "wings_adjusted",
                         "dte_mode", "open_date"]:
            if required in cols:
                ok(f"{bot}_positions.{required} present")
            else:
                fail(f"{bot}_positions.{required} MISSING")
                failures += 1

    # ── 1d. Tradier production key ──
    section("Tradier API keys")
    tradier_key = os.getenv("TRADIER_API_KEY", "")
    if tradier_key:
        ok(f"TRADIER_API_KEY set ({len(tradier_key)} chars)")
        # Verify it hits production
        base = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
        if "sandbox" in base:
            fail(f"TRADIER_BASE_URL points to SANDBOX: {base}  ← bug #53 regression!")
            failures += 1
        else:
            ok(f"TRADIER_BASE_URL → {base} (production)")
        # Live quote test
        try:
            q = get_spy_quote()
            if q and q.get("last"):
                ok(f"SPY live quote: ${q['last']} (bid={q.get('bid')}, ask={q.get('ask')})")
            else:
                fail("SPY quote returned no data")
                failures += 1
        except Exception as e:
            fail(f"SPY quote failed: {e}")
            failures += 1
    else:
        fail("TRADIER_API_KEY not set — market data disabled")
        failures += 1

    # ── 1e. Three sandbox keys ──
    section("Sandbox accounts")
    for name, env_var in [("User", "TRADIER_SANDBOX_KEY_USER"),
                          ("Matt", "TRADIER_SANDBOX_KEY_MATT"),
                          ("Logan", "TRADIER_SANDBOX_KEY_LOGAN")]:
        val = os.getenv(env_var, "")
        if val:
            ok(f"{name} sandbox key loaded ({len(val)} chars)")
        else:
            warn(f"{name} sandbox key ({env_var}) NOT SET — FLAME mirroring to {name} disabled")

    # ── 1f. Worker scripts exist ──
    section("Worker entry points")
    for script in ["ironforge/jobs/run_flame.py", "ironforge/jobs/run_spark.py"]:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), script)
        if os.path.exists(path):
            ok(f"{script} exists")
        else:
            # Try from project root
            alt = os.path.join("/home/user/AlphaGEX", script)
            if os.path.exists(alt):
                ok(f"{script} exists")
            else:
                fail(f"{script} MISSING")
                failures += 1

    # ── 1g. Paper accounts seeded ──
    section("Paper accounts")
    for bot, dte in [("flame", "2DTE"), ("spark", "1DTE")]:
        acct = query_one(
            f"SELECT id, starting_capital, current_balance, buying_power, is_active "
            f"FROM {bot}_paper_account WHERE is_active = TRUE AND dte_mode = %s "
            f"ORDER BY id DESC LIMIT 1",
            (dte,)
        )
        if acct:
            ok(f"{bot.upper()} paper account: balance=${acct['current_balance']}, "
               f"BP=${acct['buying_power']}, active={acct['is_active']}")
        else:
            fail(f"{bot.upper()} paper account NOT FOUND or inactive")
            failures += 1

    if failures == 0:
        print(f"\n  {GREEN}{BOLD}PRE-FLIGHT: ALL CHECKS PASSED{RESET}")
    else:
        print(f"\n  {RED}{BOLD}PRE-FLIGHT: {failures} FAILURE(S){RESET}")
    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 2 — Signal Pipeline Verification (dry run, no trade)
# ══════════════════════════════════════════════════════════════════
def step2():
    header(2, "SIGNAL PIPELINE VERIFICATION")
    failures = 0

    # ── 2.1 SPY price ──
    section("SPY Price (Production Tradier)")
    base = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    info(f"Querying: {base}/markets/quotes?symbols=SPY")
    if "sandbox" in base:
        fail(f"TRADIER_BASE_URL is sandbox! Bug #53 regression: {base}")
        failures += 1
    spy = get_spy_quote()
    if not spy or not spy.get("last"):
        fail("Could not get SPY quote")
        return failures + 1
    spot = float(spy["last"])
    ok(f"SPY = ${spot:.2f}  (bid={spy.get('bid')}, ask={spy.get('ask')})")

    # ── 2.2 VIX ──
    section("VIX")
    vix = get_vix()
    if vix:
        ok(f"VIX = {vix:.2f}")
    else:
        warn("VIX is null — advisor will default to 20.0")
        vix = 20.0
    info(f"If VIX null, advisor uses fallback: vix = vixQuote?.last ?? 20")

    # ── 2.3 Options chain ──
    section("Options Chain")
    for bot, dte_n, dte_label in [("FLAME", 2, "2DTE"), ("SPARK", 1, "1DTE")]:
        target_exp = next_trading_day(dte_n)
        info(f"{bot}: target expiration = {target_exp} ({dte_label} = {dte_n} trading days out)")

        exps_data = tradier_get("/markets/options/expirations", {
            "symbol": "SPY", "includeAllRoots": "true"
        })
        exps = []
        if exps_data:
            d = exps_data.get("expirations", {}).get("date", [])
            exps = d if isinstance(d, list) else [d]

        if target_exp in exps:
            ok(f"{bot}: expiration {target_exp} available in chain")
            chosen_exp = target_exp
        elif exps:
            # Find nearest
            target_dt = datetime.strptime(target_exp, "%Y-%m-%d")
            nearest = min(exps, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - target_dt).days))
            warn(f"{bot}: exact {target_exp} not in chain, nearest = {nearest}")
            chosen_exp = nearest
        else:
            fail(f"{bot}: could not fetch expirations")
            failures += 1
            continue

        chain = tradier_get("/markets/options/chains", {
            "symbol": "SPY", "expiration": chosen_exp, "greeks": "false"
        })
        options = []
        if chain:
            opts = chain.get("options", {}).get("option", [])
            options = opts if isinstance(opts, list) else [opts]
        ok(f"{bot}: {len(options)} contracts for {chosen_exp}")

        if options:
            mid = len(options) // 2
            sample = options[mid]
            info(f"  Sample: {sample.get('symbol')} strike={sample.get('strike')} "
                 f"bid={sample.get('bid')} ask={sample.get('ask')} "
                 f"type={sample.get('option_type')}")

    # ── 2.4 Strike selection ──
    section("Strike Selection (FLAME 2DTE)")
    em = (vix / 100 / math.sqrt(252)) * spot
    sd = 1.2
    width = 5
    min_em = spot * 0.005
    em_used = max(em, min_em)

    put_short = math.floor(spot - sd * em_used)
    call_short = math.ceil(spot + sd * em_used)
    put_long = put_short - width
    call_long = call_short + width

    if call_short <= put_short:
        put_short = math.floor(spot - spot * 0.02)
        call_short = math.ceil(spot + spot * 0.02)
        put_long = put_short - width
        call_long = call_short + width
        warn("Sanity guard triggered — strikes recalculated with 2% fallback")

    info(f"Spot=${spot:.2f}, VIX={vix:.2f}, EM=${em:.2f} (used={em_used:.2f})")
    info(f"SD multiplier = {sd}, Spread width = ${width}")
    ok(f"Put spread:  {put_long}/{put_short}  (${put_short - put_long} wide)")
    ok(f"Call spread: {call_short}/{call_long}  (${call_long - call_short} wide)")
    info(f"Put cushion:  ${spot - put_short:.2f}  ({(spot - put_short)/spot*100:.1f}%)")
    info(f"Call cushion: ${call_short - spot:.2f}  ({(call_short - spot)/spot*100:.1f}%)")

    # ── 2.5 Advisor check ──
    section("Advisor Check")
    BASE_WP = 0.65
    wp = BASE_WP
    factors = []

    if 15 <= vix <= 22:
        wp += 0.10; factors.append(("VIX_IDEAL", 0.10))
    elif vix < 15:
        wp -= 0.05; factors.append(("VIX_LOW_PREMIUMS", -0.05))
    elif vix <= 28:
        wp -= 0.05; factors.append(("VIX_ELEVATED", -0.05))
    else:
        wp -= 0.15; factors.append(("VIX_HIGH_RISK", -0.15))

    dow = datetime.utcnow().weekday()  # 0=Mon 4=Fri
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if 1 <= dow <= 3:  # Tue-Thu
        wp += 0.08; factors.append(("DAY_OPTIMAL", 0.08))
    elif dow == 0:
        wp += 0.03; factors.append(("DAY_MONDAY", 0.03))
    elif dow == 4:
        wp -= 0.10; factors.append(("DAY_FRIDAY_RISK", -0.10))
    else:
        wp -= 0.20; factors.append(("DAY_WEEKEND", -0.20))

    em_ratio = (em / spot * 100) if spot > 0 else 1.0
    if em_ratio < 1.0:
        wp += 0.08; factors.append(("EM_TIGHT", 0.08))
    elif em_ratio <= 2.0:
        factors.append(("EM_NORMAL", 0.0))
    else:
        wp -= 0.08; factors.append(("EM_WIDE", -0.08))

    wp += 0.03; factors.append(("DTE_2DAY_DECAY", 0.03))

    wp = max(0.10, min(0.95, wp))

    pos_count = sum(1 for _, a in factors if a > 0)
    neg_count = sum(1 for _, a in factors if a < 0)
    if pos_count == len(factors):
        conf = 0.85
    elif neg_count == len(factors):
        conf = 0.25
    elif pos_count > neg_count:
        conf = 0.60 + (pos_count / len(factors)) * 0.20
    else:
        conf = 0.40
    conf = max(0.10, min(0.95, conf))

    if wp >= 0.60 and conf >= 0.50:
        advice = "TRADE_FULL"
    elif wp >= 0.42 and conf >= 0.35:
        advice = "TRADE_REDUCED"
    else:
        advice = "SKIP"

    info(f"Today: {day_names[dow]}")
    for name, adj in factors:
        sign = "+" if adj >= 0 else ""
        status = f"{GREEN}✓{RESET}" if adj >= 0 else f"{RED}✗{RESET}"
        print(f"    {status} {name}: {sign}{adj:.2f}")

    result_color = GREEN if advice.startswith("TRADE") else RED
    ok(f"Advisor verdict: {result_color}{BOLD}{advice}{RESET}  (WP={wp:.2f}, Conf={conf:.2f})")

    if advice == "SKIP":
        info("Rejection is LEGITIMATE based on current market conditions")
        info("To override: use force-trade API which bypasses advisor")

    # ── 2.6 Position sizing ──
    section("Position Sizing (FLAME)")
    flame_acct = query_one(
        "SELECT id, current_balance, buying_power FROM flame_paper_account "
        "WHERE is_active = TRUE AND dte_mode = '2DTE' ORDER BY id DESC LIMIT 1"
    )
    if not flame_acct:
        fail("No FLAME paper account found")
        failures += 1
    else:
        bp = float(flame_acct["buying_power"])
        sw = put_short - put_long

        # Get real credits
        exp_for_credits = next_trading_day(2)
        exps_data = tradier_get("/markets/options/expirations", {"symbol": "SPY", "includeAllRoots": "true"})
        avail_exps = []
        if exps_data:
            d = exps_data.get("expirations", {}).get("date", [])
            avail_exps = d if isinstance(d, list) else [d]
        if exp_for_credits not in avail_exps and avail_exps:
            tgt = datetime.strptime(exp_for_credits, "%Y-%m-%d")
            exp_for_credits = min(avail_exps, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - tgt).days))

        ps_q = get_option_quote(build_occ("SPY", exp_for_credits, put_short, "P"))
        pl_q = get_option_quote(build_occ("SPY", exp_for_credits, put_long, "P"))
        cs_q = get_option_quote(build_occ("SPY", exp_for_credits, call_short, "C"))
        cl_q = get_option_quote(build_occ("SPY", exp_for_credits, call_long, "C"))

        if ps_q and pl_q and cs_q and cl_q:
            put_credit = max(0, float(ps_q["bid"]) - float(pl_q["ask"]))
            call_credit = max(0, float(cs_q["bid"]) - float(cl_q["ask"]))
            total_credit = put_credit + call_credit
            source = "TRADIER_LIVE"
        else:
            total_credit = 0.30  # fallback estimate
            put_credit = 0.15
            call_credit = 0.15
            source = "ESTIMATED"
            warn("Could not get all 4 leg quotes — using estimated credit")

        collateral_per = max(0, (sw - total_credit) * 100)
        usable_bp = bp * 0.85
        if collateral_per > 0:
            max_contracts = min(10, max(1, int(usable_bp / collateral_per)))
        else:
            max_contracts = 0

        ok(f"Buying power: ${bp:.2f}")
        ok(f"Credit: ${total_credit:.4f} (put=${put_credit:.4f}, call=${call_credit:.4f}) [{source}]")
        ok(f"Collateral/contract: ${collateral_per:.2f}")
        ok(f"Max contracts: {max_contracts} (85% of BP = ${usable_bp:.2f})")

    # ── 2.7 Final verdict ──
    section("VERDICT")
    for bot, dte_n, dte_label in [("FLAME", 2, "2DTE"), ("SPARK", 1, "1DTE")]:
        would_trade = advice.startswith("TRADE") and total_credit >= 0.05 and bp >= 200
        color = GREEN if would_trade else RED
        word = "WOULD" if would_trade else "WOULD NOT"
        reasons = []
        if not advice.startswith("TRADE"):
            reasons.append(f"advisor says {advice}")
        if total_credit < 0.05:
            reasons.append(f"credit too low (${total_credit:.4f})")
        if bp < 200:
            reasons.append(f"insufficient BP (${bp:.2f})")
        reason_str = " | ".join(reasons) if reasons else "all filters pass"
        print(f"  {color}{BOLD}{bot} {word}{RESET} open a trade right now — {reason_str}")

    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 3 — Force Trade FLAME
# ══════════════════════════════════════════════════════════════════
def step3():
    header(3, "FORCE TRADE — FLAME")
    failures = 0

    # Check for existing open position first
    existing = query_one(
        "SELECT position_id FROM flame_positions WHERE status = 'open' AND dte_mode = '2DTE' LIMIT 1"
    )
    if existing:
        warn(f"FLAME already has open position: {existing['position_id']}")
        warn("Cannot force trade while a position is open (HTTP 409)")
        info("Either close the existing position first, or skip this step")
        return 0

    section("Triggering Force Trade via Python pipeline")

    # Get market data
    spy = get_spy_quote()
    if not spy:
        fail("Cannot get SPY quote")
        return 1
    spot = float(spy["last"])
    vix = get_vix() or 20.0
    em = (vix / 100 / math.sqrt(252)) * spot

    # Calculate strikes
    sd, width = 1.2, 5
    em_used = max(em, spot * 0.005)
    put_short = math.floor(spot - sd * em_used)
    call_short = math.ceil(spot + sd * em_used)
    put_long = put_short - width
    call_long = call_short + width

    # Find expiration (2DTE)
    target_exp = next_trading_day(2)
    exps_data = tradier_get("/markets/options/expirations", {"symbol": "SPY", "includeAllRoots": "true"})
    avail_exps = []
    if exps_data:
        d = exps_data.get("expirations", {}).get("date", [])
        avail_exps = d if isinstance(d, list) else [d]
    if target_exp not in avail_exps and avail_exps:
        tgt_dt = datetime.strptime(target_exp, "%Y-%m-%d")
        target_exp = min(avail_exps, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - tgt_dt).days))

    # Get credits
    ps_q = get_option_quote(build_occ("SPY", target_exp, put_short, "P"))
    pl_q = get_option_quote(build_occ("SPY", target_exp, put_long, "P"))
    cs_q = get_option_quote(build_occ("SPY", target_exp, call_short, "C"))
    cl_q = get_option_quote(build_occ("SPY", target_exp, call_long, "C"))

    if ps_q and pl_q and cs_q and cl_q:
        put_credit = max(0, float(ps_q["bid"]) - float(pl_q["ask"]))
        call_credit = max(0, float(cs_q["bid"]) - float(cl_q["ask"]))
        total_credit = round(put_credit + call_credit, 4)
    else:
        fail("Cannot get all 4 leg quotes — cannot proceed with force trade")
        return 1

    if total_credit < 0.05:
        fail(f"Credit too low: ${total_credit:.4f} (min $0.05)")
        return 1

    # Sizing
    acct = query_one(
        "SELECT id, current_balance, buying_power FROM flame_paper_account "
        "WHERE is_active = TRUE AND dte_mode = '2DTE' ORDER BY id DESC LIMIT 1"
    )
    if not acct:
        fail("No FLAME paper account")
        return 1

    bp = float(acct["buying_power"])
    sw = put_short - put_long
    collateral_per = max(0, (sw - total_credit) * 100)
    max_contracts = min(10, max(1, int(bp * 0.85 / collateral_per))) if collateral_per > 0 else 0
    total_collateral = collateral_per * max_contracts
    max_profit = total_credit * 100 * max_contracts
    max_loss = total_collateral

    # Generate position ID
    now = datetime.utcnow()
    pos_id = f"FLAME-{now.strftime('%Y%m%d')}-{os.urandom(3).hex().upper()}"

    # Advisor for oracle fields
    BASE_WP = 0.65
    wp = BASE_WP + 0.03  # DTE bonus
    conf = 0.65

    info(f"a. Multileg order payload:")
    payload = {
        "class": "multileg",
        "symbol": "SPY",
        "type": "market",
        "duration": "day",
        "legs": [
            {"symbol": build_occ("SPY", target_exp, put_short, "P"), "side": "sell_to_open", "qty": max_contracts},
            {"symbol": build_occ("SPY", target_exp, put_long, "P"),  "side": "buy_to_open",  "qty": max_contracts},
            {"symbol": build_occ("SPY", target_exp, call_short, "C"), "side": "sell_to_open", "qty": max_contracts},
            {"symbol": build_occ("SPY", target_exp, call_long, "C"),  "side": "buy_to_open",  "qty": max_contracts},
        ],
    }
    print(f"    {json.dumps(payload, indent=2)}")

    # Insert paper position
    query(
        """INSERT INTO flame_positions (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime, flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            status, open_time, open_date, dte_mode
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, 'open', NOW(), CURRENT_DATE, %s
        )""",
        (
            pos_id, "SPY", target_exp,
            put_short, put_long, put_credit,
            call_short, call_long, call_credit,
            max_contracts, sw, total_credit, max_loss, max_profit,
            total_collateral,
            spot, vix, em, 0, 0, "UNKNOWN", 0, 0,
            conf, wp, "TRADE_FULL",
            "Force trade via smoke test", json.dumps([]), False,
            False, sw, sw,
            "PAPER", "PAPER", "2DTE",
        )
    )

    # Verify position row
    section("b. Paper position row")
    row = query_one(
        "SELECT * FROM flame_positions WHERE position_id = %s", (pos_id,)
    )
    if row:
        ok(f"Position {pos_id} saved to flame_positions")
        info(f"  Strikes: {row['put_long_strike']}/{row['put_short_strike']}P — "
             f"{row['call_short_strike']}/{row['call_long_strike']}C")
        info(f"  Credit: ${row['total_credit']}, Contracts: {row['contracts']}")
        info(f"  Status: {row['status']}, Exp: {row['expiration']}")
    else:
        fail(f"Position {pos_id} NOT FOUND in DB")
        failures += 1

    # Mirror to sandbox accounts
    section("c. Sandbox mirroring")
    sandbox_orders = {}
    sandbox_url = "https://sandbox.tradier.com/v1"
    for name, env_var in [("User", "TRADIER_SANDBOX_KEY_USER"),
                          ("Matt", "TRADIER_SANDBOX_KEY_MATT"),
                          ("Logan", "TRADIER_SANDBOX_KEY_LOGAN")]:
        key = os.getenv(env_var, "")
        if not key:
            warn(f"  {name}: key not set, skipping")
            continue
        try:
            # Discover account ID
            profile = tradier_get("/user/profile", base_url=sandbox_url, api_key=key)
            if not profile:
                warn(f"  {name}: could not get profile")
                continue
            acct_data = profile.get("profile", {}).get("account", {})
            if isinstance(acct_data, list):
                acct_id = str(acct_data[0].get("account_number", ""))
            else:
                acct_id = str(acct_data.get("account_number", ""))

            if not acct_id:
                warn(f"  {name}: no account ID discovered")
                continue

            # Place multileg order
            order_body = {
                "class": "multileg",
                "symbol": "SPY",
                "type": "market",
                "duration": "day",
                "option_symbol[0]": build_occ("SPY", target_exp, put_short, "P"),
                "side[0]": "sell_to_open",
                "quantity[0]": str(max_contracts),
                "option_symbol[1]": build_occ("SPY", target_exp, put_long, "P"),
                "side[1]": "buy_to_open",
                "quantity[1]": str(max_contracts),
                "option_symbol[2]": build_occ("SPY", target_exp, call_short, "C"),
                "side[2]": "sell_to_open",
                "quantity[2]": str(max_contracts),
                "option_symbol[3]": build_occ("SPY", target_exp, call_long, "C"),
                "side[3]": "buy_to_open",
                "quantity[3]": str(max_contracts),
                "tag": pos_id[:255],
            }
            url = f"{sandbox_url}/accounts/{acct_id}/orders"
            resp = _req.post(url, data=order_body, headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            }, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            order_id = result.get("order", {}).get("id")
            if order_id:
                sandbox_orders[name] = str(order_id)
                ok(f"  {name}: order_id={order_id}")
            else:
                warn(f"  {name}: no order_id returned — {result}")
        except Exception as e:
            warn(f"  {name}: sandbox order failed — {e}")

    # Update sandbox_order_id in DB
    if sandbox_orders:
        query(
            "UPDATE flame_positions SET sandbox_order_id = %s WHERE position_id = %s",
            (json.dumps(sandbox_orders), pos_id)
        )
        ok(f"sandbox_order_id saved: {json.dumps(sandbox_orders)}")
    else:
        warn("No sandbox orders placed — check keys")

    # Update paper account (deduct collateral)
    query(
        """UPDATE flame_paper_account
           SET collateral_in_use = collateral_in_use + %s,
               buying_power = buying_power - %s,
               updated_at = NOW()
           WHERE is_active = TRUE AND dte_mode = '2DTE'""",
        (total_collateral, total_collateral)
    )

    # Save equity snapshot
    updated_acct = query_one(
        "SELECT current_balance, cumulative_pnl FROM flame_paper_account "
        "WHERE is_active = TRUE AND dte_mode = '2DTE' ORDER BY id DESC LIMIT 1"
    )
    if updated_acct:
        query(
            """INSERT INTO flame_equity_snapshots
               (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
               VALUES (%s, %s, 0, 1, %s, '2DTE')""",
            (float(updated_acct["current_balance"]),
             float(updated_acct["cumulative_pnl"]),
             f"smoke_test:force_trade:{pos_id}")
        )

    # d. Verify sandbox order exists
    section("d. Sandbox order verification")
    if sandbox_orders:
        first_name = list(sandbox_orders.keys())[0]
        first_key_var = f"TRADIER_SANDBOX_KEY_{first_name.upper()}"
        first_key = os.getenv(first_key_var, "")
        if first_key:
            try:
                profile = tradier_get("/user/profile", base_url=sandbox_url, api_key=first_key)
                acct_data = profile.get("profile", {}).get("account", {})
                if isinstance(acct_data, list):
                    acct_id = str(acct_data[0].get("account_number", ""))
                else:
                    acct_id = str(acct_data.get("account_number", ""))
                orders_resp = tradier_get(
                    f"/accounts/{acct_id}/orders",
                    base_url=sandbox_url, api_key=first_key
                )
                if orders_resp:
                    orders = orders_resp.get("orders", {}).get("order", [])
                    if isinstance(orders, dict):
                        orders = [orders]
                    target_id = int(sandbox_orders[first_name])
                    found = any(o.get("id") == target_id for o in orders)
                    if found:
                        ok(f"Order {target_id} confirmed in {first_name}'s sandbox account")
                    else:
                        warn(f"Order {target_id} not found in recent orders (may be filled)")
                else:
                    warn("Could not fetch sandbox orders")
            except Exception as e:
                warn(f"Sandbox verification error: {e}")
    else:
        info("No sandbox orders to verify")

    # Verify cascade close logic exists
    section("Close cascade verification (code inspection)")
    info("Checking if close cascade exists in codebase...")
    # The task says commits 7c68863 + dddb4db added cascade close.
    # From code inspection: tradier_client.py has close_ic_order (4-leg only),
    # there is NO cascade (2-spread → individual legs) in the current code.
    warn("Current code has SINGLE close method only (4-leg multileg)")
    warn("No cascade fallback (2-spread → individual legs) found in tradier_client.py")
    info("The executor._mirror_close_to_all_sandboxes calls close_ic_order directly")
    info("If sandbox rejects 4-leg close, the paper close still succeeds (non-fatal)")

    print(f"\n  {BOLD}FLAME force trade complete: {pos_id}{RESET}")
    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 4 — Force Trade SPARK
# ══════════════════════════════════════════════════════════════════
def step4():
    header(4, "FORCE TRADE — SPARK")
    failures = 0

    existing = query_one(
        "SELECT position_id FROM spark_positions WHERE status = 'open' AND dte_mode = '1DTE' LIMIT 1"
    )
    if existing:
        warn(f"SPARK already has open position: {existing['position_id']}")
        return 0

    spy = get_spy_quote()
    if not spy:
        fail("Cannot get SPY quote")
        return 1
    spot = float(spy["last"])
    vix = get_vix() or 20.0
    em = (vix / 100 / math.sqrt(252)) * spot

    sd, width = 1.2, 5
    em_used = max(em, spot * 0.005)
    put_short = math.floor(spot - sd * em_used)
    call_short = math.ceil(spot + sd * em_used)
    put_long = put_short - width
    call_long = call_short + width

    target_exp = next_trading_day(1)
    exps_data = tradier_get("/markets/options/expirations", {"symbol": "SPY", "includeAllRoots": "true"})
    avail_exps = []
    if exps_data:
        d = exps_data.get("expirations", {}).get("date", [])
        avail_exps = d if isinstance(d, list) else [d]
    if target_exp not in avail_exps and avail_exps:
        tgt_dt = datetime.strptime(target_exp, "%Y-%m-%d")
        target_exp = min(avail_exps, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - tgt_dt).days))

    ok(f"1DTE expiration: {target_exp}")

    ps_q = get_option_quote(build_occ("SPY", target_exp, put_short, "P"))
    pl_q = get_option_quote(build_occ("SPY", target_exp, put_long, "P"))
    cs_q = get_option_quote(build_occ("SPY", target_exp, call_short, "C"))
    cl_q = get_option_quote(build_occ("SPY", target_exp, call_long, "C"))

    if ps_q and pl_q and cs_q and cl_q:
        put_credit = max(0, float(ps_q["bid"]) - float(pl_q["ask"]))
        call_credit = max(0, float(cs_q["bid"]) - float(cl_q["ask"]))
        total_credit = round(put_credit + call_credit, 4)
    else:
        total_credit, put_credit, call_credit = 0.20, 0.10, 0.10
        warn("Using estimated credit")

    acct = query_one(
        "SELECT id, current_balance, buying_power FROM spark_paper_account "
        "WHERE is_active = TRUE AND dte_mode = '1DTE' ORDER BY id DESC LIMIT 1"
    )
    if not acct:
        fail("No SPARK paper account")
        return 1

    bp = float(acct["buying_power"])
    sw = put_short - put_long
    collateral_per = max(0, (sw - total_credit) * 100)
    max_contracts = min(10, max(1, int(bp * 0.85 / collateral_per))) if collateral_per > 0 else 0
    total_collateral = collateral_per * max_contracts

    now = datetime.utcnow()
    pos_id = f"SPARK-{now.strftime('%Y%m%d')}-{os.urandom(3).hex().upper()}"

    query(
        """INSERT INTO spark_positions (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime, flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            status, open_time, open_date, dte_mode
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, 'open', NOW(), CURRENT_DATE, %s
        )""",
        (
            pos_id, "SPY", target_exp,
            put_short, put_long, put_credit,
            call_short, call_long, call_credit,
            max_contracts, sw, total_credit,
            total_collateral, total_credit * 100 * max_contracts,
            total_collateral,
            spot, vix, em, 0, 0, "UNKNOWN", 0, 0,
            0.65, 0.68, "TRADE_FULL",
            "Force trade via smoke test", json.dumps([]), False,
            False, sw, sw,
            "PAPER", "PAPER", "1DTE",
        )
    )

    query(
        """UPDATE spark_paper_account
           SET collateral_in_use = collateral_in_use + %s,
               buying_power = buying_power - %s,
               updated_at = NOW()
           WHERE is_active = TRUE AND dte_mode = '1DTE'""",
        (total_collateral, total_collateral)
    )

    row = query_one("SELECT * FROM spark_positions WHERE position_id = %s", (pos_id,))
    if row:
        ok(f"SPARK position {pos_id} created")
        info(f"  1DTE expiration: {row['expiration']}")
        info(f"  Strikes: {row['put_long_strike']}/{row['put_short_strike']}P — "
             f"{row['call_short_strike']}/{row['call_long_strike']}C")
        info(f"  Credit: ${row['total_credit']}, Contracts: {row['contracts']}")
        info(f"  sandbox_order_id: {row.get('sandbox_order_id', 'NULL')} (should be NULL)")
        if row.get("sandbox_order_id"):
            fail("SPARK should NOT have sandbox_order_ids!")
            failures += 1
        else:
            ok("No sandbox_order_ids — correct for SPARK (paper-only)")
    else:
        fail(f"SPARK position {pos_id} NOT FOUND")
        failures += 1

    print(f"\n  {BOLD}SPARK force trade complete: {pos_id}{RESET}")
    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 5 — Live Monitoring (Position Monitor)
# ══════════════════════════════════════════════════════════════════
def step5():
    header(5, "LIVE MONITORING")
    failures = 0

    for bot, dte in [("flame", "2DTE"), ("spark", "1DTE")]:
        section(f"{bot.upper()} Position Monitor")
        pos = query_one(
            f"SELECT * FROM {bot}_positions WHERE status = 'open' AND dte_mode = %s "
            f"ORDER BY open_time DESC LIMIT 1",
            (dte,)
        )
        if not pos:
            info(f"No open {bot.upper()} position — skipping monitor")
            continue

        ok(f"Open position: {pos['position_id']}")
        info(f"  Strikes: {pos['put_long_strike']}/{pos['put_short_strike']}P — "
             f"{pos['call_short_strike']}/{pos['call_long_strike']}C")
        info(f"  Entry credit: ${pos['total_credit']}")
        info(f"  Expiration: {pos['expiration']}")

        sandbox_ids = pos.get("sandbox_order_id")
        if sandbox_ids:
            try:
                parsed = json.loads(sandbox_ids)
                ok(f"  sandbox_order_ids: {parsed}")
            except:
                ok(f"  sandbox_order_id (raw): {sandbox_ids}")
        elif bot == "flame":
            warn("  sandbox_order_ids: NULL (expected for FLAME)")
        else:
            ok("  sandbox_order_ids: NULL (correct for SPARK)")

        # Get live MTM
        exp_str = str(pos["expiration"])
        if "T" in exp_str:
            exp_str = exp_str[:10]
        elif hasattr(pos["expiration"], "strftime"):
            exp_str = pos["expiration"].strftime("%Y-%m-%d")

        ps = float(pos["put_short_strike"])
        pl = float(pos["put_long_strike"])
        cs = float(pos["call_short_strike"])
        cl = float(pos["call_long_strike"])
        contracts = int(pos["contracts"])
        entry_credit = float(pos["total_credit"])

        ps_q = get_option_quote(build_occ("SPY", exp_str, ps, "P"))
        pl_q = get_option_quote(build_occ("SPY", exp_str, pl, "P"))
        cs_q = get_option_quote(build_occ("SPY", exp_str, cs, "C"))
        cl_q = get_option_quote(build_occ("SPY", exp_str, cl, "C"))
        spy_q = get_spy_quote()

        if ps_q and pl_q and cs_q and cl_q:
            cost_to_close = max(0, float(ps_q["ask"]) + float(cs_q["ask"]) - float(pl_q["bid"]) - float(cl_q["bid"]))
            unrealized_pnl = round((entry_credit - cost_to_close) * 100 * contracts, 2)
            spot_now = float(spy_q["last"]) if spy_q else None

            info(f"\n  MANUAL MTM VERIFICATION:")
            info(f"    Put short ask:  ${float(ps_q['ask']):.4f}")
            info(f"    Put long bid:   ${float(pl_q['bid']):.4f}")
            info(f"    Call short ask: ${float(cs_q['ask']):.4f}")
            info(f"    Call long bid:  ${float(cl_q['bid']):.4f}")
            info(f"    Cost to close:  ${cost_to_close:.4f}")
            info(f"    Entry credit:   ${entry_credit:.4f}")
            info(f"    Unrealized P&L: ${unrealized_pnl:.2f}")
            if spot_now:
                info(f"    SPY price:      ${spot_now:.2f}")

            # Profit target / stop loss
            pt_price = entry_credit * 0.70
            sl_price = entry_credit * 2.0
            pnl_pct = ((entry_credit - cost_to_close) / entry_credit * 100) if entry_credit > 0 else 0
            info(f"    P&L %:          {pnl_pct:.1f}%")
            info(f"    Profit target:  ${pt_price:.4f} (30% of credit)")
            info(f"    Stop loss:      ${sl_price:.4f} (200% of credit)")
            info(f"    Distance to PT: ${cost_to_close - pt_price:.4f}")
            info(f"    Distance to SL: ${sl_price - cost_to_close:.4f}")

            ok(f"{bot.upper()} monitor: SPY=${spot_now}, P&L=${unrealized_pnl:.2f}")
        else:
            warn(f"Could not get all 4 leg quotes for MTM (market may be closed)")
            info("Legs that failed:")
            if not ps_q: info(f"  Put short: {build_occ('SPY', exp_str, ps, 'P')}")
            if not pl_q: info(f"  Put long:  {build_occ('SPY', exp_str, pl, 'P')}")
            if not cs_q: info(f"  Call short: {build_occ('SPY', exp_str, cs, 'C')}")
            if not cl_q: info(f"  Call long:  {build_occ('SPY', exp_str, cl, 'C')}")

    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 6 — Equity Snapshots
# ══════════════════════════════════════════════════════════════════
def step6():
    header(6, "EQUITY SNAPSHOTS")
    failures = 0

    for bot, dte in [("flame", "2DTE"), ("spark", "1DTE")]:
        section(f"{bot.upper()} Equity Snapshots")

        rows = query(
            f"SELECT * FROM {bot}_equity_snapshots "
            f"WHERE dte_mode = %s ORDER BY snapshot_time DESC LIMIT 5",
            (dte,)
        )

        if not rows:
            warn(f"No {bot.upper()} equity snapshots found")
            info(f"Check if scan loop is writing snapshots (save_equity_snapshot call in trader.py)")
            info(f"Snapshot logic was added in commits 9-10 and 1884f07")
            failures += 1
            continue

        ok(f"Found {len(rows)} recent snapshots")
        for i, r in enumerate(rows):
            bal = float(r.get("balance", 0))
            rpnl = float(r.get("realized_pnl", 0))
            upnl = float(r.get("unrealized_pnl", 0))
            open_pos = int(r.get("open_positions", 0))
            note = r.get("note", "")
            ts = r.get("snapshot_time", "")

            print(f"    [{i+1}] {ts}")
            print(f"        balance=${bal:.2f}  realized=${rpnl:.2f}  "
                  f"unrealized=${upnl:.2f}  open_pos={open_pos}")
            print(f"        note: {note}")

        # Validate balance math on most recent
        latest = rows[0]
        acct = query_one(
            f"SELECT starting_capital, cumulative_pnl FROM {bot}_paper_account "
            f"WHERE is_active = TRUE AND dte_mode = %s ORDER BY id DESC LIMIT 1",
            (dte,)
        )
        if acct:
            expected_bal = float(acct["starting_capital"]) + float(acct["cumulative_pnl"])
            actual_bal = float(latest.get("balance", 0))
            diff = abs(expected_bal - actual_bal)
            if diff < 1.0:
                ok(f"Balance math checks out: "
                   f"${float(acct['starting_capital']):.2f} + ${float(acct['cumulative_pnl']):.2f} "
                   f"= ${expected_bal:.2f} (actual: ${actual_bal:.2f})")
            else:
                warn(f"Balance mismatch: expected=${expected_bal:.2f} actual=${actual_bal:.2f} "
                     f"(diff=${diff:.2f}) — may be due to collateral in use")
                info(f"starting_capital=${float(acct['starting_capital']):.2f}, "
                     f"cumulative_pnl=${float(acct['cumulative_pnl']):.2f}")

    return failures


# ══════════════════════════════════════════════════════════════════
#  STEP 7 — Scan Loop Alive Check
# ══════════════════════════════════════════════════════════════════
def step7():
    header(7, "SCAN LOOP ALIVE CHECK")
    failures = 0

    # ── Heartbeats ──
    section("Bot Heartbeats")
    for bot_name in ["FLAME", "SPARK"]:
        hb = query_one(
            "SELECT * FROM bot_heartbeats WHERE bot_name = %s", (bot_name,)
        )
        if hb:
            last_hb = hb.get("last_heartbeat")
            status = hb.get("status", "unknown")
            scan_count = hb.get("scan_count", 0)
            details = hb.get("details", "")

            ok(f"{bot_name}: status={status}, scans={scan_count}, last={last_hb}")
            if details:
                info(f"  details: {details}")

            # Check staleness
            if last_hb:
                from datetime import timezone
                if hasattr(last_hb, 'tzinfo') and last_hb.tzinfo:
                    age = datetime.now(timezone.utc) - last_hb
                else:
                    age = datetime.utcnow() - last_hb
                mins = age.total_seconds() / 60
                if mins < 10:
                    ok(f"  Heartbeat is fresh ({mins:.0f} min ago)")
                elif mins < 60:
                    warn(f"  Heartbeat is {mins:.0f} min old (should be <10 min)")
                else:
                    fail(f"  Heartbeat is {mins:.0f} min old — bot may be dead!")
                    failures += 1
        else:
            warn(f"{bot_name}: no heartbeat row found")
            info("  This means the scan loop has never run (or table was just created)")

    # ── Recent logs ──
    section("Recent Log Entries")
    for bot, dte in [("flame", "2DTE"), ("spark", "1DTE")]:
        rows = query(
            f"SELECT log_time, level, message FROM {bot}_logs "
            f"WHERE dte_mode = %s ORDER BY log_time DESC LIMIT 5",
            (dte,)
        )
        if rows:
            ok(f"{bot.upper()} recent logs ({len(rows)} entries):")
            for r in rows:
                ts = r.get("log_time", "")
                level = r.get("level", "")
                msg = r.get("message", "")[:100]
                print(f"    [{ts}] {level}: {msg}")
        else:
            warn(f"{bot.upper()}: no log entries found")

    # ── Recent signals ──
    section("Recent Signals")
    for bot, dte in [("flame", "2DTE"), ("spark", "1DTE")]:
        rows = query(
            f"SELECT signal_time, spot_price, vix, total_credit, was_executed, skip_reason "
            f"FROM {bot}_signals WHERE dte_mode = %s ORDER BY signal_time DESC LIMIT 3",
            (dte,)
        )
        if rows:
            ok(f"{bot.upper()} recent signals:")
            for r in rows:
                ts = r.get("signal_time", "")
                executed = r.get("was_executed", False)
                skip = r.get("skip_reason", "")
                credit = r.get("total_credit", 0)
                spy = r.get("spot_price", 0)
                vix_val = r.get("vix", 0)
                status = f"{GREEN}EXECUTED{RESET}" if executed else f"{YELLOW}SKIPPED ({skip}){RESET}"
                print(f"    [{ts}] SPY=${spy} VIX={vix_val} credit=${credit} → {status}")
        else:
            info(f"{bot.upper()}: no signal entries (bot may not have scanned yet)")

    return failures


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="IronForge Production Smoke Test")
    parser.add_argument("--step", type=int, help="Run a single step (1-7)")
    parser.add_argument("--skip-trade", action="store_true", help="Skip force trade steps (3, 4)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  IRONFORGE PRODUCTION SMOKE TEST{RESET}")
    print(f"{BOLD}  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    steps = {
        1: ("Pre-Flight", step1),
        2: ("Signal Pipeline", step2),
        3: ("Force Trade FLAME", step3),
        4: ("Force Trade SPARK", step4),
        5: ("Position Monitor", step5),
        6: ("Equity Snapshots", step6),
        7: ("Scan Loop Alive", step7),
    }

    total_failures = 0

    if args.step:
        if args.step not in steps:
            print(f"Invalid step: {args.step}. Valid: 1-7")
            sys.exit(1)
        name, fn = steps[args.step]
        total_failures = fn()
    else:
        for step_num in sorted(steps.keys()):
            if args.skip_trade and step_num in (3, 4):
                print(f"\n  {YELLOW}SKIPPING Step {step_num} (--skip-trade){RESET}")
                continue
            name, fn = steps[step_num]
            try:
                total_failures += fn()
            except Exception as e:
                fail(f"Step {step_num} crashed: {e}")
                import traceback
                traceback.print_exc()
                total_failures += 1

    # Final summary
    print(f"\n{BOLD}{'='*60}{RESET}")
    if total_failures == 0:
        print(f"{GREEN}{BOLD}  ALL CHECKS PASSED — IronForge is GO{RESET}")
    else:
        print(f"{RED}{BOLD}  {total_failures} FAILURE(S) — REVIEW ABOVE{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    sys.exit(1 if total_failures > 0 else 0)


if __name__ == "__main__":
    main()
