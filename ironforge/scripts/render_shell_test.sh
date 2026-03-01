#!/bin/bash
# =============================================================
#  IronForge Render Shell Diagnostic
#  Run from ANY Render service shell (web or worker)
#
#  Usage:  bash /opt/render/project/src/ironforge/scripts/render_shell_test.sh
#  Or:     curl ... | bash   (if you host it somewhere)
# =============================================================

set -e

IRONFORGE_DIR="/opt/render/project/src/ironforge"
VENV_DIR="/tmp/ironforge_venv"

echo "============================================================"
echo "  IRONFORGE RENDER SHELL DIAGNOSTIC"
echo "============================================================"

# Step 1: Create venv + install deps
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[1/6] Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet psycopg2-binary requests
    echo "  -> psycopg2-binary + requests installed"
else
    echo "[1/6] Virtual environment already exists at $VENV_DIR"
fi

PY="$VENV_DIR/bin/python"

# Step 2-6: Run inline Python diagnostic
"$PY" - "$IRONFORGE_DIR" <<'PYEOF'
import sys, os

ironforge_dir = sys.argv[1]
sys.path.insert(0, ironforge_dir)
os.chdir(ironforge_dir)

passed = 0
failed = 0

def check(label, fn):
    global passed, failed
    try:
        ok, detail = fn()
        tag = "[+] PASS" if ok else "[X] FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  {tag} {label}: {detail}")
    except Exception as e:
        failed += 1
        print(f"  [X] FAIL {label}: {e}")

# ---- 2. CONFIG ----
print("=" * 60)
print("  2. CONFIGURATION")
print("=" * 60)

from config import Config

check("Config.validate()", lambda: Config.validate())
check("DATABASE_URL set", lambda: (
    bool(Config.DATABASE_URL and "postgresql" in Config.DATABASE_URL),
    Config.DATABASE_URL[:50] + "..." if Config.DATABASE_URL else "NOT SET"
))
check("TRADIER_API_KEY set", lambda: (
    bool(Config.TRADIER_API_KEY),
    Config.TRADIER_API_KEY[:10] + "..." if Config.TRADIER_API_KEY else "NOT SET"
))
check("TRADIER_BASE_URL (sandbox)", lambda: (
    "sandbox.tradier.com" in Config.TRADIER_BASE_URL,
    Config.TRADIER_BASE_URL
))

# ---- 3. DATABASE ----
print("=" * 60)
print("  3. DATABASE CONNECTION")
print("=" * 60)

from trading.db_adapter import db_connection

def test_db():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1")
        return True, "Connected OK"

check("PostgreSQL connection", test_db)

# ---- 4. TABLES ----
print("=" * 60)
print("  4. TABLE VERIFICATION")
print("=" * 60)

def test_tables():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT tablename FROM pg_tables
            WHERE tablename LIKE 'flame_%'
               OR tablename LIKE 'spark_%'
               OR tablename = 'bot_heartbeats'
            ORDER BY tablename
        """)
        rows = [r[0] for r in c.fetchall()]
        if not rows:
            return False, "No IronForge tables found"
        return True, f"{len(rows)} tables: {', '.join(rows)}"

check("IronForge tables exist", test_tables)

def test_table_setup():
    from setup_tables import setup_all_tables
    setup_all_tables()
    return True, "setup_all_tables() completed"

check("setup_all_tables()", test_table_setup)

# ---- 5. PAPER ACCOUNTS ----
print("=" * 60)
print("  5. PAPER ACCOUNTS")
print("=" * 60)

from trading.db import TradingDatabase

for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    def test_account(b=bot, m=mode):
        db = TradingDatabase(bot_name=b, dte_mode=m)
        acct = db.get_paper_account()
        return True, (
            f"balance=${acct.balance:.2f}, "
            f"cumP&L=${acct.cumulative_pnl:.2f}, "
            f"BP=${acct.buying_power:.2f}, "
            f"trades={acct.total_trades}"
        )
    check(f"{bot} paper account", test_account)

# ---- 6. OPEN POSITIONS ----
print("=" * 60)
print("  6. OPEN POSITIONS")
print("=" * 60)

for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    def test_positions(b=bot, m=mode):
        db = TradingDatabase(bot_name=b, dte_mode=m)
        positions = db.get_open_positions()
        if not positions:
            return True, "0 open positions"
        lines = []
        for p in positions:
            lines.append(
                f"{p.position_id}: "
                f"{p.put_long}/{p.put_short_strike}P-"
                f"{p.call_short_strike}/{p.call_long}C "
                f"x{p.contracts} @ ${p.total_credit:.2f} "
                f"exp={p.expiration}"
            )
        return True, f"{len(positions)} open: " + "; ".join(lines)
    check(f"{bot} positions", test_positions)

# ---- 7. TRADIER API ----
print("=" * 60)
print("  7. TRADIER API (live quotes)")
print("=" * 60)

def test_tradier():
    import requests
    resp = requests.get(
        f"{Config.TRADIER_BASE_URL}/markets/quotes",
        params={"symbols": "SPY", "greeks": "false"},
        headers={
            "Authorization": f"Bearer {Config.TRADIER_API_KEY}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    data = resp.json()
    quote = data.get("quotes", {}).get("quote", {})
    last = quote.get("last")
    if last is None:
        return False, f"No last price in response: {data}"
    return True, f"SPY last=${last}"

check("Tradier SPY quote", test_tradier)

# ---- 8. TRADING WINDOW ----
print("=" * 60)
print("  8. TRADING WINDOW")
print("=" * 60)

from datetime import datetime
from trading.models import CENTRAL_TZ

now = datetime.now(CENTRAL_TZ)
print(f"  Current time (CT): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  Day of week: {now.strftime('%A')}")

for bot, mode in [("FLAME", "2DTE"), ("SPARK", "1DTE")]:
    def test_window(b=bot, m=mode):
        from trading.trader import Trader
        from trading.models import flame_config, spark_config
        cfg = flame_config() if m == "2DTE" else spark_config()
        t = Trader.__new__(Trader)
        t.config = cfg
        in_window, msg = t._is_in_trading_window(now)
        return in_window, msg
    check(f"{bot} trading window", test_window)

# ---- 9. SIGNAL GENERATION ----
print("=" * 60)
print("  9. SIGNAL GENERATION (dry run)")
print("=" * 60)

def test_signal():
    from trading.models import flame_config
    from trading.signals import SignalGenerator
    sg = SignalGenerator(flame_config())
    signal = sg.generate_signal()
    if signal is None:
        return False, "generate_signal() returned None"
    if not signal.is_valid:
        return False, f"Invalid signal: {signal.reasoning}"
    return True, (
        f"SPY {signal.put_long}/{signal.put_short}P-"
        f"{signal.call_short}/{signal.call_long}C "
        f"credit=${signal.total_credit:.2f} "
        f"conf={signal.confidence:.2f} "
        f"exp={signal.expiration}"
    )

check("FLAME signal generation", test_signal)

# ---- 10. HEARTBEATS ----
print("=" * 60)
print("  10. BOT HEARTBEATS")
print("=" * 60)

def test_heartbeats():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT bot_name, last_heartbeat, status, scan_count
            FROM bot_heartbeats ORDER BY bot_name
        """)
        rows = c.fetchall()
        if not rows:
            return False, "No heartbeats recorded yet"
        lines = []
        for r in rows:
            lines.append(f"{r[0]}: {r[2]} (scans={r[3]}, last={r[1]})")
        return True, "; ".join(lines)

check("Bot heartbeats", test_heartbeats)

# ---- SUMMARY ----
print("=" * 60)
print(f"  SUMMARY: {passed} passed, {failed} failed")
print("=" * 60)
if failed == 0:
    print("  ALL CHECKS PASSED — IronForge is operational")
else:
    print("  Some checks FAILED — review output above")

PYEOF
