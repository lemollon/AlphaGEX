#!/bin/bash
# =============================================================
#  IronForge Force Trade (Render Shell)
#  Forces FLAME or SPARK to execute a paper trade NOW,
#  bypassing trading-window and has-traded-today checks.
#
#  Usage (paste into Render shell):
#    bash /opt/render/project/src/ironforge/scripts/render_force_trade.sh
#    bash /opt/render/project/src/ironforge/scripts/render_force_trade.sh spark
#    bash /opt/render/project/src/ironforge/scripts/render_force_trade.sh flame --close-first
# =============================================================

IRONFORGE_DIR="/opt/render/project/src/ironforge"
VENV_DIR="/tmp/ironforge_venv"
BOT="${1:-flame}"
CLOSE_FIRST="${2:-}"

echo "============================================================"
echo "  IRONFORGE FORCE TRADE: ${BOT^^}"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

# Ensure venv
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[SETUP] Creating venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet psycopg2-binary requests 2>/dev/null
fi

PY="$VENV_DIR/bin/python"

"$PY" - "$IRONFORGE_DIR" "$BOT" "$CLOSE_FIRST" <<'PYEOF'
import sys, os, json, traceback
from datetime import datetime

ironforge_dir = sys.argv[1]
bot_arg = sys.argv[2].lower()
close_first = sys.argv[3] if len(sys.argv) > 3 else ""

sys.path.insert(0, ironforge_dir)
os.chdir(ironforge_dir)

if bot_arg not in ("flame", "spark"):
    print(f"  ERROR: Invalid bot '{bot_arg}'. Use 'flame' or 'spark'.")
    sys.exit(1)

from config import Config
valid, msg = Config.validate()
if not valid:
    print(f"  CONFIG ERROR: {msg}")
    sys.exit(1)

from setup_tables import setup_all_tables
setup_all_tables()

from trading.models import flame_config, spark_config, CENTRAL_TZ
from trading.signals import SignalGenerator
from trading.executor import PaperExecutor
from trading.db import TradingDatabase

config = flame_config() if bot_arg == "flame" else spark_config()
db = TradingDatabase(bot_name=config.bot_name, dte_mode=config.dte_mode)
db.initialize_paper_account(config.starting_capital)

now = datetime.now(CENTRAL_TZ)
print(f"  Bot: {config.bot_name} ({config.dte_mode})")
print(f"  Time (CT): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# ================================================================
# STEP 0: Force-close open positions if --close-first
# ================================================================
open_positions = db.get_open_positions()

if open_positions:
    print(f"\n  OPEN POSITIONS: {len(open_positions)}")
    for p in open_positions:
        print(f"    {p.position_id}: "
            f"{p.put_long_strike}/{p.put_short_strike}P-"
            f"{p.call_short_strike}/{p.call_long_strike}C "
            f"x{p.contracts} @ ${p.total_credit:.4f} "
            f"exp={p.expiration}")

    if close_first == "--close-first":
        print(f"\n  FORCE-CLOSING {len(open_positions)} position(s)...")
        signal_gen = SignalGenerator(config)
        executor = PaperExecutor(config, db)

        for p in open_positions:
            # Try to get MTM, fall back to entry credit (breakeven)
            mtm = signal_gen.get_ic_mark_to_market(
                put_short=p.put_short_strike,
                put_long=p.put_long_strike,
                call_short=p.call_short_strike,
                call_long=p.call_long_strike,
                expiration=p.expiration,
            )
            close_price = mtm if mtm is not None else p.total_credit
            success, pnl = executor.close_paper_position(p, close_price, "force_close_manual")
            status = "OK" if success else "FAILED"
            print(f"    {p.position_id}: {status} (close@${close_price:.4f}, P&L=${pnl:.2f})")
            db.log("FORCE_CLOSE", f"Manual force close: {p.position_id} P&L=${pnl:.2f}")

        # Refresh
        open_positions = db.get_open_positions()
        print(f"  Remaining open: {len(open_positions)}")
    else:
        print(f"\n  Cannot open new trade with {len(open_positions)} position(s) open.")
        print(f"  Options:")
        print(f"    1. Wait for positions to close (PT/SL/EOD)")
        print(f"    2. Re-run with --close-first flag:")
        print(f"       bash .../render_force_trade.sh {bot_arg} --close-first")
        sys.exit(1)

if open_positions:
    print(f"  Still {len(open_positions)} open after close attempt. Aborting.")
    sys.exit(1)

# ================================================================
# STEP 1: Paper account check
# ================================================================
print(f"\n{'='*56}")
print(f"  STEP 1: PAPER ACCOUNT")
print(f"{'='*56}")

account = db.get_paper_account()
print(f"  Balance: ${account.balance:.2f}")
print(f"  Buying Power: ${account.buying_power:.2f}")
print(f"  Cumulative P&L: ${account.cumulative_pnl:.2f}")
print(f"  Total Trades: {account.total_trades}")
print(f"  Active: {account.is_active}")

if account.buying_power < 200:
    print(f"\n  ERROR: Buying power ${account.buying_power:.2f} < $200 minimum")
    print(f"  This usually means collateral is tied up in a position.")
    sys.exit(1)

# ================================================================
# STEP 2: Signal generation
# ================================================================
print(f"\n{'='*56}")
print(f"  STEP 2: SIGNAL GENERATION")
print(f"{'='*56}")

signal_gen = SignalGenerator(config)
executor = PaperExecutor(config, db)

print(f"  Tradier connected: {signal_gen.tradier is not None}")

market_data = signal_gen.get_market_data()
if market_data:
    print(f"  SPY: ${market_data['spot_price']:.2f}")
    print(f"  VIX: {market_data['vix']:.1f}")
    print(f"  Expected Move: ${market_data['expected_move']:.2f}")
    print(f"  VIX skip threshold: {config.vix_skip}")
else:
    print(f"  ERROR: No market data. Tradier API may be down.")
    sys.exit(1)

signal = signal_gen.generate_signal()
if not signal:
    print(f"  ERROR: generate_signal() returned None")
    sys.exit(1)
if not signal.is_valid:
    print(f"  ERROR: Signal not valid: {signal.reasoning}")
    print(f"\n  Signal details:")
    print(f"    Strikes: {signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C")
    print(f"    Credit: ${signal.total_credit:.4f}")
    print(f"    Source: {signal.source}")
    sys.exit(1)

print(f"\n  SIGNAL VALID:")
print(f"    Strikes: {signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C")
print(f"    Expiration: {signal.expiration}")
print(f"    Credit: ${signal.total_credit:.4f} ({signal.source})")
print(f"    Win Probability: {signal.oracle_win_probability:.2f}")
print(f"    Confidence: {signal.confidence:.2f}")
print(f"    Advice: {signal.oracle_advice}")
print(f"    Wings adjusted: {signal.wings_adjusted}")

# ================================================================
# STEP 3: Trade sizing
# ================================================================
print(f"\n{'='*56}")
print(f"  STEP 3: TRADE SIZING")
print(f"{'='*56}")

spread_width = signal.put_short - signal.put_long
collateral_per = executor.calculate_collateral(spread_width, signal.total_credit)
max_contracts = executor.calculate_max_contracts(account.buying_power, collateral_per)

print(f"  Spread width: ${spread_width:.0f}")
print(f"  Collateral/contract: ${collateral_per:.2f}")
print(f"  Usable BP (85%): ${account.buying_power * 0.85:.2f}")
print(f"  Max contracts: {max_contracts} (cap={config.max_contracts})")
print(f"  Total collateral: ${collateral_per * max_contracts:.2f}")
print(f"  Max profit: ${signal.total_credit * 100 * max_contracts:.2f}")
print(f"  Max loss: ${collateral_per * max_contracts:.2f}")

if max_contracts < 1:
    print(f"\n  ERROR: Cannot afford any contracts")
    print(f"  Need at least ${collateral_per:.2f} buying power for 1 contract")
    sys.exit(1)

# ================================================================
# STEP 4: Execute paper trade
# ================================================================
print(f"\n{'='*56}")
print(f"  STEP 4: EXECUTING PAPER TRADE")
print(f"{'='*56}")

position = executor.open_paper_position(signal, max_contracts)
if not position:
    print(f"  ERROR: Paper execution failed!")
    sys.exit(1)

# Log signal
db.log_signal(
    spot_price=signal.spot_price,
    vix=signal.vix,
    expected_move=signal.expected_move,
    call_wall=signal.call_wall,
    put_wall=signal.put_wall,
    gex_regime=signal.gex_regime,
    put_short=signal.put_short,
    put_long=signal.put_long,
    call_short=signal.call_short,
    call_long=signal.call_long,
    total_credit=signal.total_credit,
    confidence=signal.confidence,
    was_executed=True,
    reasoning=f"FORCE_TRADE: {signal.reasoning}",
    wings_adjusted=signal.wings_adjusted,
)

db.update_heartbeat("active", "force_trade")
db.log("FORCE_TRADE", f"Forced {position.position_id}: "
    f"{signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C "
    f"x{max_contracts} @ ${signal.total_credit:.4f}")

# Verify position saved
verify_positions = db.get_open_positions()
saved = any(p.position_id == position.position_id for p in verify_positions)

updated_account = db.get_paper_account()

print(f"\n  {'='*52}")
print(f"  SUCCESS!")
print(f"  {'='*52}")
print(f"  Position ID: {position.position_id}")
print(f"  Strikes: {signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C")
print(f"  Expiration: {signal.expiration}")
print(f"  Contracts: {max_contracts}")
print(f"  Credit: ${signal.total_credit:.4f}")
print(f"  Collateral: ${collateral_per * max_contracts:.2f}")
print(f"  DB verified: {'YES' if saved else 'NO — CHECK DB!'}")
print(f"  New balance: ${updated_account.balance:.2f}")
print(f"  New BP: ${updated_account.buying_power:.2f}")
print(f"  {'='*52}")

print(f"\n  The position will be managed automatically by the scheduler.")
print(f"  Profit target: {config.profit_target_pct}% | Stop loss: {config.stop_loss_pct}% | EOD: {config.eod_cutoff_et} ET")
print(f"\n  To force-close this position later:")
print(f"    bash .../render_force_trade.sh {bot_arg} --close-first")

PYEOF
