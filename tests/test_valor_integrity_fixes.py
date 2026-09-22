"""Regression tests for audit findings; no broker or production DB writes."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from trading.valor.models import ValorConfig, TradingMode, TradeDirection, PositionStatus, CENTRAL_TZ
from trading.valor.executor import TastytradeExecutor
from trading.valor.trader import ValorTrader
from trading.valor.db import ValorDatabase
from trading.valor.integrity import serialized


def executor():
    with patch.dict('os.environ', {'TASTYTRADE_CLIENT_SECRET':'test-secret', 'TASTYTRADE_REFRESH_TOKEN':'test-refresh'}):
        return TastytradeExecutor(ValorConfig())


def test_oauth_without_password_and_relative_expiry():
    e=executor(); e.username=e.password=None
    response=MagicMock(status_code=200)
    response.json.return_value={'access_token':'test-token','expires_in':900}
    before=datetime.now(CENTRAL_TZ)
    with patch('trading.valor.executor.requests.post', return_value=response) as post:
        assert e._authenticate()
    assert post.call_args.args[0].endswith('/oauth/token')
    assert e._get_headers()['Authorization']=='Bearer test-token'
    assert before+timedelta(seconds=839) < e.token_expiry < before+timedelta(seconds=841)


def test_oauth_failure_clears_old_token():
    e=executor(); e.session_token='old'
    with patch('trading.valor.executor.requests.post', return_value=MagicMock(status_code=401)):
        assert not e._authenticate()
    assert e.session_token is None


@pytest.mark.parametrize('direction,expected', [(TradeDirection.LONG,90),(TradeDirection.SHORT,110)])
def test_gap_exit_uses_market_not_perfect_stop(direction,expected):
    e=executor(); e.get_mes_quote=MagicMock(return_value={'bid':90,'ask':110})
    p=SimpleNamespace(ticker='MNQ',symbol='/MNQZ6',direction=direction)
    assert e._simulate_close(p,'STOP',100)[2]==expected
    e.get_mes_quote.assert_called_once_with(symbol='/MNQZ6',ticker='MNQ')


def test_missing_quote_does_not_fabricate_exit():
    e=executor(); e.get_mes_quote=MagicMock(return_value=None)
    assert not e._simulate_close(SimpleNamespace(ticker='MGC',symbol='/MGCZ6'),'STALE',100)[0]


def test_actual_paper_entry_fill_is_persistable():
    e=executor(); e.get_mes_quote=MagicMock(return_value={'bid':99,'ask':101})
    s=SimpleNamespace(ticker='MGC',direction=TradeDirection.LONG,contracts=1,entry_price=100)
    assert e._simulate_execution(s,'id')[0]
    assert s.entry_price==101


def trader():
    t=ValorTrader.__new__(ValorTrader); t.config=ValorConfig(); t.db=MagicMock(); t.executor=MagicMock()
    return t


def test_quarantine_prevents_order_even_with_saved_ticker_configuration():
    t=trader(); s=SimpleNamespace(ticker='CL')
    assert not ValorTrader._execute_signal_internal.__wrapped__(t,s,100000,'id',ticker='CL')
    t.executor.execute_signal.assert_not_called()


def test_duplicate_or_cooldown_blocks_before_executor():
    t=trader(); t.db.entry_allowed.return_value=False
    assert not ValorTrader._execute_signal_internal.__wrapped__(t,SimpleNamespace(ticker='MNQ'),100000,'id',ticker='MNQ')
    t.executor.execute_signal.assert_not_called()


def test_closed_position_cannot_send_second_exit():
    t=trader(); p=SimpleNamespace(position_id='id',status=PositionStatus.CLOSED)
    t.db.get_position_by_id.return_value=p
    assert not ValorTrader._close_position.__wrapped__(t,p,100,PositionStatus.CLOSED,'stop')
    t.executor.close_position_order.assert_not_called()


def test_stale_exit_precedes_trailing_and_uses_instrument_limit():
    t=trader(); p=SimpleNamespace(position_id='id',ticker='CL',status=PositionStatus.OPEN,
        open_time=datetime.now(CENTRAL_TZ)-timedelta(hours=13))
    t.db.get_position_by_id.return_value=p; t._close_position=MagicMock(return_value=True)
    assert ValorTrader._manage_position.__wrapped__(t,p,75,'CL')
    assert t._close_position.call_args.args[-1]=='STALE_WATCHDOG_12H'


def test_lock_contention_does_not_execute():
    conn=MagicMock(); conn.cursor.return_value.fetchone.return_value=(False,)
    @contextmanager
    def connection(): yield conn
    called=[]
    @serialized
    def action(self): called.append(True)
    with patch('trading.valor.integrity.db_connection',connection):
        assert action(None) is False
    assert called==[]


def test_nested_lock_reuses_connection_and_releases_on_failure():
    conn=MagicMock(); conn.cursor.return_value.fetchone.return_value=(True,)
    @contextmanager
    def connection(): yield conn
    @serialized
    def nested(self): raise ValueError('test')
    @serialized
    def action(self): nested(self)
    with patch('trading.valor.integrity.db_connection',connection), pytest.raises(ValueError):
        action(None)
    calls=[c.args[0] for c in conn.cursor.return_value.execute.call_args_list]
    assert len(calls)==2 and 'pg_advisory_unlock' in calls[-1]


def test_missing_account_raises_so_ledger_transaction_rolls_back():
    db=ValorDatabase.__new__(ValorDatabase); cursor=MagicMock(rowcount=0)
    with pytest.raises(RuntimeError): db._apply_paper_delta(cursor,10,-200,True)


def test_database_outage_propagates_from_entry_guard():
    db=ValorDatabase.__new__(ValorDatabase)
    with patch('trading.valor.db.db_connection',side_effect=RuntimeError('unavailable')),pytest.raises(RuntimeError):
        db.entry_allowed('MES',60)

@pytest.mark.parametrize('change', [
    {'last':float('nan')}, {'bid':102,'ask':101}, {'bid':0},
    {'timestamp':(datetime.now(CENTRAL_TZ)-timedelta(minutes=3)).isoformat()},
    {'timestamp':datetime.now().isoformat()},
])
def test_bad_quotes_rejected(change):
    q={'bid':99,'ask':101,'last':100,'timestamp':datetime.now(CENTRAL_TZ).isoformat()}
    q.update(change)
    assert not TastytradeExecutor._quote_is_usable(q)


def test_fresh_quote_accepted():
    assert TastytradeExecutor._quote_is_usable({'bid':99,'ask':101,'last':100,'timestamp':datetime.now(CENTRAL_TZ).isoformat()})
