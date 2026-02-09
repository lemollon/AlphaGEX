"""
Comprehensive tests for FORTRESS Tradier integration.
Tests dual submission to AlphaGEX and Tradier sandbox.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestARESInitialization(unittest.TestCase):
    """Test FORTRESS initializes with dual Tradier clients."""

    @patch('unified_config.APIConfig')
    @patch('trading.fortress_v2.TradierDataFetcher')
    @patch('trading.fortress_v2.TRADIER_AVAILABLE', True)
    def test_paper_mode_creates_both_clients(self, mock_tradier_class, mock_config):
        """PAPER mode should create both production and sandbox clients."""
        # Configure mock APIConfig
        mock_config.TRADIER_API_KEY = 'test_key'
        mock_config.TRADIER_ACCOUNT_ID = 'test_account'
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None

        # Create mock instances
        mock_prod = MagicMock()
        mock_prod.sandbox = False
        mock_sandbox = MagicMock()
        mock_sandbox.sandbox = True
        mock_tradier_class.side_effect = [mock_prod, mock_sandbox]

        from trading.fortress_v2 import FortressTrader, TradingMode
        fortress = FortressTrader(mode=TradingMode.PAPER, initial_capital=200000)

        # Verify both clients created
        self.assertEqual(mock_tradier_class.call_count, 2)

        # First call should be production (sandbox=False)
        first_call = mock_tradier_class.call_args_list[0]
        self.assertEqual(first_call.kwargs.get('sandbox'), False)

        # Second call should be sandbox (sandbox=True)
        second_call = mock_tradier_class.call_args_list[1]
        self.assertEqual(second_call.kwargs.get('sandbox'), True)

        print("✓ PAPER mode creates both production and sandbox clients")


class TestSPYScaling(unittest.TestCase):
    """Test SPY strike and credit scaling."""

    def test_strike_scaling(self):
        """SPX strikes should scale to SPY correctly (÷10)."""
        spx_strikes = {
            'put_long_strike': 5980,
            'put_short_strike': 5990,
            'call_short_strike': 6010,
            'call_long_strike': 6020,
            'total_credit': 3.50
        }

        # Scale to SPY (same logic as in execute_iron_condor)
        spy_put_long = int(round(spx_strikes['put_long_strike'] / 10, 0))
        spy_put_short = int(round(spx_strikes['put_short_strike'] / 10, 0))
        spy_call_short = int(round(spx_strikes['call_short_strike'] / 10, 0))
        spy_call_long = int(round(spx_strikes['call_long_strike'] / 10, 0))
        spy_credit = max(0.10, round(spx_strikes['total_credit'] / 10, 2))

        self.assertEqual(spy_put_long, 598)
        self.assertEqual(spy_put_short, 599)
        self.assertEqual(spy_call_short, 601)
        self.assertEqual(spy_call_long, 602)
        self.assertEqual(spy_credit, 0.35)

        print(f"✓ SPX {spx_strikes['put_long_strike']}/{spx_strikes['put_short_strike']}P → SPY {spy_put_long}/{spy_put_short}P")
        print(f"✓ SPX {spx_strikes['call_short_strike']}/{spx_strikes['call_long_strike']}C → SPY {spy_call_short}/{spy_call_long}C")
        print(f"✓ Credit ${spx_strikes['total_credit']:.2f} → ${spy_credit:.2f}")

    def test_minimum_credit_floor(self):
        """Credit should have $0.10 minimum."""
        # Very small SPX credit
        spx_credit = 0.50  # Would be $0.05 scaled
        spy_credit = max(0.10, round(spx_credit / 10, 2))

        self.assertEqual(spy_credit, 0.10)  # Should be floored to $0.10
        print("✓ Minimum credit floor of $0.10 applied")

    def test_integer_strikes(self):
        """SPY strikes should be integers, not floats."""
        spx_strike = 5985  # Not evenly divisible by 10
        spy_strike = int(round(spx_strike / 10, 0))

        self.assertIsInstance(spy_strike, int)
        self.assertEqual(spy_strike, 598)  # 598.5 rounds to 598 (banker's rounding)
        print(f"✓ SPX {spx_strike} → SPY {spy_strike} (integer)")

        # Test another case that rounds up
        spx_strike2 = 5986
        spy_strike2 = int(round(spx_strike2 / 10, 0))
        self.assertEqual(spy_strike2, 599)  # 598.6 rounds to 599
        print(f"✓ SPX {spx_strike2} → SPY {spy_strike2} (integer)")


class TestExecuteIronCondor(unittest.TestCase):
    """Test the execute_iron_condor method."""

    def setUp(self):
        """Set up mocks for each test."""
        self.ic_strikes = {
            'put_long_strike': 5980,
            'put_short_strike': 5990,
            'call_short_strike': 6010,
            'call_long_strike': 6020,
            'total_credit': 3.50,
            'put_credit': 1.75,
            'call_credit': 1.75
        }
        self.market_data = {
            'underlying_price': 6000,
            'vix': 18.5,
            'expected_move': 50
        }
        self.expiration = '2024-12-10'
        self.contracts = 2

    @patch('unified_config.APIConfig')
    @patch('trading.fortress_v2.TradierDataFetcher')
    @patch('trading.fortress_v2.TRADIER_AVAILABLE', True)
    def test_paper_mode_submits_to_both(self, mock_tradier_class, mock_config):
        """PAPER mode should submit to AlphaGEX AND Tradier sandbox."""
        mock_config.TRADIER_API_KEY = 'test_key'
        mock_config.TRADIER_ACCOUNT_ID = 'test_account'
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None

        # Create mock clients
        mock_prod = MagicMock()
        mock_prod.sandbox = False
        mock_prod.get_quote.return_value = {'last': 6000}

        mock_sandbox = MagicMock()
        mock_sandbox.sandbox = True
        mock_sandbox.place_iron_condor.return_value = {
            'order': {'id': 'SANDBOX-123', 'status': 'pending'}
        }

        mock_tradier_class.side_effect = [mock_prod, mock_sandbox]

        from trading.fortress_v2 import FortressTrader, TradingMode
        fortress = FortressTrader(mode=TradingMode.PAPER, initial_capital=200000)

        # Execute trade
        position = fortress.execute_iron_condor(
            ic_strikes=self.ic_strikes,
            contracts=self.contracts,
            expiration=self.expiration,
            market_data=self.market_data
        )

        # Verify position created (AlphaGEX tracking)
        self.assertIsNotNone(position)
        self.assertEqual(position.contracts, self.contracts)
        print("✓ AlphaGEX position created")

        # Verify sandbox was called with SPY
        mock_sandbox.place_iron_condor.assert_called_once()
        call_kwargs = mock_sandbox.place_iron_condor.call_args.kwargs

        self.assertEqual(call_kwargs['symbol'], 'SPY')
        self.assertEqual(call_kwargs['put_long'], 598)
        self.assertEqual(call_kwargs['put_short'], 599)
        self.assertEqual(call_kwargs['call_short'], 601)
        self.assertEqual(call_kwargs['call_long'], 602)
        self.assertEqual(call_kwargs['quantity'], 2)
        self.assertEqual(call_kwargs['limit_price'], 0.35)
        print("✓ Tradier sandbox called with correct SPY parameters")

    @patch('unified_config.APIConfig')
    @patch('trading.fortress_v2.TradierDataFetcher')
    @patch('trading.fortress_v2.TRADIER_AVAILABLE', True)
    def test_sandbox_error_doesnt_fail_trade(self, mock_tradier_class, mock_config):
        """Sandbox errors should be logged but not fail the trade."""
        mock_config.TRADIER_API_KEY = 'test_key'
        mock_config.TRADIER_ACCOUNT_ID = 'test_account'
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None

        mock_prod = MagicMock()
        mock_prod.sandbox = False

        mock_sandbox = MagicMock()
        mock_sandbox.sandbox = True
        mock_sandbox.place_iron_condor.return_value = {
            'errors': {'error': 'Insufficient buying power'}
        }

        mock_tradier_class.side_effect = [mock_prod, mock_sandbox]

        from trading.fortress_v2 import FortressTrader, TradingMode
        fortress = FortressTrader(mode=TradingMode.PAPER, initial_capital=200000)

        # Execute trade - should NOT raise exception
        position = fortress.execute_iron_condor(
            ic_strikes=self.ic_strikes,
            contracts=self.contracts,
            expiration=self.expiration,
            market_data=self.market_data
        )

        # AlphaGEX position should still be created
        self.assertIsNotNone(position)
        print("✓ Sandbox error logged but trade still tracked in AlphaGEX")

    @patch('unified_config.APIConfig')
    @patch('trading.fortress_v2.TradierDataFetcher')
    @patch('trading.fortress_v2.TRADIER_AVAILABLE', True)
    def test_sandbox_exception_doesnt_fail_trade(self, mock_tradier_class, mock_config):
        """Sandbox exceptions should be caught and logged."""
        mock_config.TRADIER_API_KEY = 'test_key'
        mock_config.TRADIER_ACCOUNT_ID = 'test_account'
        mock_config.TRADIER_SANDBOX_API_KEY = None
        mock_config.TRADIER_SANDBOX_ACCOUNT_ID = None

        mock_prod = MagicMock()
        mock_prod.sandbox = False

        mock_sandbox = MagicMock()
        mock_sandbox.sandbox = True
        mock_sandbox.place_iron_condor.side_effect = Exception("Network error")

        mock_tradier_class.side_effect = [mock_prod, mock_sandbox]

        from trading.fortress_v2 import FortressTrader, TradingMode
        fortress = FortressTrader(mode=TradingMode.PAPER, initial_capital=200000)

        # Execute trade - should NOT raise exception
        position = fortress.execute_iron_condor(
            ic_strikes=self.ic_strikes,
            contracts=self.contracts,
            expiration=self.expiration,
            market_data=self.market_data
        )

        # AlphaGEX position should still be created
        self.assertIsNotNone(position)
        print("✓ Sandbox exception caught, trade still tracked in AlphaGEX")


class TestOCCSymbolFormat(unittest.TestCase):
    """Test OCC option symbol generation."""

    def test_spy_symbol_format(self):
        """SPY option symbols should be correctly formatted."""
        # Expected format: SPY + YYMMDD + C/P + strike*1000 (8 digits)
        # Example: SPY241210P00598000

        symbol = "SPY"
        expiration = "2024-12-10"
        strike = 598

        from datetime import datetime
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        exp_str = exp_date.strftime('%y%m%d')  # 241210
        strike_str = f"{int(strike * 1000):08d}"  # 00598000

        expected_put = f"SPY{exp_str}P{strike_str}"  # SPY241210P00598000
        expected_call = f"SPY{exp_str}C{strike_str}"  # SPY241210C00598000

        self.assertEqual(expected_put, "SPY241210P00598000")
        self.assertEqual(expected_call, "SPY241210C00598000")
        print(f"✓ Put symbol: {expected_put}")
        print(f"✓ Call symbol: {expected_call}")


class TestCredentialFallback(unittest.TestCase):
    """Test credential fallback logic."""

    def test_fallback_to_production_credentials(self):
        """Should use production credentials if sandbox-specific not set."""
        prod_key = "prod_api_key"
        prod_account = "prod_account_id"
        sandbox_key = None
        sandbox_account = None

        # This is the fallback logic from the code
        final_key = sandbox_key or prod_key
        final_account = sandbox_account or prod_account

        self.assertEqual(final_key, prod_key)
        self.assertEqual(final_account, prod_account)
        print("✓ Falls back to production credentials when sandbox not set")

    def test_uses_sandbox_credentials_when_set(self):
        """Should use sandbox credentials when explicitly set."""
        prod_key = "prod_api_key"
        prod_account = "prod_account_id"
        sandbox_key = "sandbox_api_key"
        sandbox_account = "sandbox_account_id"

        final_key = sandbox_key or prod_key
        final_account = sandbox_account or prod_account

        self.assertEqual(final_key, sandbox_key)
        self.assertEqual(final_account, sandbox_account)
        print("✓ Uses sandbox credentials when explicitly set")


def run_tests():
    """Run all tests with verbose output."""
    print("=" * 60)
    print("FORTRESS TRADIER INTEGRATION TESTS")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSPYScaling))
    suite.addTests(loader.loadTestsFromTestCase(TestOCCSymbolFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestCredentialFallback))
    suite.addTests(loader.loadTestsFromTestCase(TestARESInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestExecuteIronCondor))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("ALL TESTS PASSED ✓")
    else:
        print(f"FAILURES: {len(result.failures)}, ERRORS: {len(result.errors)}")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
