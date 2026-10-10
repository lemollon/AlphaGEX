import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import os
import numpy as np
import pandas as pd
from scripts import valor_research_repair_v7 as m
from scripts import valor_mes_session_v6 as v6


def sample_rows():
    return [dict(spec='sample',trades=1,net_dollars=12.,gross_wins=12.,gross_losses=0.,
                 cost_ticks_each_side=2,ledger=[dict(net=12.)])]


def cached():
    rows=sample_rows();b=m.pack(rows)
    return (dict(fingerprint='correct',status='completed'),m.summaries(rows),hashlib.sha256(b).hexdigest(),b)


def tape(n=390, year=2024):
    ts=pd.date_range(str(year)+'-02-01 08:30',periods=n,freq='min',tz='America/Chicago').tz_convert('UTC')
    op=5000+np.arange(n)*.25
    return pd.DataFrame(dict(timestamp=ts,instrument_id=42,open=op,high=op+.5,
                             low=op-.5,close=op+.25,volume=100))


class GuardTests(unittest.TestCase):
    def test_plan_includes_every_family_every_year(self):
        jobs=m.job_plan()
        self.assertEqual(len(jobs),63)
        self.assertEqual(len(set(jobs)),63)
        self.assertEqual(sum(m.expected_rows(f) for f,t,y in jobs),3276)
        for family in m.FAMILIES:
            self.assertEqual({y for f,t,y in jobs if f==family},{2023,2024,2025})

    def test_completed_does_not_override_wrong_code_fingerprint(self):
        with self.assertRaises(m.IntegrityError):m.validated_cached_job(cached(),'changed',1)

    def test_good_completed_evidence_can_reuse(self):
        self.assertEqual(m.validated_cached_job(cached(),'correct',1),m.summaries(sample_rows()))

    def test_missing_job_requires_calculation(self):
        self.assertIsNone(m.validated_cached_job(None,'correct',1))

    def test_corrupt_completed_artifact_is_blocked(self):
        a,b,c,d=cached()
        with self.assertRaises(m.IntegrityError):m.validated_cached_job((a,b,c,d+b'bad'),'correct',1)

    def test_wrong_summary_is_blocked(self):
        a,b,c,d=cached();b[0]['net_dollars']=999.
        with self.assertRaises(m.IntegrityError):m.validated_cached_job((a,b,c,d),'correct',1)

    def test_incomplete_completed_job_is_blocked(self):
        with self.assertRaises(m.IntegrityError):m.validated_cached_job(cached(),'correct',2)

    def test_duplicate_scenario_blocked(self):
        with self.assertRaises(m.IntegrityError):m.validate_rows(sample_rows()*2,2)

    def test_ledger_accounting_checked(self):
        rows=sample_rows();rows[0]['ledger'][0]['net']=3.
        with self.assertRaises(m.IntegrityError):m.validate_rows(rows,1)

    def test_raw_changed_blocks_even_with_same_saved_metadata(self):
        with self.assertRaises(m.IntegrityError):m.check_bytes(b'new',hashlib.sha256(b'old').hexdigest())

    def test_identity_changes_for_every_critical_input(self):
        args=dict(family='x',ticker='MES',year=2023,source_hashes={'code':'a'},
                  input_hashes={'raw':'b','gex':'c'},runtime={'python':'v'},config={'fee':3,'ticks':2})
        old=m.job_fingerprint(**args)
        for field,value in [('family','y'),('year',2024),('source_hashes',{'code':'new'}),
              ('input_hashes',{'raw':'new','gex':'c'}),('input_hashes',{'raw':'b','gex':'new'}),
              ('runtime',{'python':'new'}),('config',{'fee':4,'ticks':2}),('config',{'fee':3,'ticks':4})]:
            new=copy.deepcopy(args);new[field]=value
            self.assertNotEqual(old,m.job_fingerprint(**new))

    def test_identities_are_deterministic(self):
        self.assertEqual(m.digest({'a':1,'b':2}),m.digest({'b':2,'a':1}))
        self.assertEqual(m.pack(sample_rows()),m.pack(sample_rows()))

    def test_nonfinite_forbidden(self):
        with self.assertRaises(ValueError):m.digest({'x':float('nan')})

    def test_no_legacy_run_called(self):
        import ast,inspect
        tree=ast.parse(inspect.getsource(m))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(any(c.func.attr in ('get_range','Historical') for c in calls))
        source=inspect.getsource(m.evaluate_family)
        self.assertNotIn('.run(',source)
        self.assertNotIn('SELECT',source)

    def test_legacy_snapshots_not_written(self):
        text=Path(m.__file__).read_text()
        import re
        tables=re.findall(r'(?:INSERT INTO|UPDATE|CREATE TABLE IF NOT EXISTS)\s+([a-z_0-9]+)',text)
        self.assertTrue(tables)
        self.assertEqual(set(tables),{'valor_repair_v7_runs','valor_repair_v7_jobs'})


class CausalTests(unittest.TestCase):
    def test_daylag_excludes_same_day(self):
        src=m.sanitize_source([('2024-02-01',-1),('2024-02-02',1)])
        o=[dict(index=10,signal_time='2024-02-02T15:00:00+00:00')]
        yes,_=m.filter_orders(o,src,1,'negative_only')
        no,_=m.filter_orders(o,src,1,'positive_only')
        self.assertEqual(len(yes),1);self.assertFalse(no)
        self.assertEqual(yes[0]['gex_source_date'],'2024-02-01')

    def test_gex_future_perturbation_has_no_effect(self):
        o=[dict(index=10,signal_time='2024-02-02T15:00:00+00:00')]
        a=m.filter_orders(o,m.sanitize_source([('2024-02-01',1),('2024-02-02',-1)]),1,'positive_only')
        b=m.filter_orders(o,m.sanitize_source([('2024-02-01',1),('2024-02-02',10000)]),1,'positive_only')
        self.assertEqual(a,b)

    def test_missing_gex_not_negative(self):
        out,stats=m.filter_orders([dict(signal_time='2023-01-03T15:00:00+00:00')],
                    m.sanitize_source([('2023-01-03',-1)]),1,'negative_only')
        self.assertFalse(out);self.assertEqual(stats['missing_gex_orders'],1)

    def test_2025_evaluates_instead_of_gate_skipping(self):
        manifest,rows=m.evaluate_family('v6_recomputed',tape(year=2025), 'MES',2025,{'v6':v6},{})
        self.assertEqual(len(rows),18)
        self.assertTrue(manifest['previous_promotion_gates_do_not_skip_years'])

    def test_prices_not_saved_results_drive_evaluation(self):
        x=tape();a=v6.evaluate(x,2024)[1][0]['net_dollars']
        x.loc[30:,['open','high','low','close']]=[4900.,4901.,4899.,4900.]
        b=v6.evaluate(x,2024)[1][0]['net_dollars']
        self.assertNotEqual(a,b)

    def test_causal_prefix(self):
        x=tape();a=v6.orders(v6.prepare(x),'morning_continuation')
        x.loc[30:,['open','high','low','close']]+=1000
        b=v6.orders(v6.prepare(x),'morning_continuation')
        self.assertEqual(a,b)

    def test_zero_and_missing_source_not_guessed(self):
        source=m.sanitize_source([('2024-02-01',0)])
        orders=[dict(signal_time='2024-02-02T15:00:00+00:00')]
        self.assertFalse(m.filter_orders(orders,source,1,'negative_only')[0])
        self.assertTrue(m.filter_orders(orders,source,1,'all_matched')[0])

    def test_source_duplicates_fail(self):
        with self.assertRaises(m.IntegrityError):m.sanitize_source([('2024-02-01',1),('2024-02-01',2)])

    def test_gex_filter_applied_to_all_candidates_not_first_trade_only(self):
        orders=[dict(index=i,signal_time='2024-02-02T15:00:00+00:00') for i in (10,20,30)]
        kept,_=m.filter_orders(orders,m.sanitize_source([('2024-02-01',1)]),1,'positive_only')
        self.assertEqual([x['index'] for x in kept],[10,20,30])

    def test_explicit_disable_overrides_older_flags(self):
        old=dict(os.environ)
        try:
            os.environ['VALOR_RESEARCH_REPAIR_V7_AUTORUN']='false'
            os.environ['VALOR_CONTRACT_RESEARCH_AUTORUN']='true'
            self.assertFalse(m.launch_if_enabled())
        finally:
            os.environ.clear();os.environ.update(old)


class InitialScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Base:
            @staticmethod
            def prepare(frame,ticker):return v6.prepare(frame),{}
        cls.engines={'v2':Base}
        cls.raw=tape()
        cls.rows=m.initial_grid(cls.raw,'MES',cls.engines)

    def test_coverage(self):
        m.validate_rows(self.rows,150)

    def test_next_bar_open_not_signal_close(self):
        r=next(r for r in self.rows if r['rule']=='momentum_15m' and r['horizon_min']==30 and r['session']=='RTH' and r['cost_ticks_each_side']==2)
        self.assertTrue(r['raw_ledger'])
        for e,j,side,entry,exit_ in r['raw_ledger']:
            self.assertEqual(entry,self.raw.open.iloc[e])
            self.assertEqual(exit_,self.raw.open.iloc[j])
            self.assertEqual(j-e,30)

    def test_real_nonoverlap(self):
        for r in self.rows:
            trades=r['raw_ledger']
            self.assertTrue(all(b[0]>a[1] for a,b in zip(trades,trades[1:])))

    def test_identical_cost_scenario_paths(self):
        for a,b in zip(self.rows[::2],self.rows[1::2]):
            self.assertEqual(a['trades'],b['trades'])
            self.assertAlmostEqual(b['net_dollars']-a['net_dollars'],-5*a['trades'],places=5)
            self.assertEqual(a['raw_price_pnl'],b['raw_price_pnl'])

    def test_known_trend_can_win_and_reversal_can_lose(self):
        a=next(r for r in self.rows if r['rule']=='momentum_15m' and r['horizon_min']==60 and r['session']=='RTH' and r['cost_ticks_each_side']==2)
        b=next(r for r in self.rows if r['rule']=='mean_reversion_15m' and r['horizon_min']==60 and r['session']=='RTH' and r['cost_ticks_each_side']==2)
        self.assertGreater(a['net_dollars'],0)
        self.assertLess(b['net_dollars'],0)

    def test_missing_minute_not_bridged_or_filled(self):
        raw=self.raw.drop(index=70)
        rows=m.initial_grid(raw,'MES',self.engines)
        self.assertTrue(any(r['unresolved'] for r in rows))
        d=v6.prepare(raw)
        for r in rows:
            for e,j,side,entry,exit_ in r['raw_ledger']:
                self.assertEqual(d.segment.iloc[e],d.segment.iloc[j])

    def test_roll_not_counted_as_price_profit(self):
        raw=self.raw.copy();raw.loc[70:,'instrument_id']=43
        raw.loc[70:,['open','high','low','close']]+=1000
        rows=m.initial_grid(raw,'MES',self.engines)
        d=v6.prepare(raw)
        for r in rows:
            for e,j,side,entry,exit_ in r['raw_ledger']:
                self.assertEqual(d.instrument_id.iloc[e],d.instrument_id.iloc[j])
                self.assertLess(abs(exit_-entry),200)

if __name__=='__main__':unittest.main()
