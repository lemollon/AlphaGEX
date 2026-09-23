import copy
from datetime import date
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[2]/'scripts'/'valor_mes_gex_overlay_v5.py'
spec = importlib.util.spec_from_file_location('overlay', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def trade(day='2023-01-05', net=17., side=1):
    entry = 4000.
    exit_ = entry+side*(net+3)/5
    return dict(signal_time=day+'T15:00:00+00:00',entry=day+'T15:00:00+00:00',
                exit=day+'T16:00:00+00:00',entry_fill=entry,exit_fill=exit_,side=side,net=net)


def base_rows(year=2023):
    out = []
    for name in m.SPECS:
        for ticks in (2,4):
            ts = [trade(f'{year}-01-05',17 if ticks==2 else 12),
                  trade(f'{year}-01-06',-13 if ticks==2 else -18)]
            out.append(dict(spec=name,cost_ticks_each_side=ticks,
                trade_ledger=ts,censored_ledger=[],trades=2,net_dollars=sum(t['net'] for t in ts)))
    return out


class Tests(unittest.TestCase):
    def setUp(self):
        self.source = m.clean_source([('2023-01-03',10),('2023-01-04',-20),('2023-01-05',100)])

    def test_same_day_excluded(self):
        x = m.attach([trade()],self.source,1)[0]
        self.assertEqual(x['gex']['source_date'],'2023-01-04')
        self.assertEqual(x['gex']['sign'],-1)

    def test_two_session_lag(self):
        self.assertEqual(m.attach([trade()],self.source,2)[0]['gex']['source_date'],'2023-01-03')

    def test_future_perturbation(self):
        a = m.attach([trade()],self.source,1)
        b = m.attach([trade()],self.source[:2]+[(date(2023,1,5),-99999.),(date(2023,1,6),99999.)],1)
        self.assertEqual(a,b)

    def test_no_backfill(self):
        self.assertIsNone(m.attach([trade('2023-01-03')],self.source,1)[0]['gex'])

    def test_stale_not_filled(self):
        self.assertEqual(m.attach([trade('2023-01-12')],self.source,1)[0]['gex_missing_reason'],'stale_source_date')

    def test_weekend_lag_valid(self):
        s = m.clean_source([('2023-01-06',1)])
        self.assertIsNotNone(m.attach([trade('2023-01-09')],s,1)[0]['gex'])

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            m.clean_source([('2023-01-03',1),('2023-01-03',2)])

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            m.clean_source([('2023-01-03',float('nan'))])

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            m.aware('2023-01-05T09:00:00')

    def test_fill_cannot_precede_decision(self):
        t = trade(); t['entry'] = '2023-01-05T14:59:00+00:00'
        with self.assertRaises(ValueError):
            m.attach([t],self.source,1)

    def test_nondev_rejected(self):
        with self.assertRaises(ValueError):
            m.attach([trade('2025-01-05')],self.source,1)

    def test_lag_not_optimized(self):
        with self.assertRaises(ValueError):
            m.attach([trade()],self.source,3)

    def test_missing_is_not_negative(self):
        self.assertFalse(m.retained({'gex':None},'negative_only'))

    def test_zero_not_positive_or_negative(self):
        t = {'gex':{'sign':0}}
        self.assertTrue(m.retained(t,'all_matched'))
        self.assertFalse(m.retained(t,'positive_only'))
        self.assertFalse(m.retained(t,'negative_only'))

    def test_cost_difference_no_reentry(self):
        rows = base_rows(); src = {k:self.source for k in m.SERIES}
        snapshot = copy.deepcopy(rows)
        result = m.evaluate(rows,src,2023)
        self.assertEqual(rows,snapshot)
        self.assertEqual(len(result),72)
        a = [r for r in result if r['filter']=='negative_only' and r['lag_sessions']==1]
        self.assertEqual(a[0]['trades'],1)
        self.assertEqual(a[0]['net_dollars'],17)
        self.assertEqual(a[0]['blocked_matched_net'],-13)

    def test_base_reconcile(self):
        rows = base_rows(); rows[0]['net_dollars'] += 1
        with self.assertRaises(ValueError):
            m.validate_base(rows,2023)

    def test_contract_multiplier_reconcile(self):
        rows = base_rows(); rows[0]['trade_ledger'][0]['exit_fill'] += 1
        with self.assertRaises(ValueError):
            m.validate_base(rows,2023)

    def test_censored_accounted_separately(self):
        ts = m.attach([trade()],self.source,1)
        x = m.stats(ts,ts)
        self.assertEqual(x['censored_fraction'],.5)
        self.assertEqual(x['net_dollars'],17)

    def test_empty_not_profitable(self):
        x = m.stats([],[])
        self.assertEqual(x['net_dollars'],0)
        self.assertIsNone(x['profit_factor'])
        self.assertFalse(any(x['development_numeric_gate'] for x in m.gates([])))

    def test_new_year_cannot_select(self):
        fake = dict(source=m.SERIES[0],spec=m.SPECS[0],filter='positive_only',year=2025,
                    cost_ticks_each_side=4,lag_sessions=1,trades=500,net_dollars=100000,
                    profit_factor=3,censored_fraction=0,closed_trade_max_drawdown=100)
        self.assertFalse(any(r['development_numeric_gate'] for r in m.gates([fake,dict(fake,year=2026)])))

    def test_duplicate_year_cannot_select(self):
        fake = dict(source=m.SERIES[0],spec=m.SPECS[0],filter='positive_only',year=2023,
                    cost_ticks_each_side=4,lag_sessions=1,trades=500,net_dollars=100000,
                    profit_factor=3,censored_fraction=0,closed_trade_max_drawdown=100)
        self.assertFalse(any(r['development_numeric_gate'] for r in m.gates([fake,fake])))

    def test_passing_numbers_are_not_live_authorization(self):
        fake = dict(source=m.SERIES[0],spec=m.SPECS[0],filter='positive_only',year=2023,
                    cost_ticks_each_side=4,lag_sessions=1,trades=150,net_dollars=300,
                    profit_factor=1.4,censored_fraction=0,closed_trade_max_drawdown=100)
        decisions = m.gates([fake,dict(fake,year=2024)])
        self.assertEqual(sum(x['development_numeric_gate'] for x in decisions),1)
        self.assertFalse(any(x['ready_for_promotion'] for x in decisions))


if __name__=='__main__':
    unittest.main()
