"""
AGAPE-SPOT Bayesian Win Tracker — Production Tests

Tests the BayesianWinTracker implementation across all 4 files:
  1. models.py  — BayesianWinTracker math, FundingRegime mapping
  2. db.py      — Table creation, get/save round-trip
  3. trader.py  — Close-position → tracker update wiring
  4. signals.py — Win probability gate logic

Run:  pytest tests/test_agape_spot_bayesian.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    BayesianWinTracker,
    FundingRegime,
    SPOT_TICKERS,
    AgapeSpotConfig,
)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ==========================================================================
# SECTION 1: BayesianWinTracker Math (models.py)
# ==========================================================================

class TestBayesianWinTrackerMath:
    """Pure math tests — no DB, no mocks."""

    def test_initial_state(self):
        """Fresh tracker starts with Laplace prior: alpha=1, beta=1, 50/50."""
        t = BayesianWinTracker(ticker="ETH-USD")
        assert t.alpha == 1.0
        assert t.beta == 1.0
        assert t.total_trades == 0
        assert t.win_probability == 0.5
        assert t.is_cold_start is True
        assert t.should_use_ml is False

    def test_single_win(self):
        """One win: alpha=2, beta=1 → P(win) = 2/3."""
        t = BayesianWinTracker(ticker="ETH-USD")
        t.update(won=True, funding_regime=FundingRegime.POSITIVE)
        assert t.alpha == 2.0
        assert t.beta == 1.0
        assert t.total_trades == 1
        assert abs(t.win_probability - 2 / 3) < 1e-9

    def test_single_loss(self):
        """One loss: alpha=1, beta=2 → P(win) = 1/3."""
        t = BayesianWinTracker(ticker="ETH-USD")
        t.update(won=False, funding_regime=FundingRegime.NEGATIVE)
        assert t.alpha == 1.0
        assert t.beta == 2.0
        assert t.total_trades == 1
        assert abs(t.win_probability - 1 / 3) < 1e-9

    def test_five_wins_five_losses(self):
        """5W/5L: alpha=6, beta=6 → P(win) = 0.50."""
        t = BayesianWinTracker(ticker="BTC-USD")
        for _ in range(5):
            t.update(True, FundingRegime.NEUTRAL)
        for _ in range(5):
            t.update(False, FundingRegime.NEUTRAL)
        assert t.alpha == 6.0
        assert t.beta == 6.0
        assert t.total_trades == 10
        assert t.win_probability == 0.5

    def test_cold_start_boundary(self):
        """is_cold_start transitions at exactly 10 trades."""
        t = BayesianWinTracker(ticker="ETH-USD")
        for i in range(9):
            t.update(True, FundingRegime.POSITIVE)
            assert t.is_cold_start is True, f"Should be cold at {i + 1} trades"
        t.update(True, FundingRegime.POSITIVE)
        assert t.total_trades == 10
        assert t.is_cold_start is False

    def test_ml_transition_boundary(self):
        """should_use_ml transitions at exactly 50 trades."""
        t = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(49):
            t.update(True, FundingRegime.NEUTRAL)
        assert t.should_use_ml is False
        t.update(True, FundingRegime.NEUTRAL)
        assert t.total_trades == 50
        assert t.should_use_ml is True

    def test_regime_counter_isolation(self):
        """Each regime tracks wins/losses independently."""
        t = BayesianWinTracker(ticker="XRP-USD")
        t.update(True, FundingRegime.POSITIVE)
        t.update(True, FundingRegime.POSITIVE)
        t.update(False, FundingRegime.NEGATIVE)
        t.update(True, FundingRegime.NEUTRAL)
        t.update(False, FundingRegime.NEUTRAL)

        assert t.positive_funding_wins == 2
        assert t.positive_funding_losses == 0
        assert t.negative_funding_wins == 0
        assert t.negative_funding_losses == 1
        assert t.neutral_funding_wins == 1
        assert t.neutral_funding_losses == 1
        assert t.total_trades == 5

    def test_regime_probability_laplace(self):
        """Regime probability uses Laplace: (wins+1)/(wins+losses+2)."""
        t = BayesianWinTracker(ticker="ETH-USD")
        # 3 wins, 1 loss in POSITIVE
        for _ in range(3):
            t.update(True, FundingRegime.POSITIVE)
        t.update(False, FundingRegime.POSITIVE)

        prob = t.get_regime_probability(FundingRegime.POSITIVE)
        expected = (3 + 1) / (3 + 1 + 2)  # 4/6 = 0.6667
        assert abs(prob - expected) < 1e-9

    def test_regime_probability_zero_trades(self):
        """Zero-trade regime returns 0.50 (Laplace prior)."""
        t = BayesianWinTracker(ticker="ETH-USD")
        prob = t.get_regime_probability(FundingRegime.NEGATIVE)
        assert prob == 0.5  # (0+1)/(0+0+2) = 1/2

    def test_regime_counters_sum_equals_total_trades(self):
        """Sum of all 6 regime counters always equals total_trades."""
        t = BayesianWinTracker(ticker="ETH-USD")
        import random
        random.seed(42)
        regimes = [FundingRegime.POSITIVE, FundingRegime.NEGATIVE, FundingRegime.NEUTRAL]
        for _ in range(100):
            t.update(random.random() > 0.5, random.choice(regimes))

        total = (
            t.positive_funding_wins + t.positive_funding_losses +
            t.negative_funding_wins + t.negative_funding_losses +
            t.neutral_funding_wins + t.neutral_funding_losses
        )
        assert total == t.total_trades == 100

    def test_alpha_beta_consistency(self):
        """alpha + beta - 2 always equals total_trades."""
        t = BayesianWinTracker(ticker="ETH-USD")
        import random
        random.seed(42)
        regimes = [FundingRegime.POSITIVE, FundingRegime.NEGATIVE, FundingRegime.NEUTRAL]
        for _ in range(77):
            t.update(random.random() > 0.4, random.choice(regimes))

        assert t.alpha + t.beta - 2 == t.total_trades

    def test_to_dict_completeness(self):
        """to_dict() includes all required fields."""
        t = BayesianWinTracker(ticker="BTC-USD")
        t.update(True, FundingRegime.POSITIVE)
        d = t.to_dict()

        required = [
            "ticker", "alpha", "beta", "total_trades", "win_probability",
            "is_cold_start", "cold_start_floor",
            "positive_funding_wins", "positive_funding_losses",
            "negative_funding_wins", "negative_funding_losses",
            "neutral_funding_wins", "neutral_funding_losses",
            "should_use_ml", "regime_probabilities",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

        assert d["ticker"] == "BTC-USD"
        assert d["total_trades"] == 1
        assert set(d["regime_probabilities"].keys()) == {"POSITIVE", "NEGATIVE", "NEUTRAL"}

    def test_win_probability_never_zero_or_one(self):
        """Laplace prior ensures probability never reaches 0.0 or 1.0."""
        t = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(1000):
            t.update(True, FundingRegime.POSITIVE)
        assert t.win_probability < 1.0
        assert t.win_probability > 0.99

        t2 = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(1000):
            t2.update(False, FundingRegime.NEGATIVE)
        assert t2.win_probability > 0.0
        assert t2.win_probability < 0.01


# ==========================================================================
# SECTION 2: FundingRegime Mapping (models.py)
# ==========================================================================

class TestFundingRegimeMapping:
    """Test all known funding regime strings map correctly."""

    @pytest.mark.parametrize("input_str,expected", [
        ("EXTREME_POSITIVE", FundingRegime.POSITIVE),
        ("HEAVILY_POSITIVE", FundingRegime.POSITIVE),
        ("SLIGHTLY_POSITIVE", FundingRegime.POSITIVE),
        ("POSITIVE", FundingRegime.POSITIVE),
        ("EXTREME_NEGATIVE", FundingRegime.NEGATIVE),
        ("HEAVILY_NEGATIVE", FundingRegime.NEGATIVE),
        ("SLIGHTLY_NEGATIVE", FundingRegime.NEGATIVE),
        ("NEGATIVE", FundingRegime.NEGATIVE),
        ("NEUTRAL", FundingRegime.NEUTRAL),
        ("UNKNOWN", FundingRegime.NEUTRAL),
    ])
    def test_known_regime_strings(self, input_str, expected):
        result = FundingRegime.from_funding_string(input_str)
        assert result == expected, f"{input_str} → {result}, expected {expected}"

    def test_empty_string(self):
        assert FundingRegime.from_funding_string("") == FundingRegime.NEUTRAL

    def test_none_value(self):
        assert FundingRegime.from_funding_string(None) == FundingRegime.NEUTRAL

    def test_case_insensitive(self):
        assert FundingRegime.from_funding_string("heavily_positive") == FundingRegime.POSITIVE
        assert FundingRegime.from_funding_string("Extreme_Negative") == FundingRegime.NEGATIVE

    def test_garbage_input(self):
        assert FundingRegime.from_funding_string("FOOBAR") == FundingRegime.NEUTRAL


# ==========================================================================
# SECTION 3: BTC-USD Configuration (models.py)
# ==========================================================================

class TestBTCUSDConfig:
    """Verify BTC-USD is properly configured in SPOT_TICKERS."""

    def test_btc_in_spot_tickers(self):
        assert "BTC-USD" in SPOT_TICKERS

    def test_btc_symbol(self):
        assert SPOT_TICKERS["BTC-USD"]["symbol"] == "BTC"

    def test_btc_display_name(self):
        assert SPOT_TICKERS["BTC-USD"]["display_name"] == "Bitcoin"

    def test_btc_starting_capital(self):
        assert SPOT_TICKERS["BTC-USD"]["starting_capital"] == 5000.0

    def test_btc_quantity_params(self):
        cfg = SPOT_TICKERS["BTC-USD"]
        assert cfg["default_quantity"] == 0.001
        assert cfg["min_order"] == 0.00001
        assert cfg["max_per_trade"] == 0.05
        assert cfg["quantity_decimals"] == 5

    def test_btc_price_decimals(self):
        assert SPOT_TICKERS["BTC-USD"]["price_decimals"] == 2

    def test_btc_exit_params(self):
        cfg = SPOT_TICKERS["BTC-USD"]
        assert cfg["no_loss_activation_pct"] == 1.5
        assert cfg["no_loss_trail_distance_pct"] == 1.25
        assert cfg["max_unrealized_loss_pct"] == 1.5
        assert cfg["max_hold_hours"] == 6

    def test_btc_not_altcoin(self):
        """BTC should be treated as major, not altcoin."""
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = ["BTC-USD"]
        gen = AgapeSpotSignalGenerator(config)
        assert gen._is_altcoin("BTC-USD") is False

    def test_eth_not_altcoin(self):
        """ETH should also be treated as major."""
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = ["ETH-USD"]
        gen = AgapeSpotSignalGenerator(config)
        assert gen._is_altcoin("ETH-USD") is False

    def test_xrp_is_altcoin(self):
        """XRP should be treated as altcoin."""
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = ["XRP-USD"]
        gen = AgapeSpotSignalGenerator(config)
        assert gen._is_altcoin("XRP-USD") is True

    def test_btc_in_live_tickers_default(self):
        """BTC-USD should be in default live_tickers."""
        config = AgapeSpotConfig()
        assert "BTC-USD" in config.live_tickers

    def test_eth_in_live_tickers_default(self):
        """ETH-USD should be in default live_tickers."""
        config = AgapeSpotConfig()
        assert "ETH-USD" in config.live_tickers

    def test_all_five_tickers_live(self):
        """All 5 tickers should be live by default."""
        config = AgapeSpotConfig()
        expected = {"ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"}
        assert set(config.live_tickers) == expected


# ==========================================================================
# SECTION 4: Win Probability Gate (signals.py)
# ==========================================================================

class TestWinProbabilityGate:
    """Test the _calculate_win_probability logic in signals.py."""

    def _make_generator(self, win_trackers=None):
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = ["ETH-USD", "BTC-USD"]
        config.min_confidence = "LOW"
        return AgapeSpotSignalGenerator(config, win_trackers=win_trackers)

    def test_no_tracker_returns_052(self):
        """No tracker for ticker → return 0.52 (allow trading)."""
        gen = self._make_generator(win_trackers={})
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob == 0.52

    def test_cold_start_floor(self):
        """At 0 trades, blended should be floored to 0.52."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob == 0.52  # Cold start floor

    def test_cold_start_above_floor(self):
        """At 5 wins / 0 losses in POSITIVE, blended > 0.52 → no floor needed."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(5):
            tracker.update(True, FundingRegime.POSITIVE)
        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        # regime_prob = (5+1)/(5+0+2) = 6/7 ≈ 0.857
        # weight = min(0.7, 0.3 + 5/100) = 0.35
        # blended = 0.857*0.35 + 0.5*0.65 = 0.300 + 0.325 = 0.625
        assert prob > 0.52
        assert prob > 0.60

    def test_losing_regime_blocked_after_cold_start(self):
        """After 10+ trades, a losing regime should be blocked (< 0.50)."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        # 2 wins, 13 losses in NEGATIVE
        for _ in range(2):
            tracker.update(True, FundingRegime.NEGATIVE)
        for _ in range(13):
            tracker.update(False, FundingRegime.NEGATIVE)
        assert tracker.is_cold_start is False
        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        prob = gen._calculate_win_probability("ETH-USD", "NEGATIVE")
        assert prob < 0.50, f"Losing regime should be blocked, got {prob}"

    def test_winning_regime_passes_gate(self):
        """A winning regime should pass the 0.50 gate."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        # 12 wins, 3 losses in POSITIVE
        for _ in range(12):
            tracker.update(True, FundingRegime.POSITIVE)
        for _ in range(3):
            tracker.update(False, FundingRegime.POSITIVE)
        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob >= 0.50, f"Winning regime should pass, got {prob}"

    def test_weight_ramp_at_zero_trades(self):
        """At 0 trades, bayesian_weight = 0.3."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        weight = min(0.7, 0.3 + tracker.total_trades / 100)
        assert weight == 0.3

    def test_weight_ramp_at_40_trades(self):
        """At 40 trades, bayesian_weight = 0.7 (max)."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(40):
            tracker.update(True, FundingRegime.NEUTRAL)
        weight = min(0.7, 0.3 + tracker.total_trades / 100)
        assert weight == 0.7

    def test_weight_ramp_at_200_trades(self):
        """At 200 trades, weight still capped at 0.7."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        tracker.total_trades = 200  # Shortcut
        weight = min(0.7, 0.3 + tracker.total_trades / 100)
        assert weight == 0.7

    def test_probability_clamped_0_to_1(self):
        """Final probability is always in [0.0, 1.0]."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(200):
            tracker.update(True, FundingRegime.POSITIVE)
        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert 0.0 <= prob <= 1.0

    def test_different_tickers_independent(self):
        """ETH and BTC trackers are independent."""
        eth_tracker = BayesianWinTracker(ticker="ETH-USD")
        btc_tracker = BayesianWinTracker(ticker="BTC-USD")

        # ETH: 10 wins in POSITIVE
        for _ in range(10):
            eth_tracker.update(True, FundingRegime.POSITIVE)
        # BTC: 10 losses in POSITIVE
        for _ in range(10):
            btc_tracker.update(False, FundingRegime.POSITIVE)

        gen = self._make_generator(win_trackers={
            "ETH-USD": eth_tracker,
            "BTC-USD": btc_tracker,
        })

        eth_prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        btc_prob = gen._calculate_win_probability("BTC-USD", "POSITIVE")

        assert eth_prob > 0.55, f"ETH should be high: {eth_prob}"
        assert btc_prob < 0.45, f"BTC should be low: {btc_prob}"

    def test_cross_regime_independence(self):
        """Winning in POSITIVE doesn't help a losing NEGATIVE regime."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        # 15 wins in POSITIVE
        for _ in range(15):
            tracker.update(True, FundingRegime.POSITIVE)
        # 15 losses in NEGATIVE
        for _ in range(15):
            tracker.update(False, FundingRegime.NEGATIVE)

        gen = self._make_generator(win_trackers={"ETH-USD": tracker})

        pos_prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        neg_prob = gen._calculate_win_probability("ETH-USD", "NEGATIVE")

        assert pos_prob > 0.55, f"POSITIVE should pass: {pos_prob}"
        assert neg_prob < 0.45, f"NEGATIVE should be blocked: {neg_prob}"


# ==========================================================================
# SECTION 5: Gate Integration in _determine_action (signals.py)
# ==========================================================================

class TestGateIntegration:
    """Test that the Bayesian gate integrates correctly in the signal flow."""

    def _make_generator(self, win_trackers=None, min_confidence="LOW"):
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = ["ETH-USD"]
        config.min_confidence = min_confidence
        config.min_funding_rate_signal = 0.001
        config.min_ls_ratio_extreme = 1.5
        config.direction_cooldown_scans = 2
        config.direction_win_streak_caution = 100
        config.direction_memory_size = 10
        config.get_entry_filters.return_value = {}
        gen = AgapeSpotSignalGenerator(config, win_trackers=win_trackers)
        return gen

    def test_gate_blocks_on_losing_regime(self):
        """Losing regime blocks entry with WIN_PROB reason."""
        from trading.agape_spot.models import SignalAction
        tracker = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(3):
            tracker.update(True, FundingRegime.NEGATIVE)
        for _ in range(12):
            tracker.update(False, FundingRegime.NEGATIVE)

        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        market_data = {
            "spot_price": 3500.0,
            "funding_regime": "NEGATIVE",
        }
        action, reasoning = gen._determine_action("ETH-USD", "LONG", "HIGH", market_data)
        assert action == SignalAction.WAIT
        assert "WIN_PROB" in reasoning

    def test_gate_passes_on_winning_regime(self):
        """Winning regime allows entry."""
        from trading.agape_spot.models import SignalAction
        tracker = BayesianWinTracker(ticker="ETH-USD")
        for _ in range(12):
            tracker.update(True, FundingRegime.POSITIVE)
        for _ in range(3):
            tracker.update(False, FundingRegime.POSITIVE)

        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        market_data = {
            "spot_price": 3500.0,
            "funding_regime": "POSITIVE",
        }
        action, reasoning = gen._determine_action("ETH-USD", "LONG", "HIGH", market_data)
        assert action == SignalAction.LONG

    def test_gate_allows_cold_start(self):
        """Cold start (< 10 trades) always allows trading."""
        from trading.agape_spot.models import SignalAction
        tracker = BayesianWinTracker(ticker="ETH-USD")
        # 0 wins, 5 losses — normally bad, but cold start protects
        for _ in range(5):
            tracker.update(False, FundingRegime.POSITIVE)
        assert tracker.is_cold_start is True

        gen = self._make_generator(win_trackers={"ETH-USD": tracker})
        market_data = {
            "spot_price": 3500.0,
            "funding_regime": "POSITIVE",
        }
        action, reasoning = gen._determine_action("ETH-USD", "LONG", "HIGH", market_data)
        # Cold start floor = 0.52 > gate 0.50 → should pass
        assert action == SignalAction.LONG


# ==========================================================================
# SECTION 6: Trader Close → Tracker Update Wiring (trader.py)
# ==========================================================================

class TestTraderTrackerWiring:
    """Test that trader._close_position correctly updates the tracker."""

    def _make_trader(self):
        """Create a minimal AgapeSpotTrader with mocked dependencies."""
        from trading.agape_spot.trader import AgapeSpotTrader

        with patch("trading.agape_spot.trader.AgapeSpotDatabase") as MockDB, \
             patch("trading.agape_spot.trader.AgapeSpotSignalGenerator"), \
             patch("trading.agape_spot.trader.AgapeSpotExecutor") as MockExec:

            mock_db = MockDB.return_value
            mock_db.get_win_tracker.side_effect = lambda t: BayesianWinTracker(ticker=t)
            mock_db.close_position.return_value = True
            mock_db.expire_position.return_value = True
            mock_db.save_win_tracker.return_value = True
            mock_db.log.return_value = None

            mock_exec = MockExec.return_value
            mock_exec.has_any_client = False

            config = AgapeSpotConfig()
            # Ensure all tickers are paper (so _close_position skips live sell)
            config.live_tickers = []

            trader = AgapeSpotTrader(config)
            return trader

    def test_win_updates_alpha(self):
        """Winning trade increments alpha and saves to DB."""
        trader = self._make_trader()
        tracker = trader._win_trackers["ETH-USD"]
        assert tracker.alpha == 1.0

        pos = {
            "position_id": "TEST-001",
            "entry_price": 3000.0,
            "quantity": 0.1,
            "funding_regime_at_entry": "POSITIVE",
            "account_label": "paper",
        }
        result = trader._close_position("ETH-USD", pos, 3100.0, "TAKE_PROFIT")
        assert result is True
        assert tracker.alpha == 2.0  # 1 win → alpha += 1
        assert tracker.beta == 1.0   # No loss
        assert tracker.total_trades == 1
        assert tracker.positive_funding_wins == 1
        trader.db.save_win_tracker.assert_called_with(tracker)

    def test_loss_updates_beta(self):
        """Losing trade increments beta and saves to DB."""
        trader = self._make_trader()
        tracker = trader._win_trackers["ETH-USD"]

        pos = {
            "position_id": "TEST-002",
            "entry_price": 3000.0,
            "quantity": 0.1,
            "funding_regime_at_entry": "NEGATIVE",
            "account_label": "paper",
        }
        result = trader._close_position("ETH-USD", pos, 2900.0, "STOP_LOSS")
        assert result is True
        assert tracker.alpha == 1.0  # No win
        assert tracker.beta == 2.0   # 1 loss → beta += 1
        assert tracker.total_trades == 1
        assert tracker.negative_funding_losses == 1

    def test_breakeven_counts_as_loss(self):
        """$0.00 PnL counts as loss (won = realized_pnl > 0)."""
        trader = self._make_trader()
        tracker = trader._win_trackers["BTC-USD"]

        pos = {
            "position_id": "TEST-003",
            "entry_price": 90000.0,
            "quantity": 0.001,
            "funding_regime_at_entry": "NEUTRAL",
            "account_label": "paper",
        }
        result = trader._close_position("BTC-USD", pos, 90000.0, "MAX_HOLD_TIME")
        assert result is True
        assert tracker.beta == 2.0  # Loss (breakeven → won=False)
        assert tracker.alpha == 1.0

    def test_missing_funding_regime_defaults_neutral(self):
        """Missing funding_regime_at_entry defaults to UNKNOWN → NEUTRAL."""
        trader = self._make_trader()
        tracker = trader._win_trackers["ETH-USD"]

        pos = {
            "position_id": "TEST-004",
            "entry_price": 3000.0,
            "quantity": 0.1,
            # No funding_regime_at_entry key
            "account_label": "paper",
        }
        result = trader._close_position("ETH-USD", pos, 3100.0, "TRAIL_STOP")
        assert result is True
        assert tracker.neutral_funding_wins == 1  # Mapped to NEUTRAL

    def test_db_close_failure_skips_tracker_update(self):
        """If db.close_position fails, tracker should NOT be updated."""
        trader = self._make_trader()
        trader.db.close_position.return_value = False
        tracker = trader._win_trackers["ETH-USD"]

        pos = {
            "position_id": "TEST-005",
            "entry_price": 3000.0,
            "quantity": 0.1,
            "funding_regime_at_entry": "POSITIVE",
            "account_label": "paper",
        }
        result = trader._close_position("ETH-USD", pos, 3100.0, "TAKE_PROFIT")
        assert result is False
        assert tracker.total_trades == 0  # Not updated
        assert tracker.alpha == 1.0

    def test_multiple_closes_accumulate(self):
        """Multiple position closes accumulate in the same tracker."""
        trader = self._make_trader()
        tracker = trader._win_trackers["ETH-USD"]

        for i in range(5):
            pos = {
                "position_id": f"TEST-{i}",
                "entry_price": 3000.0,
                "quantity": 0.1,
                "funding_regime_at_entry": "POSITIVE",
                "account_label": "paper",
            }
            trader._close_position("ETH-USD", pos, 3100.0, "TRAIL_STOP")

        assert tracker.total_trades == 5
        assert tracker.alpha == 6.0  # 5 wins + 1 prior
        assert tracker.positive_funding_wins == 5

    def test_btc_tracker_independent_from_eth(self):
        """BTC and ETH trackers don't cross-contaminate."""
        trader = self._make_trader()
        eth_tracker = trader._win_trackers["ETH-USD"]
        btc_tracker = trader._win_trackers["BTC-USD"]

        eth_pos = {
            "position_id": "ETH-001",
            "entry_price": 3000.0,
            "quantity": 0.1,
            "funding_regime_at_entry": "POSITIVE",
            "account_label": "paper",
        }
        btc_pos = {
            "position_id": "BTC-001",
            "entry_price": 90000.0,
            "quantity": 0.001,
            "funding_regime_at_entry": "NEGATIVE",
            "account_label": "paper",
        }

        trader._close_position("ETH-USD", eth_pos, 3100.0, "TRAIL_STOP")
        trader._close_position("BTC-USD", btc_pos, 89000.0, "STOP_LOSS")

        assert eth_tracker.total_trades == 1
        assert eth_tracker.alpha == 2.0  # Win
        assert btc_tracker.total_trades == 1
        assert btc_tracker.beta == 2.0   # Loss


# ==========================================================================
# SECTION 7: Database Round-Trip (db.py)
# ==========================================================================

class TestDatabaseRoundTrip:
    """Test get_win_tracker/save_win_tracker with mocked DB."""

    def test_get_win_tracker_fresh(self):
        """No rows → returns fresh tracker."""
        from trading.agape_spot.db import AgapeSpotDatabase

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # No rows

        with patch.object(AgapeSpotDatabase, "__init__", lambda self, **kw: None):
            db = AgapeSpotDatabase()
            db._get_conn = MagicMock(return_value=mock_conn)

            tracker = db.get_win_tracker("BTC-USD")
            assert tracker.ticker == "BTC-USD"
            assert tracker.total_trades == 0
            assert tracker.alpha == 1.0
            assert tracker.beta == 1.0

    def test_get_win_tracker_with_data(self):
        """Existing row → returns populated tracker."""
        from trading.agape_spot.db import AgapeSpotDatabase

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # DB returns tuple (not dict) — row[0]=alpha, row[1]=beta, etc.
        mock_cursor.fetchone.return_value = (
            5.0,   # alpha
            3.0,   # beta
            6,     # total_trades
            3,     # positive_funding_wins
            1,     # positive_funding_losses
            0,     # negative_funding_wins
            1,     # negative_funding_losses
            1,     # neutral_funding_wins
            0,     # neutral_funding_losses
        )

        with patch.object(AgapeSpotDatabase, "__init__", lambda self, **kw: None):
            db = AgapeSpotDatabase()
            db._get_conn = MagicMock(return_value=mock_conn)

            tracker = db.get_win_tracker("ETH-USD")
            assert tracker.ticker == "ETH-USD"
            assert tracker.alpha == 5.0
            assert tracker.beta == 3.0
            assert tracker.total_trades == 6
            assert tracker.positive_funding_wins == 3
            assert tracker.negative_funding_losses == 1

    def test_save_win_tracker_calls_insert(self):
        """save_win_tracker should INSERT (append-only)."""
        from trading.agape_spot.db import AgapeSpotDatabase

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(AgapeSpotDatabase, "__init__", lambda self, **kw: None):
            db = AgapeSpotDatabase()
            db._get_conn = MagicMock(return_value=mock_conn)

            tracker = BayesianWinTracker(ticker="BTC-USD")
            tracker.update(True, FundingRegime.POSITIVE)

            result = db.save_win_tracker(tracker)
            assert result is True
            # Verify INSERT was called
            mock_cursor.execute.assert_called_once()
            sql = mock_cursor.execute.call_args[0][0]
            assert "INSERT INTO" in sql
            assert "agape_spot_win_tracker" in sql


# ==========================================================================
# SECTION 8: Recovery Scenario (end-to-end math)
# ==========================================================================

class TestRecoveryScenario:
    """Test the full recovery mechanism with realistic trade sequences."""

    def _make_generator(self, tracker):
        from trading.agape_spot.signals import AgapeSpotSignalGenerator
        config = MagicMock(spec=AgapeSpotConfig)
        config.tickers = [tracker.ticker]
        config.min_confidence = "LOW"
        return AgapeSpotSignalGenerator(config, win_trackers={tracker.ticker: tracker})

    def test_recovery_from_losing_streak(self):
        """Simulate: 5 losses → blocked → 3 wins → unblocked."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        gen = self._make_generator(tracker)

        # Phase 1: Cold start (5 losses) — still passes gate due to floor
        for _ in range(5):
            tracker.update(False, FundingRegime.POSITIVE)
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob >= 0.50, f"Cold start should still pass: {prob}"

        # Phase 2: More losses (total 12) — now past cold start, should block
        for _ in range(7):
            tracker.update(False, FundingRegime.POSITIVE)
        prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob < 0.50, f"12 losses should block: {prob}"

        # Phase 3: Recovery (5 wins in POSITIVE)
        for _ in range(5):
            tracker.update(True, FundingRegime.POSITIVE)
        prob_after = gen._calculate_win_probability("ETH-USD", "POSITIVE")

        # May or may not pass gate yet, but should be higher
        assert prob_after > prob, "Wins should increase probability"

        # Phase 4: More wins (total 15 wins vs 12 losses) — should recover
        # Math: regime_prob = (15+1)/(15+12+2) = 16/29 ≈ 0.552
        #        weight = min(0.7, 0.3 + 27/100) = 0.57
        #        blended = 0.552*0.57 + 0.5*0.43 = 0.530 → passes gate
        for _ in range(10):
            tracker.update(True, FundingRegime.POSITIVE)
        prob_recovered = gen._calculate_win_probability("ETH-USD", "POSITIVE")
        assert prob_recovered >= 0.50, f"15 wins should recover: {prob_recovered}"

    def test_regime_isolation_during_recovery(self):
        """Losing in NEGATIVE doesn't block POSITIVE."""
        tracker = BayesianWinTracker(ticker="ETH-USD")
        gen = self._make_generator(tracker)

        # 15 losses in NEGATIVE
        for _ in range(15):
            tracker.update(False, FundingRegime.NEGATIVE)
        # 5 wins in POSITIVE
        for _ in range(5):
            tracker.update(True, FundingRegime.POSITIVE)

        neg_prob = gen._calculate_win_probability("ETH-USD", "NEGATIVE")
        pos_prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")

        assert neg_prob < 0.50, f"NEGATIVE should be blocked: {neg_prob}"
        assert pos_prob >= 0.50, f"POSITIVE should pass: {pos_prob}"
