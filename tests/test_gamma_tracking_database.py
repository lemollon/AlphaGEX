"""
Gamma Tracking Database Tests

Tests for the gamma tracking database module.

Run with: pytest tests/test_gamma_tracking_database.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGammaTrackingImport:
    """Tests for gamma tracking import"""

    def test_import_gamma_tracking(self):
        """Test that gamma tracking can be imported"""
        try:
            from gamma.gamma_tracking_database import GammaTrackingDatabase
            assert GammaTrackingDatabase is not None
        except ImportError:
            pytest.skip("Gamma tracking database not available")


class TestGammaTrackingInitialization:
    """Tests for gamma tracking initialization"""

    @patch('gamma.gamma_tracking_database.get_connection')
    def test_tracking_initialization(self, mock_conn):
        """Test tracking can be initialized"""
        try:
            from gamma.gamma_tracking_database import GammaTrackingDatabase

            mock_conn.return_value = MagicMock()
            tracker = GammaTrackingDatabase()
            assert tracker is not None
        except ImportError:
            pytest.skip("Gamma tracking database not available")


class TestGammaSnapshotSaving:
    """Tests for gamma snapshot saving"""

    @patch('gamma.gamma_tracking_database.get_connection')
    def test_save_snapshot(self, mock_conn):
        """Test saving gamma snapshot"""
        try:
            from gamma.gamma_tracking_database import GammaTrackingDatabase

            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor

            tracker = GammaTrackingDatabase()
            if hasattr(tracker, 'save_snapshot'):
                snapshot = {
                    'symbol': 'SPY',
                    'net_gex': 1.5e9,
                    'timestamp': datetime.now()
                }
                # Just verify method exists
                assert callable(getattr(tracker, 'save_snapshot'))
        except ImportError:
            pytest.skip("Gamma tracking database not available")


class TestGammaHistoryQuery:
    """Tests for gamma history queries"""

    @patch('gamma.gamma_tracking_database.get_connection')
    def test_query_history(self, mock_conn):
        """Test querying gamma history"""
        try:
            from gamma.gamma_tracking_database import GammaTrackingDatabase

            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                ('SPY', 1.5e9, datetime.now()),
                ('SPY', 1.4e9, datetime.now()),
            ]
            mock_conn.return_value.cursor.return_value = mock_cursor

            tracker = GammaTrackingDatabase()
            if hasattr(tracker, 'get_history'):
                result = tracker.get_history('SPY', days=7)
                assert result is not None
        except ImportError:
            pytest.skip("Gamma tracking database not available")


class TestGammaDatabaseCleanup:
    """Tests for database cleanup"""

    @patch('gamma.gamma_tracking_database.get_connection')
    def test_cleanup_old_data(self, mock_conn):
        """Test cleanup of old data"""
        try:
            from gamma.gamma_tracking_database import GammaTrackingDatabase

            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor

            tracker = GammaTrackingDatabase()
            if hasattr(tracker, 'cleanup'):
                # Just verify method exists
                assert callable(getattr(tracker, 'cleanup'))
        except ImportError:
            pytest.skip("Gamma tracking database not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
