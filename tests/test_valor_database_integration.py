"""Real PostgreSQL tests, isolated in a disposable schema supplied by CI."""
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch
import pytest
from trading.valor.models import FuturesPosition, TradeDirection, PositionStatus, CENTRAL_TZ
from trading.valor.db import ValorDatabase


@pytest.fixture
def database(monkeypatch):
    dsn=os.environ.get('TEST_VALOR_DB_URL')
    if not dsn:
        pytest.skip('TEST_VALOR_DB_URL is required for isolated PostgreSQL integration tests')
    import psycopg2
    from psycopg2 import sql
    schema='valor_test_'+uuid.uuid4().hex
    admin=psycopg2.connect(dsn);admin.autocommit=True
    with admin.cursor() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect(): return psycopg2.connect(dsn,options=f'-c search_path={schema}')
    monkeypatch.setattr('trading.valor.db.get_connection',connect)
    try:
        db=ValorDatabase()
        assert db.initialize_paper_account(100000)
        yield db,connect
    finally:
        with admin.cursor() as c: c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        admin.close()


def position(pid='test',contracts=1):
    return FuturesPosition(position_id=pid,ticker='MES',symbol='/MESZ6',direction=TradeDirection.LONG,
        contracts=contracts,entry_price=100,entry_value=500*contracts,initial_stop=95,current_stop=95,
        breakeven_price=100,open_time=datetime.now(CENTRAL_TZ))


def test_atomic_paper_open_close_and_zero_pnl_count(database):
    db,connect=database
    assert db.save_position(position(),paper=True)
    assert not db.save_position(position(),paper=True)
    assert db.get_paper_account()['margin_used']==2100
    assert db.close_position('test',100,'TEST',paper=True)==(True,0)
    assert db.close_position('test',100,'TEST',paper=True)==(False,0)
    account=db.get_paper_account()
    assert account['margin_used']==0
    assert account['total_trades']==1
    assert account['current_balance']==100000


def test_account_failure_rolls_back_position(database):
    db,connect=database
    with patch.object(db,'_apply_paper_delta',side_effect=RuntimeError('test failure')):
        assert not db.save_position(position(),paper=True)
    assert db.get_position_by_id('test') is None


def test_entry_guard_and_persistent_intent(database):
    db,connect=database
    assert db.entry_allowed('MES',60)
    assert db.claim_order_intent('pending','MES',{'kind':'entry'})
    assert not db.entry_allowed('MES',60)
    assert not db.claim_order_intent('pending','MES')
    db.complete_order_intent('pending')
    assert db.entry_allowed('MES',60)
    assert db.save_position(position(),paper=True)
    assert not db.entry_allowed('MES',60)


def test_partial_close_reduces_only_executed_quantity_once(database):
    db,connect=database
    assert db.save_position(position(contracts=3))
    assert db.claim_order_intent('partial','MES',{'kind':'close'})
    assert db.close_position('test',101,'PARTIAL',contracts_closed=1,execution_id='partial')==(True,5)
    assert db.get_position_by_id('test').contracts==2
    assert db.get_position_by_id('test').status==PositionStatus.OPEN
    assert db.close_position('test',101,'PARTIAL',contracts_closed=1,execution_id='partial')==(False,0)
    assert db.get_position_by_id('test').contracts==2
    assert db.get_pending_order_intents()==[]


def test_screened_tracker_and_view_are_installed(database):
    db,connect=database
    assert db.save_position(position(),paper=True)
    assert db.close_position('test',101,'STALE_WATCHDOG_24H',paper=True)[0]
    assert db.get_win_tracker().total_trades==0
    report=db.get_quality_performance()
    assert report['quality'][0]['quality_status']=='hold_violation'
    assert report['performance']==[]
