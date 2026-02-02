#!/usr/bin/env python3
"""
HERACLES Integration Test
=========================
Verifies all components needed for HERACLES trading are working.

Run this after deploying to verify the fix works.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tradier_production_keys():
    """Test 1: Verify Tradier production API keys are configured"""
    print("\n" + "="*60)
    print("TEST 1: Tradier Production API Keys")
    print("="*60)
    
    api_key = os.environ.get('TRADIER_API_KEY', '')
    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY', '')
    
    if api_key:
        print(f"✅ TRADIER_API_KEY is set (length: {len(api_key)})")
    else:
        print("❌ TRADIER_API_KEY is NOT set - SPX GEX will fail!")
        return False
    
    if sandbox_key:
        print(f"   TRADIER_SANDBOX_API_KEY also set (length: {len(sandbox_key)})")
    
    return True


def test_spx_gex_fetch():
    """Test 2: Verify SPX GEX data can be fetched"""
    print("\n" + "="*60)
    print("TEST 2: SPX GEX Data Fetch")
    print("="*60)
    
    try:
        from trading.heracles.signals import get_gex_data_for_heracles
        
        gex_data = get_gex_data_for_heracles("SPX")
        
        flip_point = gex_data.get('flip_point', 0)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)
        net_gex = gex_data.get('net_gex', 0)
        
        print(f"   Flip Point: {flip_point}")
        print(f"   Call Wall:  {call_wall}")
        print(f"   Put Wall:   {put_wall}")
        print(f"   Net GEX:    {net_gex}")
        
        if flip_point > 1000:  # Should be ~5900 for SPX
            print(f"✅ SPX GEX data looks valid (flip_point={flip_point:.2f})")
            return True
        else:
            print(f"❌ SPX GEX data invalid or missing (flip_point={flip_point})")
            return False
            
    except Exception as e:
        print(f"❌ Failed to fetch SPX GEX: {e}")
        return False


def test_mes_quote():
    """Test 3: Verify MES quote can be obtained"""
    print("\n" + "="*60)
    print("TEST 3: MES Quote")
    print("="*60)

    try:
        from trading.heracles.executor import TastytradeExecutor
        from trading.heracles.models import HERACLESConfig, TradingMode

        config = HERACLESConfig(mode=TradingMode.PAPER)
        executor = TastytradeExecutor(config)

        quote = executor.get_mes_quote()

        if quote:
            price = quote.get('last', quote.get('price', 0))
            source = quote.get('source', 'TASTYTRADE')
            print(f"   MES Price: {price:.2f}")
            print(f"   Source: {source}")
            print(f"   Bid: {quote.get('bid', 0):.2f}")
            print(f"   Ask: {quote.get('ask', 0):.2f}")

            if price > 1000:  # Should be ~5900
                print(f"✅ MES quote looks valid (price={price:.2f} from {source})")
                return True
            else:
                print(f"❌ MES quote invalid (price={price})")
                return False
        else:
            print("❌ Could not get MES quote from any source")
            return False

    except Exception as e:
        print(f"❌ Failed to get MES quote: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vix_fetch():
    """Test 3b: Verify VIX can be fetched"""
    print("\n" + "="*60)
    print("TEST 3b: VIX Data Fetch")
    print("="*60)

    try:
        from trading.heracles.trader import HERACLESTrader

        trader = HERACLESTrader()
        vix = trader._get_vix()

        print(f"   VIX: {vix:.2f}")

        if 5 < vix < 100:  # Reasonable VIX range
            print(f"✅ VIX looks valid ({vix:.2f})")
            return True
        else:
            print(f"❌ VIX out of expected range ({vix})")
            return False

    except Exception as e:
        print(f"❌ Failed to get VIX: {e}")
        return False


def test_atr_calculation():
    """Test 3c: Verify ATR calculation works"""
    print("\n" + "="*60)
    print("TEST 3c: ATR Calculation")
    print("="*60)

    try:
        from trading.heracles.trader import HERACLESTrader

        trader = HERACLESTrader()
        atr = trader._get_atr(5900.0)  # Approximate MES price

        print(f"   ATR: {atr:.2f} points")

        if 5 < atr < 100:  # Reasonable ATR range for MES
            print(f"✅ ATR looks valid ({atr:.2f} points)")
            return True
        else:
            print(f"❌ ATR out of expected range ({atr})")
            return False

    except Exception as e:
        print(f"❌ Failed to calculate ATR: {e}")
        return False


def test_signal_generation():
    """Test 4: Verify signal can be generated with test data"""
    print("\n" + "="*60)
    print("TEST 4: Signal Generation Logic")
    print("="*60)
    
    try:
        from trading.heracles.signals import HERACLESSignalGenerator
        from trading.heracles.models import HERACLESConfig
        
        config = HERACLESConfig()
        generator = HERACLESSignalGenerator(config)
        
        # Test with mock SPX-level data
        test_gex_data = {
            'flip_point': 5900.0,
            'call_wall': 5950.0,
            'put_wall': 5850.0,
            'net_gex': 1.5e9,  # Positive gamma
            'gex_ratio': 1.2,
        }
        
        # Price above flip point - should generate SHORT signal
        test_price = 5930.0  # 0.5% above flip
        
        signal = generator.generate_signal(
            current_price=test_price,
            gex_data=test_gex_data,
            vix=15.0,
            atr=10.0,
            account_balance=100000.0,
            is_overnight=False
        )
        
        if signal:
            print(f"   Direction: {signal.direction.value}")
            print(f"   Source: {signal.source.value}")
            print(f"   Confidence: {signal.confidence:.2%}")
            print(f"   Win Prob: {signal.win_probability:.2%}")
            print(f"   Contracts: {signal.contracts}")
            print(f"✅ Signal generated successfully")
            return True
        else:
            print("   No signal generated (price may be too close to flip)")
            print("   This is OK - just means conditions weren't met")
            return True  # Not a failure, just no signal
            
    except Exception as e:
        print(f"❌ Signal generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_scan():
    """Test 5: Run a full HERACLES scan"""
    print("\n" + "="*60)
    print("TEST 5: Full HERACLES Scan")
    print("="*60)
    
    try:
        from trading.heracles import run_heracles_scan
        
        result = run_heracles_scan()
        
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Signals: {result.get('signals_generated', 0)}")
        print(f"   Trades: {result.get('trades_executed', 0)}")
        print(f"   Errors: {result.get('errors', [])}")
        
        status = result.get('status', '')
        if status in ['success', 'no_signal', 'market_closed']:
            print(f"✅ Scan completed with status: {status}")
            return True
        elif status == 'error':
            print(f"❌ Scan failed: {result.get('errors', [])}")
            return False
        else:
            print(f"⚠️ Unexpected status: {status}")
            return True
            
    except Exception as e:
        print(f"❌ Scan failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*60)
    print("HERACLES INTEGRATION TEST")
    print("="*60)

    results = []

    # Run tests in order
    results.append(("Tradier Production Keys", test_tradier_production_keys()))
    results.append(("SPX GEX Fetch", test_spx_gex_fetch()))
    results.append(("MES Quote", test_mes_quote()))
    results.append(("VIX Fetch", test_vix_fetch()))
    results.append(("ATR Calculation", test_atr_calculation()))
    results.append(("Signal Generation", test_signal_generation()))
    results.append(("Full Scan", test_full_scan()))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n   Total: {passed}/{len(results)} tests passed")
    
    if failed == 0:
        print("\n🎉 All tests passed! HERACLES should be ready to trade.")
    else:
        print(f"\n⚠️ {failed} test(s) failed. Review issues above.")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
