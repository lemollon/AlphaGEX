#!/usr/bin/env python3
"""
AGAPE Render Shell Bootstrap & Diagnostic Script

Paste this entire script into your Render shell (or run: python scripts/agape_render_bootstrap.py)
It will:
  1. Check if DATABASE_URL is set
  2. Check if COINGLASS_API_KEY is set
  3. Create all 4 AGAPE tables if they don't exist
  4. Seed AGAPE config into autonomous_config
  5. Seed initial equity snapshot so the chart renders
  6. Test API endpoints (if server is running)
  7. Print a full diagnostic report

No commits needed - run directly in Render shell.
"""

import os
import sys
import json
from datetime import datetime, timedelta

# ============================================================
# STEP 0: Check environment
# ============================================================

print("=" * 70)
print("  AGAPE RENDER BOOTSTRAP & DIAGNOSTIC")
print("=" * 70)

# Check DATABASE_URL
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("\n[FAIL] DATABASE_URL not set!")
    print("  Set it in Render Environment Variables tab.")
    sys.exit(1)
else:
    # Mask the password for display
    parts = DATABASE_URL.split("@")
    if len(parts) > 1:
        safe = f"***@{parts[-1]}"
    else:
        safe = "***"
    print(f"\n[OK] DATABASE_URL: {safe}")

# Check COINGLASS_API_KEY
COINGLASS_KEY = os.environ.get("COINGLASS_API_KEY")
if COINGLASS_KEY:
    print(f"[OK] COINGLASS_API_KEY: {COINGLASS_KEY[:8]}...")
else:
    print("[WARN] COINGLASS_API_KEY not set!")
    print("  CoinGlass funding rate/liquidation data will show '---'")
    print("  Get key at: https://www.coinglass.com/pricing")

# Check tastytrade keys
for key in ["TASTYTRADE_USERNAME", "TASTYTRADE_PASSWORD", "TASTYTRADE_ACCOUNT_ID"]:
    val = os.environ.get(key)
    if val:
        print(f"[OK] {key}: set")
    else:
        print(f"[INFO] {key}: not set (paper mode only)")

# ============================================================
# STEP 1: Connect to database
# ============================================================

print("\n" + "-" * 70)
print("STEP 1: Database Connection")
print("-" * 70)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[FAIL] psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cursor = conn.cursor()
    cursor.execute("SELECT version()")
    ver = cursor.fetchone()[0]
    print(f"[OK] Connected: {ver[:60]}...")
except Exception as e:
    print(f"[FAIL] Cannot connect: {e}")
    sys.exit(1)

# ============================================================
# STEP 2: Check if AGAPE tables exist
# ============================================================

print("\n" + "-" * 70)
print("STEP 2: Check/Create AGAPE Tables")
print("-" * 70)

REQUIRED_TABLES = [
    "agape_positions",
    "agape_equity_snapshots",
    "agape_scan_activity",
    "agape_activity_log",
]

for table in REQUIRED_TABLES:
    cursor.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
        (table,)
    )
    exists = cursor.fetchone()[0]
    if exists:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] {table}: exists ({count} rows)")
    else:
        print(f"[MISSING] {table}: does NOT exist - will create")

# ============================================================
# STEP 3: Create tables
# ============================================================

print("\n" + "-" * 70)
print("STEP 3: Creating Tables (IF NOT EXISTS)")
print("-" * 70)

try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agape_positions (
            id SERIAL PRIMARY KEY,
            position_id VARCHAR(100) UNIQUE NOT NULL,
            side VARCHAR(10) NOT NULL,
            contracts INTEGER NOT NULL,
            entry_price FLOAT NOT NULL,
            stop_loss FLOAT,
            take_profit FLOAT,
            max_risk_usd FLOAT,

            underlying_at_entry FLOAT,
            funding_rate_at_entry FLOAT,
            funding_regime_at_entry VARCHAR(50),
            ls_ratio_at_entry FLOAT,
            squeeze_risk_at_entry VARCHAR(20),
            max_pain_at_entry FLOAT,
            crypto_gex_at_entry FLOAT,
            crypto_gex_regime_at_entry VARCHAR(20),

            oracle_advice VARCHAR(50),
            oracle_win_probability FLOAT,
            oracle_confidence FLOAT,
            oracle_top_factors TEXT,

            signal_action VARCHAR(20),
            signal_confidence VARCHAR(20),
            signal_reasoning TEXT,

            status VARCHAR(20) DEFAULT 'open',
            open_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            close_time TIMESTAMP WITH TIME ZONE,
            close_price FLOAT,
            close_reason VARCHAR(100),
            realized_pnl FLOAT,

            high_water_mark FLOAT DEFAULT 0,
            oracle_prediction_id INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    print("[OK] agape_positions: ensured")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agape_equity_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            equity FLOAT NOT NULL,
            unrealized_pnl FLOAT DEFAULT 0,
            realized_pnl_cumulative FLOAT DEFAULT 0,
            open_positions INTEGER DEFAULT 0,
            eth_price FLOAT,
            funding_rate FLOAT,
            note VARCHAR(200)
        )
    """)
    print("[OK] agape_equity_snapshots: ensured")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agape_scan_activity (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            outcome VARCHAR(50) NOT NULL,
            eth_price FLOAT,
            funding_rate FLOAT,
            funding_regime VARCHAR(50),
            ls_ratio FLOAT,
            ls_bias VARCHAR(30),
            squeeze_risk VARCHAR(20),
            leverage_regime VARCHAR(30),
            max_pain FLOAT,
            crypto_gex FLOAT,
            crypto_gex_regime VARCHAR(20),
            combined_signal VARCHAR(30),
            combined_confidence VARCHAR(20),
            oracle_advice VARCHAR(50),
            oracle_win_prob FLOAT,
            signal_action VARCHAR(20),
            signal_reasoning TEXT,
            position_id VARCHAR(100),
            error_message TEXT
        )
    """)
    print("[OK] agape_scan_activity: ensured")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agape_activity_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            level VARCHAR(20) DEFAULT 'INFO',
            action VARCHAR(100),
            message TEXT,
            details JSONB
        )
    """)
    print("[OK] agape_activity_log: ensured")

    # Indexes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_agape_positions_status ON agape_positions(status)",
        "CREATE INDEX IF NOT EXISTS idx_agape_positions_open_time ON agape_positions(open_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agape_equity_snapshots_ts ON agape_equity_snapshots(timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_agape_scan_activity_ts ON agape_scan_activity(timestamp DESC)",
    ]:
        cursor.execute(idx_sql)
    print("[OK] Indexes created")

    conn.commit()
    print("[OK] All tables committed")

except Exception as e:
    print(f"[FAIL] Table creation error: {e}")
    conn.rollback()
    sys.exit(1)

# ============================================================
# STEP 4: Seed AGAPE config in autonomous_config
# ============================================================

print("\n" + "-" * 70)
print("STEP 4: Seed AGAPE Config")
print("-" * 70)

# Check if autonomous_config table exists
cursor.execute(
    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'autonomous_config')"
)
config_table_exists = cursor.fetchone()[0]

if not config_table_exists:
    print("[WARN] autonomous_config table doesn't exist - creating it")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_config (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    print("[OK] autonomous_config table created")

# Check if AGAPE config exists (key/value schema with agape_ prefix)
cursor.execute("SELECT COUNT(*) FROM autonomous_config WHERE key LIKE 'agape_%'")
agape_config_count = cursor.fetchone()[0]

if agape_config_count > 0:
    print(f"[OK] AGAPE config already exists ({agape_config_count} keys)")
    cursor.execute("SELECT key, value FROM autonomous_config WHERE key LIKE 'agape_%' ORDER BY key")
    for row in cursor.fetchall():
        print(f"      {row[0]} = {row[1]}")
else:
    print("[MISSING] No AGAPE config found - seeding defaults")
    config_defaults = {
        "agape_starting_capital": "5000.0",
        "agape_risk_per_trade_pct": "5.0",
        "agape_max_contracts": "10",
        "agape_max_open_positions": "2",
        "agape_cooldown_minutes": "30",
        "agape_instrument": "/MET",
        "agape_ticker": "ETH",
        "agape_mode": "paper",
        "agape_min_oracle_win_probability": "0.45",
        "agape_require_oracle_approval": "true",
        "agape_max_hold_hours": "24",
        "agape_profit_target_pct": "50.0",
        "agape_stop_loss_pct": "100.0",
    }

    for key, value in config_defaults.items():
        cursor.execute(
            """INSERT INTO autonomous_config (key, value)
               VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (key, value),
        )
    conn.commit()
    print(f"[OK] Seeded {len(config_defaults)} AGAPE config keys")

# ============================================================
# STEP 5: Seed initial equity snapshots
# ============================================================

print("\n" + "-" * 70)
print("STEP 5: Seed Equity Snapshots (for chart display)")
print("-" * 70)

cursor.execute("SELECT COUNT(*) FROM agape_equity_snapshots")
snap_count = cursor.fetchone()[0]

if snap_count > 0:
    print(f"[OK] {snap_count} equity snapshots already exist")
    cursor.execute("SELECT timestamp, equity, eth_price FROM agape_equity_snapshots ORDER BY timestamp DESC LIMIT 3")
    for row in cursor.fetchall():
        print(f"      {row[0]} | equity=${row[1]} | ETH=${row[2]}")
else:
    print("[MISSING] No equity snapshots - seeding initial data")

    # Get current ETH price from Deribit (free, no API key needed)
    eth_price = None
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            "https://www.deribit.com/api/v2/public/get_index_price?index_name=eth_usd",
            headers={"User-Agent": "AlphaGEX-Bootstrap/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read())
            eth_price = data.get("result", {}).get("index_price")
            if eth_price:
                print(f"[OK] Current ETH price from Deribit: ${eth_price:.2f}")
    except Exception as e:
        print(f"[WARN] Could not fetch ETH price: {e}")
        eth_price = 1900.0  # fallback
        print(f"[INFO] Using fallback ETH price: ${eth_price}")

    # Seed snapshots for the last 7 days (one per day) so the chart has history
    starting_capital = 5000.0
    now = datetime.utcnow()

    for days_ago in range(7, -1, -1):
        ts = now - timedelta(days=days_ago)
        cursor.execute(
            """INSERT INTO agape_equity_snapshots
               (timestamp, equity, unrealized_pnl, realized_pnl_cumulative, open_positions, eth_price, note)
               VALUES (%s, %s, 0, 0, 0, %s, 'bootstrap_seed')""",
            (ts, starting_capital, eth_price),
        )

    conn.commit()
    print(f"[OK] Seeded 8 equity snapshots (7 days + today) at $5,000 starting capital")

# ============================================================
# STEP 6: Seed a bootstrap log entry
# ============================================================

print("\n" + "-" * 70)
print("STEP 6: Log Bootstrap Event")
print("-" * 70)

cursor.execute(
    """INSERT INTO agape_activity_log (level, action, message, details)
       VALUES ('INFO', 'BOOTSTRAP', 'AGAPE bootstrap script executed on Render',
               %s)""",
    (json.dumps({"coinglass_key_set": bool(COINGLASS_KEY), "timestamp": datetime.utcnow().isoformat()}),)
)
conn.commit()
print("[OK] Bootstrap event logged")

# ============================================================
# STEP 7: Verify data
# ============================================================

print("\n" + "-" * 70)
print("STEP 7: Verification")
print("-" * 70)

for table in REQUIRED_TABLES:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

cursor.execute("SELECT COUNT(*) FROM autonomous_config WHERE key LIKE 'agape_%'")
config_count = cursor.fetchone()[0]
print(f"  autonomous_config (agape_*): {config_count} keys")

# Check the equity curve would return data
cursor.execute("""
    SELECT COUNT(*) FROM agape_positions
    WHERE status IN ('closed', 'expired', 'stopped')
""")
closed_count = cursor.fetchone()[0]
print(f"\n  Closed trades (for equity curve): {closed_count}")

cursor.execute("SELECT COUNT(*) FROM agape_equity_snapshots")
snap_count = cursor.fetchone()[0]
print(f"  Equity snapshots (for intraday): {snap_count}")

if closed_count == 0:
    print("\n  NOTE: The historical equity curve will show a flat line at $5,000")
    print("        because there are 0 closed trades. This is EXPECTED for a new bot.")
    print("        The chart WILL render now (it needs at least 1 data point).")
    print("        Once AGAPE makes its first trade, the curve will populate.")

# ============================================================
# STEP 8: Test API (if server is running)
# ============================================================

print("\n" + "-" * 70)
print("STEP 8: Test API Endpoints (local)")
print("-" * 70)

try:
    import urllib.request
    import urllib.error

    API_BASE = "http://localhost:8000"

    endpoints = [
        "/api/agape/status",
        "/api/agape/equity-curve",
        "/api/agape/equity-curve/intraday",
        "/api/agape/performance",
        "/api/agape/positions",
        "/api/agape/logs?limit=5",
        "/api/agape/scan-activity?limit=5",
        "/api/agape/gex-mapping",
        "/api/agape/snapshot",
        "/api/agape/signal",
    ]

    for ep in endpoints:
        try:
            req = urllib.request.Request(f"{API_BASE}{ep}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                success = data.get("success", False)
                status_icon = "[OK]" if success else "[WARN]"

                # Extra info for equity curve
                if "equity-curve" in ep and "intraday" not in ep:
                    points = data.get("points", 0)
                    eq = data.get("data", {}).get("equity_curve", [])
                    status_icon = "[OK]" if eq else "[EMPTY]"
                    print(f"  {status_icon} {ep} → {len(eq)} points, success={success}")
                else:
                    print(f"  {status_icon} {ep} → success={success}")
        except urllib.error.URLError:
            print(f"  [SKIP] {ep} → server not reachable")
            break
        except Exception as e:
            print(f"  [FAIL] {ep} → {e}")

except Exception as e:
    print(f"  [SKIP] API testing skipped: {e}")

# ============================================================
# CLEANUP
# ============================================================

cursor.close()
conn.close()

# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("  AGAPE BOOTSTRAP COMPLETE")
print("=" * 70)
print("""
WHAT WAS DONE:
  ✓ Created 4 AGAPE database tables (if missing)
  ✓ Seeded AGAPE config in autonomous_config
  ✓ Seeded equity snapshots (chart will now render)
  ✓ Logged bootstrap event

NEXT STEPS:
  1. If CoinGlass shows '---': Add COINGLASS_API_KEY to Render env vars
  2. Restart the web service to pick up changes
  3. The equity curve will show a flat $5,000 line until real trades occur
  4. AGAPE needs to be scheduled (add to trader_scheduler.py) to auto-trade

TO ADD COINGLASS_API_KEY:
  Render Dashboard → Environment → Add:
    COINGLASS_API_KEY = <your key from coinglass.com/pricing>

TO TEST MANUALLY (run a single trade cycle):
  python -c "
from trading.agape.trader import create_agape_trader
t = create_agape_trader()
result = t.run_cycle()
print(result)
"
""")
print("=" * 70)
