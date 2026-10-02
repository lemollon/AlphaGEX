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
        with admin.cursor() as c:
            c.execute("SELECT to_regclass(%s)", (schema+'.valor_paper_reset_batches',))
            if c.fetchone()[0]:
                c.execute(sql.SQL('SELECT archive_schema FROM {}.valor_paper_reset_batches').format(sql.Identifier(schema)))
                archives = c.fetchall()
            else:
                archives = []
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            for (archive,) in archives:
                c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(archive)))
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


def test_count_and_cent_drift_reconcile_without_deleting_history(database):
    db,connect=database
    assert db.save_position(position(),paper=True)
    assert db.close_position('test',101,'TEST',paper=True)[0]
    with connect() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE valor_paper_account SET cumulative_pnl=cumulative_pnl+0.01,total_trades=0")
    assert not db.verify_data_integrity()['is_consistent']
    assert db.reconcile_paper_account()['reconciled']
    assert db.verify_data_integrity()['is_consistent']
    assert len(db.get_closed_trades())==1
    account=db.get_paper_account()
    assert account['margin_available']==account['current_balance']-account['margin_used']


def test_concurrent_schema_initializers_complete(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ready = Barrier(2)
    def initialize():
        ready.wait(timeout=5)
        return ValorDatabase()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(initialize) for _ in range(2)]
        assert all(f.result(timeout=15) is not None for f in futures)


def test_paper_fees_are_atomic_once_with_fill_audit(database):
    db,connect=database
    assert db.save_position(position(),paper=True,paper_fill={'bid':99.75,'ask':100,'contract_symbol':'/MESZ6'})
    assert db.close_position('test',101,'TEST',paper=True,paper_fee=3,paper_fill={'bid':101})==(True,2)
    assert db.close_position('test',101,'TEST',paper=True,paper_fee=3)==(False,0)
    assert db.get_paper_account()['current_balance']==100002
    with connect() as conn,conn.cursor() as c:
        c.execute("SELECT details FROM valor_paper_fills WHERE phase='exit'")
        assert c.fetchone()[0]['fees']==3


def test_reset_archives_and_removes_old_performance(database):
    db,connect=database
    p=position();p.order_id='PAPER-test'
    assert db.save_position(p,paper=True)
    assert db.reset_paper_account(600000)
    account=db.get_paper_account()
    assert account['current_balance']==600000
    assert account['total_trades']==0 and account['margin_used']==0
    assert db.get_open_positions()==[]
    with connect() as conn,conn.cursor() as c:
        from psycopg2 import sql
        c.execute("SELECT archive_schema FROM valor_paper_reset_batches")
        archive=c.fetchone()[0]
        c.execute(sql.SQL('SELECT COUNT(*) FROM {}.valor_positions').format(sql.Identifier(archive)))
        assert c.fetchone()[0]==1
        c.execute("SELECT COUNT(*) FROM valor_trade_quality")
        assert c.fetchone()[0]==0
    assert db.save_position(position('fresh'),paper=True)
    assert db.close_position('fresh',101,'TEST',paper=True)[0]
    with connect() as conn,conn.cursor() as c:
        c.execute("SELECT COUNT(*) FROM valor_trade_quality")
        assert c.fetchone()[0]==1
        c.execute("SELECT COUNT(*) FROM valor_paper_reset_batches")
        assert c.fetchone()[0]==1


def test_reset_refuses_live_mode_or_pending_intents(database):
    db,connect=database
    with connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO valor_config(config_key,config_value) VALUES ('mode','\"live\"')")
    assert not db.reset_paper_account(600000)
    with connect() as conn,conn.cursor() as c:
        c.execute("UPDATE valor_config SET config_value='\"paper\"' WHERE config_key='mode'")
    assert db.claim_order_intent('pending','MES',{'kind':'entry'})
    assert not db.reset_paper_account(600000)
    assert db.get_paper_account()['current_balance']==100000
