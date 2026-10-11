import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('calibration',Path(__file__).parents[1]/'scripts/calibrate_valor_execution.py')
cal=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def tx(**overrides):
    r=dict(id=1,symbol='/MESZ6',transaction_type='Trade',action='Buy to Open',quantity='2',
           price='7800',value='100',net_value='97',commission='-2',clearing_fees='-0.8',
           regulatory_fees='-0.2',is_estimated_fee=False)
    return dict(r,**overrides)


def test_fee_signs_quantity_and_rebates():
    report=cal.fee_report([tx(),tx(id=2,action='Sell to Close',commission='0.2',
        clearing_fees='-0.8',regulatory_fees='-0.2',net_value='99.2')])
    rates={r['phase']:r['fee_per_contract'] for r in report['observed_fee_rates']}
    assert rates=={'open':1.5,'close':0.4}
    assert report['automatically_applied'] is False


def test_estimates_mismatch_duplicates_and_reversals_excluded():
    rows=[tx(),tx(),tx(id=2,is_estimated_fee=True),tx(id=3,net_value='90'),
          tx(id=4),tx(id=5,reverses_id=4)]
    report=cal.fee_report(rows)
    assert report['observed_fee_rates'][0]['rows']==1
    assert report['excluded']=={'duplicate':1,'estimated_or_unknown_fee_status':1,
        'fees_do_not_reconcile':1,'reversal_requires_review':2}


def test_missing_fees_never_become_zero():
    report=cal.fee_report([tx(commission=None,clearing_fees=None,regulatory_fees=None)])
    assert report['observed_fee_rates']==[]
    assert report['excluded']['incomplete_fee_record']==1


def event(ms,bid,size):
    return dict(elapsed_ms=ms,bid=bid,ask=bid+0.25,bid_size=size,ask_size=size)


def scenario(events,latency=250,qty=5,fraction=1,side='buy'):
    return next(r for r in cal.shadow_report(events) if r['assumed_latency_ms']==latency
        and r['requested_quantity']==qty and r['displayed_liquidity_fraction']==fraction and r['side']==side)


def test_arrival_uses_future_observation_and_preserves_unfilled_remainder():
    rows=[event(2000,100,5),event(2200,90,5),event(2300,101,2)]
    result=scenario(rows)
    assert result['median_adverse_move_ticks']==4
    assert result['counts']['partial']==1
    assert result['counts']['modeled_filled_contracts']==2
    assert result['counts']['modeled_unfilled_contracts']==3
    assert result['median_observation_delay_ms']==300


def test_liquidity_haircut_floors_contracts_and_does_not_reuse_snapshot():
    result=scenario([event(2000,100,5),event(2300,101,1)],fraction=0.5)
    assert result['counts']['unfilled']==1
    assert result['counts']['modeled_filled_contracts']==0
    assert result['p95_adverse_move_ticks'] is None


def test_missing_or_late_arrival_does_not_invent_fill():
    for rows in ([event(2000,100,5)], [event(2000,100,5),event(5000,101,5)]):
        result=scenario(rows)
        assert result['counts'].get('trials',0)==0
        assert result['counts']['missing_arrival_observation']>=1
