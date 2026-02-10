#!/usr/bin/env python3
"""
AGAPE-SPOT Diagnostic Script
Run in Render shell to verify all 4 coins are working after the fix.

Usage:
  python scripts/diagnose_agape_spot.py
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"
WARN = "\033[93m WARN \033[0m"
INFO = "\033[94m INFO \033[0m"

TICKERS = ["ETH-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]
SYMBOLS = ["ETH", "XRP", "SHIB", "DOGE"]

errors = []
warnings = []


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label, passed, detail=""):
    tag = PASS if passed else FAIL
    print(f"  {tag} {label}")
    if detail:
        print(f"         {detail}")
    if not passed:
        errors.append(label)
    return passed


def warn(label, detail=""):
    print(f"  {WARN} {label}")
    if detail:
        print(f"         {detail}")
    warnings.append(label)


def info(label, detail=""):
    print(f"  {INFO} {label}")
    if detail:
        print(f"         {detail}")


# =========================================================================
# 1. Environment Variables
# =========================================================================
section("1. ENVIRONMENT VARIABLES")

cb_key = os.getenv("COINBASE_API_KEY")
cb_secret = os.getenv("COINBASE_API_SECRET")
check("COINBASE_API_KEY (default)", bool(cb_key),
      f"{'Set' if cb_key else 'MISSING - no default Coinbase account'}")
check("COINBASE_API_SECRET (default)", bool(cb_secret),
      f"{'Set' if cb_secret else 'MISSING - no default Coinbase account'}")

coinglass_key = os.getenv("COINGLASS_API_KEY")
check("COINGLASS_API_KEY", bool(coinglass_key),
      f"{'Set' if coinglass_key else 'MISSING - funding rates/L/S ratio will be unavailable'}")

# Per-ticker overrides
for symbol in SYMBOLS:
    env_key = f"COINBASE_{symbol}_API_KEY"
    env_secret = f"COINBASE_{symbol}_API_SECRET"
    has_key = bool(os.getenv(env_key))
    has_secret = bool(os.getenv(env_secret))
    if has_key and has_secret:
        info(f"{env_key} / {env_secret}", "Dedicated account configured")
    elif has_key or has_secret:
        warn(f"{env_key} / {env_secret}", "Only one of key/secret set - need BOTH")
    else:
        info(f"{env_key}", f"Not set - {symbol} will use default account")


# =========================================================================
# 2. Spot Price Fetch (CryptoDataProvider - the main fix)
# =========================================================================
section("2. SPOT PRICE FETCH (CryptoDataProvider)")

try:
    from data.crypto_data_provider import get_crypto_data_provider
    provider = get_crypto_data_provider()
    info("CryptoDataProvider", "Loaded successfully")

    for symbol in SYMBOLS:
        try:
            price = provider._get_spot_price(symbol)
            check(f"{symbol} spot price", price is not None and price > 0,
                  f"${price:,.8f}" if price else "FAILED - no price returned")
        except Exception as e:
            check(f"{symbol} spot price", False, f"Exception: {e}")

except ImportError as e:
    check("CryptoDataProvider import", False, str(e))
except Exception as e:
    check("CryptoDataProvider init", False, str(e))


# =========================================================================
# 3. Market Data Snapshots
# =========================================================================
section("3. MARKET DATA SNAPSHOTS")

try:
    from data.crypto_data_provider import get_crypto_data_provider
    provider = get_crypto_data_provider()

    for symbol in SYMBOLS:
        try:
            snapshot = provider.get_snapshot(symbol)
            has_snapshot = snapshot is not None
            check(f"{symbol} snapshot", has_snapshot,
                  f"price=${snapshot.spot_price:,.4f} signal={snapshot.combined_signal} "
                  f"confidence={snapshot.combined_confidence}"
                  if has_snapshot else "FAILED - None returned")

            if has_snapshot:
                has_funding = snapshot.funding_rate is not None
                has_gex = snapshot.crypto_gex is not None
                details = []
                if has_funding:
                    details.append(f"funding={snapshot.funding_rate.rate:.6f}")
                else:
                    details.append("funding=N/A")
                if has_gex:
                    details.append(f"gex_regime={snapshot.crypto_gex.gamma_regime}")
                else:
                    details.append("gex=N/A (no Deribit for this coin)")
                if snapshot.ls_ratio:
                    details.append(f"ls_ratio={snapshot.ls_ratio.ratio:.2f}")
                else:
                    details.append("ls_ratio=N/A")
                info(f"  {symbol} details", " | ".join(details))

        except Exception as e:
            check(f"{symbol} snapshot", False, f"Exception: {e}")

except Exception as e:
    check("Snapshot fetch", False, str(e))


# =========================================================================
# 4. Coinbase Executor Clients
# =========================================================================
section("4. COINBASE EXECUTOR CLIENTS")

try:
    from trading.agape_spot.models import AgapeSpotConfig, SPOT_TICKERS
    from trading.agape_spot.executor import AgapeSpotExecutor, coinbase_available

    check("coinbase-advanced-py installed", coinbase_available)

    if coinbase_available:
        config = AgapeSpotConfig()
        executor = AgapeSpotExecutor(config)

        check("Default Coinbase client", executor._client is not None)
        info("Per-ticker clients", str(list(executor._ticker_clients.keys())) or "None")

        for ticker in TICKERS:
            client = executor._get_client(ticker)
            is_dedicated = ticker in executor._ticker_clients
            label = "DEDICATED" if is_dedicated else ("DEFAULT" if client else "NONE")
            check(f"{ticker} client", client is not None,
                  f"account={label}")

        # Test price fetch from executor
        for ticker in TICKERS:
            try:
                price = executor.get_current_price(ticker)
                check(f"{ticker} executor price", price is not None and price > 0,
                      f"${price:,.8f}" if price else "FAILED")
            except Exception as e:
                check(f"{ticker} executor price", False, str(e))

except ImportError as e:
    check("Executor import", False, str(e))
except Exception as e:
    check("Executor init", False, str(e))


# =========================================================================
# 5. Signal Generation
# =========================================================================
section("5. SIGNAL GENERATION")

try:
    from trading.agape_spot.models import AgapeSpotConfig
    from trading.agape_spot.signals import AgapeSpotSignalGenerator

    config = AgapeSpotConfig()
    signals = AgapeSpotSignalGenerator(config)

    for ticker in TICKERS:
        try:
            signal = signals.generate_signal(ticker=ticker)
            has_signal = signal is not None
            if has_signal:
                check(f"{ticker} signal", True,
                      f"action={signal.action.value} confidence={signal.confidence} "
                      f"reasoning={signal.reasoning[:60]}")
                if signal.action.value == "LONG":
                    info(f"  {ticker} trade params",
                         f"qty={signal.quantity} entry=${signal.entry_price} "
                         f"stop=${signal.stop_loss} target=${signal.take_profit}")
            else:
                check(f"{ticker} signal", False, "None returned")
        except Exception as e:
            check(f"{ticker} signal", False, f"Exception: {e}")

except ImportError as e:
    check("Signal generator import", False, str(e))
except Exception as e:
    check("Signal generator init", False, str(e))


# =========================================================================
# 6. Database Tables
# =========================================================================
section("6. DATABASE TABLES")

try:
    from database_adapter import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()

    tables = [
        "agape_spot_positions",
        "agape_spot_equity_snapshots",
        "agape_spot_scan_activity",
        "agape_spot_activity_log",
    ]
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            check(f"{table}", True, f"{count:,} rows")
        except Exception as e:
            check(f"{table}", False, f"Table missing or error: {e}")
            conn.rollback()

    # Check last scan per ticker
    print()
    info("Last scan activity per ticker:")
    try:
        cur.execute("""
            SELECT ticker, outcome, timestamp
            FROM agape_spot_scan_activity
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY timestamp DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        if rows:
            seen_tickers = set()
            for row in rows:
                ticker, outcome, ts = row
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    age_min = (datetime.now(ts.tzinfo) - ts).total_seconds() / 60 if ts.tzinfo else 0
                    info(f"  {ticker}", f"outcome={outcome} at {ts} ({age_min:.0f}min ago)")
            missing = set(TICKERS) - seen_tickers
            for t in missing:
                warn(f"  {t}", "No scan activity in last 24h")
        else:
            warn("No scan activity in last 24 hours")
    except Exception as e:
        warn(f"Scan activity query failed: {e}")
        conn.rollback()

    # Check open positions per ticker
    print()
    info("Open positions per ticker:")
    try:
        cur.execute("""
            SELECT ticker, COUNT(*) as cnt
            FROM agape_spot_positions
            WHERE status = 'open'
            GROUP BY ticker
        """)
        rows = cur.fetchall()
        if rows:
            for ticker, cnt in rows:
                info(f"  {ticker}", f"{cnt} open positions")
        else:
            info("  No open positions across any ticker")
    except Exception as e:
        warn(f"Position query failed: {e}")
        conn.rollback()

    # Check closed trades per ticker
    print()
    info("Closed trades per ticker (last 7 days):")
    try:
        cur.execute("""
            SELECT ticker,
                   COUNT(*) as trades,
                   SUM(realized_pnl) as total_pnl,
                   SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time > NOW() - INTERVAL '7 days'
            GROUP BY ticker
            ORDER BY ticker
        """)
        rows = cur.fetchall()
        if rows:
            for ticker, trades, pnl, wins in rows:
                wr = f"{wins/trades*100:.0f}%" if trades > 0 else "N/A"
                info(f"  {ticker}",
                     f"{trades} trades, P&L=${pnl:+.2f}, win_rate={wr}")
        else:
            info("  No closed trades in last 7 days")

        # Highlight missing tickers
        traded_tickers = {r[0] for r in rows} if rows else set()
        missing = set(TICKERS) - traded_tickers
        for t in missing:
            warn(f"  {t}", "No trades in last 7 days")
    except Exception as e:
        warn(f"Closed trades query failed: {e}")
        conn.rollback()

    cur.close()
    conn.close()

except ImportError:
    warn("database_adapter not available - skipping DB checks")
except Exception as e:
    warn(f"Database connection failed: {e}")


# =========================================================================
# 7. Trader Singleton
# =========================================================================
section("7. TRADER SINGLETON")

try:
    from trading.agape_spot.trader import get_agape_spot_trader
    trader = get_agape_spot_trader()
    if trader:
        info("Trader singleton", "Already initialized (running in worker)")
        status = trader.get_status()
        info("Status", f"enabled={status.get('status')} cycles={status.get('cycle_count')}")
        info("Tickers", str(status.get("tickers")))
        info("Live tickers", str(status.get("live_tickers")))
        info("Connected", str(status.get("coinbase_connected")))

        per_ticker = status.get("per_ticker", {})
        for t, ts in per_ticker.items():
            acct = ts.get("coinbase_account", "unknown")
            ready = ts.get("live_ready", False)
            mode = ts.get("mode", "unknown")
            open_pos = ts.get("open_positions", 0)
            info(f"  {t}", f"mode={mode} account={acct} live_ready={ready} open={open_pos}")
    else:
        info("Trader singleton", "Not initialized (run from Render shell, not worker)")
        info("  This is expected", "The trader is created by the scheduler in the worker process")

except ImportError as e:
    warn(f"Trader import failed: {e}")
except Exception as e:
    warn(f"Trader check failed: {e}")


# =========================================================================
# Summary
# =========================================================================
section("SUMMARY")

if errors:
    print(f"\n  {FAIL} {len(errors)} FAILURES:")
    for e in errors:
        print(f"       - {e}")
else:
    print(f"\n  {PASS} All checks passed!")

if warnings:
    print(f"\n  {WARN} {len(warnings)} WARNINGS:")
    for w in warnings:
        print(f"       - {w}")

print()
print("  Next steps:")
if any("COINBASE" in e for e in errors):
    print("  1. Verify COINBASE_API_KEY/SECRET env vars are set in Render")
if any("COINGLASS" in e for e in errors):
    print("  2. Verify COINGLASS_API_KEY env var is set in Render")
if not errors:
    print("  1. Deploy this branch to Render")
    print("  2. After deploy, run this script again in Render shell")
    print("  3. Check scan activity after 5-10 minutes for all 4 tickers")
    print("  4. Verify scans show LONG or market data signals (not NO_MARKET_DATA)")

print()
