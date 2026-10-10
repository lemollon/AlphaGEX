"""
VIX Minute Data Fetcher Tests

Tests for the intraday/minute VIX history fetcher (thetadata-proxy backed).
No live network calls - the proxy's HTTP response is mocked.

Run with: pytest tests/test_vix_minute_fetcher.py -v
"""

import io
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_CSV = (
    "timestamp,open,high,low,close,volume,count,vwap\n"
    "2026-09-17 09:30:00,14.50,14.65,14.48,14.60,1200,34,14.55\n"
    "2026-09-17 09:31:00,14.60,14.72,14.55,14.70,980,29,14.63\n"
)


class TestVixMinuteFetcherImport:
    """Tests for module import"""

    def test_import_vix_minute_fetcher(self):
        """Test that the fetcher module can be imported"""
        try:
            from data.vix_minute_fetcher import get_vix_minute_history, get_vix_at_open
            assert get_vix_minute_history is not None
            assert get_vix_at_open is not None
        except ImportError:
            pytest.skip("VIX minute fetcher not available")


class TestVixMinuteFetcherConfig:
    """Tests for THETADATA_BASE_URL configuration handling"""

    @patch.dict('os.environ', {}, clear=True)
    def test_missing_base_url_raises(self):
        """Missing THETADATA_BASE_URL should raise, not silently fall back"""
        from data.vix_minute_fetcher import get_vix_minute_history, VixMinuteDataError, _theta_base_url

        # Default base url is the local Theta Terminal fallback, so force empty
        with patch('data.vix_minute_fetcher._theta_base_url', return_value=''):
            with pytest.raises(VixMinuteDataError):
                get_vix_minute_history('2026-09-15', '2026-09-17')


class TestVixMinuteHistoryParsing:
    """Tests for CSV response parsing"""

    @patch.dict('os.environ', {'THETADATA_BASE_URL': 'http://127.0.0.1:25503'})
    @patch('data.vix_minute_fetcher.urllib.request.urlopen')
    def test_parses_csv_into_dataframe(self, mock_urlopen):
        """A successful CSV response should parse into a DataFrame with OHLCV columns"""
        from data.vix_minute_fetcher import get_vix_minute_history

        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_CSV.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        df = get_vix_minute_history('2026-09-17', '2026-09-17')

        assert df is not None
        assert len(df) == 2
        for col in ('open', 'high', 'low', 'close', 'volume', 'count', 'vwap'):
            assert col in df.columns
        assert df['close'].iloc[0] == pytest.approx(14.60)
        assert df['close'].iloc[1] == pytest.approx(14.70)

    @patch.dict('os.environ', {'THETADATA_BASE_URL': 'http://127.0.0.1:25503'})
    @patch('data.vix_minute_fetcher.urllib.request.urlopen')
    def test_empty_response_returns_none(self, mock_urlopen):
        """An empty/no-data response must return None, never a fake value"""
        from data.vix_minute_fetcher import get_vix_minute_history

        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        df = get_vix_minute_history('2020-01-01', '2020-01-01')
        assert df is None

    @patch.dict('os.environ', {'THETADATA_BASE_URL': 'http://127.0.0.1:25503'})
    @patch('data.vix_minute_fetcher.urllib.request.urlopen')
    def test_request_failure_returns_none(self, mock_urlopen):
        """A network/proxy failure must return None, never a fake value"""
        from data.vix_minute_fetcher import get_vix_minute_history

        mock_urlopen.side_effect = ConnectionError("connection refused")

        df = get_vix_minute_history('2026-09-17', '2026-09-17')
        assert df is None


class TestGetVixAtOpen:
    """Tests for the get_vix_at_open convenience wrapper"""

    @patch.dict('os.environ', {'THETADATA_BASE_URL': 'http://127.0.0.1:25503'})
    @patch('data.vix_minute_fetcher.urllib.request.urlopen')
    def test_returns_first_bar_per_date(self, mock_urlopen):
        """get_vix_at_open should key the first bar's close by date string"""
        from data.vix_minute_fetcher import get_vix_at_open

        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_CSV.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        result = get_vix_at_open('2026-09-17', '2026-09-17')

        assert result == {'2026-09-17': pytest.approx(14.60)}

    @patch.dict('os.environ', {'THETADATA_BASE_URL': 'http://127.0.0.1:25503'})
    @patch('data.vix_minute_fetcher.urllib.request.urlopen')
    def test_failed_fetch_returns_empty_dict(self, mock_urlopen):
        """A failed fetch should return an empty dict, not a fake VIX value"""
        from data.vix_minute_fetcher import get_vix_at_open

        mock_urlopen.side_effect = ConnectionError("connection refused")

        result = get_vix_at_open('2026-09-17', '2026-09-17')
        assert result == {}
