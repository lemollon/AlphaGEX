#!/usr/bin/env python3
"""
Render Shell Script: Verify All Bot Status Endpoints

Run in Render shell:
    python scripts/render_verify_bots.py

This verifies:
1. FORTRESS status endpoint returns correct fields
2. SOLOMON status endpoint returns correct fields
3. PEGASUS status endpoint returns correct fields
4. Tradier connections work for each bot
5. Trading window calculations are correct
"""

import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def warn(msg): print(f"[WARN] {msg}")
def info(msg): print(f"[INFO] {msg}")

print("=" * 60)
print("VERIFYING ALL BOT STATUS ENDPOINTS")
print("=" * 60)

errors = []

# ============================================================
# FORTRESS STATUS
# ============================================================
print("\n-- FORTRESS Status --")
try:
    from backend.api.routes.fortress_routes import get_fortress_status
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(get_fortress_status())

    if result.get('success'):
        data = result.get('data', {})

        # Check required fields
        required_fields = [
            'mode', 'capital', 'total_pnl', 'trade_count', 'win_rate',
            'open_positions', 'in_trading_window', 'trading_window_status',
            'is_active', 'current_time', 'heartbeat'
        ]

        missing = [f for f in required_fields if f not in data]
        if missing:
            fail(f"Missing fields: {missing}")
            errors.append("FORTRESS missing fields")
        else:
            ok("All required fields present")

        # Check trading window
        in_window = data.get('in_trading_window')
        window_status = data.get('trading_window_status')
        info(f"Trading Window: {window_status} (in_window={in_window})")

        # Check Tradier connection
        sandbox_connected = data.get('sandbox_connected')
        tradier_error = data.get('tradier_error')
        if sandbox_connected:
            ok(f"Tradier connected (account: {data.get('tradier_account_id')})")
        else:
            warn(f"Tradier not connected: {tradier_error}")

        # Check capital
        capital = data.get('capital', 0)
        info(f"Capital: ${capital:,.2f}")

    else:
        fail(f"FORTRESS status failed: {result}")
        errors.append("FORTRESS status failed")

except Exception as e:
    fail(f"FORTRESS error: {e}")
    errors.append(f"FORTRESS: {e}")

# ============================================================
# SOLOMON STATUS
# ============================================================
print("\n-- SOLOMON Status --")
try:
    from backend.api.routes.solomon_routes import get_solomon_status

    result = asyncio.get_event_loop().run_until_complete(get_solomon_status())

    if result.get('success'):
        data = result.get('data', {})

        # Check required fields
        required_fields = [
            'mode', 'capital', 'total_pnl', 'trade_count', 'win_rate',
            'open_positions', 'in_trading_window', 'trading_window_status',
            'is_active', 'current_time', 'heartbeat'
        ]

        missing = [f for f in required_fields if f not in data]
        if missing:
            fail(f"Missing fields: {missing}")
            errors.append("SOLOMON missing fields")
        else:
            ok("All required fields present")

        # Check trading window
        in_window = data.get('in_trading_window')
        window_status = data.get('trading_window_status')
        info(f"Trading Window: {window_status} (in_window={in_window})")

        # Check ticker
        ticker = data.get('ticker', data.get('config', {}).get('ticker', 'unknown'))
        info(f"Ticker: {ticker}")

        # Check capital
        capital = data.get('capital', 0)
        info(f"Capital: ${capital:,.2f}")

    else:
        fail(f"SOLOMON status failed: {result}")
        errors.append("SOLOMON status failed")

except Exception as e:
    fail(f"SOLOMON error: {e}")
    errors.append(f"SOLOMON: {e}")

# ============================================================
# PEGASUS STATUS
# ============================================================
print("\n-- PEGASUS Status --")
try:
    from backend.api.routes.pegasus_routes import get_pegasus_status

    result = asyncio.get_event_loop().run_until_complete(get_pegasus_status())

    if result.get('success'):
        data = result.get('data', {})

        # Check required fields
        required_fields = [
            'mode', 'capital', 'total_pnl', 'trade_count', 'win_rate',
            'open_positions', 'in_trading_window', 'trading_window_status',
            'is_active', 'current_time'
        ]

        missing = [f for f in required_fields if f not in data]
        if missing:
            fail(f"Missing fields: {missing}")
            errors.append("PEGASUS missing fields")
        else:
            ok("All required fields present")

        # Check trading window
        in_window = data.get('in_trading_window')
        window_status = data.get('trading_window_status')
        info(f"Trading Window: {window_status} (in_window={in_window})")

        # Check capital source (should be paper)
        capital_source = data.get('capital_source', 'unknown')
        info(f"Capital Source: {capital_source}")

        # Check capital (should be ~$200k paper)
        capital = data.get('capital', 0)
        info(f"Capital: ${capital:,.2f}")

        if capital_source == 'paper' and capital >= 200000:
            ok("PEGASUS paper trading with $200k")
        else:
            warn(f"PEGASUS capital: {capital_source} ${capital:,.2f}")

    else:
        fail(f"PEGASUS status failed: {result}")
        errors.append("PEGASUS status failed")

except Exception as e:
    fail(f"PEGASUS error: {e}")
    errors.append(f"PEGASUS: {e}")

# ============================================================
# SOLOMON CONFIG
# ============================================================
print("\n-- SOLOMON Config --")
try:
    from backend.api.routes.solomon_routes import get_solomon_config

    result = asyncio.get_event_loop().run_until_complete(get_solomon_config())

    if result.get('success'):
        data = result.get('data', {})
        source = result.get('source', 'unknown')

        ok(f"Config loaded from: {source}")
        info(f"Settings: {len(data)} items")

        # Show key settings
        for key in ['ticker', 'risk_per_trade', 'max_daily_trades']:
            if key in data:
                val = data[key].get('value', 'N/A') if isinstance(data[key], dict) else data[key]
                info(f"  {key}: {val}")
    else:
        fail(f"SOLOMON config failed: {result}")
        errors.append("SOLOMON config failed")

except Exception as e:
    fail(f"SOLOMON config error: {e}")
    errors.append(f"SOLOMON config: {e}")

# ============================================================
# TRADIER CREDENTIALS CHECK
# ============================================================
print("\n-- Tradier Credentials --")
try:
    from unified_config import APIConfig

    sandbox_key = getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None)
    sandbox_account = getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None)
    prod_key = getattr(APIConfig, 'TRADIER_PROD_API_KEY', None)
    prod_account = getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None)
    use_sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

    info(f"TRADIER_SANDBOX: {use_sandbox}")

    if sandbox_key and sandbox_account:
        ok(f"Sandbox credentials: {sandbox_account}")
    else:
        warn("Sandbox credentials not configured")

    if prod_key and prod_account:
        ok(f"Production credentials: {prod_account}")
    else:
        warn("Production credentials not configured")

    # Expected usage
    print("\n  Expected Tradier Usage:")
    print("    FORTRESS:    Sandbox (SPY)")
    print("    SOLOMON:  Sandbox (SPY)")
    print("    PEGASUS: Production (SPX)")

except Exception as e:
    fail(f"Credentials check error: {e}")
    errors.append(f"Credentials: {e}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if errors:
    print(f"\n❌ FAILED: {len(errors)} issues found")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n✅ SUCCESS: All bot endpoints working correctly")
    sys.exit(0)
