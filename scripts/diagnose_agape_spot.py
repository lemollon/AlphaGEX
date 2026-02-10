#!/usr/bin/env python3
"""
AGAPE-SPOT Diagnostic Script
Run in Render shell: python scripts/diagnose_agape_spot.py
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

G = "\033[92m"  # green
R = "\033[91m"  # red
Y = "\033[93m"  # yellow
B = "\033[94m"  # blue
W = "\033[0m"   # reset

TICKERS = ["ETH-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]
SYMBOLS = ["ETH", "XRP", "SHIB", "DOGE"]
fails = 0


def ok(msg):
    print(f"  {G}OK{W}  {msg}")


def fail(msg):
    global fails
    fails += 1
    print(f"  {R}FAIL{W} {msg}")


def note(msg):
    print(f"  {B}--{W}  {msg}")


def header(title):
    print(f"\n{Y}=== {title} ==={W}")


# ── 1. ENV VARS ──────────────────────────────────────────────────────────
header("1. Environment Variables")

for name in ["COINBASE_API_KEY", "COINBASE_API_SECRET", "COINGLASS_API_KEY"]:
    if os.getenv(name):
        ok(f"{name} is set")
    else:
        fail(f"{name} is NOT set")

for sym in SYMBOLS:
    k = os.getenv(f"COINBASE_{sym}_API_KEY")
    s = os.getenv(f"COINBASE_{sym}_API_SECRET")
    if k and s:
        ok(f"COINBASE_{sym}_API_KEY/SECRET  -> dedicated account")
    elif k or s:
        fail(f"COINBASE_{sym}_API_KEY/SECRET  -> only ONE of key/secret set (need both)")
    else:
        note(f"COINBASE_{sym}_API_KEY/SECRET  -> not set, will use default account")


# ── 2. SPOT PRICES (the main fix) ────────────────────────────────────────
header("2. Spot Prices (CryptoDataProvider)")

try:
    from data.crypto_data_provider import get_crypto_data_provider
    provider = get_crypto_data_provider()

    for sym in SYMBOLS:
        try:
            price = provider._get_spot_price(sym)
            if price and price > 0:
                ok(f"{sym:5s} = ${price:,.8f}")
            else:
                fail(f"{sym:5s} = no price returned")
        except Exception as e:
            fail(f"{sym:5s} error: {e}")
except Exception as e:
    fail(f"CryptoDataProvider init: {e}")


# ── 3. MARKET SNAPSHOTS ──────────────────────────────────────────────────
header("3. Market Data Snapshots")

try:
    from data.crypto_data_provider import get_crypto_data_provider
    provider = get_crypto_data_provider()

    for sym in SYMBOLS:
        try:
            snap = provider.get_snapshot(sym)
            if snap:
                funding = f"funding={snap.funding_rate.rate:.6f}" if snap.funding_rate else "funding=N/A"
                gex = f"gex={snap.crypto_gex.gamma_regime}" if snap.crypto_gex else "gex=N/A"
                ok(f"{sym:5s} signal={snap.combined_signal:12s} conf={snap.combined_confidence:6s} {funding}  {gex}")
            else:
                fail(f"{sym:5s} snapshot returned None")
        except Exception as e:
            fail(f"{sym:5s} error: {e}")
except Exception as e:
    fail(f"Snapshot fetch: {e}")


# ── 4. COINBASE CLIENTS ──────────────────────────────────────────────────
header("4. Coinbase Executor Clients")

try:
    from trading.agape_spot.models import AgapeSpotConfig
    from trading.agape_spot.executor import AgapeSpotExecutor, coinbase_available

    if not coinbase_available:
        fail("coinbase-advanced-py NOT installed")
    else:
        ok("coinbase-advanced-py installed")
        config = AgapeSpotConfig()
        executor = AgapeSpotExecutor(config)

        if executor._client:
            ok("Default client connected")
        else:
            fail("Default client NOT connected")

        for ticker in TICKERS:
            client = executor._get_client(ticker)
            dedicated = ticker in executor._ticker_clients
            label = "DEDICATED" if dedicated else ("default" if client else "NONE")
            if client:
                ok(f"{ticker:10s} client={label}")
            else:
                fail(f"{ticker:10s} NO CLIENT")

        # Price from executor
        print()
        note("Executor price check:")
        for ticker in TICKERS:
            try:
                price = executor.get_current_price(ticker)
                if price and price > 0:
                    ok(f"{ticker:10s} ${price:,.8f}")
                else:
                    fail(f"{ticker:10s} no price")
            except Exception as e:
                fail(f"{ticker:10s} error: {e}")

except Exception as e:
    fail(f"Executor init: {e}")
    traceback.print_exc()


# ── 5. SIGNAL GENERATION ─────────────────────────────────────────────────
header("5. Signal Generation")

try:
    from trading.agape_spot.models import AgapeSpotConfig
    from trading.agape_spot.signals import AgapeSpotSignalGenerator

    config = AgapeSpotConfig()
    gen = AgapeSpotSignalGenerator(config)

    for ticker in TICKERS:
        try:
            sig = gen.generate_signal(ticker=ticker)
            if sig:
                reason = sig.reasoning[:50]
                if sig.action.value == "LONG":
                    ok(f"{ticker:10s} {G}LONG{W}  qty={sig.quantity} entry=${sig.entry_price}  {reason}")
                elif "NO_MARKET_DATA" in sig.reasoning:
                    fail(f"{ticker:10s} {sig.action.value:5s} {reason}  <-- THIS IS THE BUG")
                else:
                    ok(f"{ticker:10s} {sig.action.value:5s} {reason}")
            else:
                fail(f"{ticker:10s} None returned")
        except Exception as e:
            fail(f"{ticker:10s} error: {e}")

except Exception as e:
    fail(f"Signal generator: {e}")
    traceback.print_exc()


# ── 6. DATABASE ───────────────────────────────────────────────────────────
header("6. Database")

try:
    from database_adapter import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()

    # Tables exist?
    for table in ["agape_spot_positions", "agape_spot_scan_activity",
                   "agape_spot_equity_snapshots", "agape_spot_activity_log"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cur.fetchone()[0]
            ok(f"{table:35s} {cnt:>6,} rows")
        except Exception:
            fail(f"{table:35s} MISSING")
            conn.rollback()

    # Last scan per ticker
    print()
    note("Most recent scan per ticker:")
    try:
        cur.execute("""
            SELECT DISTINCT ON (ticker) ticker, outcome, timestamp
            FROM agape_spot_scan_activity
            ORDER BY ticker, timestamp DESC
        """)
        rows = cur.fetchall()
        seen = set()
        for ticker, outcome, ts in rows:
            seen.add(ticker)
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/Chicago"))
            if ts.tzinfo:
                age = (now - ts.astimezone(ZoneInfo("America/Chicago"))).total_seconds() / 60
            else:
                age = 0
            marker = f"{R}(stale){W}" if age > 30 else ""
            if "NO_MARKET_DATA" in (outcome or ""):
                note(f"  {ticker:10s} {R}{outcome}{W}  {age:.0f}min ago  <-- BUG WAS HERE")
            else:
                note(f"  {ticker:10s} {outcome:30s} {age:.0f}min ago {marker}")
        for t in set(TICKERS) - seen:
            fail(f"  {t:10s} NO SCANS EVER")
    except Exception as e:
        note(f"  Query failed: {e}")
        conn.rollback()

    # Open positions
    print()
    note("Open positions:")
    try:
        cur.execute("""
            SELECT ticker, COUNT(*) FROM agape_spot_positions
            WHERE status = 'open' GROUP BY ticker ORDER BY ticker
        """)
        rows = cur.fetchall()
        if rows:
            for ticker, cnt in rows:
                note(f"  {ticker:10s} {cnt} open")
        else:
            note("  None across all tickers")
    except Exception as e:
        note(f"  Query failed: {e}")
        conn.rollback()

    # Recent trades
    print()
    note("Trades last 7 days:")
    try:
        cur.execute("""
            SELECT ticker, COUNT(*) as n,
                   COALESCE(SUM(realized_pnl), 0) as pnl,
                   SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM agape_spot_positions
            WHERE status IN ('closed','expired','stopped')
              AND close_time > NOW() - INTERVAL '7 days'
            GROUP BY ticker ORDER BY ticker
        """)
        rows = cur.fetchall()
        if rows:
            for ticker, n, pnl, wins in rows:
                wr = f"{wins/n*100:.0f}%" if n > 0 else "N/A"
                note(f"  {ticker:10s} {n} trades  P&L=${pnl:+.2f}  WR={wr}")
        else:
            note("  No closed trades in last 7 days")
        traded = {r[0] for r in rows} if rows else set()
        for t in set(TICKERS) - traded:
            note(f"  {Y}{t:10s} no trades last 7d{W}")
    except Exception as e:
        note(f"  Query failed: {e}")
        conn.rollback()

    cur.close()
    conn.close()

except ImportError:
    note("database_adapter not available - skipping DB checks")
except Exception as e:
    fail(f"Database: {e}")


# ── 7. LIVE TRADER (only if running in worker) ───────────────────────────
header("7. Live Trader Singleton")

try:
    from trading.agape_spot.trader import get_agape_spot_trader
    trader = get_agape_spot_trader()
    if trader:
        st = trader.get_status()
        ok(f"Trader running: cycles={st.get('cycle_count')} status={st.get('status')}")
        for t, ts in st.get("per_ticker", {}).items():
            acct = ts.get("coinbase_account", "?")
            mode = ts.get("mode", "?")
            ready = ts.get("live_ready", False)
            note(f"  {t:10s} mode={mode:5s} account={acct:10s} live_ready={ready}")
    else:
        note("Trader not initialized (normal in shell - it runs in the worker process)")
except Exception as e:
    note(f"Trader check: {e}")


# ── SUMMARY ───────────────────────────────────────────────────────────────
header("SUMMARY")

if fails == 0:
    print(f"\n  {G}ALL CHECKS PASSED{W}")
    print(f"\n  Wait 5-10 min after deploy, then re-run to confirm scans")
    print(f"  show real signals for all 4 coins (not NO_MARKET_DATA).\n")
else:
    print(f"\n  {R}{fails} FAILURE(S){W}")
    print(f"\n  Fix the issues above and re-run.\n")
