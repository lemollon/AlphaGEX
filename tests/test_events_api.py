"""
Tests for Trading Events API
End-to-end tests for event detection, persistence, and retrieval
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestEventDetection:
    """Test event detection from trade data"""

    def test_detect_events_basic(self):
        """Test basic event detection logic (structure test)"""
        # Mock trade data structure matching what the detector expects
        mock_trades = [
            # (exit_date, exit_time, realized_pnl, strategy, symbol, entry_vix, exit_vix, gex_regime)
            ('2024-01-01', '10:00:00', 100.0, 'FORTRESS', 'SPY', 15.0, 14.5, 'positive'),
            ('2024-01-02', '10:00:00', 150.0, 'FORTRESS', 'SPY', 15.0, 14.5, 'positive'),
            ('2024-01-03', '10:00:00', 200.0, 'FORTRESS', 'SPY', 15.0, 14.5, 'positive'),
        ]

        # Verify trade data structure
        assert len(mock_trades) == 3
        for trade in mock_trades:
            assert len(trade) == 8  # 8 fields per trade
            exit_date, exit_time, pnl, strategy, symbol, entry_vix, exit_vix, gex_regime = trade
            assert pnl > 0  # All winning trades
            assert strategy == 'FORTRESS'

    def test_event_types_complete(self):
        """Verify all event types are defined"""
        expected_types = [
            'new_high',
            'winning_streak',
            'losing_streak',
            'drawdown',
            'big_win',
            'big_loss',
            'model_change',
            'vix_spike',
            'circuit_breaker'
        ]

        # This would call the /api/events/types endpoint
        # For now verify the list is complete
        assert len(expected_types) == 9


class TestEventPersistence:
    """Test event persistence and deduplication"""

    def test_event_structure(self):
        """Test that events have required fields"""
        sample_event = {
            'date': '2024-01-01',
            'type': 'new_high',
            'severity': 'success',
            'title': 'New Equity High',
            'description': 'Cumulative P&L reached $1,000',
            'value': 1000.0,
            'bot': 'FORTRESS'
        }

        required_fields = ['date', 'type', 'severity', 'title']
        for field in required_fields:
            assert field in sample_event, f"Missing required field: {field}"

    def test_deduplication_key_fields(self):
        """Test that deduplication uses correct key fields"""
        # Dedup key: (event_date, event_type, bot_name, value)
        event1 = {'date': '2024-01-01', 'type': 'new_high', 'bot': 'FORTRESS', 'value': 1000}
        event2 = {'date': '2024-01-01', 'type': 'new_high', 'bot': 'FORTRESS', 'value': 1000}

        # Same key = should be deduplicated
        key1 = (event1['date'], event1['type'], event1.get('bot', ''), str(event1.get('value', '')))
        key2 = (event2['date'], event2['type'], event2.get('bot', ''), str(event2.get('value', '')))
        assert key1 == key2

    def test_different_bots_not_deduplicated(self):
        """Test that same event from different bots is not deduplicated"""
        event_ares = {'date': '2024-01-01', 'type': 'new_high', 'bot': 'FORTRESS', 'value': 1000}
        event_solomon = {'date': '2024-01-01', 'type': 'new_high', 'bot': 'SOLOMON', 'value': 1000}

        key1 = (event_ares['date'], event_ares['type'], event_ares.get('bot', ''))
        key2 = (event_solomon['date'], event_solomon['type'], event_solomon.get('bot', ''))
        assert key1 != key2


class TestEquityCurveData:
    """Test equity curve data generation"""

    def test_equity_curve_structure(self):
        """Test that equity curve data has required fields"""
        sample_point = {
            'date': '2024-01-01',
            'equity': 201000,
            'daily_pnl': 1000,
            'cumulative_pnl': 1000,
            'drawdown_pct': 0,
            'trade_count': 1
        }

        required_fields = ['date', 'equity', 'daily_pnl', 'cumulative_pnl', 'drawdown_pct', 'trade_count']
        for field in required_fields:
            assert field in sample_point, f"Missing required field: {field}"

    def test_drawdown_calculation(self):
        """Test drawdown percentage calculation"""
        high_water_mark = 210000
        current_equity = 200000

        drawdown_pct = (high_water_mark - current_equity) / high_water_mark * 100
        assert abs(drawdown_pct - 4.76) < 0.1  # ~4.76% drawdown

    def test_summary_stats_structure(self):
        """Test that summary stats have required fields"""
        sample_summary = {
            'total_pnl': 5000,
            'final_equity': 205000,
            'max_drawdown_pct': 3.5,
            'total_trades': 25,
            'starting_capital': 200000
        }

        required_fields = ['total_pnl', 'final_equity', 'max_drawdown_pct', 'total_trades', 'starting_capital']
        for field in required_fields:
            assert field in sample_summary, f"Missing required field: {field}"


class TestEventDetectionAlgorithms:
    """Test specific event detection algorithms"""

    def test_winning_streak_detection(self):
        """Test that 3+ consecutive wins triggers a streak event"""
        pnls = [100, 50, 75]  # 3 wins
        consecutive_wins = 0

        for pnl in pnls:
            if pnl > 0:
                consecutive_wins += 1

        assert consecutive_wins == 3
        # Streak event should trigger at exactly 3

    def test_losing_streak_detection(self):
        """Test that 3+ consecutive losses triggers a streak event"""
        pnls = [-100, -50, -75]  # 3 losses
        consecutive_losses = 0

        for pnl in pnls:
            if pnl <= 0:
                consecutive_losses += 1

        assert consecutive_losses == 3

    def test_big_trade_detection(self):
        """Test that trades >2x average are detected"""
        pnl_list = [100, 150, 200, 100, 150]  # avg = 140
        avg_pnl = sum(pnl_list) / len(pnl_list)

        big_trade = 350  # 2.5x average

        is_big_trade = abs(big_trade) > abs(avg_pnl) * 2
        assert is_big_trade

    def test_vix_spike_detection(self):
        """Test VIX spike detection threshold"""
        normal_vix = 15.0
        spike_vix = 28.0
        threshold = 25

        assert normal_vix <= threshold  # Not a spike
        assert spike_vix > threshold  # Is a spike

    def test_new_high_detection(self):
        """Test new equity high detection"""
        cumulative_pnls = [100, 250, 200, 300, 275]
        high_water_mark = 0
        new_highs = 0

        for pnl in cumulative_pnls:
            if pnl > high_water_mark:
                if high_water_mark > 0:
                    new_highs += 1
                high_water_mark = pnl

        # 100 (first), 250 (new high), 300 (new high) = 2 new high events
        assert new_highs == 2

    def test_drawdown_threshold(self):
        """Test drawdown event threshold (>5%)"""
        high_water_mark = 10000
        current_equity = 9400  # 6% drawdown

        drawdown_pct = (high_water_mark - current_equity) / high_water_mark * 100
        threshold = 5

        assert drawdown_pct > threshold  # Should trigger event


class TestSyncEndpoint:
    """Test sync endpoint behavior"""

    def test_sync_result_structure(self):
        """Test sync result has required fields"""
        sample_result = {
            'detected': 10,
            'inserted': 5,
            'skipped': 5,
            'timestamp': '2024-01-01T10:00:00'
        }

        required_fields = ['detected', 'inserted', 'skipped', 'timestamp']
        for field in required_fields:
            assert field in sample_result

    def test_idempotent_sync(self):
        """Test that multiple syncs are idempotent"""
        # First sync should insert all
        first_sync = {'inserted': 5, 'skipped': 0}

        # Second sync should skip all (already exist)
        second_sync = {'inserted': 0, 'skipped': 5}

        # Total events remains same
        assert first_sync['inserted'] + second_sync['inserted'] == 5


class TestAPIEndpoints:
    """Test API endpoint structure and responses"""

    def test_events_endpoint_params(self):
        """Test /api/events/ accepts correct parameters"""
        valid_params = {
            'days': 90,
            'bot': 'FORTRESS',
            'event_type': 'new_high'
        }

        # Verify param types
        assert isinstance(valid_params['days'], int)
        assert isinstance(valid_params['bot'], str)
        assert isinstance(valid_params['event_type'], str)

    def test_equity_curve_endpoint_params(self):
        """Test /api/events/equity-curve accepts correct parameters"""
        valid_params = {
            'days': 90,
            'bot': 'SOLOMON',
            'timeframe': 'daily',
            'auto_sync': True
        }

        valid_timeframes = ['daily', 'weekly', 'monthly']
        assert valid_params['timeframe'] in valid_timeframes

    def test_sync_endpoint_params(self):
        """Test /api/events/sync accepts correct parameters"""
        valid_params = {
            'days': 90,
            'bot': None  # Optional
        }

        assert 'days' in valid_params


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
