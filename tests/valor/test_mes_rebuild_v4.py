import ast
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scripts import valor_mes_rebuild_v4 as m


def tape(start='2023-01-03T15:00:00Z', n=15):
    return pd.DataFrame(dict(timestamp=pd.date_range(start, periods=n, freq='min'),
        instrument_id=np.ones(n, dtype=int), open=np.full(n, 4000.),
        high=np.full(n, 4000.5), low=np.full(n, 3999.5), close=np.full(n, 4000.),
        volume=np.full(n, 10)))


def order(i=0, side=1):
    return dict(index=i, side=side, reference=4000., stop=3995. if side==1 else 4005.,
        target=4010. if side==1 else 3990., risk=5., signal_time='2023-01-03T15:01:00+00:00')


def pattern():
    d=tape('2023-01-03T12:00:00Z',420)
    d['high']=4001.;d['low']=3999.
    for minute,op,cl,lo,hi in [('15:00',4002.,4003.,4001.75,4003.5),
                              ('15:05',4003.,4004.,4002.75,4004.5),
                              ('15:10',4002.,4004.5,4000.5,4005.)]:
        t=pd.Timestamp('2023-01-03T'+minute+':00Z')
        x=d.timestamp.between(t,t+pd.Timedelta(minutes=4))
        d.loc[x,['open','close','low','high']]=[op,cl,lo,hi]
    return d


def test_mes_specs_and_only_three_rules():
    assert (m.PV,m.TICK,m.FEE)==(5.,.25,3.)
    assert len(m.SPECS)==3

@pytest.mark.parametrize('bad',['naive','duplicate','offgrid','negative','bad_ohlc','missing_id','seconds'])
def test_bad_input_rejected(bad):
    d=tape()
    if bad=='naive':d['timestamp']=d.timestamp.dt.tz_localize(None)
    if bad=='duplicate':d.loc[1,'timestamp']=d.loc[0,'timestamp']
    if bad=='offgrid':d.loc[0,'close']=4000.01
    if bad=='negative':d.loc[0,'volume']=-1
    if bad=='bad_ohlc':d.loc[0,'high']=3999.
    if bad=='missing_id':d=d.drop(columns='instrument_id')
    if bad=='seconds':d['timestamp']=d.timestamp+pd.Timedelta(seconds=1)
    with pytest.raises((ValueError,KeyError)):m.prepare(d)


def test_next_bar_entry_not_same_close():
    d=tape();d.loc[1,['open','high','close']]=[4002.,4002.5,4002.]
    trades,c,rej=m.replay(m.prepare(d),[order()],2)
    assert not c and trades[0]['entry_raw']==4002.
    assert pd.Timestamp(trades[0]['entry'])==d.timestamp.iloc[1]
    assert pd.Timestamp(trades[0]['exit'])==d.timestamp.iloc[3]

@pytest.mark.parametrize('side',[1,-1])
def test_stop_first_ambiguous_bar(side):
    d=tape();d.loc[1,['high','low']]=[4011.,3989.]
    trades,_,_=m.replay(m.prepare(d),[order(side=side)],2)
    assert trades[0]['reason']=='stop'
    assert trades[0]['exit_raw']==order(side=side)['stop']


def test_gap_outside_bracket_is_charged_not_skipped():
    d=tape();d.loc[1,['open','high','low','close']]=[3990.,3991.,3989.,3990.]
    t,c,r=m.replay(m.prepare(d),[order()],3)
    s=m.summarize(t,c,r,'a',2)
    assert t[0]['reason']=='entry_gap_outside_bracket'
    assert s['trades']==1 and s['net_dollars']==-8.


def test_later_gap_stop_fills_worse_than_stop():
    d=tape();d.loc[2,['open','high','low','close']]=[3990.,3991.,3989.,3990.]
    t,_,_=m.replay(m.prepare(d),[order()],5)
    assert t[0]['reason']=='gap_stop' and t[0]['exit_raw']==3990.

@pytest.mark.parametrize('kind',['missing','roll'])
def test_unresolved_data_not_counted_as_profit(kind):
    d=tape()
    if kind=='missing':d=d.drop(index=3).reset_index(drop=True)
    else:d.loc[3:,'instrument_id']=2
    t,c,_=m.replay(m.prepare(d),[order()],10)
    assert len(t)==0 and len(c)==1


def test_missing_next_minute_no_entry():
    d=tape().drop(index=1).reset_index(drop=True)
    t,c,r=m.replay(m.prepare(d),[order()],2)
    assert not t and not c and r['missing_next_minute']==1


def test_one_attempt_per_cash_day_even_when_first_trade_closes():
    t,_,_=m.replay(m.prepare(tape()),[order(0),order(3),order(6)],2)
    assert len(t)==1


def test_session_cap_and_no_weekend_feature_signals():
    d=tape('2023-01-03T20:28:00Z',92)
    t,_,_=m.replay(m.prepare(d),[order()],120)
    assert t[0]['exit']=='2023-01-03T21:00:00+00:00'
    z=m.prepare(tape('2023-01-07T15:00:00Z',100))
    assert not z.rth.any()


def test_cost_scenarios_same_raw_path():
    t,c,r=m.replay(m.prepare(tape()),[order()],3)
    a=m.summarize(t,c,r,'a',2);b=m.summarize(t,c,r,'a',4)
    assert a['raw_price_pnl']==b['raw_price_pnl']
    assert a['net_dollars']-b['net_dollars']==5*a['trades']


def test_five_minute_bars_complete_and_reset_after_holes():
    d=tape('2023-01-03T12:00:00Z',110).drop(index=77).reset_index(drop=True)
    b,_=m.context(m.prepare(d))
    assert (b.n==5).all()
    assert pd.Timestamp('2023-01-03T13:15:00Z') not in list(b.bar_start)
    assert b[b.bar_start>=pd.Timestamp('2023-01-03T13:20:00Z')].atr.isna().all()


def test_true_positive_candidate_and_prefix_invariance():
    d=pattern();full=m.candidates(m.prepare(d))
    a=full['opening_acceptance_retest']
    assert len(a)>0
    cutoff=pd.Timestamp('2023-01-03T15:14:00Z')
    prefix=d[d.timestamp<=cutoff]
    early=m.candidates(m.prepare(prefix))
    for name in m.SPECS:
        assert early[name]==[x for x in full[name] if x['index']<len(prefix)]
    changed=d.copy();mask=changed.timestamp>cutoff
    changed.loc[mask,['open','high','low','close']]+=100.
    newer=m.candidates(m.prepare(changed))
    for name in m.SPECS:
        assert early[name]==[x for x in newer[name] if x['index']<len(prefix)]


def test_incomplete_opening_range_prevents_signal():
    d=pattern();d=d[d.timestamp!=pd.Timestamp('2023-01-03T14:42:00Z')]
    assert all(not x for x in m.candidates(m.prepare(d)).values())


def test_prior_session_does_not_cross_contract():
    d1=tape('2023-01-02T14:30:00Z',390)
    d2=tape('2023-01-03T14:30:00Z',390);d2['instrument_id']=2
    d=pd.concat([d1,d2],ignore_index=True)
    out=m.candidates(m.prepare(d))
    assert not out['prior_extreme_reclaim'] and not out['gap_fill_after_opening_failure']


def test_selection_ignores_2025_and_uses_stress():
    name=next(iter(m.SPECS))
    row=dict(spec=name,cost_ticks_each_side=4,trades=100,net_dollars=200.,
        profit_factor=1.2,censored_fraction=0.,closed_trade_max_drawdown=100.)
    assert m.select_candidate({2023:[row],2024:[row],2025:[]})==name
    assert m.select_candidate({2023:[dict(row,net_dollars=-1)],2024:[row],2025:[row]}) is None
    assert m.select_candidate({2023:[dict(row,trades=99)],2024:[row]}) is None
    assert m.select_candidate({2023:[dict(row,censored_fraction=.02)],2024:[row]}) is None


def test_no_vendor_broker_dependencies_or_old_table_mutations():
    text=Path(m.__file__).read_text();tree=ast.parse(text)
    imported=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):imported.extend(a.name for a in n.names)
        if isinstance(n,ast.ImportFrom):imported.append(n.module)
    assert not any(any(x in (v or '') for x in ('databento','tastytrade','trading.valor','requests','httpx')) for v in imported)
    assert 'UPDATE valor_positions' not in text and 'UPDATE valor_config' not in text
    assert 'INSERT INTO valor_mes_v4_results' in text


def test_evaluate_json_roundtrip_and_determinism():
    a=m.evaluate(pattern());b=m.evaluate(pattern())
    assert a==b
    import json
    json.dumps(a,allow_nan=False)
