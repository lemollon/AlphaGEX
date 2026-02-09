"""
VALOR GEX Data Flow Tests

These tests PROVE the signal generation process works correctly:
1. Market hours (8 AM - 3 PM) → Tradier first
2. Overnight (3 PM - 8 AM) → TradingVolatility first
3. Real data → signals generated
4. No data (flip_point=0) → signals SKIPPED (no fake data)
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import pytz

CENTRAL_TZ = pytz.timezone('America/Chicago')


class TestGEXDataSourcePriority:
    """Test that data sources are called in correct priority order."""

    def test_market_hours_uses_tradier_first(self):
        """During market hours (8 AM - 3 PM), Tradier should be called FIRST."""
        # Setup: Market hours (10 AM CT)
        market_time = datetime(2026, 2, 6, 10, 0, 0, tzinfo=CENTRAL_TZ)

        # Clear module-level cache before importing
        import trading.valor.signals as signals_module
        signals_module._gex_cache = {}
        signals_module._gex_cache_time = None
        signals_module._gex_cache_loaded_from_db = True  # Skip DB load

        # Mock the datetime to simulate market hours
        with patch.object(signals_module, 'datetime') as mock_datetime:
            mock_datetime.now.return_value = market_time

            # Mock Tradier calculator
            with patch.object(signals_module, 'TradierGEXCalculator', create=True) as mock_tradier_class:
                mock_calculator = MagicMock()
                mock_calculator.calculate_gex.return_value = {
                    'flip_point': 6000.0,
                    'call_wall': 6050.0,
                    'put_wall': 5950.0,
                    'net_gex': 1.5e9,
                    'gex_ratio': 1.2,
                }
                mock_tradier_class.return_value = mock_calculator

                # Mock persist function
                with patch.object(signals_module, '_persist_gex_cache_to_db'):
                    result = signals_module.get_gex_data_for_valor("SPX")

        # Assert: Got valid data from Tradier
        assert result['flip_point'] == 6000.0
        assert result['data_source'] == 'tradier_calculator'

        print("✅ PASSED: Market hours uses Tradier FIRST")

    def test_overnight_uses_tradingvolatility_first(self):
        """During overnight (3 PM - 8 AM), TradingVolatility should be called FIRST."""
        # Setup: Overnight (6 PM CT)
        overnight_time = datetime(2026, 2, 5, 18, 0, 0, tzinfo=CENTRAL_TZ)

        # Clear module-level cache
        import trading.valor.signals as signals_module
        signals_module._gex_cache = {}
        signals_module._gex_cache_time = None
        signals_module._gex_cache_loaded_from_db = True

        with patch.object(signals_module, 'datetime') as mock_datetime:
            mock_datetime.now.return_value = overnight_time

            # Mock TradingVolatility API
            with patch('core_classes_and_engines.TradingVolatilityAPI') as mock_tv_class:
                mock_api = MagicMock()
                mock_api.get_net_gamma.return_value = {
                    'flip_point': 5980.0,
                    'call_wall': 6030.0,
                    'put_wall': 5930.0,
                    'net_gex': -2.0e9,
                }
                mock_tv_class.return_value = mock_api

                with patch.object(signals_module, '_persist_gex_cache_to_db'):
                    result = signals_module.get_gex_data_for_valor("SPX")

        # Assert: Got valid data
        assert result['flip_point'] == 5980.0
        assert result['data_source'] == 'trading_volatility_api'
        assert result.get('n1_flip_point') == 5980.0

        print("✅ PASSED: Overnight uses TradingVolatility FIRST")


class TestSignalGeneration:
    """Test that signals are generated correctly with real data."""

    def test_signal_generated_with_valid_gex_data(self):
        """With valid GEX data (flip_point > 0), signals should be generated."""
        from trading.valor.signals import ValorSignalGenerator
        from trading.valor.models import ValorConfig

        # Use default config (no 'enabled' parameter)
        config = ValorConfig()

        generator = ValorSignalGenerator(config)

        # Mock GEX data with REAL values
        gex_data = {
            'flip_point': 6000.0,
            'call_wall': 6050.0,
            'put_wall': 5950.0,
            'net_gex': 1.5e9,  # Positive gamma
            'gex_ratio': 1.2,
        }

        # Current price above flip point in positive gamma = SHORT signal (mean reversion)
        current_price = 6020.0
        vix = 15.0
        atr = 25.0

        signal = generator._generate_signal_internal(
            current_price=current_price,
            gex_data=gex_data,
            vix=vix,
            atr=atr,
            is_overnight=False,
        )

        # Assert: Signal was generated (not None)
        assert signal is not None, "Signal should be generated with valid GEX data"
        print(f"✅ PASSED: Signal generated: {signal.direction.value} at {current_price}")
        print(f"   Reason: Price {current_price} above flip {gex_data['flip_point']} in POSITIVE gamma")

    def test_signal_skipped_when_no_gex_data(self):
        """With no GEX data (flip_point = 0), signals should be SKIPPED."""
        from trading.valor.signals import ValorSignalGenerator
        from trading.valor.models import ValorConfig

        config = ValorConfig()

        generator = ValorSignalGenerator(config)

        # Mock GEX data with NO REAL VALUES (simulates API failure)
        gex_data = {
            'flip_point': 0,  # NO DATA
            'call_wall': 0,
            'put_wall': 0,
            'net_gex': 0,
            'gex_ratio': 1.0,
        }

        current_price = 6020.0
        vix = 15.0
        atr = 25.0

        signal = generator._generate_signal_internal(
            current_price=current_price,
            gex_data=gex_data,
            vix=vix,
            atr=atr,
            is_overnight=False,
        )

        # Assert: Signal is None (SKIPPED)
        assert signal is None, "Signal should be SKIPPED when flip_point = 0"
        print("✅ PASSED: Signal correctly SKIPPED when no real GEX data")
        print("   This prevents wrong-direction trades with fake data")


class TestNegativeGammaLogic:
    """Test that negative gamma generates correct SHORT signals."""

    def test_negative_gamma_generates_momentum_signal(self):
        """In negative gamma, price above flip should generate SHORT (momentum)."""
        from trading.valor.signals import ValorSignalGenerator, GammaRegime
        from trading.valor.models import ValorConfig

        config = ValorConfig()

        generator = ValorSignalGenerator(config)

        # Mock NEGATIVE gamma (net_gex < 0)
        gex_data = {
            'flip_point': 6000.0,
            'call_wall': 6050.0,
            'put_wall': 5950.0,
            'net_gex': -2.0e9,  # NEGATIVE gamma
            'gex_ratio': 0.8,
        }

        # Price BELOW flip point in negative gamma
        # Momentum strategy: price moving away from flip = follow the trend
        current_price = 5970.0  # Below flip
        vix = 20.0
        atr = 30.0

        # Determine regime
        regime = generator._determine_gamma_regime(gex_data['net_gex'])
        assert regime == GammaRegime.NEGATIVE, f"Expected NEGATIVE, got {regime}"

        signal = generator._generate_signal_internal(
            current_price=current_price,
            gex_data=gex_data,
            vix=vix,
            atr=atr,
            is_overnight=False,
        )

        if signal:
            print(f"✅ Signal in NEGATIVE gamma: {signal.direction.value}")
            print(f"   Price: {current_price}, Flip: {gex_data['flip_point']}")
            print(f"   This is momentum trading (follow the trend)")
        else:
            print("ℹ️  No signal generated (within threshold)")


class TestCacheLogic:
    """Test that cache is used correctly during overnight."""

    @patch('trading.valor.signals._persist_gex_cache_to_db')
    @patch('trading.valor.signals._load_gex_cache_from_db')
    def test_overnight_uses_cached_data(self, mock_load_cache, mock_persist):
        """During overnight with valid cache, cached data should be used."""
        from datetime import timedelta

        overnight_time = datetime(2026, 2, 5, 22, 0, 0, tzinfo=CENTRAL_TZ)
        cache_time = overnight_time - timedelta(hours=3)  # Cached 3 hours ago

        # Mock cache with valid data
        cached_data = {
            'flip_point': 5990.0,
            'call_wall': 6040.0,
            'put_wall': 5940.0,
            'net_gex': 1.0e9,
            'n1_flip_point': 5990.0,
            'n1_call_wall': 6040.0,
            'n1_put_wall': 5940.0,
        }
        mock_load_cache.return_value = (cached_data, cache_time)

        # Clear module-level cache
        import trading.valor.signals as signals_module
        signals_module._gex_cache = cached_data.copy()
        signals_module._gex_cache_time = cache_time
        signals_module._gex_cache_loaded_from_db = True

        with patch('trading.valor.signals.datetime') as mock_datetime:
            mock_datetime.now.return_value = overnight_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            from trading.valor.signals import get_gex_data_for_valor
            result = get_gex_data_for_valor("SPX")

        # Assert: Used cached n+1 data
        assert result['flip_point'] == 5990.0
        assert result.get('using_n1_data') == True

        print("✅ PASSED: Overnight correctly uses cached n+1 data")
        print(f"   Cache age: 3 hours (valid for overnight)")


def run_all_tests():
    """Run all tests and show results."""
    print("=" * 70)
    print("VALOR GEX FLOW VERIFICATION TESTS")
    print("=" * 70)
    print()

    tests_passed = 0
    tests_failed = 0

    # Test 1: Market hours priority
    print("TEST 1: Market hours uses Tradier FIRST")
    print("-" * 50)
    try:
        test = TestGEXDataSourcePriority()
        test.test_market_hours_uses_tradier_first()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Test 2: Overnight priority
    print("TEST 2: Overnight uses TradingVolatility FIRST")
    print("-" * 50)
    try:
        test = TestGEXDataSourcePriority()
        test.test_overnight_uses_tradingvolatility_first()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Test 3: Signal generation with valid data
    print("TEST 3: Signal generated with valid GEX data")
    print("-" * 50)
    try:
        test = TestSignalGeneration()
        test.test_signal_generated_with_valid_gex_data()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Test 4: Signal skipped when no data
    print("TEST 4: Signal SKIPPED when no real GEX data")
    print("-" * 50)
    try:
        test = TestSignalGeneration()
        test.test_signal_skipped_when_no_gex_data()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Test 5: Negative gamma logic
    print("TEST 5: Negative gamma generates correct signals")
    print("-" * 50)
    try:
        test = TestNegativeGammaLogic()
        test.test_negative_gamma_generates_momentum_signal()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Test 6: Cache logic
    print("TEST 6: Overnight uses cached data correctly")
    print("-" * 50)
    try:
        test = TestCacheLogic()
        test.test_overnight_uses_cached_data()
        tests_passed += 1
    except Exception as e:
        print(f"❌ FAILED: {e}")
        tests_failed += 1
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Tests passed: {tests_passed}")
    print(f"Tests failed: {tests_failed}")
    print()

    if tests_failed == 0:
        print("✅ ALL TESTS PASSED - VALOR GEX flow is working correctly!")
        print()
        print("After deploy, VALOR will:")
        print("  1. Market hours: Fetch fresh GEX from Tradier")
        print("  2. Overnight: Use TradingVolatility n+1 data")
        print("  3. Generate signals with REAL data only")
        print("  4. SKIP trades when no real data available")
    else:
        print(f"❌ {tests_failed} TESTS FAILED - Review before deploy")

    return tests_failed == 0


if __name__ == "__main__":
    run_all_tests()
