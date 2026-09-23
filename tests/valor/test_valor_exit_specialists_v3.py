import unittest
import numpy as np
import pandas as pd
from scripts import valor_exit_specialists_v3 as v


def frame(n=200,start='2023-03-06T15:00:00Z'):
    ts=pd.date_range(start,periods=n,freq='min',tz='UTC')
    d=pd.DataFrame(dict(timestamp=ts,instrument_id=1,open=100.,high=101.,low=99.,close=100.,volume=100.))
    local=d.timestamp.dt.tz_convert('America/Chicago')
    d['date']=local.dt.strftime('%Y-%m-%d');d['minute']=local.dt.hour*60+local.dt.minute;d['segment']=1
    return d


def ctx(d,a=1.,eff=.5):
    return dict(atr5=np.full(len(d),a),efficiency=np.full(len(d),eff),high30=np.full(len(d),102.),
        low30=np.full(len(d),98.),vwap=np.full(len(d),105.),opening_mid=np.full(len(d),105.),range_mid=np.full(len(d),105.))


def signal(d,indices=(0,),side=1):
    s=np.zeros(len(d),int);s[list(indices)]=side;return s


class ResearchTests(unittest.TestCase):
    def test_next_bar_not_signal_close(self):
        d=frame(5);d.loc[1,['open','close']]=102.;d.loc[1,'high']=103.
        t,c,r=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('test','x','3r',1,0))
        self.assertEqual(t[0]['entry_raw'],102.)
        self.assertEqual(t[0]['entry'],d.timestamp.iloc[1].isoformat())
    def test_stop_first(self):
        d=frame(5);d.loc[1,['low','high']]=[90.,120.]
        t,_,_=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('x','x','3r',60,0))
        self.assertEqual(t[0]['reason'],'stop');self.assertEqual(t[0]['exit_raw'],95.)
    def test_gap_uses_worse_open(self):
        d=frame(6);d.loc[2,['open','high','low','close']]=[90.,91.,89.,90.]
        t,_,_=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('x','x','3r',60,0))
        self.assertEqual(t[0]['reason'],'gap_stop');self.assertEqual(t[0]['exit_raw'],90.)
    def test_gap_censors(self):
        d=frame(8);d.loc[3:,'segment']=2
        t,c,_=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('x','x','3r',60,0))
        self.assertFalse(t);self.assertEqual(len(c),1)
    def test_missing_entry_never_fills(self):
        d=frame(8);d.loc[1:,'segment']=2
        t,c,r=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('x','x','3r',60,0))
        self.assertFalse(t);self.assertFalse(c);self.assertEqual(r['missing_next_bar'],1)
    def test_costs_share_raw_path(self):
        d=frame(8);s=v.Spec('x','x','3r',1,0)
        t,c,r=v.simulate(d,'MNQ',signal(d),ctx(d),s)
        a=v.summarize(t,c,r,'MNQ',2,s);b=v.summarize(t,c,r,'MNQ',4,s)
        self.assertEqual(a['trades'],b['trades']);self.assertAlmostEqual(a['net_dollars']-b['net_dollars'],2.)
        self.assertAlmostEqual(a['net_dollars'],-5.)
    def test_two_attempts_and_cooldown(self):
        d=frame(100)
        t,_,_=v.simulate(d,'MNQ',np.ones(len(d),int),ctx(d),v.Spec('x','x','3r',1,0))
        self.assertEqual(len(t),2)
        self.assertGreaterEqual(pd.Timestamp(t[1]['entry'])-pd.Timestamp(t[0]['exit']),pd.Timedelta(minutes=15))
    def test_no_overlap(self):
        d=frame(180)
        t,_,_=v.simulate(d,'MNQ',np.ones(len(d),int),ctx(d),v.Spec('x','x','3r',40,0))
        for a,b in zip(t,t[1:]):self.assertGreater(pd.Timestamp(b['entry']),pd.Timestamp(a['exit']))
    def test_target_cost_gate(self):
        d=frame(8);c=ctx(d,eff=.1);c['vwap'][:]=100.25
        t,_,r=v.simulate(d,'MES',signal(d),c,v.Spec('x','x','vwap',60,0,'range'))
        self.assertFalse(t);self.assertEqual(r['structure_or_cost_gate'],1)
    def test_short_stop_and_cost(self):
        d=frame(5);d.loc[1,['high','low']]=[120.,80.];s=v.Spec('x','x','3r',60,0)
        t,c,r=v.simulate(d,'MNQ',signal(d,side=-1),ctx(d),s)
        self.assertEqual(t[0]['exit_raw'],105.)
        self.assertEqual(v.summarize(t,c,r,'MNQ',2,s)['net_dollars'],-15.)
    def test_future_perturbation_context(self):
        d=frame(240,start='2023-03-06T14:30:00Z');e=d.copy();e.loc[180:,['high','close']]=500.
        a=v.context(d,'MES');b=v.context(e,'MES')
        for k in a:np.testing.assert_allclose(a[k][:180],b[k][:180],equal_nan=True)
    def test_gap_warmup(self):
        d=frame(240,start='2023-03-06T14:30:00Z').drop(index=100).reset_index(drop=True)
        d['segment']=(d.timestamp.diff()!=pd.Timedelta(minutes=1)).cumsum()
        a=v.context(d,'MES')['atr5'];self.assertTrue(np.isnan(a[100:160]).all());self.assertTrue(np.isfinite(a[200]))
    def test_opening_range_requires_thirty_bars(self):
        d=frame(100,start='2023-03-06T14:30:00Z').drop(index=10).reset_index(drop=True)
        d['segment']=(d.timestamp.diff()!=pd.Timedelta(minutes=1)).cumsum()
        self.assertTrue(np.isnan(v.context(d,'MES')['opening_mid']).all())
    def test_five_minute_atr_available_after_close_only(self):
        d=frame(80,start='2023-03-06T14:30:00Z');a=v.context(d,'MES')['atr5']
        self.assertTrue(np.isnan(a[:69]).all());self.assertTrue(np.isfinite(a[69]))
    def test_selection_ignores_2025(self):
        r=dict(spec='A',cost_ticks_each_side=4,trades=101,net_dollars=10.,censored_fraction=0.,closed_trade_max_drawdown=5.)
        a={2023:[r],2024:[r],2025:[dict(r,net_dollars=-999999.)]}
        self.assertEqual(v.select_candidate(a),'A');a[2023]=[dict(r,net_dollars=-1.)];self.assertIsNone(v.select_candidate(a))
    def test_sparse_or_censored_rejected(self):
        r=dict(spec='A',cost_ticks_each_side=4,trades=101,net_dollars=10.,censored_fraction=0.,closed_trade_max_drawdown=5.)
        self.assertIsNone(v.select_candidate({2023:[dict(r,trades=12)],2024:[r]}))
        self.assertIsNone(v.select_candidate({2023:[dict(r,censored_fraction=.5)],2024:[r]}))
    def test_trail_active_next_bar_only(self):
        d=frame(10);d.loc[1,['open','high','low','close']]=[100.,112.,99.,110.]
        d.loc[2,['open','high','low','close']]=[109.,110.,108.,109.]
        t,_,_=v.simulate(d,'MNQ',signal(d),ctx(d),v.Spec('x','x','trail',60,0))
        self.assertEqual(t[0]['exit'],(d.timestamp.iloc[2]+pd.Timedelta(minutes=1)).isoformat())
        self.assertEqual(t[0]['reason'],'gap_stop');self.assertEqual(t[0]['exit_raw'],109.)
    def test_mng_tick_math(self):
        self.assertEqual(v.PRODUCTS['NG'][1]*v.PRODUCTS['NG'][2],1.)
    def test_future_open_cannot_change_entry_eligibility(self):
        d=frame(8);e=d.copy();e.loc[1,['open','high','low','close']]=[120.,121.,119.,120.]
        s=v.Spec('x','x','3r',1,0)
        a,_,_=v.simulate(d,'MNQ',signal(d),ctx(d),s);b,c,_=v.simulate(e,'MNQ',signal(e),ctx(e),s)
        self.assertEqual(len(a),len(b));self.assertFalse(c)
        self.assertEqual(a[0]['initial_risk_points'],b[0]['initial_risk_points'])
        self.assertEqual(b[0]['reason'],'entry_gap_outside_bracket')
        self.assertEqual(b[0]['raw_price_pnl'],0.)
    def test_level_decisions_unchanged_by_future_open(self):
        d=frame(8);e=d.copy();e.loc[1,'open']=102.;s=v.Spec('x','x','3r',1,0)
        a,_,_=v.simulate(d,'MNQ',signal(d),ctx(d),s);b,_,_=v.simulate(e,'MNQ',signal(e),ctx(e),s)
        self.assertEqual(a[0]['signal_reference'],b[0]['signal_reference'])
        self.assertEqual(a[0]['initial_risk_points'],b[0]['initial_risk_points'])

if __name__=='__main__':unittest.main()
