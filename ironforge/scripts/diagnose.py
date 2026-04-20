"""
IronForge Diagnostic Script
=============================

Tests each step of the trading pipeline to identify what's blocking trades.

Usage:
    cd ironforge
    DATABASE_URL=postgresql://... TRADIER_API_KEY=... python scripts/diagnose.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("diagnose")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    icon = "  [+]" if ok else "  [X]"
    msg = f"{icon} {label}: {status}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main():
    all_ok = True

    # ---- 1. Config ----
    section("1. CONFIGURATION")
    from config import Config

    valid, msg = Config.validate()
    all_ok &= check("Config.validate()", valid, msg)
    all_ok &= check(
        "DATABASE_URL set",
        bool(Config.DATABASE_URL) and Config.DATABASE_URL != "postgresql://localhost:5432/ironforge",
        Config.DATABASE_URL[:40] + "..." if len(Config.DATABASE_URL) > 40 else Config.DATABASE_URL,
    )
    all_ok &= check(
        "TRADIER_API_KEY set",
        bool(Config.TRADIER_API_KEY),
        f"{Config.TRADIER_API_KEY[:8]}..." if Config.TRADIER_API_KEY else "EMPTY",
    )
    # Per-bot routing: SPARK resolves to production, everyone else to sandbox.
    from config import PRODUCTION_BOT, get_tradier_base_url
    for bot_name in ("flame", "spark", "inferno"):
        try:
            url = get_tradier_base_url(bot_name)
            label = "production" if bot_name == PRODUCTION_BOT else "sandbox"
            all_ok &= check(
                f"TRADIER base URL [{bot_name}]",
                bool(url),
                f"{url} ({label})",
            )
        except Exception as e:
            all_ok &= check(
                f"TRADIER base URL [{bot_name}]",
                False,
                f"unresolved: {e}",
            )

    # ---- 2. Database ----
    section("2. DATABASE CONNECTION")
    try:
        from trading.db_adapter import db_connection

        with db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1")
            check("PostgreSQL connection", True, "connected")
    except Exception as e:
        check("PostgreSQL connection", False, str(e))
        all_ok = False

    # ---- 3. Tables ----
    section("3. TABLE SETUP")
    try:
        from setup_tables import setup_all_tables

        setup_all_tables()
        check("setup_all_tables()", True, "tables created/verified")
    except Exception as e:
        check("setup_all_tables()", False, str(e))
        all_ok = False

    # Verify tables exist
    try:
        with db_connection() as conn:
            c = conn.cursor()
            for tbl in [
                "flame_paper_account", "spark_paper_account",
                "flame_positions", "spark_positions",
                "bot_heartbeats",
            ]:
                c.execute(f"SELECT COUNT(*) FROM {tbl}")
                cnt = c.fetchone()[0]
                check(f"Table {tbl}", True, f"{cnt} rows")
    except Exception as e:
        check("Table verification", False, str(e))
        all_ok = False

    # ---- 4. Tradier API ----
    section("4. TRADIER API")
    try:
        from trading.tradier_client import TradierClient

        # Use the production-bot router so diagnose verifies the endpoint SPARK
        # will actually hit, not the sandbox default.
        client = TradierClient(bot=PRODUCTION_BOT) if Config.TRADIER_PROD_API_KEY else TradierClient()
        quote = client.get_quote("SPY")
        if quote and quote.get("last", 0) > 0:
            spot = float(quote["last"])
            check("SPY quote", True, f"${spot:.2f}")
        else:
            check("SPY quote", False, f"response: {quote}")
            all_ok = False

        vix = client.get_vix()
        check("VIX quote", vix is not None and vix > 0, f"{vix}")

        expirations = client.get_option_expirations("SPY")
        if expirations:
            check("Option expirations", True, f"{len(expirations)} dates, nearest: {expirations[0]}")
        else:
            check("Option expirations", False, "no expirations returned")
            all_ok = False

    except Exception as e:
        check("Tradier API", False, str(e))
        all_ok = False

    # ---- 5. Trading Window ----
    section("5. TRADING WINDOW")
    from datetime import datetime
    from trading.models import CENTRAL_TZ, flame_config, spark_config

    now = datetime.now(CENTRAL_TZ)
    print(f"  Current time (CT): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Day of week: {now.strftime('%A')}")

    for cfg_fn, label in [(flame_config, "FLAME"), (spark_config, "SPARK")]:
        cfg = cfg_fn()
        current_minutes = now.hour * 60 + now.minute
        start_parts = cfg.entry_start.split(":")
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        eod_minutes = 14 * 60 + 45

        in_window = start_minutes <= current_minutes <= eod_minutes
        is_weekday = now.weekday() < 5
        check(
            f"{label} trading window",
            in_window and is_weekday,
            f"window={cfg.entry_start}-14:45 CT, now={now.strftime('%H:%M')}, weekday={is_weekday}",
        )

    # ---- 6. Signal Generation ----
    section("6. SIGNAL GENERATION (FLAME)")
    try:
        from trading.signals import SignalGenerator

        cfg = flame_config()
        gen = SignalGenerator(cfg)
        check("SignalGenerator init", gen.tradier is not None, "Tradier connected" if gen.tradier else "NO Tradier!")

        market_data = gen.get_market_data()
        if market_data:
            check(
                "Market data",
                True,
                f"SPY=${market_data['spot_price']:.2f}, VIX={market_data['vix']:.1f}, EM={market_data['expected_move']:.2f}",
            )
            check(
                "VIX within threshold",
                market_data["vix"] <= cfg.vix_skip,
                f"VIX {market_data['vix']:.1f} vs skip threshold {cfg.vix_skip}",
            )
        else:
            check("Market data", False, "returned None")
            all_ok = False

        signal = gen.generate_signal()
        if signal:
            if signal.is_valid:
                check(
                    "Signal generated",
                    True,
                    f"{signal.put_long}P/{signal.put_short}P-{signal.call_short}C/{signal.call_long}C "
                    f"exp={signal.expiration} credit=${signal.total_credit:.4f} ({signal.source})",
                )
            else:
                check("Signal generated", False, f"INVALID: {signal.reasoning}")
                all_ok = False
        else:
            check("Signal generated", False, "returned None")
            all_ok = False

    except Exception as e:
        check("Signal generation", False, str(e))
        import traceback
        traceback.print_exc()
        all_ok = False

    # ---- 7. Paper Account ----
    section("7. PAPER ACCOUNT (FLAME)")
    try:
        from trading.db import TradingDatabase

        db = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
        db.initialize_paper_account(10000.0)
        account = db.get_paper_account()
        check("Paper account", True, f"balance=${account.balance:.2f}, BP=${account.buying_power:.2f}")
        check("Buying power sufficient", account.buying_power >= 200, f"${account.buying_power:.2f} (min $200)")

        today_str = now.strftime("%Y-%m-%d")
        traded = db.has_traded_today(today_str)
        check("Hasn't traded today", not traded, "already traded" if traded else "no trades yet")

        open_pos = db.get_open_positions()
        check("No open positions", len(open_pos) == 0, f"{len(open_pos)} open")

        pdt_count = db.get_day_trade_count_rolling_5_days()
        check("PDT room", pdt_count < 3, f"{pdt_count}/3 day trades used")

    except Exception as e:
        check("Paper account", False, str(e))
        all_ok = False

    # ---- Summary ----
    section("SUMMARY")
    if all_ok:
        print("  All checks passed! The bot should be trading.")
        print("  If still no trades, check Render worker logs for runtime errors.")
    else:
        print("  Some checks FAILED. Fix the issues above before expecting trades.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
