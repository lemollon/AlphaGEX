"""Production report contract: corruption, missing sources and lifecycle failures."""
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine
from backend import full_options_report as report
from backend.report_contract import REQUIREMENTS, validate_report, prepare_report_delivery, validate_rendered_report
from backend.report_policy import (normalize_blocks, observed, policy_identity, build_strategy_blocks,
                                   validate_semantics)

NOW=datetime(2026,10,6,16,5,tzinfo=timezone.utc)

def empty_blocks():
    return {n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}

def item(value=1,age=0):
    return observed(value,'Observed provider feed',NOW-timedelta(seconds=age),NOW)

def test_schema_retains_all_legacy_fields_and_new_strategy_policy():
    assert len(REQUIREMENTS)==33
    assert sum(map(len,REQUIREMENTS.values()))==245
    assert 'delivery_manifest' in REQUIREMENTS['visuals']
    assert all(n in REQUIREMENTS for n in ('day_strategy','near_forward_strategy','forward_strategy','horizon_comparison','adaptation_rules','data_integrity','market_control'))
    assert len(REQUIREMENTS['visuals'])==14
    assert REQUIREMENTS['market_control']==['control_side','control_evidence','control_confidence','forward_control_outlook']

@pytest.mark.parametrize('name,field',[(n,f) for n,fs in REQUIREMENTS.items() for f in fs])
def test_any_omitted_contract_field_is_rejected(name,field):
    blocks=empty_blocks();del blocks[name][field]
    assert name+'.'+field+': omitted' in validate_report(blocks)['errors']

@freeze_time(NOW)
def test_renderer_discards_model_prose_preserves_all_sections_and_is_idempotent():
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':empty_blocks(),
             'report_markdown':'Guaranteed profit. Buy 123 invented contracts.','chart_urls':{}}
    assert prepare_report_delivery(payload)['publishable']
    first=payload['report_markdown']
    assert 'Guaranteed profit' not in first
    assert payload['report_unverified_prose'].startswith('Guaranteed profit')
    assert all(x in first for x in ('Today’s mission','30-second scoreboard','Today vs forward'))
    assert prepare_report_delivery(payload)['publishable']
    assert first==payload['report_markdown']
    payload['report_policy']['sha256']='wrong'
    assert not validate_rendered_report(payload)['publishable']

@freeze_time(NOW)
def test_expired_observations_downgrade_without_refreshing_clock():
    blocks=empty_blocks();blocks['surface']['atm_iv']=item(.2,0)
    blocks['macro']['rates']=item({'rates_2y':item(4.2,20)},0)
    clean=normalize_blocks(blocks,NOW+timedelta(seconds=100))
    assert clean['surface']['atm_iv']['status']=='historical'
    assert clean['surface']['atm_iv']['source_timestamp']==NOW.isoformat()
    assert clean['macro']['rates']['value']['rates_2y']['age_seconds']==120
    assert clean['macro']['rates']['value']['rates_2y']['status']=='historical'

@pytest.mark.parametrize('corrupt',[{'value':float('nan')},{'value':{'x':float('inf')}},
    {'source_timestamp':(NOW+timedelta(seconds=1)).isoformat()},
    {'source_timestamp':NOW.replace(tzinfo=None).isoformat()},
    {'source':'MOCK ThetaData'}, {'source':'hypothetical observed feed'}, {'confidence':'LOW'}])
def test_invalid_provenance_values_and_clocks_cannot_be_live(corrupt):
    blocks=empty_blocks();blocks['surface']['atm_iv']=dict(item(),**corrupt)
    rejected=normalize_blocks(blocks,NOW)['surface']['atm_iv']
    assert rejected['status']=='unavailable' and rejected['reason']

def test_validator_rejects_nan_historical_age_and_boolean_live_age():
    blocks=empty_blocks();blocks['surface']['atm_iv']=dict(item(),age_seconds=True)
    assert not validate_report(blocks)['publishable']
    blocks['surface']['atm_iv']=dict(item(),status='historical',age_seconds=float('nan'))
    assert not validate_report(blocks)['publishable']

def test_frozen_expected_move_does_not_follow_current_iv():
    core={'surface':{'SPY':{'spot':104,'expected_move_dollars_1d':10,'source_timestamp':NOW.isoformat()}}}
    base={'generated_at':NOW.isoformat(),'evidence':{'surface':{'SPY':{'spot':100,'expected_move_dollars_1d':2,'expected_move_low':98,'expected_move_high':102}}}}
    result=report.market_comparison(core,base)['SPY']
    assert result['frozen_expected_move']==2
    assert abs(result['current_spot']-result['morning_spot'])/result['frozen_expected_move']==2

def test_0dte_flow_cannot_populate_forward_strategy():
    blocks=empty_blocks()
    core={'surface':{},'flow':{'SPY':{'confidence':'MEDIUM','source_timestamp':NOW.isoformat(),'evidence':{'concentrations':[
        {'expiration':NOW.date().isoformat(),'initiation':'calls_bought','premium':1000}]}}}}
    build_strategy_blocks(blocks,core,{}, {},{'trade_details':[]}, {},{},NOW)
    assert blocks['near_forward_strategy']['thesis']['status']=='unavailable'
    assert blocks['forward_strategy']['thesis']['status']=='unavailable'
    assert blocks['forward_strategy']['status']['value']=='PENDING EVIDENCE'

def test_matching_expiry_flow_produces_aged_forward_watch_not_entry():
    blocks=empty_blocks()
    core={'surface':{},'flow':{'SPY':{'confidence':'MEDIUM','source_timestamp':(NOW-timedelta(days=1)).isoformat(),
        'evidence':{'concentrations':[{'expiration':'2026-10-09','initiation':'calls_bought','premium':1000}]}}}}
    build_strategy_blocks(blocks,core,{}, {},{'trade_details':[]}, {},{},NOW)
    thesis=blocks['near_forward_strategy']['thesis']
    assert thesis['status']=='historical'
    assert thesis['value']['SPY']['upside_initiation_premium']==1000
    assert blocks['near_forward_strategy']['status']['value']=='WATCH'
    assert blocks['near_forward_strategy']['contracts']['status']=='unavailable'

def test_other_setup_entry_ready_cannot_activate_selected_package():
    blocks=empty_blocks();blocks['contract_packages']['legs']=item([{'setup_id':'selected','value':[{'expiration':'2026-10-09'}]}])
    runtime={'per_symbol_state':{'SPY':[{'setup_id':'different','state':'ENTRY_READY','source_timestamp':NOW.isoformat(),'confirmation_evidence':[{},{}]}]}}
    build_strategy_blocks(blocks,{'surface':{},'flow':{}},{},runtime,{'trade_details':[]},{},{},NOW)
    assert blocks['day_strategy']['status']['value']!='ENTRY_READY'

def test_invalid_flow_and_zero_sample_paper_statistics_are_rejected():
    payload={'evidence':{'paper':{'closed':0,'win_rate':.8},'flow':{'SPY':{'evidence':{'total_contracts':10,'total_premium':20,
        'buckets':{'0dte':{'calls_bought':{'contracts':9,'premium':20}}}}}}}}
    errors=validate_semantics(payload,NOW)
    assert 'Zero-sample paper win rate is undefined' in errors
    assert 'SPY: flow contracts do not reconcile' in errors

def test_mock_delivery_is_rejected():
    assert 'Mock reports cannot enter production delivery' in validate_semantics({'mock_mode':True},NOW)

def test_verification_and_other_days_cannot_replace_frozen_morning(monkeypatch):
    engine=create_engine('sqlite:///:memory:')
    monkeypatch.setattr(report,'engine',engine);report.ensure_tables()
    import json
    from sqlalchemy import text
    with engine.begin() as c:
        for rid,kind,when in [('old','morning',NOW-timedelta(days=1)),('first','morning',NOW-timedelta(hours=3)),
                              ('second','morning',NOW-timedelta(hours=2)),('v','verification',NOW-timedelta(minutes=1))]:
            c.execute(text('INSERT INTO sw_full_reports (report_id,kind,generated_at,payload_json) VALUES (:id,:kind,:date,:payload)'),
              {'id':rid,'kind':kind,'date':when.replace(tzinfo=None),'payload':json.dumps({'report_id':rid,'generated_at':when.isoformat()})})
    morning,prior=report.previous_reports(NOW)
    assert morning['report_id']=='first';assert prior['report_id']=='second'

def test_delivery_lease_retry_and_success_deduplication(monkeypatch):
    monkeypatch.setattr(report,'engine',create_engine('sqlite:///:memory:'))
    slot=report.claim_delivery('intraday',NOW)
    assert slot and report.claim_delivery('intraday',NOW) is None
    report.finish_delivery(slot,'r',False,'transport failed')
    assert report.claim_delivery('intraday',NOW)==slot
    report.finish_delivery(slot,'r',True)
    assert report.claim_delivery('intraday',NOW+timedelta(minutes=5)) is None
    assert report.claim_delivery('intraday',NOW+timedelta(hours=1))!=slot

def test_partial_source_has_specific_disclosure():
    item=report.merge_symbols({'SPY':{'atm_iv':.2,'confidence':'MEDIUM','source':'Observed provider','source_timestamp':NOW.isoformat()},
        'QQQ':{'reason':'Entitlement denied'}},['atm_iv'],NOW)
    assert item['status']=='unavailable';assert 'QQQ: Entitlement denied' in item['reason']
    assert item['value']['SPY']['atm_iv']==.2

def test_fresh_summary_cannot_refresh_old_or_missing_dependencies():
    blocks=empty_blocks()
    blocks['horizon_comparison']['forward_options']=item({'forward':item('Old flow',3600)})
    normalized=normalize_blocks(blocks,NOW)['horizon_comparison']['forward_options']
    assert normalized['status']=='historical' and normalized['age_seconds']==3600
    blocks['horizon_comparison']['forward_options']=item({'forward':{'status':'unavailable','reason':'No forward expirations'}})
    assert normalize_blocks(blocks,NOW)['horizon_comparison']['forward_options']['status']=='unavailable'

@freeze_time(NOW)
def test_entry_ready_downgrades_when_quotes_age_at_publication():
    blocks=empty_blocks()
    blocks['day_strategy']['status']=item('ENTRY_READY')
    blocks['day_strategy']['contracts']=item([{'setup_id':'A'}],100)
    payload={'generated_at':NOW.isoformat(),'report_blocks':blocks}
    assert prepare_report_delivery(payload)['publishable']
    assert payload['report_blocks']['day_strategy']['status']['value']=='WATCH'

def test_optional_collector_failure_preserves_other_core_sources(monkeypatch):
    from backend import market_structure as ms
    def fail(*args,**kw):raise TimeoutError('unavailable')
    monkeypatch.setattr(ms,'_cached_vol_payload',fail)
    monkeypatch.setattr(ms,'fetch_cross_asset',lambda now:{'assets':{}})
    monkeypatch.setattr(report,'stored_futures',lambda now:{})
    for name in ('_latest_surface','_latest_gamma','_latest_trade_quote_flow'):
        monkeypatch.setattr(ms,name,lambda *args,**kw:{'confidence':'MEDIUM','source_timestamp':NOW.isoformat()})
    core=report.cached_core(NOW)
    assert core['failures']['volatility']=='TimeoutError'
    assert core['surface']['SPY']['confidence']=='MEDIUM'
