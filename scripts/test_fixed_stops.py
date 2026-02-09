#!/usr/bin/env python3
"""
Quick test to verify FIXED stops are now the default.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.valor.signals import ValorSignalGenerator, is_ab_test_enabled
from trading.valor.models import ValorConfig, TradingMode

print("=" * 60)
print("VALOR STOP TYPE TEST")
print("=" * 60)

# Check A/B test status
ab_enabled = is_ab_test_enabled()
print(f"\nA/B Test Enabled: {ab_enabled}")

# Create signal generator
config = ValorConfig(mode=TradingMode.PAPER)
print(f"\nConfig initial_stop_points: {config.initial_stop_points} pts (${config.initial_stop_points * 5:.2f})")
print(f"Config profit_target_points: {config.profit_target_points} pts (${config.profit_target_points * 5:.2f})")

# Expected behavior
if ab_enabled:
    print("\n⚠️  A/B Test is ENABLED - 50% FIXED, 50% DYNAMIC")
else:
    print("\n✅ A/B Test is DISABLED - All trades will use FIXED stops")
    print(f"   Max loss per contract: ${config.initial_stop_points * 5:.2f}")
    print(f"   Profit target per contract: ${config.profit_target_points * 5:.2f}")
    print(f"   Risk:Reward ratio: 1:{config.profit_target_points / config.initial_stop_points:.1f}")

# Test the _set_stop_levels method
print("\n" + "-" * 60)
print("Testing stop level calculation...")
print("-" * 60)

gen = ValorSignalGenerator(config=config)

# Mock a signal to test
from trading.valor.models import ValorSignal, TradeDirection, GammaRegime, SignalSource
from datetime import datetime
import pytz

CENTRAL_TZ = pytz.timezone('America/Chicago')

test_signal = ValorSignal(
    timestamp=datetime.now(CENTRAL_TZ),
    symbol="/MESH6",
    direction=TradeDirection.LONG,
    entry_price=6000.0,
    confidence=0.75,
    gamma_regime=GammaRegime.POSITIVE,
    gex_value=1000000,
    flip_point=5950.0,
    call_wall=6050.0,
    put_wall=5900.0,
    vix=18.5,
    signal_source=SignalSource.GEX_MEAN_REVERSION,
    win_probability=0.65,
    trade_reasoning="Test signal"
)

# Call the method
signal, stop_type, stop_points = gen._set_stop_levels(test_signal, atr=8.5)

print(f"\nResult:")
print(f"  Stop Type: {stop_type}")
print(f"  Stop Points: {stop_points}")
print(f"  Stop Price: {signal.stop_price}")
print(f"  Target Price: {signal.target_price}")
print(f"  Risk (pts): {abs(signal.entry_price - signal.stop_price):.2f}")
print(f"  Reward (pts): {abs(signal.target_price - signal.entry_price):.2f}")
print(f"  Risk ($): ${abs(signal.entry_price - signal.stop_price) * 5:.2f}")
print(f"  Reward ($): ${abs(signal.target_price - signal.entry_price) * 5:.2f}")

if stop_type == 'FIXED':
    print("\n✅ FIXED stops are working correctly!")
else:
    print("\n❌ WARNING: Still using DYNAMIC stops!")

print("\n" + "=" * 60)
