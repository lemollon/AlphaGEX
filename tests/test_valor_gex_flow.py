"""Exercise current per-instrument providers, cache isolation and signal API."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest
import trading.valor.signals as signals
from trading.valor.models import ValorConfig, BayesianWinTracker, TradeDirection

TZ=ZoneInfo('America/Chicago')

@pytest.fixture(autouse=True)
def isolated_sources(monkeypatch):
    monkeypatch.setattr(signals,'_gex_cache_by_ticker',{})
    monkeypatch.setattr(signals,'_gex_cache',{})
    monkeypatch.setattr(signals,'_gex_cache_loaded_from_db',True)
    monkeypatch.setattr(signals,'_persist_gex_cache_to_db',MagicMock())
    monkeypatch.setattr(signals,'_get_tradier_gex_calculator',MagicMock(return_value=None))
    monkeypatch.setattr(signals,'_fetch_gex_from_trading_volatility',MagicMock(return_value=None))
    monkeypatch.setattr(signals,'is_ab_test_enabled',lambda:False)


def at(monkeypatch,hour):
    now=datetime(2026,9,22,hour,tzinfo=TZ)
    clock=MagicMock();clock.now.return_value=now
    monkeypatch.setattr(signals,'datetime',clock)
    return now


def gex(flip):
    return {'flip_point':flip,'call_wall':flip*1.01,'put_wall':flip*.99,'net_gex':1.5e9}


def test_market_hours_mes_uses_unscaled_spx(monkeypatch):
    at(monkeypatch,10)
    calc=MagicMock();calc.calculate_gex.return_value=gex(6000)
    signals._get_tradier_gex_calculator.return_value=calc
    result=signals.get_gex_data_for_valor('SPY','MES')
    assert result['flip_point']==6000
    calc.calculate_gex.assert_called_once_with('SPX')
    signals._fetch_gex_from_trading_volatility.assert_not_called()


def test_overnight_tv_fallback_scales_spy_once(monkeypatch):
    at(monkeypatch,18)
    signals._fetch_gex_from_trading_volatility.return_value=gex(598)
    result=signals.get_gex_data_for_valor('SPY','MES')
    assert result['flip_point']==5980
    assert result['n1_flip_point']==5980
    assert result['data_source']=='trading_volatility_overnight'


def test_overnight_cache_uses_its_own_instrument(monkeypatch):
    now=at(monkeypatch,22)
    signals._gex_cache_by_ticker['MES']={'data':gex(5990),'cache_time':now-timedelta(hours=3)}
    signals._gex_cache_by_ticker['MNQ']={'data':gex(21000),'cache_time':now-timedelta(hours=3)}
    assert signals.get_gex_data_for_valor('SPY','MES')['flip_point']==5990
    assert signals.get_gex_data_for_valor('QQQ','MNQ')['flip_point']==21000
    signals._fetch_gex_from_trading_volatility.assert_not_called()


@pytest.mark.parametrize('net,direction',[(1.5e9,TradeDirection.SHORT),(-1.5e9,TradeDirection.LONG)])
def test_current_signal_api_routes_gamma_regime(monkeypatch,net,direction):
    generator=signals.ValorSignalGenerator(ValorConfig(),BayesianWinTracker())
    monkeypatch.setattr(generator,'_calculate_win_probability',lambda *a:.6)
    data=gex(6000);data['net_gex']=net
    signal=generator.generate_signal(6060,data,15,25,100000,ticker='MES')
    assert signal is not None
    assert signal.direction==direction
    assert signal.ticker=='MES'


def test_missing_gex_blocks_signal():
    generator=signals.ValorSignalGenerator(ValorConfig(),BayesianWinTracker())
    assert generator.generate_signal(6020,gex(0),15,25,100000,ticker='MES') is None
