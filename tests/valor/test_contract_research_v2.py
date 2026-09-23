"""Synthetic correctness tests, NOT historical profitability evidence."""
import json
import numpy as np
import pandas as pd
import pytest
from scripts.valor_contract_research_v2 import PRODUCTS, RULES, prepare, features, replay, adverse_fill, evaluate


def tape(n=240, start='2024-01-03 14:30:00Z', price=100., tick=.25):
    t = pd.date_range(start, periods=n, freq='min')
    return pd.DataFrame({'timestamp':t,'instrument_id':1,'open':price,'high':price+tick,
                         'low':price-tick,'close':price,'volume':10})


def test_mng_specs():
    assert PRODUCTS['NG'][1]*PRODUCTS['NG'][2] == 1.
    assert PRODUCTS['NG'][1] == 1000.


def test_warmup_is_no_signal_not_error():
    d,_=prepare(tape(10),'MNQ')
    f=features(d,'MNQ')
    assert all(not a.any() for k,a in f.items() if k!='atr')


def test_next_bar_execution_and_nonoverlap():
    raw=tape(240)
    raw.loc[1,['open','close']]=101.
    raw.loc[1,'high']=101.25
    d,_=prepare(raw,'MES')
    s=np.ones(len(d),dtype=int); atr=np.full(len(d),10.)
    r=replay(d,'MES',s,atr,20,2)
    first=r['trade_ledger'][0]
    assert first['entry']==d.timestamp.iloc[1].isoformat()
    assert first['entry_price']==101.5
    assert all(pd.Timestamp(a['exit'])<=pd.Timestamp(b['entry'])
               for a,b in zip(r['trade_ledger'],r['trade_ledger'][1:]))


def test_no_forward_information():
    raw=tape(240)
    raw['close']=100+np.round(np.sin(np.arange(240)/8)*8)*.25
    raw['open']=raw.close
    raw['high']=raw.close+.5; raw['low']=raw.close-.5
    d,_=prepare(raw,'MES'); original=features(d,'MES')
    raw.loc[150:,['open','high','low','close']]+=20.
    changed,_=prepare(raw,'MES'); later=features(changed,'MES')
    for k in original:
        np.testing.assert_allclose(original[k][:150],later[k][:150],equal_nan=True)


def test_roll_censors_position_and_resets_warmup():
    raw=tape(200); raw.loc[100:,'instrument_id']=2
    raw.loc[100:,['open','high','low','close']]+=10
    d,m=prepare(raw,'MNQ'); s=np.zeros(len(d),int); s[90]=1
    r=replay(d,'MNQ',s,np.full(len(d),100.),30,0)
    assert r['censored_positions']==1 and r['trades']==0
    assert m['contract_switches']==1
    f=features(d,'MNQ')
    assert not f['trend_breakout'][100:150].any()


def test_missing_next_bar_is_not_filled():
    raw=tape(100).drop(index=51).reset_index(drop=True)
    d,_=prepare(raw,'MES'); s=np.zeros(len(d),int); s[50]=1
    r=replay(d,'MES',s,np.ones(len(d)),20,0)
    assert r['unfilled_signals']==1 and r['trades']==0


def test_gap_during_position_not_synthetic_return():
    raw=tape(160).drop(index=80).reset_index(drop=True)
    d,_=prepare(raw,'MES'); s=np.zeros(len(d),int); s[60]=1
    r=replay(d,'MES',s,np.full(len(d),100.),60,0)
    assert r['censored_positions']==1 and r['trades']==0


def test_both_barriers_stop_first():
    raw=tape(10); raw.loc[1,'high']=110.; raw.loc[1,'low']=90.
    d,_=prepare(raw,'MES'); s=np.zeros(len(d),int); s[0]=1
    r=replay(d,'MES',s,np.ones(len(d)),5,0)
    assert r['trade_ledger'][0]['reason']=='stop'
    assert r['trade_ledger'][0]['net']==-23.


def test_stop_gap_uses_open_not_ideal_trigger():
    raw=tape(10); raw.loc[2,['open','high','low','close']]=90.
    d,_=prepare(raw,'MES'); s=np.zeros(len(d),int); s[0]=1
    r=replay(d,'MES',s,np.ones(len(d)),5,0)
    assert r['trade_ledger'][0]['reason']=='gap_stop'
    assert r['trade_ledger'][0]['net']==-53.


def test_larger_cost_penalty_flat_tape():
    d,_=prepare(tape(240),'MNQ'); s=np.zeros(len(d),int); s[20]=1
    a=replay(d,'MNQ',s,np.full(len(d),100.),60,2)
    b=replay(d,'MNQ',s,np.full(len(d),100.),60,4)
    assert a['net_dollars']==-5. and b['net_dollars']==-7.


def test_reject_duplicate_and_offgrid():
    raw=tape(10)
    with pytest.raises(ValueError): prepare(pd.concat([raw,raw.iloc[:1]]),'MES')
    raw.loc[1,'close']+=.01
    with pytest.raises(ValueError): prepare(raw,'MES')


def test_adverse_tick_rounding():
    assert adverse_fill(100.1,1,.25,2)==100.75
    assert adverse_fill(100.1,-1,.25,2)==99.5


def test_result_serializes_and_is_research_only():
    m,r=evaluate(tape(),'MES')
    json.dumps([m,r],allow_nan=False)
    assert len(r)==12
    assert all(x['live_ready'] is False and x['gex_used'] is False for x in r)
    assert RULES['MES'] != RULES['MNQ']
