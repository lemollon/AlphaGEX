#!/bin/bash
# =============================================================
#  IronForge Render Shell Diagnostic v2
#  Comprehensive pipeline check: Config -> DB -> Tradier -> Signal -> Trade readiness
#
#  Usage (paste into Render shell):
#    bash /opt/render/project/src/ironforge/scripts/render_diagnostic.sh
# =============================================================

IRONFORGE_DIR="/opt/render/project/src/ironforge"
VENV_DIR="/tmp/ironforge_venv"

echo "============================================================"
echo "  IRONFORGE RENDER DIAGNOSTIC v2"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

# Step 1: Ensure venv with deps
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[SETUP] Creating venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet psycopg2-binary requests 2>/dev/null
    echo "  -> deps installed"
else
    echo "[SETUP] Venv ready at $VENV_DIR"
fi

PY="$VENV_DIR/bin/python"

# Run the full diagnostic inline
"$PY" - "$IRONFORGE_DIR" <<'PYEOF'
import sys, os, json, traceback
from datetime import datetime, timedelta

ironforge_dir = sys.argv[1]
sys.path.insert(0, ironforge_dir)
os.chdir(ironforge_dir)

passed = 0
failed = 0
warnings = 0

def section(title, num):
    print(f"\n{'='*60}")
    print(f"  {num}. {title}")
    print(f"{'='*60}")

def check(label, ok, detail=""):
    global passed, failed
    tag = "  [+] PASS" if ok else "  [X] FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    msg = f"{tag} {label}"
    if detail:
        msg += f": {detail}"
    print(msg)
    return ok

def warn(label, detail=""):
    global warnings
    warnings += 1
    msg = f"  [!] WARN {label}"
    if detail:
        msg += f": {detail}"
    print(msg)

# ================================================================
# 1. ENVIRONMENT
# ================================================================
section("ENVIRONMENT", 1)
print(f"  Python: {sys.version.split()[0]}")
print(f"  Working dir: {os.getcwd()}")
print(f"  IronForge dir: {ironforge_dir}")
check("ironforge dir exists", os.path.isdir(ironforge_dir))
check("config.py exists", os.path.isfile(os.path.join(ironforge_dir, "config.py")))
check("trading/ exists", os.path.isdir(os.path.join(ironforge_dir, "trading")))

# ================================================================
# 2. CONFIGURATION
# ================================================================
section("CONFIGURATION", 2)
try:
    from config import Config
    valid, msg = Config.validate()
    check("Config.validate()", valid, msg)
except Exception as e:
    check("Config import", False, str(e))
    print("\n  FATAL: Cannot proceed without config. Exiting.")
    sys.exit(1)

check("DATABASE_URL set",
    bool(Config.DATABASE_URL and Config.DATABASE_URL != "postgresql://localhost:5432/ironforge"),
    Config.DATABASE_URL[:50] + "..." if len(Config.DATABASE_URL) > 50 else Config.DATABASE_URL
)
check("TRADIER_API_KEY set",
    bool(Config.TRADIER_API_KEY),
    f"{Config.TRADIER_API_KEY[:10]}..." if Config.TRADIER_API_KEY else "EMPTY"
)
check("TRADIER_ACCOUNT_ID set",
    bool(Config.TRADIER_ACCOUNT_ID),
    f"{Config.TRADIER_ACCOUNT_ID[:6]}..." if Config.TRADIER_ACCOUNT_ID else "EMPTY (sandbox orders will fail)"
)
check("TRADIER_BASE_URL",
    "api.tradier.com" in Config.TRADIER_BASE_URL,
    Config.TRADIER_BASE_URL
)

sandbox_accounts = Config.get_sandbox_accounts()
if sandbox_accounts:
    check("Sandbox accounts", True, f"{len(sandbox_accounts)} configured: {[a['name'] for a in sandbox_accounts]}")
else:
    warn("No sandbox accounts", "FLAME mirroring will be disabled")

# ================================================================
# 3. DATABASE CONNECTION
# ================================================================
section("DATABASE CONNECTION", 3)
try:
    from trading.db_adapter import db_connection
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT version()")
        pg_version = c.fetchone()[0].split(",")[0]
        check("PostgreSQL connection", True, pg_version)

        c.execute("SELECT NOW() AT TIME ZONE 'America/Chicago'")
        db_time = c.fetchone()[0]
        print(f"  DB time (CT): {db_time}")
except Exception as e:
    check("PostgreSQL connection", False, str(e))
    print("\n  FATAL: Cannot proceed without database. Exiting.")
    sys.exit(1)

# ================================================================
# 4. TABLE VERIFICATION
# ================================================================
section("TABLE VERIFICATION", 4)
try:
    from setup_tables import setup_all_tables
    setup_all_tables()
    check("setup_all_tables()", True, "all tables created/verified")
except Exception as e:
    check("setup_all_tables()", False, str(e))

expected_tables = [
    "flame_positions", "flame_paper_account", "flame_signals",
    "flame_logs", "flame_equity_snapshots", "flame_pdt_log",
    "flame_daily_perf", "flame_config",
    "spark_positions", "spark_paper_account", "spark_signals",
    "spark_logs", "spark_equity_snapshots", "spark_pdt_log",
    "spark_daily_perf", "spark_config",
    "bot_heartbeats",
]

try:
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND (tablename LIKE 'flame_%' OR tablename LIKE 'spark_%' OR tablename = 'bot_heartbeats')
            ORDER BY tablename
        """)
        actual_tables = [r[0] for r in c.fetchall()]
        missing = [t for t in expected_tables if t not in actual_tables]
        check("All expected tables exist",
            len(missing) == 0,
            f"{len(actual_tables)} found" + (f", missing: {missing}" if missing else "")
        )
except Exception as e:
    check("Table listing", False, str(e))

# ================================================================
# 5. PAPER ACCOUNTS
# ================================================================
section("PAPER ACCOUNTS", 5)
from trading.db import TradingDatabase

for bot, mode, capital in [("FLAME", "2DTE", 10000.0), ("SPARK", "1DTE", 10000.0)]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        db.initialize_paper_account(capital)
        acct = db.get_paper_account()
        check(f"{bot} paper account", True,
            f"balance=${acct.balance:.2f}, cum_pnl=${acct.cumulative_pnl:.2f}, "
            f"BP=${acct.buying_power:.2f}, trades={acct.total_trades}, "
            f"collateral=${acct.collateral_in_use:.2f}, active={acct.is_active}"
        )
        if acct.buying_power < 200:
            warn(f"{bot} low buying power", f"${acct.buying_power:.2f} < $200 minimum")
    except Exception as e:
        check(f"{bot} paper account", False, str(e))

# ================================================================
# 6. OPEN POSITIONS
# ================================================================
section("OPEN POSITIONS", 6)
for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        positions = db.get_open_positions()
        if not positions:
            check(f"{bot} positions", True, "0 open (ready to trade)")
        else:
            for p in positions:
                print(f"  [{bot}] {p.position_id}: "
                    f"{p.put_long_strike}/{p.put_short_strike}P-"
                    f"{p.call_short_strike}/{p.call_long_strike}C "
                    f"x{p.contracts} @ ${p.total_credit:.4f} "
                    f"exp={p.expiration} opened={p.open_time}")
            check(f"{bot} positions", True, f"{len(positions)} open (will monitor, not open new)")
    except Exception as e:
        check(f"{bot} positions", False, str(e))

# ================================================================
# 7. CLOSED TRADES (recent)
# ================================================================
section("RECENT CLOSED TRADES", 7)
for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        trades = db.get_closed_trades(limit=5)
        if not trades:
            print(f"  [{bot}] No closed trades yet")
        else:
            for t in trades:
                pnl_str = f"${t['realized_pnl']:+.2f}"
                print(f"  [{bot}] {t['close_time'][:16] if t.get('close_time') else '?'} "
                    f"{t['put_long_strike']}/{t['put_short_strike']}P-"
                    f"{t['call_short_strike']}/{t['call_long_strike']}C "
                    f"x{t['contracts']} {pnl_str} [{t['close_reason']}]")
        stats = db.get_performance_stats()
        check(f"{bot} performance", True,
            f"{stats['total_trades']} trades, WR={stats['win_rate']}%, "
            f"P&L=${stats['total_pnl']:.2f}, avg_win=${stats['avg_win']:.2f}, avg_loss=${stats['avg_loss']:.2f}"
        )
    except Exception as e:
        check(f"{bot} trades", False, str(e))

# ================================================================
# 8. TRADIER API (raw HTTP)
# ================================================================
section("TRADIER API", 8)
import requests

if Config.TRADIER_API_KEY:
    headers = {
        "Authorization": f"Bearer {Config.TRADIER_API_KEY}",
        "Accept": "application/json",
    }

    # SPY quote
    try:
        resp = requests.get(
            f"{Config.TRADIER_BASE_URL}/markets/quotes",
            params={"symbols": "SPY,VIX"},
            headers=headers, timeout=10,
        )
        check("Tradier HTTP status", resp.status_code == 200, f"HTTP {resp.status_code}")

        data = resp.json()
        quotes = data.get("quotes", {}).get("quote", [])
        if isinstance(quotes, dict):
            quotes = [quotes]

        for q in quotes:
            sym = q.get("symbol", "?")
            last = q.get("last")
            bid = q.get("bid")
            ask = q.get("ask")
            print(f"  {sym}: last=${last}, bid=${bid}, ask=${ask}")

        spy_quote = next((q for q in quotes if q.get("symbol") == "SPY"), None)
        check("SPY quote valid",
            spy_quote and float(spy_quote.get("last", 0)) > 0,
            f"SPY=${spy_quote.get('last')}" if spy_quote else "not found"
        )
    except Exception as e:
        check("Tradier API call", False, str(e))

    # Option chain test
    try:
        resp = requests.get(
            f"{Config.TRADIER_BASE_URL}/markets/options/expirations",
            params={"symbol": "SPY"},
            headers=headers, timeout=10,
        )
        exps = resp.json().get("expirations", {}).get("date", [])
        if isinstance(exps, str):
            exps = [exps]
        check("SPY option expirations", len(exps) > 0, f"{len(exps)} dates, nearest={exps[0] if exps else 'none'}")
    except Exception as e:
        check("Option expirations", False, str(e))

    # Account ID test (for sandbox orders)
    if Config.TRADIER_ACCOUNT_ID:
        check("TRADIER_ACCOUNT_ID", True, f"{Config.TRADIER_ACCOUNT_ID[:6]}...")
    else:
        try:
            resp = requests.get(
                f"{Config.TRADIER_BASE_URL}/user/profile",
                headers=headers, timeout=10,
            )
            profile = resp.json().get("profile", {})
            account = profile.get("account", {})
            if isinstance(account, list):
                acct_id = account[0].get("account_number") if account else None
            else:
                acct_id = account.get("account_number")
            check("Auto-discover account ID", bool(acct_id), f"found: {acct_id}" if acct_id else "not found")
        except Exception as e:
            check("Account ID discovery", False, str(e))
else:
    warn("TRADIER_API_KEY not set", "Skipping all Tradier checks")

# ================================================================
# 9. TRADING WINDOW & SCHEDULE
# ================================================================
section("TRADING WINDOW", 9)
from trading.models import CENTRAL_TZ, flame_config, spark_config

now = datetime.now(CENTRAL_TZ)
print(f"  Current time (CT): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  Day of week: {now.strftime('%A')} ({now.weekday()})")
is_weekday = now.weekday() < 5
check("Is weekday", is_weekday, now.strftime('%A'))

for cfg_fn, label in [(flame_config, "FLAME"), (spark_config, "SPARK")]:
    cfg = cfg_fn()
    current_min = now.hour * 60 + now.minute
    start_h, start_m = map(int, cfg.entry_start.split(":"))
    start_min = start_h * 60 + start_m
    eod_min = 14 * 60 + 45  # 2:45 PM CT = 3:45 PM ET

    in_window = is_weekday and start_min <= current_min <= eod_min
    check(f"{label} trading window", in_window,
        f"window={cfg.entry_start}-14:45 CT, now={now.strftime('%H:%M')} CT"
    )

# ================================================================
# 10. SIGNAL GENERATION (dry run)
# ================================================================
section("SIGNAL GENERATION (dry run)", 10)

for cfg_fn, label in [(flame_config, "FLAME"), (spark_config, "SPARK")]:
    try:
        from trading.signals import SignalGenerator
        cfg = cfg_fn()
        sg = SignalGenerator(cfg)

        # Market data check
        md = sg.get_market_data()
        if md:
            check(f"{label} market data", True,
                f"SPY=${md['spot_price']:.2f}, VIX={md['vix']:.1f}, EM=${md['expected_move']:.2f}"
            )
        else:
            check(f"{label} market data", False, "returned None (Tradier may be down)")
            continue

        # Full signal
        signal = sg.generate_signal()
        if signal and signal.is_valid:
            check(f"{label} signal", True,
                f"{signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C "
                f"exp={signal.expiration} credit=${signal.total_credit:.4f} "
                f"WP={signal.oracle_win_probability:.2f} conf={signal.confidence:.2f} "
                f"({signal.source})"
            )
        elif signal:
            check(f"{label} signal", False, f"INVALID: {signal.reasoning}")
        else:
            check(f"{label} signal", False, "returned None")
    except Exception as e:
        check(f"{label} signal generation", False, str(e))
        traceback.print_exc()

# ================================================================
# 11. TRADE SIZING (dry run)
# ================================================================
section("TRADE SIZING (dry run)", 11)
try:
    from trading.executor import PaperExecutor
    cfg = flame_config()
    db = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
    executor = PaperExecutor(cfg, db)
    acct = db.get_paper_account()

    # Use signal if available, else mock
    if signal and signal.is_valid:
        spread_width = signal.put_short - signal.put_long
        collateral_per = executor.calculate_collateral(spread_width, signal.total_credit)
        max_contracts = executor.calculate_max_contracts(acct.buying_power, collateral_per)

        print(f"  Spread width: ${spread_width:.0f}")
        print(f"  Collateral/contract: ${collateral_per:.2f}")
        print(f"  Buying power: ${acct.buying_power:.2f}")
        print(f"  Max contracts: {max_contracts}")
        print(f"  Total collateral: ${collateral_per * max_contracts:.2f}")
        check("Can afford trade", max_contracts >= 1,
            f"{max_contracts} contracts @ ${collateral_per:.2f} each"
        )
    else:
        warn("Sizing skipped", "No valid signal to size")
except Exception as e:
    check("Trade sizing", False, str(e))

# ================================================================
# 12. TRADE GATES
# ================================================================
section("TRADE GATES", 12)
for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        today_str = now.strftime("%Y-%m-%d")

        traded = db.has_traded_today(today_str)
        check(f"{bot} hasn't traded today", not traded,
            "already traded (will skip)" if traded else "no trades yet (eligible)"
        )

        pdt_count = db.get_day_trade_count_rolling_5_days()
        check(f"{bot} PDT room", pdt_count < 3,
            f"{pdt_count}/3 day trades in 5-day window"
        )

        is_active = db.get_bot_active()
        check(f"{bot} is active (enabled)", is_active,
            "ENABLED" if is_active else "DISABLED (toggle on to trade)"
        )
    except Exception as e:
        check(f"{bot} trade gates", False, str(e))

# ================================================================
# 13. BOT HEARTBEATS
# ================================================================
section("BOT HEARTBEATS", 13)
try:
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT bot_name, last_heartbeat, status, scan_count,
                   EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
            FROM bot_heartbeats ORDER BY bot_name
        """)
        rows = c.fetchall()
        if not rows:
            warn("No heartbeats", "Bots may not have run yet since deploy")
        else:
            for r in rows:
                name, hb, status, scans, ago = r
                ago_str = f"{int(ago)}s ago" if ago else "never"
                is_stale = ago and ago > 600  # >10 min stale
                tag = "[STALE]" if is_stale else "[OK]"
                print(f"  {tag} {name}: status={status}, scans={scans}, last={ago_str}")
                if is_stale:
                    warn(f"{name} heartbeat stale", f"last seen {int(ago)}s ago")
except Exception as e:
    check("Heartbeats", False, str(e))

# ================================================================
# 14. CONFIG OVERRIDES (DB)
# ================================================================
section("CONFIG OVERRIDES (from DB)", 14)
for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        overrides = db.load_config()
        if overrides:
            print(f"  [{bot}] DB overrides: {json.dumps(overrides, indent=4)}")
        else:
            print(f"  [{bot}] No DB config overrides (using code defaults)")
    except Exception as e:
        print(f"  [{bot}] Config load error: {e}")

# ================================================================
# 15. RECENT LOGS
# ================================================================
section("RECENT LOGS (last 10)", 15)
for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    try:
        db = TradingDatabase(bot_name=bot, dte_mode=mode)
        logs = db.get_logs(limit=10)
        if not logs:
            print(f"  [{bot}] No logs yet")
        else:
            for log in logs[:10]:
                ts = log['timestamp'][:19] if log.get('timestamp') else '?'
                print(f"  [{bot}] {ts} [{log['level']}] {log['message'][:80]}")
    except Exception as e:
        print(f"  [{bot}] Log error: {e}")

# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'='*60}")
print(f"  SUMMARY: {passed} passed, {failed} failed, {warnings} warnings")
print(f"{'='*60}")
if failed == 0:
    print("  ALL CHECKS PASSED")
    if warnings > 0:
        print(f"  {warnings} warning(s) — review above")
    print("  IronForge should be trading during market hours.")
else:
    print("  SOME CHECKS FAILED — fix the [X] items above")
    print("  Common fixes:")
    print("    - Set TRADIER_API_KEY in Render env vars")
    print("    - Set TRADIER_ACCOUNT_ID in Render env vars")
    print("    - Restart the worker service after env var changes")

PYEOF
