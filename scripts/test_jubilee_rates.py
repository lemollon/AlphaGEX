#!/usr/bin/env python3
"""
JUBILEE Rate System Test
===========================

RUN IN RENDER SHELL:
    python scripts/test_jubilee_rates.py

Tests the rate fetcher -> signals -> API data flow.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

def main():
    print("="*60)
    print("JUBILEE RATE SYSTEM TEST")
    print("="*60)
    print(f"Time: {datetime.now()}")
    print(f"FRED_API_KEY: {'SET' if os.environ.get('FRED_API_KEY') else 'NOT SET'}")
    
    errors = []
    
    # Test 1: Rate Fetcher
    print("\n" + "-"*60)
    print("1. RATE FETCHER")
    print("-"*60)
    try:
        from trading.jubilee.rate_fetcher import get_current_rates
        rates = get_current_rates()
        print(f"  Fed Funds: {rates.fed_funds_rate:.2f}%")
        print(f"  SOFR: {rates.sofr_rate:.2f}%")
        print(f"  Source: {rates.source}")
        print(f"  Last Updated: {rates.last_updated}")
        
        if rates.source not in ['live', 'mixed', 'fomc_based', 'treasury_direct', 'fallback']:
            errors.append(f"Invalid source: {rates.source}")
        else:
            print(f"  ✅ Source valid: {rates.source}")
            
    except Exception as e:
        errors.append(f"Rate fetcher failed: {e}")
        print(f"  ❌ Error: {e}")
    
    # Test 2: Signal Generator
    print("\n" + "-"*60)
    print("2. SIGNAL GENERATOR")
    print("-"*60)
    try:
        from trading.jubilee.signals import BoxSpreadSignalGenerator
        generator = BoxSpreadSignalGenerator()
        analysis = generator.analyze_current_rates()
        
        print(f"  Fed Funds: {analysis.fed_funds_rate:.2f}%")
        print(f"  Box Rate: {analysis.box_implied_rate:.2f}%")
        print(f"  rates_source: {analysis.rates_source}")
        print(f"  rates_last_updated: {analysis.rates_last_updated}")
        print(f"  is_favorable: {analysis.is_favorable}")
        
        if not analysis.rates_source:
            errors.append("rates_source not populated in BorrowingCostAnalysis")
        else:
            print(f"  ✅ rates_source populated: {analysis.rates_source}")
            
        if not analysis.rates_last_updated:
            errors.append("rates_last_updated not populated")
        else:
            print(f"  ✅ rates_last_updated populated")
            
    except Exception as e:
        errors.append(f"Signal generator failed: {e}")
        print(f"  ❌ Error: {e}")
    
    # Test 3: Trader
    print("\n" + "-"*60)
    print("3. TRADER")
    print("-"*60)
    try:
        from trading.jubilee.trader import JubileeTrader
        trader = JubileeTrader()
        
        # Check config
        print(f"  Mode: {trader.config.mode.value}")
        print(f"  Entry Start: {trader.config.entry_start}")
        print(f"  Entry End: {trader.config.entry_end}")
        
        if trader.config.entry_start != "08:30":
            errors.append(f"Wrong entry_start: {trader.config.entry_start}, expected 08:30")
        else:
            print(f"  ✅ Entry start correct: 08:30")
            
        # Check rate analysis flows through
        rate_analysis = trader.get_rate_analysis()
        if 'rates_source' in rate_analysis:
            print(f"  ✅ rates_source in API response: {rate_analysis['rates_source']}")
        else:
            errors.append("rates_source missing from get_rate_analysis()")
            print(f"  ❌ rates_source missing from API response")
            
        if 'rates_last_updated' in rate_analysis:
            print(f"  ✅ rates_last_updated in API response")
        else:
            errors.append("rates_last_updated missing from get_rate_analysis()")
            print(f"  ❌ rates_last_updated missing from API response")
            
    except Exception as e:
        errors.append(f"Trader failed: {e}")
        print(f"  ❌ Error: {e}")
    
    # Test 4: Timezone
    print("\n" + "-"*60)
    print("4. TIMEZONE CHECK")
    print("-"*60)
    try:
        from trading.jubilee.trader import CENTRAL_TZ
        from trading.jubilee.executor import CENTRAL_TZ as EXEC_TZ
        from trading.jubilee.signals import CENTRAL_TZ as SIG_TZ
        from trading.jubilee.db import CENTRAL_TZ as DB_TZ
        
        all_ct = all(str(tz) == "America/Chicago" for tz in [CENTRAL_TZ, EXEC_TZ, SIG_TZ, DB_TZ])
        if all_ct:
            print(f"  ✅ All modules use America/Chicago")
        else:
            errors.append("Not all modules use America/Chicago timezone")
            print(f"  ❌ Timezone mismatch")
            
    except Exception as e:
        errors.append(f"Timezone check failed: {e}")
        print(f"  ❌ Error: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if errors:
        print(f"\n❌ {len(errors)} ERRORS FOUND:")
        for err in errors:
            print(f"  - {err}")
        return 1
    else:
        print("\n✅ ALL TESTS PASSED - JUBILEE RATE SYSTEM IS WORKING")
        return 0

if __name__ == "__main__":
    sys.exit(main())
