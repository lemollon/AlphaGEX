from datetime import datetime,timedelta
from unittest.mock import MagicMock
from trading.valor.executor import TastytradeExecutor
from trading.valor.models import ValorConfig,CENTRAL_TZ


def test_paper_liquidity_age_market_and_adverse_tick_rounding():
    e=TastytradeExecutor(ValorConfig())
    e.is_market_open=MagicMock(return_value=True)
    q=dict(bid=100,ask=100.25,last=100.125,bid_size=2,ask_size=1,timestamp=datetime.now(CENTRAL_TZ).isoformat())
    assert e._paper_fill(q,'ask',1,'MES')==100.5
    assert e.last_paper_fill['slippage_ticks']==1
    assert e._paper_fill(q,'ask',2,'MES') is None
    assert e.last_paper_fill is None
    assert e._paper_fill(q,'bid',2,'MES')==99.75
    q['timestamp']=(datetime.now(CENTRAL_TZ)-timedelta(seconds=11)).isoformat()
    assert e._paper_fill(q,'bid',1,'MES') is None
    q['timestamp']=datetime.now(CENTRAL_TZ).isoformat()
    e.is_market_open.return_value=False
    assert e._paper_fill(q,'ask',1,'MES') is None


def test_non_mes_management_uses_its_own_scale():
    from scripts.replay_valor_execution import make_engine,models
    e=make_engine(models.ValorConfig(),0,3,True)
    e.position=models.FuturesPosition(position_id='NG',ticker='NG',symbol='/MNGV6',
        direction=models.TradeDirection.LONG,contracts=1,entry_price=3,entry_value=3000,
        initial_stop=2.85,current_stop=2.85,breakeven_price=3,open_time=e.clock.current,
        high_price_since_entry=3,low_price_since_entry=3)
    cfg=models.get_ticker_config('NG')
    e.price=3-cfg['sar_trigger_pts']-.00001
    assert e._manage_position(e.position,e.price,ticker='NG')
    assert e.trades[0]['status']=='sar_closed'


def test_broker_active_contract_selection_refuses_expired_or_ambiguous():
    from types import SimpleNamespace
    now=datetime.now(CENTRAL_TZ)
    def contract(symbol,ends,active=True):
        return SimpleNamespace(product_code='MNG',symbol=symbol,active_month=active,is_tradeable=True,
                               is_closing_only=False,stops_trading_at=ends,streamer_symbol=symbol+':XNYM')
    expired=contract('/MNGU6',now-timedelta(days=1))
    current=contract('/MNGV6',now+timedelta(days=10))
    assert TastytradeExecutor._choose_active_contract([expired,current],'MNG',now)=='/MNGV6'
    assert TastytradeExecutor._choose_active_contract([expired],'MNG',now) is None
    assert TastytradeExecutor._choose_active_contract([current,current],'MNG',now) is None
