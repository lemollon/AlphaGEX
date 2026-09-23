"""Offline regression tests: no broker, no real orders, no database connection.

Uses the actual pure strategy/models/mixin and extracts actual existing executor
and dispatch method bodies. Locks/DB are mocked; this is not a live-feed test.
"""
import ast
from datetime import datetime, timedelta
import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
for name in ('_mnqtest', '_mnqtest.valor'):
    module = ModuleType(name); module.__path__ = [str(ROOT / name.replace('_mnqtest', 'trading').replace('.', '/'))]
    sys.modules[name] = module

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

s = load('_mnqtest.valor.mnq_breakout', 'trading/valor/mnq_breakout.py')
m = load('_mnqtest.valor.models', 'trading/valor/models.py')
fake_integrity = ModuleType('_mnqtest.valor.integrity')
fake_integrity.serialized = lambda fn: fn
sys.modules[fake_integrity.__name__] = fake_integrity
fake_db = ModuleType('_mnqtest.valor.db')
def forbidden_connection(): raise AssertionError('No real database in tests')
fake_db.db_connection = forbidden_connection
sys.modules[fake_db.__name__] = fake_db
adapter = load('_mnqtest.valor.mnq_breakout_trader', 'trading/valor/mnq_breakout_trader.py')
CT = ZoneInfo('America/Chicago')
NOW = datetime(2026, 9, 23, 9, 0, 10, tzinfo=CT)
SYMBOL = '/MNQZ6'


def tape(now=NOW, side=1):
    boundary = now.replace(second=0, microsecond=0)
    rows = [dict(timestamp=(boundary-timedelta(minutes=n)).isoformat(), contract_symbol=SYMBOL,
                 open=20000., high=20001., low=19999., close=20000.) for n in range(31, 0, -1)]
    if side == 1: rows[-1].update(high=20004., close=20003.)
    if side == -1: rows[-1].update(low=19996., close=19997.)
    return rows


def signal(now=NOW):
    d=s.decide(tape(now), SYMBOL, now)
    return m.FuturesSignal(ticker='MNQ', direction=m.TradeDirection.LONG, confidence=0.,
        source=m.SignalSource.MNQ_BREAKOUT_30M, current_price=d.reference,
        gamma_regime=m.GammaRegime.NEUTRAL, gex_value=0, flip_point=0, call_wall=0,
        put_wall=0, vix=0, atr=0, entry_price=d.reference, contract_symbol=SYMBOL,
        contracts=1, stop_price=0, target_price=0, stop_type='TIME_ONLY_PAPER',
        reasoning=json.dumps(d.metadata()))


def position(now=NOW):
    a=signal(now)
    return m.FuturesPosition(position_id='paper-test', symbol=SYMBOL, ticker='MNQ',
        direction=a.direction, contracts=1, entry_price=a.entry_price, entry_value=a.entry_price*2,
        initial_stop=0, current_stop=0, breakeven_price=a.entry_price,
        signal_source=a.source, trade_reasoning=a.reasoning, stop_type='TIME_ONLY_PAPER',
        open_time=now)


def method_class(path, class_name, methods):
    tree=ast.parse((ROOT/path).read_text())
    cls=next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name==class_name)
    bodies=[]
    for name in methods:
        node=next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name==name)
        node.decorator_list=[];bodies.append(node)
    minimal=ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
        ast.ClassDef(name='ActualMethods', bases=[], keywords=[], body=bodies, decorator_list=[])], type_ignores=[])
    space=dict(vars(m), __name__='_mnqtest.valor.tests', __package__='_mnqtest.valor', logger=logging.getLogger('test'))
    exec(compile(ast.fix_missing_locations(minimal), str(path), 'exec'), space)
    return space['ActualMethods'], space


class SignalTests(unittest.TestCase):
    def test_long_uses_previous_highs_not_signal_high(self):
        d=s.decide(tape(), SYMBOL, NOW); self.assertEqual(d.side,1); self.assertEqual(d.prior_high,20001)
    def test_short(self): self.assertEqual(s.decide(tape(side=-1),SYMBOL,NOW).side,-1)
    def test_wick_is_not_close_confirmation(self):
        a=tape();a[-1]['close']=20000.;self.assertIsNone(s.decide(a,SYMBOL,NOW))
    def test_touch_is_not_breakout(self):
        a=tape();a[-1]['close']=20001.;self.assertIsNone(s.decide(a,SYMBOL,NOW))
    def test_incomplete_current_bar_never_used(self):
        a=tape();b=dict(a[-1],timestamp=NOW.replace(second=0).isoformat(),close=30000.,high=30000.)
        self.assertEqual(s.decide(a,SYMBOL,NOW),s.decide(a+[b],SYMBOL,NOW))
    def test_missing_prior_bar(self):
        with self.assertRaises(s.InvalidMarketData):s.decide(tape()[1:],SYMBOL,NOW)
    def test_duplicate(self):
        with self.assertRaises(s.InvalidMarketData):s.decide(tape()+tape()[-1:],SYMBOL,NOW)
    def test_mixed_contract(self):
        a=tape();a[0]['contract_symbol']='/MNQU6'
        with self.assertRaises(s.InvalidMarketData):s.decide(a,SYMBOL,NOW)
    def test_naive(self):
        a=tape();a[0]['timestamp']='2026-09-23T08:29:00'
        with self.assertRaises(s.InvalidMarketData):s.decide(a,SYMBOL,NOW)
    def test_off_tick(self):
        a=tape();a[-1]['close']=20003.1
        with self.assertRaises(s.InvalidMarketData):s.decide(a,SYMBOL,NOW)
    def test_nonfinite(self):
        a=tape();a[-1]['close']=float('nan')
        with self.assertRaises(s.InvalidMarketData):s.decide(a,SYMBOL,NOW)
    def test_geometry(self):
        a=tape();a[-1]['high']=19000
        with self.assertRaises(s.InvalidMarketData):s.decide(a,SYMBOL,NOW)
    def test_stale_snapshot(self):
        with self.assertRaises(s.InvalidMarketData):s.decide(tape(),SYMBOL,NOW+timedelta(minutes=1))
    def test_entry_delay_limit(self): self.assertIsNone(s.decide(tape(),SYMBOL,NOW.replace(second=46)))
    def test_repeat_identity_deterministic(self):
        self.assertEqual(s.decide(tape(),SYMBOL,NOW).key,s.decide(list(reversed(tape())),SYMBOL,NOW).key)
    def test_four_hour_deadline(self):
        d=s.decide(tape(),SYMBOL,NOW)
        self.assertEqual(d.deadline-d.decision_at,timedelta(hours=4))
    def test_afternoon_deadline_capped(self):
        now=NOW.replace(hour=14);d=s.decide(tape(now),SYMBOL,now)
        self.assertEqual(d.deadline.astimezone(CT).strftime('%H:%M'),'14:55')
    def test_early_close(self):
        now=datetime(2026,11,27,10,0,10,tzinfo=CT);d=s.decide(tape(now),SYMBOL,now)
        self.assertEqual(d.deadline.astimezone(CT).strftime('%H:%M'),'11:55')
    def test_holiday_and_weekend(self):
        for day in [datetime(2026,11,26,9,tzinfo=CT),datetime(2026,9,26,9,tzinfo=CT),datetime(2025,1,9,9,tzinfo=CT)]:
            self.assertFalse(s.entry_window(day))
    def test_flatten_time_is_not_entry_time(self): self.assertFalse(s.entry_window(NOW.replace(hour=14,minute=55)))
    def test_before_open(self): self.assertFalse(s.entry_window(NOW.replace(hour=8,minute=29)))
    def test_unknown_calendar_year_blocked(self):
        with self.assertRaises(s.InvalidMarketData):s.entry_window(NOW.replace(year=2027))
    def test_dst(self):
        for day in [datetime(2026,1,20,8,30,tzinfo=CT),datetime(2026,6,1,8,30,tzinfo=CT)]: self.assertTrue(s.entry_window(day))
    def test_legacy_ETF_not_accepted(self):
        with self.assertRaises(s.InvalidMarketData):s.decide(tape(),'QQQ',NOW)


class SafetyTests(unittest.TestCase):
    def test_paper_order_accepted(self):self.assertTrue(s.paper_order_valid(signal(),m.TradingMode.PAPER,NOW))
    def test_live_order_denied(self):self.assertFalse(s.paper_order_valid(signal(),m.TradingMode.LIVE,NOW))
    def test_size_not_expandable(self):
        for size in (0,2,True):
            a=signal();a.contracts=size;self.assertFalse(s.paper_order_valid(a,m.TradingMode.PAPER,NOW))
    def test_no_fictitious_stop(self):
        a=signal();self.assertIsNone(a.risk_points);self.assertIsNone(a.risk_dollars)
        p=position();self.assertIsNone(p.risk_amount);self.assertIsNone(p.to_dict()['current_stop'])
    def test_legacy_risk_unchanged(self):
        p=position();p.signal_source=m.SignalSource.GEX_MOMENTUM;p.initial_stop=p.entry_price-10
        self.assertEqual(p.risk_amount,20);self.assertEqual(p.to_dict()['current_stop'],0)
    def test_modified_deadline_rejected(self):
        a=signal();meta=json.loads(a.reasoning);meta['scheduled_exit']=s.aware(meta['scheduled_exit']).replace(hour=23).isoformat()
        a.reasoning=json.dumps(meta);self.assertFalse(s.paper_order_valid(a,m.TradingMode.PAPER,NOW))
    def test_no_stop_added_without_variant(self):
        a=signal();a.stop_price=19000;self.assertFalse(s.paper_order_valid(a,m.TradingMode.PAPER,NOW))
    def test_metadata_survives_restart(self):
        p=position();detail=s.metadata(p.trade_reasoning,SYMBOL)
        self.assertEqual(s.aware(detail['scheduled_exit']),s.decide(tape(),SYMBOL,NOW).deadline)
    def test_direct_live_paths_block_without_order_submission(self):
        cls,_=method_class('trading/valor/executor.py','TastytradeExecutor',['_live_execution','_live_close'])
        e=cls();e._submit_market_order=Mock(side_effect=AssertionError('Broker called'))
        self.assertFalse(e._live_execution(signal(),'test')[0]);self.assertFalse(e._live_close(position(),'test')[0])
        e._submit_market_order.assert_not_called()
    def test_dispatch_only_MNQ(self):
        cls,space=method_class('trading/valor/trader.py','ValorTrader',['_run_ticker_scan'])
        t=cls();t._run_mnq_breakout_scan=Mock(return_value={'status':'mnq'});space['uuid']=SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='abc'))
        self.assertEqual(t._run_ticker_scan('MNQ',16,100000,False),{'status':'mnq'})
        t._run_mnq_breakout_scan.assert_called_once()
    def test_entry_method_preserves_legacy_reconciliation(self):
        text=(ROOT/'trading/valor/trader.py').read_text()
        self.assertIn('elif ticker == "MNQ" and reconciled_order is None:',text)
    def test_GEX_training_excludes_new_source(self):
        for f in ('trading/valor/ml.py','trading/valor/db.py'):
            self.assertIn("COALESCE(signal_source,'') <> 'MNQ_BREAKOUT_30M'",(ROOT/f).read_text())


class AdapterTests(unittest.TestCase):
    def trader(self):
        t=adapter.MNQBreakoutMixin();t.config=m.ValorConfig();t.config.mode=m.TradingMode.PAPER
        t.db=Mock();t.db.get_open_positions.return_value=[];t.db.get_ticker_performance_stats.return_value={}
        t.margin_manager=Mock();t.margin_manager.can_open_position.return_value=(True,'ok',1)
        t._update_position_high_low=Mock();t._close_position=Mock(return_value=True)
        return t
    def test_before_deadline_does_not_SAR_or_trail(self):
        t=self.trader();p=position()
        with patch.object(adapter,'datetime') as clock:
            clock.now.return_value=NOW;self.assertFalse(t._manage_mnq_breakout(p,19000))
        t._close_position.assert_not_called()
    def test_due_position_closes_at_observed_price(self):
        t=self.trader();p=position();due=s.aware(json.loads(p.trade_reasoning)['scheduled_exit'])
        with patch.object(adapter,'datetime') as clock:
            clock.now.return_value=due+timedelta(seconds=7);self.assertTrue(t._manage_mnq_breakout(p,19800))
        self.assertEqual(t._close_position.call_args.args[1],19800)
        self.assertIn('lateness_seconds=7',t._close_position.call_args.args[3])
    def test_tag_does_not_reclassify_old_MNQ(self):
        t=self.trader();p=position();p.signal_source=m.SignalSource.GEX_MEAN_REVERSION
        self.assertFalse(t._is_mnq_breakout(p))
    def test_mode_flip_cannot_close_at_broker(self):
        t=self.trader();t.config.mode=m.TradingMode.LIVE;t.executor=Mock()
        self.assertFalse(t._close_mnq_breakout(position(),20000,m.PositionStatus.CLOSED,'test'))
        t.executor.close_position_order.assert_not_called()
    def test_missing_quote_retains_position(self):
        t=self.trader();p=position();t.db.get_position_by_id.return_value=p;t.executor=Mock()
        t.executor.close_position_order.return_value=(False,'no quote',0)
        self.assertFalse(t._close_mnq_breakout(p,20000,m.PositionStatus.CLOSED,'test'))
        t.db.close_position.assert_not_called()
    def test_no_new_entry_while_position_exists(self):
        t=self.trader();t.db.get_open_positions.return_value=[position()]
        with patch.object(adapter,'datetime') as clock:
            clock.now.return_value=NOW;self.assertFalse(t._mnq_entry_permitted(signal(),100000))
    def test_margin_gate_retained(self):
        t=self.trader();t.margin_manager.can_open_position.return_value=(False,'margin',0)
        with patch.object(adapter,'datetime') as clock:
            clock.now.return_value=NOW;self.assertFalse(t._mnq_entry_permitted(signal(),100000))
    def test_paper_mode_and_valid_data_permit_single_contract(self):
        t=self.trader()
        with patch.object(adapter,'datetime') as clock:
            clock.now.return_value=NOW;self.assertTrue(t._mnq_entry_permitted(signal(),100000))
    def test_disabled_does_not_fallback_to_GEX(self):
        t=self.trader()
        with patch.dict('os.environ',{'VALOR_MNQ_BREAKOUT_PAPER_ENABLED':'false'}), patch.object(adapter,'datetime') as clock:
            clock.now.return_value=NOW;self.assertFalse(t._mnq_entry_permitted(signal(),100000))
    def test_no_new_entry_in_live_mode(self):
        t=self.trader();t.config.mode=m.TradingMode.LIVE;t.executor=Mock()
        r=t._run_mnq_breakout_scan(100000)
        self.assertEqual(r['status'],'mnq_breakout_refuses_live_mode');t.executor.get_mes_quote.assert_not_called()
    def test_close_updates_paper_ledger_not_GEX_models(self):
        t=self.trader();p=position();t.db.get_position_by_id.return_value=p;t.executor=Mock()
        t.executor.close_position_order.return_value=(True,'ok',20000);t.executor.last_paper_fill={}
        t.db.close_position.return_value=(True,-9);t.daily_pnl=0;t.daily_trades=0;t._daily_losses={};t.win_tracker=Mock()
        self.assertTrue(t._close_mnq_breakout(p,20000,m.PositionStatus.CLOSED,'test'))
        t.win_tracker.update.assert_not_called();self.assertEqual(t._daily_losses['MNQ'],-9)


if __name__=='__main__':unittest.main()
