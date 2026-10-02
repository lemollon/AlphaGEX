import copy
import numpy as np
import pandas as pd
import pytest
from scripts import valor_mes_session_v6 as m


def tape(day='2024-02-01', n=390):
    ts=pd.date_range(day+' 08:30',periods=n,freq='min',tz='America/Chicago').tz_convert('UTC')
    op=5000+np.arange(n)*.25
    return pd.DataFrame(dict(timestamp=ts,instrument_id=42,open=op,high=op+.5,
                             low=op-.5,close=op+.25,volume=100))


def order(d, index=29, side=1, risk=20., exit_minute=545):
    return dict(index=index,date=d.date.iloc[index],side=side,
                signal_time=(d.timestamp.iloc[index]+pd.Timedelta(minutes=1)).isoformat(),
                reference=float(d.close.iloc[index]),risk=risk,exit_minute=exit_minute)


def test_bar_count_and_clock():
    d=m.prepare(tape()); assert len(d)==390 and d.minute.iloc[0]==510


@pytest.mark.parametrize('day',['2024-02-01','2024-06-03'])
def test_dst_clock_invariance(day):
    d=m.prepare(tape(day)); s,_=m.orders(d,'morning_continuation')
    assert len(s)==1 and s[0]['index']==29
    assert pd.Timestamp(s[0]['signal_time']).tz_convert('America/Chicago').hour==9


def test_signal_uses_completed_prefix_only():
    raw=tape(); d=m.prepare(raw); orig,_=m.orders(d,'morning_continuation')
    raw.loc[30:,['open','high','low','close']]+=1000
    changed,_=m.orders(m.prepare(raw),'morning_continuation')
    assert orig==changed


def test_future_truncation_does_not_erase_entry():
    a,_=m.orders(m.prepare(tape()),'morning_continuation')
    b,_=m.orders(m.prepare(tape().iloc[:30]),'morning_continuation')
    assert a==b


def test_future_missing_minute_does_not_filter_signal():
    a,_=m.orders(m.prepare(tape()),'morning_continuation')
    b,_=m.orders(m.prepare(tape().drop(index=150)),'morning_continuation')
    assert a==b


def test_incomplete_past_rejected():
    s,k=m.orders(m.prepare(tape().drop(index=10)),'morning_continuation')
    assert not s and k['incomplete_known_context']==1


def test_roll_in_context_rejected():
    raw=tape();raw.loc[20:,'instrument_id']=43
    assert not m.orders(m.prepare(raw),'morning_continuation')[0]


def test_next_open_and_scheduled_open():
    d=m.prepare(tape()); s=order(d)
    ts,u=m.replay(d,[s],'signal')
    assert not u and len(ts)==1
    assert ts[0]['entry_raw']==d.open.iloc[30] and ts[0]['exit_raw']==d.open.iloc[35]
    assert ts[0]['reason']=='scheduled_open'


def test_exit_bar_future_high_low_not_used():
    raw=tape(); d=m.prepare(raw); s=order(d)
    a,_=m.replay(d,[s],'signal')
    raw.loc[35,'low']=4900
    b,_=m.replay(m.prepare(raw),[s],'signal')
    assert a==b


def test_intrabar_stop():
    raw=tape(); d=m.prepare(raw); s=order(d,risk=10)
    raw.loc[31,'low']=s['reference']-11
    a,u=m.replay(m.prepare(raw),[s],'signal')
    assert not u and a[0]['reason']=='stop' and a[0]['exit_raw']==s['reference']-10


def test_adverse_gap_not_stopped_at_fictional_level():
    raw=tape();d=m.prepare(raw);s=order(d,risk=10)
    raw.loc[31,['open','high','low','close']]=[4900,4901,4899,4900]
    a,_=m.replay(m.prepare(raw),[s],'signal')
    assert a[0]['exit_raw']==4900 and a[0]['reason']=='gap_stop'


def test_entry_outside_stop_pays_roundtrip():
    raw=tape();d=m.prepare(raw);s=order(d,risk=10)
    raw.loc[30,['open','high','low','close']]=[4900,4901,4899,4900]
    a,u=m.replay(m.prepare(raw),[s],'signal');r=m.summarize(a,u,2024,2)
    assert r['net_dollars']==-8 and r['trades']==1


def test_missing_entry_is_unresolved_not_zero_trade():
    raw=tape();d=m.prepare(raw);s=order(d)
    a,u=m.replay(m.prepare(raw.drop(index=30)),[s],'signal')
    assert not a and u[0]['reason']=='missing_entry_bar'


def test_contract_change_after_entry_unresolved():
    raw=tape();d=m.prepare(raw);s=order(d)
    raw.loc[33:,'instrument_id']=43
    a,u=m.replay(m.prepare(raw),[s],'signal')
    assert not a and u[0]['reason']=='missing_bar_roll_or_end'


def test_missing_exit_unresolved():
    raw=tape();d=m.prepare(raw);s=order(d)
    a,u=m.replay(m.prepare(raw.drop(index=35)),[s],'signal')
    assert not a and len(u)==1


def test_one_daily_attempt_enforced():
    d=m.prepare(tape());s=order(d)
    with pytest.raises(ValueError,match='More than one'):
        m.replay(d,[s,s],'signal')


def test_costs_identical_raw_paths():
    d=m.prepare(tape());s=order(d);a,u=m.replay(d,[s],'signal')
    low=m.summarize(a,u,2024,2); high=m.summarize(a,u,2024,4)
    assert high['net_dollars']-low['net_dollars']==-5*low['trades']
    assert [t['entry'] for t in low['ledger']]==[t['entry'] for t in high['ledger']]


def test_controls_share_entry_dates():
    d=m.prepare(tape());s,_=m.orders(d,'morning_continuation')
    results=[m.replay(d,s,k)[0] for k in ('signal','matched_long','matched_short')]
    assert len({a[0]['entry'] for a in results})==1
    assert results[2][0]['side']==-1


def test_liquidation_drawdown_includes_initial_costs():
    d=m.prepare(tape());s=order(d);a,u=m.replay(d,[s],'signal')
    r=m.summarize(a,u,2024,2)
    assert r['resolved_minute_liquidation_mark_drawdown']>=8


@pytest.mark.parametrize('error',['duplicate','naive','tick','ohlc'])
def test_validation(error):
    raw=tape()
    if error=='duplicate':raw=pd.concat([raw,raw.iloc[[0]]])
    if error=='naive':raw['timestamp']=raw.timestamp.dt.tz_localize(None)
    if error=='tick':raw.loc[0,'open']+=.1
    if error=='ohlc':raw.loc[0,'high']=100
    with pytest.raises(ValueError):m.prepare(raw)


def winning_rows(year):
    return [dict(year=year,spec=spec,view=view,cost_ticks_each_side=4,trades=120,
                 net_dollars=1000 if view=='signal' else 100,profit_factor=1.5,
                 unresolved_fraction=0) for spec in m.SPECS for view in ('signal','matched_long','matched_short')]


def test_selector_ignores_2025():
    d={2023:winning_rows(2023),2024:winning_rows(2024)}
    a=m.decisions(d);d[2025]=[dict(r,net_dollars=-999999) for r in winning_rows(2025)]
    assert a==m.decisions(d) and all(x['selected'] for x in a)


def test_numeric_and_controls_separated():
    d={2023:winning_rows(2023),2024:winning_rows(2024)}
    for r in d[2024]:
        if r['view']=='matched_long':r['net_dollars']=2000
    out=m.decisions(d)
    assert all(x['numeric_pass'] and not x['selected'] for x in out)


def test_small_samples_fail():
    d={2023:winning_rows(2023),2024:winning_rows(2024)}
    for r in d[2024]:r['trades']=6
    assert not any(x['selected'] for x in m.decisions(d))


def test_no_import_side_effects(monkeypatch):
    monkeypatch.setenv('VALOR_MES_SESSION_V6_AUTORUN','false')
    monkeypatch.setenv('VALOR_MES_GEX_V5_AUTORUN','true')
    assert m.launch_if_enabled() is False


def test_all_summaries_reconcile():
    _,rs=m.evaluate(tape(),2024)
    assert len(rs)==18
    for r in rs:
        assert abs(r['long_net']+r['short_net']-r['net_dollars'])<1e-8
        assert sum(r['monthly'].values())==r['net_dollars']
        assert r['trades']+r['unresolved']==r['decisions']
