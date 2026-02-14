#!/usr/bin/env python3
"""
Test Perpetual Trades - Forces a test trade on ALL 5 perpetual bots.

Creates:
  1. One OPEN position per coin (visible on Positions tab)
  2. Two CLOSED trades per coin with P&L (visible on History/Performance tabs)
  3. Equity snapshots per coin (visible on Equity Curve tab)
  4. Scan activity entries per coin (visible on Activity tab)

Usage:
    python scripts/test_perpetual_trades.py          # Insert test trades
    python scripts/test_perpetual_trades.py --clean   # Remove test trades only

This gives you confidence the full pipeline works end-to-end.
"""

import sys
import os
import uuid
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

CENTRAL_TZ = ZoneInfo("America/Chicago")

# ============================================================================
# COIN CONFIGURATIONS
# ============================================================================
COINS = [
    {
        "ticker": "ETH",
        "table_prefix": "agape_eth_perp",
        "position_id_prefix": "AGAPE-ETH-PERP",
        "price_col": "eth_price",
        "spot_price": 2650.00,
        "default_quantity": 0.1,
        "starting_capital": 12500.0,
        "stop_pct": 0.02,
        "tp_pct": 0.03,
    },
    {
        "ticker": "BTC",
        "table_prefix": "agape_btc_perp",
        "position_id_prefix": "AGAPE-BTC-PERP",
        "price_col": "btc_price",
        "spot_price": 97500.00,
        "default_quantity": 0.001,
        "starting_capital": 50000.0,
        "stop_pct": 0.02,
        "tp_pct": 0.03,
    },
    {
        "ticker": "XRP",
        "table_prefix": "agape_xrp_perp",
        "position_id_prefix": "AGAPE-XRP-PERP",
        "price_col": "xrp_price",
        "spot_price": 2.45,
        "default_quantity": 500.0,
        "starting_capital": 10000.0,
        "stop_pct": 0.03,
        "tp_pct": 0.04,
    },
    {
        "ticker": "DOGE",
        "table_prefix": "agape_doge_perp",
        "position_id_prefix": "AGAPE-DOGE-PERP",
        "price_col": "doge_price",
        "spot_price": 0.255,
        "default_quantity": 10000.0,
        "starting_capital": 5000.0,
        "stop_pct": 0.03,
        "tp_pct": 0.05,
    },
    {
        "ticker": "SHIB",
        "table_prefix": "agape_shib_perp",
        "position_id_prefix": "AGAPE-SHIB-PERP",
        "price_col": "shib_price",
        "spot_price": 0.0000155,
        "default_quantity": 1000000.0,
        "starting_capital": 5000.0,
        "stop_pct": 0.03,
        "tp_pct": 0.05,
    },
]

# Tag to identify test trades for cleanup
TEST_TAG = "TEST_TRADE_SCRIPT"


def gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def clean_test_trades():
    """Remove all test trades inserted by this script."""
    conn = get_connection()
    if not conn:
        print("ERROR: No database connection")
        return

    try:
        cursor = conn.cursor()
        for coin in COINS:
            pfx = coin["table_prefix"]

            # Delete test positions (identified by signal_reasoning containing our tag)
            cursor.execute(f"""
                DELETE FROM {pfx}_positions
                WHERE signal_reasoning LIKE %s
            """, (f"%{TEST_TAG}%",))
            pos_deleted = cursor.rowcount

            # Delete test scan activity
            cursor.execute(f"""
                DELETE FROM {pfx}_scan_activity
                WHERE signal_reasoning LIKE %s
            """, (f"%{TEST_TAG}%",))
            scan_deleted = cursor.rowcount

            # Delete test equity snapshots (by note)
            cursor.execute(f"""
                DELETE FROM {pfx}_equity_snapshots
                WHERE note LIKE %s
            """, (f"%{TEST_TAG}%",))
            snap_deleted = cursor.rowcount

            # Delete test activity logs
            cursor.execute(f"""
                DELETE FROM {pfx}_activity_log
                WHERE message LIKE %s
            """, (f"%{TEST_TAG}%",))
            log_deleted = cursor.rowcount

            conn.commit()
            print(f"  {coin['ticker']}: Removed {pos_deleted} positions, "
                  f"{scan_deleted} scans, {snap_deleted} snapshots, {log_deleted} logs")

        print("\nAll test data cleaned up.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR during cleanup: {e}")
    finally:
        cursor.close()
        conn.close()


def insert_test_trades():
    """Insert test trades for all 5 perpetual coins."""
    conn = get_connection()
    if not conn:
        print("ERROR: No database connection. Make sure DATABASE_URL is set.")
        return

    now = datetime.now(CENTRAL_TZ)
    cursor = conn.cursor()

    for coin in COINS:
        pfx = coin["table_prefix"]
        ticker = coin["ticker"]
        spot = coin["spot_price"]
        qty = coin["default_quantity"]
        cap = coin["starting_capital"]
        price_col = coin["price_col"]

        print(f"\n{'=' * 60}")
        print(f"  {ticker}-PERP  |  Spot: ${spot}  |  Qty: {qty}")
        print(f"{'=' * 60}")

        try:
            # ==================================================================
            # 1. OPEN POSITION (long) - shows on Positions tab
            # ==================================================================
            open_id = gen_id(coin["position_id_prefix"])
            entry = round(spot * 0.998, 8)  # slight discount on entry
            sl = round(spot * (1 - coin["stop_pct"]), 8)
            tp = round(spot * (1 + coin["tp_pct"]), 8)
            risk = round(qty * spot * coin["stop_pct"], 2)

            cursor.execute(f"""
                INSERT INTO {pfx}_positions (
                    position_id, side, quantity, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, high_water_mark
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
            """, (
                open_id, "long", qty, entry,
                sl, tp, risk,
                spot, 0.0001,
                "POSITIVE", 1.05,
                "LOW", round(spot * 1.002, 8),
                5.2, "POSITIVE",
                "TRADE", 0.68, 0.75,
                json.dumps(["funding_positive", "gex_bullish", "low_squeeze_risk"]),
                "LONG", "HIGH", f"Test open long position [{TEST_TAG}]",
                "open", now - timedelta(hours=2), spot,
            ))
            print(f"  [+] Open position: {open_id} (LONG {qty} @ ${entry})")

            # ==================================================================
            # 2. CLOSED TRADE - WIN (shows on History + Performance tabs)
            # ==================================================================
            win_id = gen_id(coin["position_id_prefix"])
            win_entry = round(spot * 0.99, 8)
            win_close = round(spot * 1.015, 8)
            win_pnl = round((win_close - win_entry) * qty, 2)

            cursor.execute(f"""
                INSERT INTO {pfx}_positions (
                    position_id, side, quantity, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, close_time, close_price,
                    realized_pnl, close_reason, high_water_mark
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                win_id, "long", qty, win_entry,
                round(win_entry * 0.98, 8), round(win_entry * 1.03, 8), risk,
                spot, 0.00015,
                "POSITIVE", 1.1,
                "LOW", round(spot * 1.001, 8),
                4.8, "POSITIVE",
                "TRADE", 0.72, 0.8,
                json.dumps(["strong_trend", "funding_positive"]),
                "LONG", "HIGH", f"Test winning trade [{TEST_TAG}]",
                "closed", now - timedelta(hours=8), now - timedelta(hours=5),
                win_close, win_pnl, "TAKE_PROFIT", win_close,
            ))
            print(f"  [+] Closed WIN: {win_id} (P&L: +${win_pnl:.2f})")

            # ==================================================================
            # 3. CLOSED TRADE - LOSS (shows on History + Performance tabs)
            # ==================================================================
            loss_id = gen_id(coin["position_id_prefix"])
            loss_entry = round(spot * 1.005, 8)
            loss_close = round(spot * 0.985, 8)
            # Short trade that lost
            loss_pnl = round((loss_entry - loss_close) * qty * -1, 2)  # negative = loss on wrong side

            cursor.execute(f"""
                INSERT INTO {pfx}_positions (
                    position_id, side, quantity, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, close_time, close_price,
                    realized_pnl, close_reason, high_water_mark
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                loss_id, "long", qty, loss_entry,
                round(loss_entry * 0.98, 8), round(loss_entry * 1.03, 8), risk,
                spot, -0.0002,
                "NEGATIVE", 0.95,
                "ELEVATED", round(spot * 0.998, 8),
                -2.1, "NEGATIVE",
                "TRADE", 0.52, 0.55,
                json.dumps(["mixed_signals", "funding_negative"]),
                "LONG", "MEDIUM", f"Test losing trade [{TEST_TAG}]",
                "closed", now - timedelta(hours=18), now - timedelta(hours=14),
                loss_close, loss_pnl, "STOP_LOSS", loss_entry,
            ))
            print(f"  [+] Closed LOSS: {loss_id} (P&L: ${loss_pnl:.2f})")

            # ==================================================================
            # 4. EQUITY SNAPSHOTS (shows on Equity Curve tab)
            # ==================================================================
            cumulative_pnl = win_pnl + loss_pnl
            for i, hours_ago in enumerate([24, 18, 12, 6, 3, 1]):
                snap_time = now - timedelta(hours=hours_ago)
                # Build equity progression
                if i < 3:
                    snap_equity = cap
                elif i == 3:
                    snap_equity = cap + win_pnl
                else:
                    snap_equity = cap + cumulative_pnl

                snap_price = round(spot * (1 + (i - 3) * 0.003), 8)
                cursor.execute(f"""
                    INSERT INTO {pfx}_equity_snapshots
                    (timestamp, equity, unrealized_pnl, realized_pnl_cumulative,
                     open_positions, {price_col}, funding_rate, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    snap_time, snap_equity,
                    round(qty * spot * 0.005, 2) if i >= 4 else 0,
                    cumulative_pnl if i >= 3 else (win_pnl if i >= 2 else 0),
                    1 if i >= 4 else 0,
                    snap_price, 0.0001,
                    f"Equity snapshot [{TEST_TAG}]",
                ))
            print(f"  [+] 6 equity snapshots inserted")

            # ==================================================================
            # 5. SCAN ACTIVITY (shows on Activity tab)
            # ==================================================================
            scan_outcomes = [
                ("NEW_TRADE", "LONG", "HIGH", "Strong bullish signal with positive funding"),
                ("NO_TRADE", "WAIT", "LOW", "Insufficient conviction - mixed GEX signals"),
                ("NO_TRADE", "WAIT", "LOW", "Cooldown active after recent trade"),
                ("POSITION_CLOSED", "CLOSE", "HIGH", "Take profit target reached"),
                ("NEW_TRADE", "LONG", "MEDIUM", "Moderate bullish signal"),
            ]
            for i, (outcome, action, conf, reasoning) in enumerate(scan_outcomes):
                scan_time = now - timedelta(hours=20 - i * 4)
                cursor.execute(f"""
                    INSERT INTO {pfx}_scan_activity (
                        timestamp, outcome, {price_col}, funding_rate, funding_regime,
                        ls_ratio, ls_bias, squeeze_risk, leverage_regime,
                        max_pain, crypto_gex, crypto_gex_regime,
                        combined_signal, combined_confidence,
                        oracle_advice, oracle_win_prob,
                        signal_action, signal_reasoning,
                        position_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    scan_time, outcome,
                    round(spot * (1 + (i - 2) * 0.002), 8),
                    0.0001 * (1 + i * 0.2), "POSITIVE",
                    1.0 + i * 0.05, "LONG_BIAS" if i % 2 == 0 else "SHORT_BIAS",
                    "LOW", "MODERATE",
                    round(spot * 1.001, 8), 4.5 + i * 0.3, "POSITIVE",
                    "BULLISH" if i % 2 == 0 else "NEUTRAL", conf,
                    "TRADE" if outcome == "NEW_TRADE" else "SKIP", 0.65 + i * 0.02,
                    action, f"{reasoning} [{TEST_TAG}]",
                    open_id if outcome == "NEW_TRADE" else None,
                ))
            print(f"  [+] 5 scan activity entries inserted")

            # ==================================================================
            # 6. ACTIVITY LOG (shows on Logs)
            # ==================================================================
            cursor.execute(f"""
                INSERT INTO {pfx}_activity_log (level, action, message, details)
                VALUES ('INFO', 'TEST_TRADE', %s, %s)
            """, (
                f"Test trade script executed for {ticker}-PERP [{TEST_TAG}]",
                json.dumps({"open_id": open_id, "win_id": win_id, "loss_id": loss_id}),
            ))

            conn.commit()
            print(f"  All {ticker}-PERP test data committed successfully")

        except Exception as e:
            conn.rollback()
            print(f"  ERROR for {ticker}: {e}")
            import traceback
            traceback.print_exc()

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print("  DONE! All 5 perpetual bots now have test data.")
    print("  Refresh the Perpetuals Crypto page to see results.")
    print(f"{'=' * 60}")
    print(f"\n  To clean up: python scripts/test_perpetual_trades.py --clean")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--clean":
        print("Cleaning up test trades...")
        clean_test_trades()
    else:
        print("Inserting test trades for all 5 perpetual coins...")
        insert_test_trades()
