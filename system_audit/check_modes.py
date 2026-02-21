#!/usr/bin/env python3
"""
Check trading mode (LIVE vs PAPER) for every bot.
Run on Render shell: python3 system_audit/check_modes.py
"""
import os
import sys

print("=" * 60)
print("  TRADING MODE CHECK - LIVE vs PAPER")
print("=" * 60)

# Find all bot directories
bot_dirs = []
trading_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'trading')
if not os.path.exists(trading_path):
    trading_path = 'trading'

for item in sorted(os.listdir(trading_path)):
    path = os.path.join(trading_path, item)
    if os.path.isdir(path) and not item.startswith('_') and item not in ('shared', '__pycache__', 'mixins'):
        bot_dirs.append(item)

print(f"\nFound {len(bot_dirs)} bot directories: {', '.join(bot_dirs)}\n")

for bot in bot_dirs:
    print(f"--- {bot.upper()} ---")

    # Check for mode in models/config/trader files
    models_path = os.path.join(trading_path, bot, 'models.py')
    trader_path = os.path.join(trading_path, bot, 'trader.py')
    config_path = os.path.join(trading_path, bot, 'config.py')

    found_any = False
    for fpath in [models_path, trader_path, config_path]:
        if os.path.exists(fpath):
            with open(fpath) as f:
                content = f.read()
            # Look for mode indicators
            for keyword in ['TradingMode.PAPER', 'TradingMode.LIVE',
                            'mode = TradingMode', 'mode=TradingMode',
                            'is_paper', 'is_live', 'sandbox=True', 'sandbox=False',
                            'PAPER', 'LIVE']:
                lines = [
                    (i + 1, line.strip())
                    for i, line in enumerate(content.split('\n'))
                    if keyword in line
                    and not line.strip().startswith('#')
                    and 'import' not in line
                    and len(line.strip()) < 120
                ]
                for linenum, line in lines:
                    basename = os.path.basename(fpath)
                    # Add flags for clarity
                    flag = ""
                    if 'PAPER' in line and '=' in line and 'LIVE' not in line:
                        flag = " <-- PAPER MODE"
                    elif 'LIVE' in line and '=' in line and 'PAPER' not in line:
                        flag = " <-- LIVE MODE"
                    elif 'sandbox=True' in line or 'sandbox = True' in line:
                        flag = " <-- SANDBOX"
                    print(f"  {basename}:{linenum}: {line[:100]}{flag}")
                    found_any = True

    # Check if executor places real Tradier orders
    executor_path = os.path.join(trading_path, bot, 'executor.py')
    if os.path.exists(executor_path):
        with open(executor_path) as f:
            content = f.read()
        has_real_orders = any(kw in content for kw in ['place_order', 'submit_order', 'create_order'])
        has_tradier = 'tradier' in content.lower()
        has_paper_sim = any(kw in content for kw in ['simulate', 'paper_fill', 'fake_fill', 'mock_fill'])
        if has_real_orders or has_tradier:
            print(f"  executor.py: Contains Tradier/order calls")
        else:
            print(f"  executor.py: No Tradier order calls found")
        if has_paper_sim:
            print(f"  executor.py: Contains simulation/paper fill logic")

    if not found_any:
        print(f"  No mode indicators found in config files")

    print()

print("Done. Review each bot for PAPER MODE or SANDBOX flags.")
print("Any bot that should be LIVE but isn't needs to be fixed.")
