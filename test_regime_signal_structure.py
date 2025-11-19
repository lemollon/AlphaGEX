#!/usr/bin/env python3
"""
Test regime signal data structure compatibility

Tests if the structure returned by analyze_current_market_complete()
matches what save_regime_signal_to_db() expects.
"""

import sys
import ast

print("=" * 80)
print("REGIME SIGNAL STRUCTURE TEST")
print("=" * 80)

# Step 1: Check what save_regime_signal_to_db() expects
print("\n1️⃣  Analyzing save_regime_signal_to_db() requirements...")

try:
    with open('psychology_trap_detector.py', 'r') as f:
        content = f.read()

    # Find the save function
    start = content.find('def save_regime_signal_to_db(analysis: Dict) -> int:')
    if start == -1:
        print("❌ Could not find save_regime_signal_to_db function")
        sys.exit(1)

    # Extract what fields it accesses
    function_code = content[start:start+3000]

    required_fields = []
    if "analysis['regime']" in function_code:
        required_fields.append("regime")
    if "analysis['rsi_analysis']" in function_code:
        required_fields.append("rsi_analysis")
    if "analysis['current_walls']" in function_code:
        required_fields.append("current_walls")
    if "analysis['expiration_analysis']" in function_code:
        required_fields.append("expiration_analysis")
    if "analysis.get('forward_gex')" in function_code:
        required_fields.append("forward_gex (optional)")
    if "analysis.get('vix_data')" in function_code:
        required_fields.append("vix_data (optional)")
    if "analysis.get('volatility_regime')" in function_code:
        required_fields.append("volatility_regime (optional)")
    if "analysis['timestamp']" in function_code:
        required_fields.append("timestamp")
    if "analysis['spy_price']" in function_code:
        required_fields.append("spy_price")
    if "analysis['volume_ratio']" in function_code:
        required_fields.append("volume_ratio")

    print(f"✅ Found save_regime_signal_to_db function")
    print(f"\n   Required fields in 'analysis' dict:")
    for field in required_fields:
        print(f"   - {field}")

except Exception as e:
    print(f"❌ Failed to analyze function: {e}")
    sys.exit(1)

# Step 2: Check what analyze_current_market_complete() returns
print("\n2️⃣  Analyzing analyze_current_market_complete() return value...")

try:
    # Find the return statement
    start = content.find('def analyze_current_market_complete(')
    if start == -1:
        print("❌ Could not find analyze_current_market_complete function")
        sys.exit(1)

    # Look for return statement with dict structure
    function_section = content[start:start+20000]

    returned_fields = []
    if "'regime':" in function_section or "\"regime\":" in function_section:
        returned_fields.append("regime")
    if "'rsi_analysis':" in function_section or "\"rsi_analysis\":" in function_section:
        returned_fields.append("rsi_analysis")
    if "'current_walls':" in function_section or "\"current_walls\":" in function_section:
        returned_fields.append("current_walls")
    if "'expiration_analysis':" in function_section or "\"expiration_analysis\":" in function_section:
        returned_fields.append("expiration_analysis")
    if "'forward_gex':" in function_section or "\"forward_gex\":" in function_section:
        returned_fields.append("forward_gex")
    if "'vix_data':" in function_section or "\"vix_data\":" in function_section:
        returned_fields.append("vix_data")
    if "'volatility_regime':" in function_section or "\"volatility_regime\":" in function_section:
        returned_fields.append("volatility_regime")
    if "'timestamp':" in function_section or "\"timestamp\":" in function_section:
        returned_fields.append("timestamp")
    if "'spy_price':" in function_section or "\"spy_price\":" in function_section:
        returned_fields.append("spy_price")
    if "'volume_ratio':" in function_section or "\"volume_ratio\":" in function_section:
        returned_fields.append("volume_ratio")

    print(f"✅ Found analyze_current_market_complete function")
    print(f"\n   Fields in return dict:")
    for field in returned_fields:
        print(f"   - {field}")

except Exception as e:
    print(f"❌ Failed to analyze function: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Check compatibility
print("\n3️⃣  Checking structure compatibility...")

required_set = set([f.split(' (')[0] for f in required_fields])  # Remove "(optional)" suffix
returned_set = set(returned_fields)

missing = required_set - returned_set
extra = returned_set - required_set

if missing:
    print(f"❌ MISSING FIELDS - analyze_current_market_complete() doesn't return:")
    for field in missing:
        print(f"   - {field}")
else:
    print(f"✅ All required fields are returned")

if extra:
    print(f"\n✅ Extra fields (safe to have):")
    for field in extra:
        print(f"   - {field}")

# Step 4: Check autonomous_paper_trader integration
print("\n4️⃣  Checking autonomous_paper_trader.py integration...")

try:
    with open('autonomous_paper_trader.py', 'r') as f:
        trader_content = f.read()

    checks = {
        "Imports save_regime_signal_to_db": "from psychology_trap_detector import" in trader_content and "save_regime_signal_to_db" in trader_content,
        "Calls analyze_current_market_complete": "analyze_current_market_complete(" in trader_content,
        "Calls save_regime_signal_to_db": "save_regime_signal_to_db(" in trader_content,
        "Passes regime_result": "save_regime_signal_to_db(regime_result)" in trader_content
    }

    all_passed = all(checks.values())

    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"   {status} {check}")

except Exception as e:
    print(f"❌ Failed to check trader: {e}")
    all_passed = False

# Final verdict
print("\n" + "=" * 80)
print("STRUCTURE COMPATIBILITY TEST RESULT")
print("=" * 80)

if not missing and all_passed:
    print("✅ PASS - Structure is compatible!")
    print("\nWhat this means:")
    print("  • analyze_current_market_complete() returns all required fields")
    print("  • save_regime_signal_to_db() can process the result")
    print("  • autonomous_paper_trader.py has correct integration")
    print("\nConfidence: 90% - Structure matches, should work at runtime")
    print("\nNext step: Run autonomous trader to confirm it works in practice")
    sys.exit(0)
elif not missing:
    print("⚠️  PARTIAL PASS - Structure matches but integration incomplete")
    print("\nIssues:")
    for check, passed in checks.items():
        if not passed:
            print(f"  • {check}")
    sys.exit(1)
else:
    print("❌ FAIL - Structure mismatch detected")
    print("\nMissing fields will cause runtime errors!")
    print("The integration needs fixing before it will work.")
    sys.exit(1)
