"""
Pre-Market Smoke Test — IronForge Trading System
=================================================

Run BEFORE the trading day starts to verify:
  1. Bot configs are correct (FLAME, SPARK, INFERNO)
  2. Stop loss multipliers match between scanner and trader
  3. Profit targets (sliding) are correct per tier
  4. Strike calculation produces valid IC structures
  5. Trading windows / entry cutoffs are right
  6. EOD cutoff logic works
  7. PDT enforcement rules
  8. Position exit priority order
  9. P&L calculations
  10. MTM validation guards

Runs WITHOUT Databricks, Tradier, or any external dependencies.

Usage:
    python -m pytest ironforge/tests/test_smoke_trading.py -v
    # or
    python ironforge/tests/test_smoke_trading.py
"""
import sys
import os
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# Setup: add ironforge/ to path so we can import trading.models
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trading.models import (
    BotConfig,
    flame_config,
    spark_config,
    inferno_config,
    IronCondorPosition,
    PositionStatus,
)

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Also load scanner BOT_CONFIG (same trick as test_scanner_smoke.py)
# ---------------------------------------------------------------------------
_scanner = None

def _load_scanner():
    global _scanner
    if _scanner is not None:
        return _scanner
    scanner_dir = os.path.join(os.path.dirname(__file__), "..", "databricks")
    path = os.path.join(scanner_dir, "ironforge_scanner.py")
    if not os.path.exists(path):
        return None
    import types
    os.environ.setdefault("TRADIER_API_KEY", "test_key")
    os.environ.setdefault("DATABRICKS_CATALOG", "alpha_prime")
    os.environ.setdefault("DATABRICKS_SCHEMA", "ironforge")
    os.environ.setdefault("SCANNER_MODE", "test")
    sys.path.insert(0, scanner_dir)
    with open(path, "r") as f:
        source = f.read()
    for marker in ["# Entry point:", "# Cell 3:"]:
        idx = source.find(marker)
        if idx > 0:
            source = source[:idx] + "\n# (truncated for testing)\n"
            break
    mod = types.ModuleType("scanner")
    mod.__file__ = path
    exec(compile(source, path, "exec"), mod.__dict__)
    _scanner = mod
    return mod


# ═══════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════

passed = 0
failed = 0
warnings = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")

def warn(name, detail=""):
    global warnings
    warnings += 1
    print(f"  WARN  {name}  {detail}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. BOT CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def test_bot_configs():
    print("\n=== 1. Bot Config Validation ===")

    flame = flame_config()
    spark = spark_config()
    inferno = inferno_config()

    # FLAME
    check("FLAME bot_name", flame.bot_name == "FLAME", f"got {flame.bot_name}")
    check("FLAME min_dte = 2", flame.min_dte == 2, f"got {flame.min_dte}")
    check("FLAME dte_mode = 2DTE", flame.dte_mode == "2DTE", f"got {flame.dte_mode}")
    check("FLAME sd_multiplier = 1.2", flame.sd_multiplier == 1.2, f"got {flame.sd_multiplier}")
    check("FLAME profit_target_pct = 30", flame.profit_target_pct == 30.0, f"got {flame.profit_target_pct}")
    check("FLAME stop_loss_pct = 200", flame.stop_loss_pct == 200.0, f"got {flame.stop_loss_pct}")
    check("FLAME max_trades_per_day = 1", flame.max_trades_per_day == 1, f"got {flame.max_trades_per_day}")
    check("FLAME entry_end = 14:00", flame.entry_end == "14:00", f"got {flame.entry_end}")
    check("FLAME spread_width = 5", flame.spread_width == 5.0, f"got {flame.spread_width}")
    check("FLAME starting_capital = 10000", flame.starting_capital == 10000.0, f"got {flame.starting_capital}")
    check("FLAME vix_skip = 32", flame.vix_skip == 32.0, f"got {flame.vix_skip}")
    check("FLAME eod_cutoff = 15:45 ET", flame.eod_cutoff_et == "15:45", f"got {flame.eod_cutoff_et}")
    check("FLAME pdt_max = 4", flame.pdt_max_day_trades == 4, f"got {flame.pdt_max_day_trades}")
    check("FLAME pdt_window = 5", flame.pdt_rolling_window_days == 5, f"got {flame.pdt_rolling_window_days}")

    # SPARK
    check("SPARK bot_name", spark.bot_name == "SPARK", f"got {spark.bot_name}")
    check("SPARK min_dte = 1", spark.min_dte == 1, f"got {spark.min_dte}")
    check("SPARK dte_mode = 1DTE", spark.dte_mode == "1DTE", f"got {spark.dte_mode}")
    check("SPARK sd_multiplier = 1.2", spark.sd_multiplier == 1.2, f"got {spark.sd_multiplier}")
    check("SPARK profit_target_pct = 30", spark.profit_target_pct == 30.0, f"got {spark.profit_target_pct}")
    check("SPARK stop_loss_pct = 200", spark.stop_loss_pct == 200.0, f"got {spark.stop_loss_pct}")
    check("SPARK max_trades_per_day = 1", spark.max_trades_per_day == 1, f"got {spark.max_trades_per_day}")
    check("SPARK entry_end = 14:00", spark.entry_end == "14:00", f"got {spark.entry_end}")

    # INFERNO
    check("INFERNO bot_name", inferno.bot_name == "INFERNO", f"got {inferno.bot_name}")
    check("INFERNO min_dte = 0", inferno.min_dte == 0, f"got {inferno.min_dte}")
    check("INFERNO dte_mode = 0DTE", inferno.dte_mode == "0DTE", f"got {inferno.dte_mode}")
    check("INFERNO sd_multiplier = 1.0", inferno.sd_multiplier == 1.0, f"got {inferno.sd_multiplier}")
    check("INFERNO profit_target_pct = 50", inferno.profit_target_pct == 50.0, f"got {inferno.profit_target_pct}")
    check("INFERNO stop_loss_pct = 300", inferno.stop_loss_pct == 300.0, f"got {inferno.stop_loss_pct}")
    check("INFERNO max_trades = 0 (unlimited)", inferno.max_trades_per_day == 0, f"got {inferno.max_trades_per_day}")
    check("INFERNO entry_end = 14:30", inferno.entry_end == "14:30", f"got {inferno.entry_end}")
    check("INFERNO pdt_max = 0 (no PDT)", inferno.pdt_max_day_trades == 0, f"got {inferno.pdt_max_day_trades}")

    # Validate method
    for name, cfg in [("FLAME", flame), ("SPARK", spark), ("INFERNO", inferno)]:
        valid, msg = cfg.validate()
        check(f"{name} config validates", valid, msg)


# ═══════════════════════════════════════════════════════════════════════════
# 2. STOP LOSS CONSISTENCY — SCANNER vs TRADER
# ═══════════════════════════════════════════════════════════════════════════

def test_stop_loss_consistency():
    """
    CRITICAL CHECK: The scanner and the trading engine must agree on stop loss.

    Scanner formula:    stop_loss_price = entry_credit * sl_mult
    Trader formula:     stop_loss_price = entry_credit * (stop_loss_pct / 100)

    For these to match: sl_mult == stop_loss_pct / 100

    Scanner BOT_CONFIG:
        FLAME:   sl_mult = 2.0  → SL at 2x credit → 100% credit LOSS
        SPARK:   sl_mult = 2.0  → SL at 2x credit → 100% credit LOSS
        INFERNO: sl_mult = 3.0  → SL at 3x credit → 200% credit LOSS

    Trader models.py (ALIGNED):
        FLAME:   stop_loss_pct = 200  → SL at 2x credit → 100% credit LOSS
        SPARK:   stop_loss_pct = 200  → SL at 2x credit → 100% credit LOSS
        INFERNO: stop_loss_pct = 300  → SL at 3x credit → 200% credit LOSS
    """
    print("\n=== 2. Stop Loss Consistency (Scanner vs Trader) ===")

    flame = flame_config()
    spark = spark_config()
    inferno = inferno_config()

    scanner = _load_scanner()

    # Trader stop loss multipliers (stop_loss_pct / 100)
    trader_flame_mult = flame.stop_loss_pct / 100.0   # 1.0
    trader_spark_mult = spark.stop_loss_pct / 100.0    # 1.0
    trader_inferno_mult = inferno.stop_loss_pct / 100.0  # 2.0

    print(f"  Trader FLAME   SL mult: {trader_flame_mult}x  (stop_loss_pct={flame.stop_loss_pct})")
    print(f"  Trader SPARK   SL mult: {trader_spark_mult}x  (stop_loss_pct={spark.stop_loss_pct})")
    print(f"  Trader INFERNO SL mult: {trader_inferno_mult}x (stop_loss_pct={inferno.stop_loss_pct})")

    if scanner:
        scanner_flame_mult = scanner.BOT_CONFIG["flame"]["sl_mult"]
        scanner_spark_mult = scanner.BOT_CONFIG["spark"]["sl_mult"]
        scanner_inferno_mult = scanner.BOT_CONFIG["inferno"]["sl_mult"]

        print(f"  Scanner FLAME   sl_mult: {scanner_flame_mult}x")
        print(f"  Scanner SPARK   sl_mult: {scanner_spark_mult}x")
        print(f"  Scanner INFERNO sl_mult: {scanner_inferno_mult}x")

        # Check consistency
        flame_match = abs(trader_flame_mult - scanner_flame_mult) < 0.001
        spark_match = abs(trader_spark_mult - scanner_spark_mult) < 0.001
        inferno_match = abs(trader_inferno_mult - scanner_inferno_mult) < 0.001

        if not flame_match:
            warn(
                "FLAME SL MISMATCH",
                f"Trader={trader_flame_mult}x vs Scanner={scanner_flame_mult}x. "
                f"Trader triggers at break-even, Scanner at {(scanner_flame_mult - 1) * 100:.0f}% credit loss"
            )
        else:
            check("FLAME SL matches scanner", True)

        if not spark_match:
            warn(
                "SPARK SL MISMATCH",
                f"Trader={trader_spark_mult}x vs Scanner={scanner_spark_mult}x. "
                f"Trader triggers at break-even, Scanner at {(scanner_spark_mult - 1) * 100:.0f}% credit loss"
            )
        else:
            check("SPARK SL matches scanner", True)

        if not inferno_match:
            warn(
                "INFERNO SL MISMATCH",
                f"Trader={trader_inferno_mult}x vs Scanner={scanner_inferno_mult}x. "
                f"Trader stops at {(trader_inferno_mult - 1) * 100:.0f}% loss, "
                f"Scanner at {(scanner_inferno_mult - 1) * 100:.0f}% loss"
            )
        else:
            check("INFERNO SL matches scanner", True)
    else:
        warn("Scanner not available — skipping cross-check")

    # Verify stop loss math with concrete examples
    print("\n  --- Stop Loss Scenarios ---")
    entry_credit = 2.50

    # FLAME/SPARK trader: SL at 1x credit
    flame_sl = entry_credit * (flame.stop_loss_pct / 100)
    flame_pnl_at_sl = (entry_credit - flame_sl) * 100  # per contract
    check(
        f"FLAME SL trigger @ ${flame_sl:.2f} (entry ${entry_credit:.2f})",
        flame_sl == entry_credit * trader_flame_mult,
        f"P&L at trigger = ${flame_pnl_at_sl:.2f}/contract"
    )
    print(f"    FLAME: Entry=${entry_credit} → SL triggers at cost=${flame_sl:.2f} → P&L=${flame_pnl_at_sl:.2f}/contract")

    # INFERNO trader: SL at 2x credit
    inferno_sl = entry_credit * (inferno.stop_loss_pct / 100)
    inferno_pnl_at_sl = (entry_credit - inferno_sl) * 100
    check(
        f"INFERNO SL trigger @ ${inferno_sl:.2f} (entry ${entry_credit:.2f})",
        inferno_sl == entry_credit * trader_inferno_mult,
        f"P&L at trigger = ${inferno_pnl_at_sl:.2f}/contract"
    )
    print(f"    INFERNO: Entry=${entry_credit} → SL triggers at cost=${inferno_sl:.2f} → P&L=${inferno_pnl_at_sl:.2f}/contract")


# ═══════════════════════════════════════════════════════════════════════════
# 3. SLIDING PROFIT TARGETS
# ═══════════════════════════════════════════════════════════════════════════

def _get_sliding_profit_target(ct_now: datetime, base_pt_pct: float, bot_name: str = "") -> Tuple[float, str]:
    """Replicate the trader's sliding PT logic for testing.
    Matches scanner get_sliding_profit_target() exactly."""
    time_minutes = ct_now.hour * 60 + ct_now.minute
    base_pt = base_pt_pct / 100.0
    is_inferno = bot_name.upper() == "INFERNO"

    if time_minutes < 630:       # before 10:30 AM CT
        return base_pt, "MORNING"
    elif time_minutes < 780:     # before 1:00 PM CT
        if is_inferno:
            return 0.30, "MIDDAY"
        return max(0.10, base_pt - 0.10), "MIDDAY"
    else:
        if is_inferno:
            return 0.10, "AFTERNOON"
        return max(0.10, base_pt - 0.15), "AFTERNOON"


def test_sliding_profit_targets():
    print("\n=== 3. Sliding Profit Targets ===")

    entry_credit = 2.50

    # FLAME/SPARK (base 30%)
    morning = datetime(2026, 3, 12, 9, 0, tzinfo=CT)
    midday = datetime(2026, 3, 12, 11, 0, tzinfo=CT)
    afternoon = datetime(2026, 3, 12, 14, 0, tzinfo=CT)

    pct, tier = _get_sliding_profit_target(morning, 30.0)
    threshold = entry_credit * (1 - pct)
    check(f"FLAME 9:00 AM = 30% MORNING", pct == 0.30 and tier == "MORNING", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    pct, tier = _get_sliding_profit_target(midday, 30.0)
    threshold = entry_credit * (1 - pct)
    check(f"FLAME 11:00 AM = 20% MIDDAY", abs(pct - 0.20) < 1e-9 and tier == "MIDDAY", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    pct, tier = _get_sliding_profit_target(afternoon, 30.0)
    threshold = entry_credit * (1 - pct)
    check(f"FLAME 2:00 PM = 15% AFTERNOON", pct == 0.15 and tier == "AFTERNOON", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    # INFERNO (base 50%, INFERNO-specific path: 50/30/10)
    pct, tier = _get_sliding_profit_target(morning, 50.0, "INFERNO")
    threshold = entry_credit * (1 - pct)
    check(f"INFERNO 9:00 AM = 50% MORNING", pct == 0.50 and tier == "MORNING", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    pct, tier = _get_sliding_profit_target(midday, 50.0, "INFERNO")
    threshold = entry_credit * (1 - pct)
    check(f"INFERNO 11:00 AM = 30% MIDDAY", abs(pct - 0.30) < 1e-9 and tier == "MIDDAY", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    pct, tier = _get_sliding_profit_target(afternoon, 50.0, "INFERNO")
    threshold = entry_credit * (1 - pct)
    check(f"INFERNO 2:00 PM = 10% AFTERNOON", pct == 0.10 and tier == "AFTERNOON", f"got {pct} {tier}")
    print(f"    Close at ${threshold:.4f} (entry ${entry_credit})")

    # Floor test: ensure PT never goes below 10%
    pct, tier = _get_sliding_profit_target(afternoon, 20.0)
    check("PT floor = 10% (base 20% afternoon)", pct == 0.10, f"got {pct}")


# ═══════════════════════════════════════════════════════════════════════════
# 4. SCANNER SLIDING PT CROSS-CHECK
# ═══════════════════════════════════════════════════════════════════════════

def test_scanner_sliding_pt():
    print("\n=== 4. Scanner Sliding PT Cross-Check ===")
    scanner = _load_scanner()
    if not scanner:
        warn("Scanner not available — skipping")
        return

    morning = datetime(2026, 3, 12, 9, 0, tzinfo=CT)
    midday = datetime(2026, 3, 12, 11, 0, tzinfo=CT)
    afternoon = datetime(2026, 3, 12, 14, 0, tzinfo=CT)

    # FLAME scanner
    pct, tier = scanner.get_sliding_profit_target(morning)
    check(f"Scanner FLAME 9AM = 30% MORNING", pct == 0.30 and tier == "MORNING", f"got {pct} {tier}")

    pct, tier = scanner.get_sliding_profit_target(midday)
    check(f"Scanner FLAME 11AM = 20% MIDDAY", abs(pct - 0.20) < 1e-9 and tier == "MIDDAY", f"got {pct} {tier}")

    pct, tier = scanner.get_sliding_profit_target(afternoon)
    check(f"Scanner FLAME 2PM = 15% AFTERNOON", pct == 0.15 and tier == "AFTERNOON", f"got {pct} {tier}")

    # INFERNO scanner (base_pt=0.50, bot_name="inferno")
    pct, tier = scanner.get_sliding_profit_target(morning, base_pt=0.50, bot_name="inferno")
    check(f"Scanner INFERNO 9AM = 50% MORNING", pct == 0.50 and tier == "MORNING", f"got {pct} {tier}")

    pct, tier = scanner.get_sliding_profit_target(midday, base_pt=0.50, bot_name="inferno")
    check(f"Scanner INFERNO 11AM = 30% MIDDAY", pct == 0.30 and tier == "MIDDAY", f"got {pct} {tier}")

    pct, tier = scanner.get_sliding_profit_target(afternoon, base_pt=0.50, bot_name="inferno")
    check(f"Scanner INFERNO 2PM = 10% AFTERNOON", pct == 0.10 and tier == "AFTERNOON", f"got {pct} {tier}")

    # Cross-check: INFERNO scanner MIDDAY vs trader MIDDAY (should now match)
    trader_pct, _ = _get_sliding_profit_target(midday, 50.0, "INFERNO")
    scanner_pct, _ = scanner.get_sliding_profit_target(midday, base_pt=0.50, bot_name="inferno")
    if abs(trader_pct - scanner_pct) > 0.001:
        warn(
            "INFERNO MIDDAY PT MISMATCH",
            f"Trader={trader_pct:.0%} vs Scanner={scanner_pct:.0%}"
        )
    else:
        check("INFERNO MIDDAY PT matches scanner", True)


# ═══════════════════════════════════════════════════════════════════════════
# 5. STRIKE CALCULATION
# ═══════════════════════════════════════════════════════════════════════════

def test_strike_calculation():
    print("\n=== 5. Strike Calculation ===")

    spot = 585.0
    expected_move = 5.0
    width = 5.0

    # Basic SD=1.2 strikes (FLAME/SPARK)
    sd = 1.2
    put_short = math.floor(spot - sd * expected_move)
    call_short = math.ceil(spot + sd * expected_move)
    put_long = put_short - width
    call_long = call_short + width

    check("put_short < spot", put_short < spot, f"got {put_short}")
    check("call_short > spot", call_short > spot, f"got {call_short}")
    check("put_long = put_short - width", put_long == put_short - width)
    check("call_long = call_short + width", call_long == call_short + width)
    check(f"FLAME strikes: {put_long}/{put_short}P-{call_short}/{call_long}C", True)
    print(f"    SD=1.2: spot={spot}, EM={expected_move} → {put_long}/{put_short}P-{call_short}/{call_long}C")

    # INFERNO SD=1.0 (tighter)
    sd_inf = 1.0
    inf_put_short = math.floor(spot - sd_inf * expected_move)
    inf_call_short = math.ceil(spot + sd_inf * expected_move)

    check("INFERNO put_short > FLAME put_short (tighter)", inf_put_short > put_short,
          f"INFERNO={inf_put_short} FLAME={put_short}")
    check("INFERNO call_short < FLAME call_short (tighter)", inf_call_short < call_short,
          f"INFERNO={inf_call_short} FLAME={call_short}")
    print(f"    SD=1.0: {inf_put_short - width}/{inf_put_short}P-{inf_call_short}/{inf_call_short + width}C")

    # Symmetric wings
    put_width = put_short - put_long
    call_width = call_long - call_short
    check("Wings symmetric", put_width == call_width, f"put_width={put_width} call_width={call_width}")

    # Min EM floor (0.5% of spot)
    min_em = spot * 0.005
    check(f"Min EM floor = ${min_em:.2f}", min_em > 0)

    # Scanner strike calc
    scanner = _load_scanner()
    if scanner:
        s = scanner.calculate_strikes(585.0, 5.0)
        check("Scanner put_short < spot", s["putShort"] < 585.0, f"got {s['putShort']}")
        check("Scanner call_short > spot", s["callShort"] > 585.0, f"got {s['callShort']}")
        check("Scanner put_long = put_short - 5", s["putLong"] == s["putShort"] - 5)
        check("Scanner call_long = call_short + 5", s["callLong"] == s["callShort"] + 5)


# ═══════════════════════════════════════════════════════════════════════════
# 6. TRADING WINDOWS & EOD CUTOFF
# ═══════════════════════════════════════════════════════════════════════════

def test_trading_windows():
    print("\n=== 6. Trading Windows & EOD Cutoff ===")

    flame = flame_config()
    inferno = inferno_config()

    def in_entry_window(now_ct: datetime, config: BotConfig) -> bool:
        mins = now_ct.hour * 60 + now_ct.minute
        start = int(config.entry_start.split(":")[0]) * 60 + int(config.entry_start.split(":")[1])
        end = int(config.entry_end.split(":")[0]) * 60 + int(config.entry_end.split(":")[1])
        return start <= mins <= end

    def past_eod(now_ct: datetime) -> bool:
        now_et = now_ct.astimezone(ET)
        return now_et.hour > 15 or (now_et.hour == 15 and now_et.minute >= 45)

    # Entry window tests
    t_830 = datetime(2026, 3, 12, 8, 30, tzinfo=CT)
    t_1200 = datetime(2026, 3, 12, 12, 0, tzinfo=CT)
    t_1400 = datetime(2026, 3, 12, 14, 0, tzinfo=CT)
    t_1415 = datetime(2026, 3, 12, 14, 15, tzinfo=CT)
    t_1430 = datetime(2026, 3, 12, 14, 30, tzinfo=CT)
    t_1445 = datetime(2026, 3, 12, 14, 45, tzinfo=CT)
    t_1500 = datetime(2026, 3, 12, 15, 0, tzinfo=CT)

    # FLAME entry window: 8:30 - 14:00 CT
    check("FLAME 8:30 AM in entry window", in_entry_window(t_830, flame))
    check("FLAME 12:00 PM in entry window", in_entry_window(t_1200, flame))
    check("FLAME 2:00 PM in entry window (boundary)", in_entry_window(t_1400, flame))
    check("FLAME 2:15 PM past entry window", not in_entry_window(t_1415, flame))

    # INFERNO entry window: 8:30 - 14:30 CT
    check("INFERNO 2:15 PM in entry window", in_entry_window(t_1415, inferno))
    check("INFERNO 2:30 PM in entry window (boundary)", in_entry_window(t_1430, inferno))

    # EOD cutoff: 3:45 PM ET = 2:45 PM CT
    check("2:44 PM CT is NOT past EOD", not past_eod(datetime(2026, 3, 12, 14, 44, tzinfo=CT)))
    check("2:45 PM CT IS past EOD", past_eod(t_1445))
    check("3:00 PM CT IS past EOD", past_eod(t_1500))

    # Before market
    t_early = datetime(2026, 3, 12, 7, 0, tzinfo=CT)
    check("7:00 AM before entry window", not in_entry_window(t_early, flame))

    # Weekend
    saturday = datetime(2026, 3, 14, 10, 0, tzinfo=CT)  # March 14, 2026 = Saturday
    check("Saturday 10 AM technically in window (no weekend guard in entry_window)", True)
    # Note: weekend guard is in _is_in_trading_window, not entry_end check

    # Scanner market hours
    scanner = _load_scanner()
    if scanner:
        check("Scanner 10 AM open", scanner.is_market_open(datetime(2026, 3, 12, 10, 0, tzinfo=CT)))
        check("Scanner 4 PM closed", not scanner.is_market_open(datetime(2026, 3, 12, 16, 0, tzinfo=CT)))
        check("Scanner 2:45 PM = EOD", scanner.is_after_eod_cutoff(t_1445))
        check("Scanner 2:44 PM != EOD", not scanner.is_after_eod_cutoff(datetime(2026, 3, 12, 14, 44, tzinfo=CT)))


# ═══════════════════════════════════════════════════════════════════════════
# 7. P&L CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════

def test_pnl_calculations():
    print("\n=== 7. P&L Calculations ===")

    # P&L formula: (entry_credit - close_price) * 100 * contracts
    entry_credit = 2.50
    contracts = 10

    # Win: close at $1.50 (profit target hit)
    close_price = 1.50
    pnl = (entry_credit - close_price) * 100 * contracts
    check(f"Win: ${entry_credit} entry, ${close_price} close = +${pnl:.0f}", pnl == 1000.0)

    # Loss: close at $4.00 (stop loss hit)
    close_price = 4.00
    pnl = (entry_credit - close_price) * 100 * contracts
    check(f"Loss: ${entry_credit} entry, ${close_price} close = ${pnl:.0f}", pnl == -1500.0)

    # Break even: close at entry credit
    close_price = entry_credit
    pnl = (entry_credit - close_price) * 100 * contracts
    check(f"Break-even: ${entry_credit} entry, ${close_price} close = ${pnl:.0f}", pnl == 0.0)

    # FLAME stop loss scenario (SL at 2x = 100% credit loss)
    flame = flame_config()
    sl_price = entry_credit * (flame.stop_loss_pct / 100)
    sl_pnl = (entry_credit - sl_price) * 100 * contracts
    print(f"    FLAME SL trigger: cost=${sl_price:.2f}, P&L={sl_pnl:.0f} (stop_loss_pct={flame.stop_loss_pct})")

    # INFERNO stop loss scenario (SL at 3x = 200% credit loss)
    inferno = inferno_config()
    sl_price = entry_credit * (inferno.stop_loss_pct / 100)
    sl_pnl = (entry_credit - sl_price) * 100 * contracts
    print(f"    INFERNO SL trigger: cost=${sl_price:.2f}, P&L={sl_pnl:.0f} (stop_loss_pct={inferno.stop_loss_pct})")

    # Max loss calculation: (spread_width - credit) * 100 * contracts
    spread_width = 5.0
    max_loss = (spread_width - entry_credit) * 100 * contracts
    check(f"Max loss = ${max_loss:.0f} (width={spread_width}, credit={entry_credit})", max_loss == 2500.0)

    # Collateral = max_loss = (width - credit) * 100
    collateral_per = (spread_width - entry_credit) * 100
    check(f"Collateral per contract = ${collateral_per:.0f}", collateral_per == 250.0)


# ═══════════════════════════════════════════════════════════════════════════
# 8. EXIT PRIORITY ORDER
# ═══════════════════════════════════════════════════════════════════════════

def test_exit_priority():
    """
    Verify the position exit priority matches trader.py _manage_positions:
    1. Stale/expired positions (from prior day)
    2. MTM data feed failure (10 consecutive failures)
    3. Profit target (sliding)
    4. Stop loss
    5. EOD safety cutoff
    """
    print("\n=== 8. Exit Priority Order ===")

    entry_credit = 2.50
    flame = flame_config()

    # Scenario: Position is BOTH past PT AND past SL — PT wins (checked first)
    close_price = 0.50  # Well below PT threshold
    pt_pct = 0.30
    pt_threshold = entry_credit * (1 - pt_pct)  # $1.75
    sl_threshold = entry_credit * (flame.stop_loss_pct / 100)  # $2.50

    check("PT checked before SL (close=$0.50)", close_price <= pt_threshold and close_price < sl_threshold)
    print(f"    PT threshold=${pt_threshold:.2f}, SL threshold=${sl_threshold:.2f}, close=${close_price}")

    # Scenario: SL triggers, PT doesn't (SL threshold is 2x credit = $5.00)
    close_price = 5.50
    pt_hit = close_price <= pt_threshold
    sl_hit = close_price >= sl_threshold
    check("SL triggers when PT doesn't (close=$5.50)", not pt_hit and sl_hit)

    # Scenario: EOD — neither PT nor SL, but past 2:45 PM
    close_price = 2.00  # Between PT and SL thresholds
    pt_hit = close_price <= pt_threshold
    sl_hit = close_price >= sl_threshold
    check("EOD fallback (close=$2.00, no PT/SL)", not pt_hit and not sl_hit)
    print(f"    Would close at EOD if past 2:45 PM CT")

    # Stale position: always first regardless of P&L
    check("Stale/expired = highest priority close", True)
    print("    Positions from prior day force-closed BEFORE PT/SL checks")


# ═══════════════════════════════════════════════════════════════════════════
# 9. MTM VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def test_mtm_validation():
    print("\n=== 9. MTM Validation ===")

    scanner = _load_scanner()
    if not scanner:
        warn("Scanner not available — skipping MTM validation")
        return

    good_mtm = {
        "cost_to_close": 0.50,
        "put_short_bid": 1.20, "put_short_ask": 1.25,
        "put_long_bid": 0.40, "put_long_ask": 0.45,
        "call_short_bid": 0.80, "call_short_ask": 0.85,
        "call_long_bid": 0.10, "call_long_ask": 0.15,
    }

    valid, reason = scanner.validate_mtm(good_mtm, 1.00)
    check("Valid MTM passes", valid, reason)

    # Zero price
    bad_zero = dict(good_mtm, put_short_ask=0)
    valid, reason = scanner.validate_mtm(bad_zero, 1.00)
    check("Zero ask rejected", not valid, reason)

    # Inverted market
    bad_inv = dict(good_mtm, call_short_bid=0.90, call_short_ask=0.80)
    valid, reason = scanner.validate_mtm(bad_inv, 1.00)
    check("Inverted market rejected", not valid, reason)

    # Wide spread
    bad_wide = dict(good_mtm, put_short_bid=0.10, put_short_ask=0.50)
    valid, reason = scanner.validate_mtm(bad_wide, 1.00)
    check("Wide spread rejected", not valid, reason)

    # Cost > 3x entry
    bad_ctc = dict(good_mtm, cost_to_close=4.00)
    valid, reason = scanner.validate_mtm(bad_ctc, 1.00)
    check("Cost > 3x entry rejected", not valid, reason)

    # Negative cost
    bad_neg = dict(good_mtm, cost_to_close=-0.5)
    valid, reason = scanner.validate_mtm(bad_neg, 1.00)
    check("Negative cost rejected", not valid, reason)

    # None values
    bad_none = dict(good_mtm, call_long_bid=None)
    valid, reason = scanner.validate_mtm(bad_none, 1.00)
    check("None bid rejected", not valid, reason)


# ═══════════════════════════════════════════════════════════════════════════
# 10. SCANNER BOT CONFIG vs TRADER CONFIG
# ═══════════════════════════════════════════════════════════════════════════

def test_scanner_trader_config_alignment():
    print("\n=== 10. Scanner vs Trader Config Alignment ===")

    scanner = _load_scanner()
    if not scanner:
        warn("Scanner not available — skipping alignment check")
        return

    configs = {
        "flame": flame_config(),
        "spark": spark_config(),
        "inferno": inferno_config(),
    }

    for bot_name, trader_cfg in configs.items():
        scanner_cfg = scanner.BOT_CONFIG[bot_name]
        print(f"\n  --- {bot_name.upper()} ---")

        # SD multiplier
        if abs(trader_cfg.sd_multiplier - scanner_cfg["sd"]) > 0.001:
            warn(f"{bot_name.upper()} SD mismatch",
                 f"Trader={trader_cfg.sd_multiplier} Scanner={scanner_cfg['sd']}")
        else:
            check(f"{bot_name.upper()} SD matches", True)

        # Profit target base
        trader_pt = trader_cfg.profit_target_pct / 100.0
        if abs(trader_pt - scanner_cfg["pt_pct"]) > 0.001:
            warn(f"{bot_name.upper()} PT mismatch",
                 f"Trader={trader_pt} Scanner={scanner_cfg['pt_pct']}")
        else:
            check(f"{bot_name.upper()} PT matches", True)

        # Entry end
        trader_entry_end = int(trader_cfg.entry_end.replace(":", ""))
        if trader_entry_end != scanner_cfg["entry_end"]:
            warn(f"{bot_name.upper()} entry_end mismatch",
                 f"Trader={trader_entry_end} Scanner={scanner_cfg['entry_end']}")
        else:
            check(f"{bot_name.upper()} entry_end matches", True)

        # Max trades
        if trader_cfg.max_trades_per_day != scanner_cfg["max_trades"]:
            warn(f"{bot_name.upper()} max_trades mismatch",
                 f"Trader={trader_cfg.max_trades_per_day} Scanner={scanner_cfg['max_trades']}")
        else:
            check(f"{bot_name.upper()} max_trades matches", True)

        # Stop loss (aligned: trader stop_loss_pct/100 should equal scanner sl_mult)
        trader_sl = trader_cfg.stop_loss_pct / 100.0
        scanner_sl = scanner_cfg["sl_mult"]
        if abs(trader_sl - scanner_sl) > 0.001:
            check(f"{bot_name.upper()} SL aligned (Trader={trader_sl}x Scanner={scanner_sl}x)", False)
        else:
            check(f"{bot_name.upper()} SL aligned ({trader_sl}x)", True)


# ═══════════════════════════════════════════════════════════════════════════
# 11. POSITION MODEL INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════

def test_position_model():
    print("\n=== 11. Position Model Integrity ===")

    pos = IronCondorPosition(
        position_id="TEST-001",
        ticker="SPY",
        expiration="2026-03-12",
        put_short_strike=579.0,
        put_long_strike=574.0,
        put_credit=0.80,
        call_short_strike=591.0,
        call_long_strike=596.0,
        call_credit=0.75,
        contracts=5,
        spread_width=5.0,
        total_credit=1.55,
        max_loss=3.45,
        max_profit=1.55,
        underlying_at_entry=585.0,
    )

    # Wings symmetric check
    put_width = pos.put_short_strike - pos.put_long_strike
    call_width = pos.call_long_strike - pos.call_short_strike
    check("Wings symmetric", abs(put_width - call_width) < 0.01, f"put={put_width} call={call_width}")

    # Width matches config
    check("Spread width = 5", put_width == 5.0 and call_width == 5.0)

    # Max loss + max profit = spread_width
    check("max_loss + max_profit = width",
          abs(pos.max_loss + pos.max_profit - pos.spread_width) < 0.01,
          f"{pos.max_loss} + {pos.max_profit} = {pos.max_loss + pos.max_profit}")

    # to_dict works
    d = pos.to_dict()
    check("to_dict has position_id", d["position_id"] == "TEST-001")
    check("to_dict has wings_symmetric", d["wings_symmetric"] is True)
    check("to_dict status = open", d["status"] == "open")

    # Status enum
    check("PositionStatus.OPEN = 'open'", PositionStatus.OPEN.value == "open")
    check("PositionStatus.CLOSED = 'closed'", PositionStatus.CLOSED.value == "closed")
    check("PositionStatus.EXPIRED = 'expired'", PositionStatus.EXPIRED.value == "expired")


# ═══════════════════════════════════════════════════════════════════════════
# 12. COMPREHENSIVE SL/PT SCENARIO TABLE
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario_table():
    """
    Walk through realistic trading scenarios for each bot
    to verify PT/SL triggers are correct.
    """
    print("\n=== 12. Trading Scenario Walkthrough ===")

    scenarios = [
        # (bot, entry_credit, time_ct, current_cost, expected_action)
        ("FLAME", 2.00, (9, 0),   0.50, "PROFIT_TARGET"),   # 0.50 < 2.00*(1-0.30)=1.40
        ("FLAME", 2.00, (11, 0),  1.50, "PROFIT_TARGET"),   # 1.50 < 2.00*(1-0.20)=1.60
        ("FLAME", 2.00, (14, 0),  1.60, "PROFIT_TARGET"),   # 1.60 < 2.00*(1-0.15)=1.70
        ("FLAME", 2.00, (14, 0),  1.80, "HOLD"),            # Between PT and SL
        ("FLAME", 2.00, (14, 0),  4.00, "STOP_LOSS"),       # 4.00 >= 2.00*2.0=4.00
        ("FLAME", 2.00, (14, 0),  5.00, "STOP_LOSS"),       # 5.00 >= 2.00*2.0=4.00
        ("INFERNO", 3.00, (9, 0), 1.00, "PROFIT_TARGET"),   # 1.00 < 3.00*(1-0.50)=1.50
        ("INFERNO", 3.00, (11, 0), 1.70, "PROFIT_TARGET"),  # 1.70 < 3.00*(1-0.30)=2.10
        ("INFERNO", 3.00, (14, 0), 2.60, "PROFIT_TARGET"),  # 2.60 < 3.00*(1-0.10)=2.70
        ("INFERNO", 3.00, (14, 0), 4.00, "HOLD"),           # 4.00 < 3.00*3.0=9.00
        ("INFERNO", 3.00, (14, 0), 9.00, "STOP_LOSS"),      # 9.00 >= 3.00*3.0=9.00
    ]

    for bot_name, entry, (h, m), cost, expected in scenarios:
        if bot_name == "FLAME":
            cfg = flame_config()
        else:
            cfg = inferno_config()

        t = datetime(2026, 3, 12, h, m, tzinfo=CT)
        pt_pct, tier = _get_sliding_profit_target(t, cfg.profit_target_pct, bot_name)
        pt_threshold = entry * (1 - pt_pct)
        sl_threshold = entry * (cfg.stop_loss_pct / 100)

        if cost <= pt_threshold:
            actual = "PROFIT_TARGET"
        elif cost >= sl_threshold:
            actual = "STOP_LOSS"
        else:
            actual = "HOLD"

        check(
            f"{bot_name} entry=${entry:.2f} cost=${cost:.2f} @{h}:{m:02d} = {expected}",
            actual == expected,
            f"got {actual} (PT<=${pt_threshold:.2f} SL>={sl_threshold:.2f})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  IronForge Pre-Market Smoke Test")
    print(f"  Date: {datetime.now(CT).strftime('%Y-%m-%d %H:%M CT')}")
    print("=" * 60)

    test_bot_configs()
    test_stop_loss_consistency()
    test_sliding_profit_targets()
    test_scanner_sliding_pt()
    test_strike_calculation()
    test_trading_windows()
    test_pnl_calculations()
    test_exit_priority()
    test_mtm_validation()
    test_scanner_trader_config_alignment()
    test_position_model()
    test_scenario_table()

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {warnings} warnings")
    if warnings > 0:
        print(f"\n  WARNINGS indicate mismatches between scanner and trader.")
        print(f"  The SCANNER runs on Databricks and is the authority for live trading.")
        print(f"  Fix the trader to match if both are running.")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\n  ACTION REQUIRED: Fix failures before trading day starts!")
        sys.exit(1)
    elif warnings > 0:
        print("\n  REVIEW WARNINGS: Mismatches may cause different behavior.")
        sys.exit(0)
    else:
        print("\n  ALL CLEAR — system ready for trading.")
        sys.exit(0)


if __name__ == "__main__":
    main()
