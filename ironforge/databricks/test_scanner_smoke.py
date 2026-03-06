"""Smoke test for ironforge_scanner.py pure functions.

Runs WITHOUT Spark or Tradier — tests all local logic:
  - OCC symbol building
  - Strike calculation
  - MTM validation (Fix 2)
  - Sliding profit targets
  - Advisor evaluation
  - Market hours logic
  - Expiration targeting
  - num()/to_int() helpers
  - Sandbox account loading
"""
import os
import sys
import math
from datetime import datetime
from unittest.mock import patch

# Ensure the scanner module can import (spark will be missing, that's OK)
os.environ.setdefault("TRADIER_API_KEY", "test_key")
os.environ.setdefault("DATABRICKS_CATALOG", "alpha_prime")
os.environ.setdefault("DATABRICKS_SCHEMA", "ironforge")
os.environ.setdefault("SCANNER_MODE", "test")  # prevent main() from running

# The scanner file has a `spark` reference that will set _HAS_SPARK=False.
# It also calls main() at the bottom — we need to prevent that.
# Import by loading only the function definitions.

# Add parent to path so we can import
sys.path.insert(0, os.path.dirname(__file__))

# We need to prevent the bottom-of-file execution.
# Patch time.sleep and intercept the main loop.
import importlib
import types

def _load_scanner_functions():
    """Load scanner module, skipping the entry-point block at the bottom."""
    path = os.path.join(os.path.dirname(__file__), "ironforge_scanner.py")
    with open(path, "r") as f:
        source = f.read()

    # Cut off everything after "# Entry point:" to avoid running main()
    marker = "# Entry point:"
    idx = source.find(marker)
    if idx > 0:
        source = source[:idx] + "\n# (truncated for testing)\n"

    # Also cut Cell 3 execution (cleanup/main calls)
    marker2 = "# Cell 3:"
    idx2 = source.find(marker2)
    if idx2 > 0:
        source = source[:idx2] + "\n# (truncated for testing)\n"

    mod = types.ModuleType("scanner")
    mod.__file__ = path
    exec(compile(source, path, "exec"), mod.__dict__)
    return mod

print("Loading scanner functions...")
scanner = _load_scanner_functions()
print("OK — scanner loaded\n")

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


# ─── OCC Symbol Building ───────────────────────────────────────────
print("=== OCC Symbol Building ===")

sym = scanner.build_occ_symbol("SPY", "2026-03-10", 580.0, "P")
test("SPY put OCC format", sym == "SPY260310P00580000", f"got {sym}")

sym = scanner.build_occ_symbol("SPY", "2026-03-10", 595.0, "C")
test("SPY call OCC format", sym == "SPY260310C00595000", f"got {sym}")

sym = scanner.build_occ_symbol("SPY", "2026-03-10", 582.5, "P")
test("Half-strike OCC", sym == "SPY260310P00582500", f"got {sym}")

# ─── num() / to_int() Helpers ──────────────────────────────────────
print("\n=== num() / to_int() Helpers ===")

test("num(None) = 0.0", scanner.num(None) == 0.0)
test("num('') = 0.0", scanner.num("") == 0.0)
test("num(3.14) = 3.14", scanner.num(3.14) == 3.14)
test("num('42.5') = 42.5", scanner.num("42.5") == 42.5)
test("num('bad') = 0.0", scanner.num("bad") == 0.0)
test("to_int(None) = 0", scanner.to_int(None) == 0)
test("to_int(7) = 7", scanner.to_int(7) == 7)
test("to_int('3') = 3", scanner.to_int("3") == 3)

# ─── Strike Calculation ────────────────────────────────────────────
print("\n=== Strike Calculation ===")

strikes = scanner.calculate_strikes(585.0, 5.0)
test("put_short < spot", strikes["putShort"] < 585.0, f"got {strikes['putShort']}")
test("call_short > spot", strikes["callShort"] > 585.0, f"got {strikes['callShort']}")
test("put_long = put_short - 5", strikes["putLong"] == strikes["putShort"] - 5)
test("call_long = call_short + 5", strikes["callLong"] == strikes["callShort"] + 5)
test("strikes use 1.2 SD", strikes["putShort"] == math.floor(585.0 - 1.2 * 5.0),
     f"expected {math.floor(585.0 - 1.2*5.0)}, got {strikes['putShort']}")

# Edge case: tiny expected move → uses min_em floor
strikes2 = scanner.calculate_strikes(585.0, 0.01)
test("tiny EM uses floor", strikes2["putShort"] < 585.0, f"got {strikes2}")

# Edge case: huge expected move
strikes3 = scanner.calculate_strikes(585.0, 100.0)
test("huge EM still valid", strikes3["putShort"] < strikes3["callShort"])

# ─── MTM Validation (Fix 2) ───────────────────────────────────────
print("\n=== MTM Validation (Fix 2) ===")

good_mtm = {
    "cost_to_close": 0.50,
    "put_short_bid": 1.20, "put_short_ask": 1.25,
    "put_long_bid": 0.40, "put_long_ask": 0.45,
    "call_short_bid": 0.80, "call_short_ask": 0.85,
    "call_long_bid": 0.10, "call_long_ask": 0.15,
}
valid, reason = scanner.validate_mtm(good_mtm, 1.00)
test("valid MTM passes", valid, reason)

# Zero price on a leg
bad_zero = dict(good_mtm, put_short_ask=0)
valid, reason = scanner.validate_mtm(bad_zero, 1.00)
test("zero ask detected", not valid, reason)
test("zero ask reason", "zero/negative" in reason.lower(), reason)

# Inverted market (ask < bid)
bad_inverted = dict(good_mtm, call_short_bid=0.90, call_short_ask=0.80)
valid, reason = scanner.validate_mtm(bad_inverted, 1.00)
test("inverted market detected", not valid, reason)
test("inverted reason", "inverted" in reason.lower(), reason)

# Wide spread (ask-bid > 50% of mid)
bad_wide = dict(good_mtm, put_short_bid=0.10, put_short_ask=0.50)
valid, reason = scanner.validate_mtm(bad_wide, 1.00)
test("wide spread detected", not valid, reason)
test("wide spread reason", "wide" in reason.lower(), reason)

# Cost to close > 3x entry
bad_ctc = dict(good_mtm, cost_to_close=4.00)
valid, reason = scanner.validate_mtm(bad_ctc, 1.00)
test("cost>3x entry detected", not valid, reason)

# Negative cost_to_close
bad_neg = dict(good_mtm, cost_to_close=-0.5)
valid, reason = scanner.validate_mtm(bad_neg, 1.00)
test("negative cost detected", not valid, reason)

# None values
bad_none = dict(good_mtm, call_long_bid=None)
valid, reason = scanner.validate_mtm(bad_none, 1.00)
test("None bid detected", not valid, reason)

# ─── Sliding Profit Targets ───────────────────────────────────────
print("\n=== Sliding Profit Targets ===")

from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")

morning = datetime(2026, 3, 6, 9, 0, tzinfo=CT)
pct, tier = scanner.get_sliding_profit_target(morning)
test("9:00 AM = 30% MORNING", pct == 0.30 and tier == "MORNING", f"{pct} {tier}")

midday = datetime(2026, 3, 6, 11, 0, tzinfo=CT)
pct, tier = scanner.get_sliding_profit_target(midday)
test("11:00 AM = 20% MIDDAY", pct == 0.20 and tier == "MIDDAY", f"{pct} {tier}")

afternoon = datetime(2026, 3, 6, 14, 0, tzinfo=CT)
pct, tier = scanner.get_sliding_profit_target(afternoon)
test("2:00 PM = 15% AFTERNOON", pct == 0.15 and tier == "AFTERNOON", f"{pct} {tier}")

# ─── Market Hours ─────────────────────────────────────────────────
print("\n=== Market Hours ===")

weekday_open = datetime(2026, 3, 6, 10, 0, tzinfo=CT)  # Friday
test("10:00 AM Fri = open", scanner.is_market_open(weekday_open))

weekday_closed = datetime(2026, 3, 6, 16, 0, tzinfo=CT)
test("4:00 PM Fri = closed", not scanner.is_market_open(weekday_closed))

saturday = datetime(2026, 3, 7, 10, 0, tzinfo=CT)
test("Saturday = closed", not scanner.is_market_open(saturday))

entry_ok = datetime(2026, 3, 6, 12, 0, tzinfo=CT)
test("12:00 PM = entry window", scanner.is_in_entry_window(entry_ok))

entry_late = datetime(2026, 3, 6, 14, 30, tzinfo=CT)
test("2:30 PM = past entry", not scanner.is_in_entry_window(entry_late))

eod = datetime(2026, 3, 6, 14, 45, tzinfo=CT)
test("2:45 PM = EOD cutoff", scanner.is_after_eod_cutoff(eod))

eod_before = datetime(2026, 3, 6, 14, 44, tzinfo=CT)
test("2:44 PM = before EOD", not scanner.is_after_eod_cutoff(eod_before))

warmup = datetime(2026, 3, 6, 8, 25, tzinfo=CT)
test("8:25 AM = warmup window", scanner.is_in_warmup_window(warmup))

not_warmup = datetime(2026, 3, 6, 8, 31, tzinfo=CT)
test("8:31 AM = not warmup", not scanner.is_in_warmup_window(not_warmup))

# ─── Advisor Evaluation ──────────────────────────────────────────
print("\n=== Advisor Evaluation ===")

adv = scanner.evaluate_advisor(18.0, 585.0, 5.0, "2DTE")
test("advisor returns dict", isinstance(adv, dict))
test("advisor has advice", adv["advice"] in ("TRADE_FULL", "TRADE_REDUCED", "SKIP"), adv["advice"])
test("advisor win_prob in range", 0.10 <= adv["winProbability"] <= 0.95, adv["winProbability"])
test("advisor confidence in range", 0.10 <= adv["confidence"] <= 0.95, adv["confidence"])
test("advisor has factors", len(adv["topFactors"]) > 0)

# VIX ideal range should boost
adv_ideal = scanner.evaluate_advisor(18.0, 585.0, 5.0, "2DTE")
adv_high = scanner.evaluate_advisor(35.0, 585.0, 5.0, "2DTE")
test("high VIX lowers win_prob", adv_high["winProbability"] < adv_ideal["winProbability"],
     f"high={adv_high['winProbability']} vs ideal={adv_ideal['winProbability']}")

# 1DTE vs 2DTE
adv_1dte = scanner.evaluate_advisor(18.0, 585.0, 5.0, "1DTE")
adv_2dte = scanner.evaluate_advisor(18.0, 585.0, 5.0, "2DTE")
test("2DTE has higher win_prob than 1DTE",
     adv_2dte["winProbability"] >= adv_1dte["winProbability"],
     f"2DTE={adv_2dte['winProbability']} 1DTE={adv_1dte['winProbability']}")

# ─── Target Expiration ────────────────────────────────────────────
print("\n=== Target Expiration ===")

exp_2dte = scanner.get_target_expiration(2)
test("2DTE expiration is a date string", len(exp_2dte) == 10 and "-" in exp_2dte, exp_2dte)

exp_1dte = scanner.get_target_expiration(1)
test("1DTE expiration is a date string", len(exp_1dte) == 10 and "-" in exp_1dte, exp_1dte)
test("2DTE >= 1DTE", exp_2dte >= exp_1dte, f"2DTE={exp_2dte} 1DTE={exp_1dte}")

# ─── Sandbox Account Loading ─────────────────────────────────────
print("\n=== Sandbox Account Loading ===")

# Reset cache
scanner._sandbox_accounts = None
accounts = scanner._get_sandbox_accounts()
test("3 sandbox accounts loaded", len(accounts) == 3, f"got {len(accounts)}")
names = [a["name"] for a in accounts]
test("User account present", "User" in names, str(names))
test("Matt account present", "Matt" in names, str(names))
test("Logan account present", "Logan" in names, str(names))

for acct in accounts:
    test(f"{acct['name']} has api_key", len(acct.get("api_key", "")) > 0)
    test(f"{acct['name']} has account_id", len(acct.get("account_id", "")) > 0)

# ─── bot_table() ──────────────────────────────────────────────────
print("\n=== bot_table() ===")

t = scanner.bot_table("flame", "positions")
test("flame positions table", t == "alpha_prime.ironforge.flame_positions", t)

t = scanner.bot_table("spark", "pdt_log")
test("spark pdt_log table", t == "alpha_prime.ironforge.spark_pdt_log", t)

# ─── Summary ──────────────────────────────────────────────────────
print(f"\n{'=' * 50}")
print(f"  SMOKE TEST RESULTS: {passed} passed, {failed} failed")
print(f"{'=' * 50}")

sys.exit(1 if failed > 0 else 0)
