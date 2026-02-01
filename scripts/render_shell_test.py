#!/usr/bin/env python3
"""
Render Shell Quick Test - Directional Bot Fixes
================================================

Quick verification script for Render shell.
Copy and paste into Render shell:

python
exec(open('scripts/render_shell_test.py').read())

Or run directly:
python scripts/render_shell_test.py
"""

import os
import sys

# Add project root to path
if os.getcwd().endswith('/scripts'):
    os.chdir('..')
sys.path.insert(0, os.getcwd())

print("\n" + "="*60)
print("QUICK VERIFICATION - DIRECTIONAL BOT FIXES")
print("="*60)

# Test 1: Oracle confidence scale
print("\n1. Oracle Confidence Scale:")
try:
    from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime
    import pytz
    from datetime import datetime

    ct = pytz.timezone('America/Chicago')
    now_ct = datetime.now(ct)

    oracle = OracleAdvisor()
    context = MarketContext(
        spot_price=590.0, vix=18.0,
        gex_put_wall=580.0, gex_call_wall=600.0,
        gex_regime=GEXRegime.NEUTRAL, gex_net=1000000,
        gex_flip_point=588.0, day_of_week=now_ct.weekday(),
        gex_normalized=0.5, gex_distance_to_flip_pct=0.34,
        gex_between_walls=True, expected_move_pct=1.1,
        vix_percentile_30d=45.0, vix_change_1d=2.5,
        price_change_1d=0.3, win_rate_30d=0.55,
    )

    pred = oracle.get_athena_advice(context=context, use_gex_walls=True, wall_filter_pct=6.0, bot_name="TEST")
    if pred:
        conf = pred.confidence
        if conf > 1.0:
            print(f"   ❌ FAIL: Confidence {conf} > 1.0 (wrong scale!)")
        else:
            print(f"   ✅ PASS: Confidence {conf:.2f} (0-1 scale)")
    else:
        print("   ⚠️ No prediction (may be expected)")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 2: ICARUS config
print("\n2. ICARUS R:R Ratio:")
try:
    from trading.icarus.models import ICARUSConfig
    cfg = ICARUSConfig()
    if cfg.profit_target_pct == 50.0 and cfg.stop_loss_pct == 50.0:
        print(f"   ✅ PASS: 50/50 (1:1 ratio)")
    else:
        print(f"   ❌ FAIL: {cfg.profit_target_pct}/{cfg.stop_loss_pct}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 3: Day of week in ICARUS signals
print("\n3. Day of Week in ICARUS:")
try:
    import inspect
    from trading.icarus.signals import SignalGenerator
    src = inspect.getsource(SignalGenerator.get_oracle_advice)
    if 'day_of_week=now_ct.weekday()' in src:
        print("   ✅ PASS: day_of_week passed to Oracle")
    else:
        print("   ❌ FAIL: day_of_week missing")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 4: ML Features in ICARUS
print("\n4. ML Features in ICARUS get_gex_data:")
try:
    import inspect
    from trading.icarus.signals import SignalGenerator
    src = inspect.getsource(SignalGenerator.get_gex_data)
    features = ['vix_percentile_30d', 'vix_change_1d', 'price_change_1d', 'win_rate_30d']
    found = [f for f in features if f in src]
    if len(found) == 4:
        print(f"   ✅ PASS: All 4 new features present")
    else:
        missing = [f for f in features if f not in src]
        print(f"   ❌ FAIL: Missing {missing}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 5: Flip filter in Oracle
print("\n5. Flip Distance Filter in Oracle:")
try:
    import inspect
    from quant.oracle_advisor import OracleAdvisor
    src = inspect.getsource(OracleAdvisor.get_athena_advice)
    if 'flip_distance_pct' in src and 'FLIP_FILTER' in src:
        print("   ✅ PASS: Flip filter active")
    else:
        print("   ⚠️ PARTIAL: Flip filter may not be complete")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 6: Friday filter in Oracle
print("\n6. Friday Filter in Oracle:")
try:
    import inspect
    from quant.oracle_advisor import OracleAdvisor
    src = inspect.getsource(OracleAdvisor.get_athena_advice)
    if 'is_friday' in src and 'FRIDAY_FILTER' in src:
        print("   ✅ PASS: Friday filter active")
    else:
        print("   ⚠️ PARTIAL: Friday filter may not be complete")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 7: ATHENA Features
print("\n7. ML Features in ATHENA get_gex_data:")
try:
    import inspect
    from trading.athena_v2.signals import SignalGenerator
    src = inspect.getsource(SignalGenerator.get_gex_data)
    features = ['vix_percentile_30d', 'vix_change_1d', 'price_change_1d', 'win_rate_30d']
    found = [f for f in features if f in src]
    if len(found) == 4:
        print(f"   ✅ PASS: All 4 new features present")
    else:
        missing = [f for f in features if f not in src]
        print(f"   ❌ FAIL: Missing {missing}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

print("\n" + "="*60)
print("VERIFICATION COMPLETE")
print("="*60)
