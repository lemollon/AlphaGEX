"""Entry selection and exact-contract quote isolation across quarterly rollover."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from trading.valor.models import CENTRAL_TZ, ValorConfig, get_front_month_symbol
from trading.valor.executor import TastytradeExecutor, _quote_cache


@pytest.mark.parametrize("when,expected", [
    ("2026-09-13T16:59:59", "/MESU6"), ("2026-09-13T17:00:00", "/MESZ6"),
    ("2026-09-14T09:00:00", "/MESZ6"), ("2026-09-22T07:00:00", "/MESZ6"),
    ("2026-12-13T16:59:59", "/MESZ6"), ("2026-12-13T17:00:00", "/MESH7"),
    ("2029-12-17T10:00:00", "/MESH0"), ("2026-06-15T10:00:00", "/MESU6"),
])
def test_equity_roll_calendar(when, expected):
    assert get_front_month_symbol("MES", datetime.fromisoformat(when).replace(tzinfo=CENTRAL_TZ)) == expected


def test_other_equity_prefixes_and_naive_time():
    now = datetime(2026, 9, 22, tzinfo=CENTRAL_TZ)
    assert get_front_month_symbol("RTY", now) == "/M2KZ6"
    assert get_front_month_symbol("MNQ", now) == "/MNQZ6"
    with pytest.raises(ValueError, match="timezone-aware"):
        get_front_month_symbol("MES", now.replace(tzinfo=None))


def test_contract_specific_cache_and_missing_exact_quote_fail_closed():
    _quote_cache.clear()


    e = TastytradeExecutor(ValorConfig())
    e.auth_method = "OAUTH"
    def quote(symbol):
        return dict(contract_symbol=symbol, bid=7800, ask=7800.25, last=7800.125,
                    timestamp=datetime.now(CENTRAL_TZ).isoformat())
    e._get_tastytrade_streaming_quote = MagicMock(side_effect=quote)
    e._get_yahoo_futures_quote = MagicMock()
    with patch("trading.valor.executor.TASTYTRADE_SDK_AVAILABLE", True):
        assert e.get_mes_quote(symbol="/MESU6", ticker="MES")["contract_symbol"] == "/MESU6"
        assert e.get_mes_quote(symbol="/MESZ6", ticker="MES")["contract_symbol"] == "/MESZ6"
        assert e._get_tastytrade_streaming_quote.call_count == 2
        assert e.get_mes_quote(symbol="/MESZ6", ticker="MES")
        assert e._get_tastytrade_streaming_quote.call_count == 2
        _quote_cache.clear()
        e._get_tastytrade_streaming_quote.return_value = None
        e._get_tastytrade_streaming_quote.side_effect = None
        assert e.get_mes_quote(symbol="/MESZ6", ticker="MES") is None
        e._get_yahoo_futures_quote.assert_not_called()
        assert e.get_mes_quote(symbol="/MNQZ6", ticker="MES") is None
    _quote_cache.clear()


@pytest.mark.parametrize("age,wrong_symbol,valid", [(2, False, True), (180, False, False), (2, True, False)])
def test_received_snapshot_preserves_broker_age_and_identity(age, wrong_symbol, valid):
    now = datetime.now(CENTRAL_TZ)
    event = SimpleNamespace(event_symbol="/MESU26:XCME" if wrong_symbol else "/MESZ26:XCME",
                            bid_price=7800, ask_price=7800.25, bid_size=10, ask_size=10,
                            bid_time=int((now - timedelta(seconds=age)).timestamp() * 1000),
                            ask_time=int(now.timestamp() * 1000))
    result = TastytradeExecutor._normalize_contract_quote(event, "/MESZ26:XCME", "/MESZ6")
    assert bool(result) is valid
    if valid:
        assert result["contract_symbol"] == "/MESZ6"
