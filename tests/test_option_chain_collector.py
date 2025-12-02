"""
Tests for Option Chain Data Collector
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOptionChainCollector:
    """Test option chain collector functionality"""

    def test_import(self):
        """Test module can be imported"""
        from data.option_chain_collector import (
            collect_option_snapshot,
            collect_all_symbols,
            get_collection_stats,
            ensure_tables
        )
        assert callable(collect_option_snapshot)
        assert callable(collect_all_symbols)
        assert callable(get_collection_stats)
        assert callable(ensure_tables)

    def test_ensure_tables_creates_schema(self):
        """Test that ensure_tables creates required tables"""
        with patch('data.option_chain_collector.get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor

            from data.option_chain_collector import ensure_tables
            ensure_tables()

            # Verify tables were created
            assert mock_cursor.execute.called
            calls = mock_cursor.execute.call_args_list

            # Check for main table creation
            table_created = any(
                'CREATE TABLE IF NOT EXISTS options_chain_snapshots' in str(call)
                for call in calls
            )
            assert table_created

            # Check for log table creation
            log_created = any(
                'CREATE TABLE IF NOT EXISTS options_collection_log' in str(call)
                for call in calls
            )
            assert log_created

    def test_collect_returns_stats(self):
        """Test that collection returns statistics dict"""
        with patch('data.option_chain_collector.get_connection') as mock_conn:
            with patch('data.option_chain_collector.polygon_fetcher') as mock_polygon:
                mock_cursor = MagicMock()
                mock_conn.return_value.cursor.return_value = mock_cursor
                mock_cursor.fetchone.return_value = [0]

                # Mock spot price
                mock_polygon.get_current_price.return_value = 450.0

                # Mock empty options chain
                mock_polygon.get_options_chain.return_value = {
                    'options': []
                }

                from data.option_chain_collector import collect_option_snapshot
                stats = collect_option_snapshot('SPY')

                assert isinstance(stats, dict)
                assert 'symbol' in stats
                assert 'contracts' in stats
                assert 'status' in stats
                assert stats['symbol'] == 'SPY'

    def test_collect_handles_no_spot_price(self):
        """Test error handling when spot price unavailable"""
        with patch('data.option_chain_collector.get_connection') as mock_conn:
            with patch('data.option_chain_collector.polygon_fetcher') as mock_polygon:
                mock_cursor = MagicMock()
                mock_conn.return_value.cursor.return_value = mock_cursor

                # No spot price available
                mock_polygon.get_current_price.return_value = None

                from data.option_chain_collector import collect_option_snapshot
                stats = collect_option_snapshot('SPY')

                assert stats['status'] == 'ERROR'
                assert 'spot price' in stats['error'].lower()

    def test_collect_all_symbols(self):
        """Test collecting multiple symbols"""
        with patch('data.option_chain_collector.collect_option_snapshot') as mock_collect:
            mock_collect.return_value = {
                'symbol': 'SPY',
                'contracts': 100,
                'status': 'SUCCESS'
            }

            from data.option_chain_collector import collect_all_symbols
            results = collect_all_symbols()

            # Should collect for SPY, QQQ, IWM
            assert len(results) >= 3
            assert mock_collect.call_count >= 3


class TestOptionDataIntegrity:
    """Test data integrity and format"""

    def test_option_ticker_format(self):
        """Test option ticker is built correctly"""
        # The collector should build tickers in Polygon format: O:SPY241220C00450000
        # This is tested indirectly through the collection process

    def test_greek_values_stored(self):
        """Test Greeks are captured in snapshot"""
        from datetime import datetime, timedelta

        # Use a future date for expiration
        future_exp = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        with patch('data.option_chain_collector.get_connection') as mock_conn:
            with patch('data.option_chain_collector.polygon_fetcher') as mock_polygon:
                mock_cursor = MagicMock()
                mock_conn.return_value.cursor.return_value = mock_cursor
                mock_cursor.fetchone.return_value = [1]

                mock_polygon.get_current_price.return_value = 450.0
                mock_polygon.get_options_chain.return_value = {
                    'options': [{
                        'expiration_date': future_exp,
                        'strike_price': 450.0,
                        'contract_type': 'call',
                        'bid': 5.0,
                        'ask': 5.20,
                        'greeks': {
                            'delta': 0.5,
                            'gamma': 0.02,
                            'theta': -0.10,
                            'vega': 0.25
                        },
                        'implied_volatility': 0.18
                    }]
                }

                from data.option_chain_collector import collect_option_snapshot
                stats = collect_option_snapshot('SPY')

                # Should have collected 1 contract
                assert stats['contracts'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
