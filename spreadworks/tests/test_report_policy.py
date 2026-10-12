"""Production report contract: corruption, missing sources and lifecycle failures."""
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine
from backend import full_options_report as report
from backend.report_contract import REQUIREMENTS, validate_report, prepare_report_delivery, validate_rendered_report, LIVE_MAX_AGE_SECONDS
from backend.report_policy import (normalize_blocks, observed, policy_identity, build_strategy_blocks,
                                   validate_semantics, section_summary, section_meaning, market_story,
                                   edge_board, biggest_traps, if_then_day_plan, SECTION_SUMMARY_SECTIONS,
                                   render_markdown, render_opening_html, plain_value, field_label, display,
                                   ct_str, fmt_number, narrative_html, positioning_panel_html,
                                   narrative_package_html, item_cell_html, narrative_setup_html,
                                   decision_brief_lines, _week_ahead_outlook_html)

NOW=datetime(2026,10,6,16,5,tzinfo=timezone.utc)

def empty_blocks():
    return {n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}

def item(value=1,age=0):
    return observed(value,'Observed provider feed',NOW-timedelta(seconds=age),NOW)

def test_schema_retains_all_legacy_fields_and_new_strategy_policy():
    assert len(REQUIREMENTS)==33
    assert sum(map(len,REQUIREMENTS.values()))==243
    assert 'regime_shift' in REQUIREMENTS['morning_comparison']
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
    assert all(x in first for x in ('Today’s mission','30-second scoreboard','Today vs forward',
        'Market story','Edge board','Biggest traps','If/then day plan'))
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

def test_designed_unavailable_field_does_not_block_completeness():
    """Leron, 2026-10-12: "why does it always say incomplete" -- futures_context.basis is
    unconditionally unavailable() every single report (full_options_report.py: same-time
    futures-vs-cash basis cannot be computed, SPY is not substituted for SPX), which alone
    made complete_live_data impossible forever, for every report kind, no matter how fresh
    everything else was. DESIGNED_UNAVAILABLE excludes it from the completeness bar while
    keeping it fully disclosed in unavailable_fields -- nothing is hidden, it just stops
    permanently vetoing COMPLETE."""
    blocks = {n: {f: item() for f in fs} for n, fs in REQUIREMENTS.items()}
    blocks['futures_context']['basis'] = {'status': 'unavailable',
        'reason': 'Exact same-time futures vs cash-index basis unavailable; SPY is not substituted for SPX'}
    check = validate_report(blocks)
    assert check['publishable']
    assert check['complete_live_data']
    assert 'futures_context.basis' in check['unavailable_fields']

    # A genuinely missing field (not the one designed-permanent exception) still blocks it.
    blocks['surface']['atm_iv'] = {'status': 'unavailable', 'reason': 'No verified observation'}
    check2 = validate_report(blocks)
    assert check2['publishable']
    assert not check2['complete_live_data']

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

def test_section_summary_cites_real_field_values_or_explicit_absence():
    """2026-10-11: Leron asked for the Section summary lines to read as narrative, not a
    field:value dump -- gamma/market_control/flow/etc now get bespoke builders in
    section_policy._NARRATIVE_BUILDERS keyed on the REAL nested producer shapes (merge_symbols()
    always wraps even a single key: {'SPY': {'net_gex_b': x}}, never a bare {'SPY': x})."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.12},'QQQ':{'net_gex_b':-3.1}})
    blocks['gamma']['flip']=item({'SPY':{'gamma_flip':775.3},'QQQ':{'gamma_flip':758.8}})
    summary=section_summary('gamma',blocks['gamma'])
    assert 'SPY' in summary and 'net GEX' in summary and '0.12' in summary
    assert 'QQQ' in summary and '-3.1' in summary
    assert '{' not in summary and '"' not in summary
    # A section with no bespoke builder still cites real values, as a sentence, never a dump.
    blocks['scanner']['minute_cadence']=item(5)
    generic=section_summary('scanner',blocks['scanner'])
    assert 'minute cadence' in generic.lower() and '5' in generic and generic[0].isupper()
    assert section_summary('profile',empty_blocks()['profile'])=='No verified observation yet this checkpoint.'

def test_section_summary_narrative_builders_cover_the_money_sections():
    """Each bespoke builder must actually fire (not silently fall back to the generic sentence)
    on realistic, production-shaped data -- this is what the live report screenshot pipeline
    renders, so a shape mismatch here is a shape mismatch on the real page."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Risk-on price confirmation')
    blocks['risk_on_defensive']['evidence']=item({'returns':{'SPY':0.60,'QQQ':0.49},
        'breadth':{'advances':319,'declines':184}})
    summary=section_summary('risk_on_defensive',blocks['risk_on_defensive'])
    assert 'leaning bullish' in summary and 'SPY' in summary and '319' in summary

    blocks['market_control']['control_side']=item({'SPY':{'0dte':'call_sellers','1_5dte':'call_sellers'}})
    blocks['market_control']['control_confidence']=item({'SPY':{'classified_contract_fraction':0.8,'label':'HIGH'}})
    summary=section_summary('market_control',blocks['market_control'])
    assert 'call sellers' in summary and 'high-confidence' in summary

    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH'})
    summary=section_summary('premium_selling',blocks['premium_selling'])
    assert 'premium is rich' in summary

    blocks['expected_move']['dollars']=item({'SPY':{'expected_move_dollars_1d':5.52}})
    blocks['expected_move']['percent']=item({'SPY':{'expected_move_pct_1d':0.71}})
    summary=section_summary('expected_move',blocks['expected_move'])
    assert '$5.52' in summary and '0.71%' in summary

    blocks['breadth']['advance_decline']=item({'advances':319,'declines':184})
    summary=section_summary('breadth',blocks['breadth'])
    assert '319' in summary and '184' in summary and 'advancing' in summary

    blocks['morning_comparison']['regime_shift']=item({'SPY':{'status':'CHANGED',
        'changed':['net GEX flipped positive to negative']}})
    summary=section_summary('morning_comparison',blocks['morning_comparison'])
    assert 'revisit the plan intraday' in summary and 'net GEX flipped' in summary

    blocks['day_strategy']['status']=item('ENTRY_READY')
    summary=section_summary('day_strategy',blocks['day_strategy'])
    assert 'every box is checked' in summary

def test_section_meaning_risk_on_defensive_reads_side_from_verdict():
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    assert 'protection' in section_meaning('risk_on_defensive',blocks['risk_on_defensive'])
    blocks['risk_on_defensive']['verdict']=item('Risk-on confirmation')
    assert 'upside' in section_meaning('risk_on_defensive',blocks['risk_on_defensive'])
    blocks['risk_on_defensive']['verdict']=item('Mixed signal')
    assert 'No clear directional bias' in section_meaning('risk_on_defensive',blocks['risk_on_defensive'])

def test_section_meaning_market_control_reads_dominant_side():
    blocks=empty_blocks()
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'inconclusive'},'QQQ':{'0dte':'inconclusive'}})
    assert 'too thin' in section_meaning('market_control',blocks['market_control'])
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'call_sellers','1_5dte':'call_sellers'},'QQQ':{'0dte':'put_sellers'}})
    assert 'Call sellers dominate' in section_meaning('market_control',blocks['market_control'])
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'put_sellers'}})
    assert 'Put sellers dominate' in section_meaning('market_control',blocks['market_control'])

def test_section_meaning_market_control_calls_back_to_mission_side():
    """Leron, 2026-10-10: "each section should flow into each [other]" -- market_control is
    the one section with its own real bull/bear-leaning read, so it explicitly agrees/
    conflicts with Today's Mission's verdict when given mission_side; every other section's
    line must not claim this (vol pricing, pipeline health etc. carry no real direction).
    Call sellers dominant = capped-upside read = agrees with a defensive mission call,
    conflicts with a risk-on one (and the reverse for put sellers dominant)."""
    blocks=empty_blocks()
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'call_sellers'}})
    agree=section_meaning('market_control',blocks['market_control'],'defensive')
    assert 'lines up with the defensive mission call' in agree
    conflict=section_meaning('market_control',blocks['market_control'],'risk-on')
    assert 'tension with the risk-on mission call' in conflict
    neutral_case=section_meaning('market_control',blocks['market_control'],'neutral')
    assert neutral_case=='Call sellers dominate where classified — a sign of capped upside expectations.'
    # No mission_side given at all -> no fabricated callback, same as before this change.
    bare=section_meaning('market_control',blocks['market_control'])
    assert bare=='Call sellers dominate where classified — a sign of capped upside expectations.'

def test_section_meaning_covers_former_bookkeeping_sections_honestly():
    """The 14 sections previously excluded from this layer now get a real line, but it must
    say what the section actually is (bookkeeping/audit) rather than inventing a market read."""
    blocks=empty_blocks()
    assert 'not advice on your account' in section_meaning('paper_scorecard',blocks['paper_scorecard'])
    assert 'never itself a market signal' in section_meaning('data_integrity',blocks['data_integrity'])
    assert 'not a market read' in section_meaning('scanner',blocks['scanner'])
    assert 'never treat it as today' in section_meaning('event_study',blocks['event_study'])

def test_section_meaning_gamma_reads_sign():
    """Real shape from merge_symbols(gamma,['net_gex_b'],now) is {"SPY":{"net_gex_b":x}},
    not {"SPY":x} — a flat fixture here passed against buggy code once already (live bug,
    caught visually 2026-10-09: "what it means" read blank despite a real net_gex value
    rendering right above it). Exercise the real nested shape, not a simplified one.
    """
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.5},'QQQ':{'net_gex_b':1.2}})
    assert 'Positive gamma dampens' in section_meaning('gamma',blocks['gamma'])
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':-0.5},'QQQ':{'net_gex_b':-1.2}})
    assert 'Negative gamma amplifies' in section_meaning('gamma',blocks['gamma'])
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.5},'QQQ':{'net_gex_b':-1.2}})
    assert 'mixed' in section_meaning('gamma',blocks['gamma'])
    # Flat shape must still work (back-compat / defensive, not the only shape relied on).
    blocks['gamma']['net_gex']=item({'SPY':0.5,'QQQ':1.2})
    assert 'Positive gamma dampens' in section_meaning('gamma',blocks['gamma'])

def test_section_meaning_flow_reads_classified_coverage():
    blocks=empty_blocks()
    blocks['flow']['classified_coverage']=item({'SPY':0.33,'QQQ':0.28})
    assert 'too thin' in section_meaning('flow',blocks['flow'])
    blocks['flow']['classified_coverage']=item({'SPY':0.8,'QQQ':0.7})
    assert 'supports a directional read' in section_meaning('flow',blocks['flow'])

def test_section_meaning_premium_selling_is_strategy_neutral():
    blocks=empty_blocks()
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH','QQQ':'PREMIUM_RICH'})
    meaning=section_meaning('premium_selling',blocks['premium_selling'])
    assert 'premium sellers' in meaning and 'spread' not in meaning.lower() and 'condor' not in meaning.lower()
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_CHEAP'})
    assert 'premium buyers' in section_meaning('premium_selling',blocks['premium_selling'])

def test_section_meaning_strategy_status_lookup():
    blocks=empty_blocks()
    blocks['day_strategy']['status']=item('ENTRY_READY')
    assert 'verify live per-leg BBO' in section_meaning('day_strategy',blocks['day_strategy'])
    blocks['near_forward_strategy']['status']=item('WATCH')
    assert 'not a trade' in section_meaning('near_forward_strategy',blocks['near_forward_strategy'])

def test_section_meaning_falls_back_to_static_role_for_generic_sections():
    assert 'sizing tool' in section_meaning('expected_move',empty_blocks()['expected_move'])
    assert 'not a standalone signal' in section_meaning('unknown_future_section',empty_blocks()['surface'])

def test_field_label_formats_dte_buckets_not_blind_underscore_replace():
    """A blind `_` -> ` ` replace turned "1_5dte" into "1 5dte" (reads as a typo) instead of
    "1-5 DTE". Confirmed live on multiple sections (control side, gamma/flow buckets, smile
    term fields) plus the gamma_expiry chart's own x-axis tick labels, 2026-10-09."""
    assert field_label('0dte')=='0 DTE'
    assert field_label('1_5dte')=='1-5 DTE'
    assert field_label('6_20dte')=='6-20 DTE'
    assert field_label('21_365dte')=='21-365 DTE'
    assert field_label('net_gex')=='net gex'  # ordinary fields unaffected
    # Prefixed buckets (Surface section's real field names) — the first version of this fix
    # only handled the bare bucket; re-checked live 2026-10-09 and every "term "/"iv " prefixed
    # field on the actual Surface section still read "term 1 5dte" / "iv 6 20dte".
    assert field_label('term_1_5dte')=='term 1-5 DTE'
    assert field_label('term_6_20dte')=='term 6-20 DTE'
    assert field_label('iv_21_365dte')=='iv 21-365 DTE'
    assert field_label('iv_0dte')=='iv 0 DTE'
    assert field_label('term_21plus')=='term 21plus'  # not a dte-bucket shape, left alone

def test_display_compact_drops_repeated_provenance_suffix_keeps_reliability_tag():
    """Edge board/scoreboard call display() once per cell; when 3 cells in one row share the
    exact same source timestamp (the common case — a registered-rule constant stamped once per
    report), the full "[LIVE NOW; updated ...; age ...]" suffix repeated 3x turned a '30-second
    scoreboard' into a wall of identical timestamps. compact=True keeps the LIVE/LAST KNOWN
    reliability signal (this report never hides staleness) but drops the verbose repeat."""
    live=item('WATCH')
    full=display(live);compact=display(live,compact=True)
    assert 'updated' in full and 'age' in full
    assert 'updated' not in compact and 'age' not in compact
    assert 'LIVE NOW' in compact and 'WATCH' in compact

def test_display_scalar_string_timestamp_value_shows_central_time():
    """Live bug, found 2026-10-10 in the markdown/Discord path: display()'s main value used
    bare str(value) for any non-dict/list field, so a field whose VALUE is itself a raw
    timestamp string (prior_hour_timestamp, heartbeat) showed bare UTC "+00:00" even though
    the same line's own "[updated ... CT; age ...]" suffix (built separately, a few lines
    down) already converted source_timestamp to Central Time -- the value and its own
    metadata disagreed on the hour."""
    ts_item=item(NOW.isoformat())
    rendered=display(ts_item)
    assert NOW.isoformat() not in rendered
    assert '2026-10-06 11:05:00 AM CT' in rendered

def test_evidence_no_longer_embeds_futures_context():
    """evidence used to embed blocks["futures_context"] wholesale, inside all three strategy
    sections. futures_context.basis is ALWAYS unavailable by design (same-time futures-vs-cash
    basis cannot be computed), and normalize_item()'s "any nested dependency unavailable ->
    mark this unavailable too" rule meant EVIDENCE could never report live/historical no matter
    how complete its own real chain data was. Live bug, confirmed 2026-10-09: EVIDENCE showed
    UNAVAILABLE directly above hundreds of lines of real strike/print data. It also tripled the
    page's futures_context weight for zero new information (the section has its own place)."""
    blocks=empty_blocks()
    core={'surface':{'SPY':{'confidence':'HIGH','source_timestamp':NOW.isoformat(),
            'surface_points':[{'expiration':NOW.date().isoformat(),'strike':774,'right':'call','iv':0.12,'dte':0}]}},
          'flow':{}}
    build_strategy_blocks(blocks,core,{},{},{'trade_details':[]},{},{},NOW)
    for name in ('day_strategy','near_forward_strategy','forward_strategy'):
        value=blocks[name]['evidence'].get('value')
        if isinstance(value,dict):assert 'futures_context' not in value

def test_catalysts_filtered_to_each_horizons_own_date_window():
    """The same full catalyst list used to repeat identically across all three horizons — a
    CPI release 6 days out showed under "today"'s catalysts. Each horizon now only carries
    catalysts whose date actually falls inside its own [from,through] window."""
    blocks=empty_blocks()
    blocks['event_calendar']['catalysts']=item([
        {'name':'Today event','impact':'MEDIUM','datetime':NOW.isoformat()},
        {'name':'CPI Report','impact':'HIGH','datetime':(NOW+timedelta(days=20)).isoformat()}])
    build_strategy_blocks(blocks,{'surface':{},'flow':{}},{},{},{'trade_details':[]},{},{},NOW)
    day_names={c['name'] for c in blocks['day_strategy']['catalysts']['value']}
    forward_names={c['name'] for c in blocks['forward_strategy']['catalysts']['value']}
    assert 'Today event' in day_names and 'CPI Report' not in day_names
    assert 'CPI Report' in forward_names

def test_catalysts_not_double_wrapped_after_horizon_filtering():
    """catalysts was already a fully observed()-wrapped dict (status/value/source/...); the
    generic per-field re-wrap loop wrapped it a second time, producing a field whose own
    "value" contained another full status/source/source_timestamp/age_seconds/reason block
    instead of the plain catalyst list. Live bug, confirmed 2026-10-09."""
    blocks=empty_blocks()
    blocks['event_calendar']['catalysts']=item([{'name':'Today event','impact':'MEDIUM','datetime':NOW.isoformat()}])
    build_strategy_blocks(blocks,{'surface':{},'flow':{}},{},{},{'trade_details':[]},{},{},NOW)
    value=blocks['day_strategy']['catalysts']['value']
    assert isinstance(value,list)
    assert all(isinstance(c,dict) and 'status' not in c for c in value)

def test_risk_exit_rules_points_to_position_management_not_duplicated_verbatim():
    """The same ~400-char fill/target/stop paragraph used to repeat verbatim in all three
    strategy sections plus a 4th time in Position Management (its canonical home)."""
    blocks=empty_blocks()
    paper={'trade_details':[],'fill_rules':'Enter at fresh executable natural BBO... (long paragraph)'}
    build_strategy_blocks(blocks,{'surface':{},'flow':{}},{},{},paper,{},{},NOW)
    for name in ('day_strategy','near_forward_strategy','forward_strategy'):
        rules=blocks[name]['risk_exit_rules']['value']
        assert rules!=paper['fill_rules']
        assert 'Position Management' in rules

def test_market_story_separates_fragments_with_sentence_stops():
    """Three independent fragments joined with bare spaces produced a run-on when a fragment
    was itself an UNAVAILABLE disclosure with no trailing punctuation: "...UNAVAILABLE — No
    timestamped observation Gamma sign is mixed..." reads as one broken sentence. Live bug,
    confirmed on the real intraday report 2026-10-09."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':0.5})
    story=market_story(blocks)
    assert 'observation Gamma sign' not in story  # the exact run-on seen live
    assert '. ' in story or story.count('.')>=2

def test_market_story_edge_board_traps_and_plan_use_real_block_values():
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH'})
    blocks['gamma']['net_gex']=item({'SPY':0.5})
    assert 'Defensive price confirmation' in market_story(blocks)
    for name in ('day_strategy','near_forward_strategy','forward_strategy'):
        blocks[name]['trigger']=item('No registered trigger')
        blocks[name]['invalidation']=item('No observed setup')
        blocks[name]['status']=item('WATCH')
    rows=edge_board(blocks)
    assert len(rows)==3 and rows[0][0]=='day strategy' and 'WATCH' in rows[0][3]
    blocks['event_calendar']['catalysts']={'status':'unavailable','reason':'partial calendar',
        'value':[{'name':'CPI Report','impact':'HIGH','datetime':'2026-10-14T07:30:00-05:00'}]}
    blocks['data_integrity']['unavailable_fields']=item([{'field':'x','reason':'y'}])
    traps=biggest_traps(blocks)
    # A data-completeness count is a different kind of fact than a market-risk event and no
    # longer belongs in the traps a trader scans (it stays in Data Integrity, not duplicated
    # here) — biggest_traps is market-risk catalysts only now.
    assert any('CPI Report' in t for t in traps)
    assert not any('unavailable this checkpoint' in t for t in traps)
    blocks['adaptation_rules']['activate']=item('Require the registered trigger')
    plan=if_then_day_plan(blocks)
    assert any(k=='Activate' and 'Require the registered trigger' in v for k,v in plan)

@freeze_time(NOW)
def test_ct_str_converts_raw_utc_to_central_time_not_bare_iso():
    """Leron (Texas, Central Time) read a report's top-of-page timestamp
    ("2026-10-09T15:10:43.895470+00:00") as a different, unlabeled hour and thought the report
    was stale/wrong-day — every OTHER timestamp on the page already converts to CT via
    display(), this was the one place still showing bare UTC. NOW=2026-10-06 16:05 UTC = 2026-10-06
    11:05 AM CT (October, CDT)."""
    assert ct_str(NOW.isoformat()) == '2026-10-06 11:05:00 AM CT'
    assert ct_str(None) == ''
    assert ct_str('not a timestamp') == 'not a timestamp'  # never crash, never fabricate

def test_render_markdown_title_line_shows_central_time_not_bare_utc():
    blocks=empty_blocks()
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)
    assert '2026-10-06 11:05:00 AM CT' in markdown
    assert NOW.isoformat() not in markdown

def test_horizon_comparison_cross_report_timestamps_are_central_time():
    """morning_baseline/prior_checkpoint embed another report's generated_at as a raw dict
    value (not through observed()/display()) — same bare-UTC bug as the page header, found
    live 2026-10-09 right after Leron flagged the header chip."""
    blocks=empty_blocks()
    morning={'report_id':'abc123','generated_at':NOW.isoformat(),'report_blocks':{}}
    prior={'report_id':'def456','generated_at':(NOW-timedelta(hours=1)).isoformat()}
    build_strategy_blocks(blocks,{'surface':{},'flow':{}},{},{},{'trade_details':[]},morning,prior,NOW)
    hc=blocks['horizon_comparison']
    assert hc['morning_baseline']['value']['timestamp']=='2026-10-06 11:05:00 AM CT'
    assert hc['prior_checkpoint']['value']['timestamp']=='2026-10-06 10:05:00 AM CT'
    assert NOW.isoformat() not in str(hc['morning_baseline']['value'])

def test_plain_value_irregular_dict_still_converts_embedded_timestamps():
    """Live bug, found 2026-10-09 in the post-deploy CT sweep: breadth has 18 keys (advances,
    coverage_pct, a nested vwap.rows keyed by symbol with its own source_timestamp, ...),
    over plain_value's len(v)<=10 cap, so the WHOLE dict fell straight to json.dumps() before
    any per-field ct_str() call ran — the one remaining bare-UTC leak after PR #3237/#3238,
    hiding inside raw JSON text instead of a normal field row."""
    breadth={f'field_{i}':i for i in range(12)}
    breadth['source_timestamp']=NOW.isoformat()
    breadth['vwap']={'above':3,'covered':5,'rows':{'SPY':{'above':True,'vwap':777.3,'close':778.5,
        'source_timestamp':NOW.isoformat(),'bars':378}}}
    rendered=plain_value(breadth)
    assert NOW.isoformat() not in rendered
    assert '2026-10-06 11:05:00 AM CT' in rendered

def test_render_markdown_adds_decision_lines_to_every_section_honestly():
    """Leron, 2026-10-10: "make the read detailed and fun to read... each section should
    flow into each [other]" -- every section gets the Section summary / What it means pair
    now, including former bookkeeping sections like Paper Scorecard, but the bookkeeping
    ones must say they're not a market read rather than inventing a signal."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':0.12})
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)
    gamma_section=markdown.split('### Gamma')[1].split('###')[0]
    assert 'Section summary:' in gamma_section and 'What it means for the day:' in gamma_section
    paper_section=markdown.split('### Paper Scorecard')[1].split('###')[0]
    assert 'Section summary:' in paper_section and 'What it means for the day:' in paper_section
    assert 'not advice on your account' in paper_section
    assert set(SECTION_SUMMARY_SECTIONS)==set(REQUIREMENTS)
    assert 'paper_scorecard' in SECTION_SUMMARY_SECTIONS

def test_render_opening_html_carries_decision_first_panels():
    """This is the function the live /view page and the email body actually render from —
    unlike render_markdown (Discord-only), a gap this catches by construction."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    blocks['adaptation_rules']['activate']=item('Require the registered trigger')
    opening=render_opening_html({'report_blocks':blocks})
    assert '<h2>🧭 Market story</h2>' in opening and 'Defensive price confirmation' in opening
    assert '<h2>🧩 Edge board</h2>' in opening
    assert '<h2>⚠️ Biggest traps</h2>' in opening
    assert '<h2>🧮 If/then day plan</h2>' in opening and 'Require the registered trigger' in opening

def test_opening_html_thesis_dict_breaks_into_labeled_lines_not_comma_runon():
    """Leron's screenshot, 2026-10-10: "near forward strategy" thesis (a dict with direction/
    volatility_context/meaning) rendered as one unbroken comma-joined sentence in the opening
    HTML table, immediately followed by the status field's own text with zero visual
    separation -- unreadable on a phone. The thesis dict must now render as separate labeled
    lines (one <div> per key), not plain_value()'s single comma-run-on string."""
    blocks=empty_blocks()
    thesis={'direction':'INCONCLUSIVE: no verified directional trade-time flow',
            'volatility_context':{'SPY':{'median_iv':0.151,'expiries':['2026-10-14']}},
            'meaning':'Observed expiry-specific option pricing supplies forward risk context.'}
    blocks['near_forward_strategy']['thesis']=item(thesis)
    blocks['near_forward_strategy']['status']=item('WATCH')
    opening=render_opening_html({'report_blocks':blocks})
    # The old bug: plain_value's comma join put "direction ..., volatility context ..., meaning
    # ..." all on one line with no tag between fields. The fix renders each key as its own div.
    assert opening.count('<div style="margin:4px 0">')>=3
    assert '<span style="color:#8b97a8">Direction:</span>' in opening
    assert '<span style="color:#8b97a8">Meaning:</span>' in opening

def test_opening_html_status_pill_is_separate_span_not_bracket_text():
    """The old display()-based cell glued "[LIVE NOW; updated ...; age ...]" onto the end of
    the value as plain bracket text, indistinguishable from the real content. The pill is now
    a styled <span>, visually and structurally separate from the value div."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    opening=render_opening_html({'report_blocks':blocks})
    assert '[LIVE NOW' not in opening
    assert 'color:#34d399' in opening  # live-status pill color
    assert '>LIVE<' in opening

def test_opening_html_flow_gamma_row_has_visual_divider_not_semicolon_join():
    """The old scoreboard() row did get("flow",...)+"; "+get("gamma",...) -- two different
    fields glued together with a semicolon, each carrying its own bracketed provenance tag,
    in one dense cell. The HTML version must visually separate them with a divider, not a
    semicolon in running text."""
    blocks=empty_blocks()
    blocks['flow']['classified_coverage']=item({'SPY':0.62})
    blocks['gamma']['net_gex']=item({'SPY':-0.04})
    opening=render_opening_html({'report_blocks':blocks})
    assert 'border-top:1px solid #2a3341' in opening

def test_opening_html_unavailable_item_still_shows_reason():
    """item_cell_html's unavailable branch must still surface the real reason text -- the
    rewrite must not silently drop unavailable-field disclosures."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']={'status':'unavailable','reason':'No source observation'}
    opening=render_opening_html({'report_blocks':blocks})
    assert 'No source observation' in opening
    assert 'color:#f87171' in opening  # unavailable-status color

def test_fmt_number_rounds_raw_float_precision():
    """Leron, 2026-10-10: "There is to many decimal places in the number it's need to be
    rounded" -- median_iv 0.15139485927028395 and net_gex_b -0.04018785705263146 (both from
    his screenshot) rendered at full float precision. Matches full_options_report._fmt_
    primitive's magnitude-tiered convention (0 decimals >=1000, 2 decimals >=1, 4 below)."""
    assert fmt_number(0.15139485927028395) == '0.1514'
    assert fmt_number(-0.04018785705263146) == '-0.0402'
    assert fmt_number(1234.5678) == '1,235'
    assert fmt_number(12.3456) == '12.35'

def test_plain_value_rounds_float_not_raw_repr():
    assert plain_value(0.15139485927028395) == '0.1514'
    assert plain_value({'median_iv': 0.15139485927028395}) == 'median iv 0.1514'

def test_narrative_html_rounds_float_not_raw_repr():
    """Same bug, opening-summary path: thesis.volatility_context.SPY.median_iv showed full
    float precision in the Today vs Forward card even after the run-on-sentence fix."""
    assert '0.1514' in narrative_html({'median_iv': 0.15139485927028395})
    assert '0.15139485927028395' not in narrative_html({'median_iv': 0.15139485927028395})
    assert '0.1514' in narrative_html({'SPY': {'median_iv': 0.15139485927028395}})

def test_positioning_panel_surfaces_walls_regime_and_premium_suitability():
    """Leron, 2026-10-10: "I need to be able to see during the day where the call sellers and
    put sellers are... Should I be playing long or should I be selling premium? And which
    strikes?" All of gamma.net_gex/walls and premium_selling.suitability already exist as
    contract fields -- this panel surfaces them at the top instead of leaving them buried in
    the Gamma/Market Control sections. No new REQUIREMENTS field, no new producer."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':11.91},'QQQ':{'net_gex_b':-0.2}})
    blocks['gamma']['walls']=item({'SPY':{'walls':{'top_call':[{'strike':780.0,'gex_b':1.0}],
        'top_put':[{'strike':779.0,'gex_b':-1.5}]}},'QQQ':{'walls':{'top_call':[],'top_put':[]}}})
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH','QQQ':'PREMIUM_CHEAP'})
    panel=positioning_panel_html(blocks)
    assert '📍 Positioning' in panel
    assert 'Positive gamma' in panel and 'favors selling premium' in panel  # SPY, net_gex_b>0
    assert 'Negative gamma' in panel and 'favors long/directional' in panel  # QQQ, net_gex_b<0
    assert 'Resistance (call wall):</span> 780.00' in panel
    assert 'Support (put wall):</span> 779.00' in panel
    assert 'Premium Rich' in panel and 'Premium Cheap' in panel

def test_positioning_panel_discloses_unavailable_premium_not_silent():
    """premium_selling.suitability is correctly unavailable pre-market (needs 60 min of
    realized trading data) -- the panel must say so, never silently omit the line or fabricate
    a suitability read."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.5}})
    panel=positioning_panel_html(blocks)
    assert 'unavailable' in panel.lower()
    assert 'PREMIUM_RICH' not in panel and 'PREMIUM_CHEAP' not in panel

def test_positioning_panel_who_is_selling_shows_thin_coverage_honestly():
    """market_control.control_side with every DTE bucket 'inconclusive' (thin classified flow
    coverage) must say so plainly, never fabricate a confident call/put-seller dominance read."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.5}})
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'inconclusive','1_5dte':'inconclusive'}})
    panel=positioning_panel_html(blocks)
    assert 'too thin to call' in panel

def test_positioning_panel_tolerates_flat_scalar_net_gex_shape():
    """Defensive: net_gex's real contract shape is {"SPY": {"net_gex_b": x}}, but the panel
    must not crash if a value ever arrives as a flat scalar {"SPY": x} instead."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':-0.04})
    panel=positioning_panel_html(blocks)
    assert 'Negative gamma' in panel

def test_positioning_panel_empty_when_no_data_available():
    blocks=empty_blocks()
    assert positioning_panel_html(blocks) == ''

def test_positioning_panel_shows_plan_status_changed_holding_and_first_report():
    """Leron, 2026-10-10: "it needs to be more nimble... the plan for the day but nimble to
    change intraday." Plan status must lead the panel so a regime flip since the morning
    report is announced, not left for the reader to notice by comparing two reports."""
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':-9.2},'QQQ':{'net_gex_b':0.5},'IWM':{'net_gex_b':0.5}})
    blocks['morning_comparison']['regime_shift']=item({
        'SPY':{'status':'CHANGED','changed':['net GEX flipped positive to negative']},
        'QQQ':{'status':'HOLDING','changed':[]},
        'IWM':{'status':'FIRST_REPORT','changed':[]}})
    panel=positioning_panel_html(blocks)
    assert 'Plan status: CHANGED since this morning' in panel and 'net GEX flipped positive to negative' in panel
    assert 'Plan status: HOLDING' in panel
    assert 'first read of the day' in panel

def test_render_opening_html_includes_positioning_panel_after_mission():
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':11.91}})
    opening=render_opening_html({'report_blocks':blocks})
    mission_idx=opening.index('Today’s mission')
    positioning_idx=opening.index('Positioning')
    scoreboard_idx=opening.index('30-second scoreboard')
    assert mission_idx<positioning_idx<scoreboard_idx

def test_plain_value_small_nested_payoff_never_collapses_to_item_count():
    """Live bug, found 2026-10-11 in Leron's screenshot of the Today's Mission panel: a
    contract package's payoff ({'max_risk':365.0,'max_reward':135.0,'breakeven':[768.65]}) is
    only 3 keys with one trivially small nested list, but it sits several levels deep inside
    contracts -> package -> value -> payoff -> breakeven. The depth>=4 (dict) / depth>=3 (list)
    cutoffs added for the raw-JSON-leak fix collapsed it to "breakeven [1 items]" instead of the
    real number -- a regression as bad as the bug it fixed, just quieter. There is no depth
    cutoff left; only the per-list item count protects against something actually unbounded."""
    payoff={'max_risk':365.0,'max_reward':135.0,'breakeven':[768.65]}
    text=plain_value(payoff,depth=4)
    assert '768.65' in text and '[1 items]' not in text and 'items]' not in text
    # Still protects against the real danger: a genuinely long flat list stays truncated.
    big=plain_value({'symbols':list(range(600))},depth=4)
    assert '(+588 more)' in big and big.count(',')<30

def test_narrative_package_html_reads_as_a_trade_idea_not_a_field_dump():
    """Leron, 2026-10-11, screenshot of the Today's Mission 'Best underlying / structure' row
    showing a raw per-leg field dump ("symbol SPY261013P00770000, action sell, right P, strike
    770.00, bid 1.62, ask 1.68, delta -0.2800..."): "I don't know how to read the information in
    this image." A qualified package list (day_strategy.contracts' real shape from
    qualify_package()) must now render as a plain-English trade sentence instead."""
    package={'strategy':'put_credit_spread','natural_credit':1.35,
        'legs':[{'symbol':'SPY261013P00770000','action':'sell','right':'P','strike':770.0,
                 'bid':1.62,'ask':1.68,'delta':-0.28},
                {'symbol':'SPY261013P00765000','action':'buy','right':'P','strike':765.0,
                 'bid':0.29,'ask':0.33,'delta':-0.14}],
        'payoff':{'max_risk':365.0,'max_reward':135.0,'breakeven':[768.65]},
        'qualification':'Fresh per-leg BBO; conditional advisory package, not a submitted order'}
    text=narrative_package_html(package)
    assert 'Sell the 770 put' in text and 'Buy the 765 put' in text
    assert 'collect $1.35' in text and 'Risk $365' in text and 'make $135' in text
    assert 'breakeven at $768.65' in text
    assert 'expiring 2026-10-13' in text
    # The raw per-leg noise from the screenshot must be gone.
    assert 'SPY261013P00770000' not in text and 'bid' not in text and 'delta' not in text

    # Integration: a list of these packages through narrative_html / item_cell_html (the actual
    # call path for day_strategy.contracts in render_opening_html's scoreboard) must use this
    # narrative path, not the generic per-item field dump.
    html_out=narrative_html([package])
    assert 'Sell the 770 put' in html_out and 'bid' not in html_out
    cell=item_cell_html(observed([package],'Qualified per-leg executable packages',NOW,NOW))
    assert 'Sell the 770 put' in cell and 'bid' not in cell

def test_narrative_setup_html_reads_as_a_trigger_not_a_17_field_dump():
    """Sibling bug to narrative_package_html's contracts fix: the Edge Board's Trigger column
    renders day_strategy.trigger, whose real shape is the FULL internal plan setup object --
    setup_id/symbol/strategy/thesis/entry/invalidation plus ~15 more fields (expiration_preference,
    profit_taking_framework, source_metadata, created_at, sessions, ...). Leron, 2026-10-11, "why
    do I feel like something is missing" right after the contracts fix shipped -- this is it."""
    setup={'setup_id':'cloud-spy-put_credit_spread','symbol':'SPY','strategy':'put_credit_spread',
        'thesis':'Dealers long gamma, range-bound, premium rich — sell the put wall',
        'entry':'Two 1-min closes above 775 with held retest','invalidation':'Break and hold below 770',
        'support_levels':[770.0],'resistance_levels':[790.0],'expiration_preference':'7-14 DTE',
        'target_delta_profile':'15-20 delta short strike','profit_taking_framework':'Take profit at 50% max credit',
        'max_risk_logic':'Defined-risk structure only.','main_risks':'Gap risk, event risk, and option liquidity at trigger time.',
        'thesis_reason':'Current evidence-supported setup.','catalyst':'No specific catalyst confirmed.',
        'source_metadata':{'engine':'cloud'},'created_at':'2026-10-13T12:00:00+00:00',
        'expires_at':'2026-10-13T20:00:00+00:00','sessions':['regular']}
    text=narrative_setup_html(setup)
    assert 'SPY put credit spread' in text
    assert 'Dealers long gamma' in text
    assert 'Enters on: Two 1-min closes above 775' in text
    assert 'Cancels if: Break and hold below 770' in text
    # The generic-catalyst placeholder is noise, not signal -- must not appear.
    assert 'No specific catalyst confirmed' not in text
    # None of the 12 supporting/bookkeeping fields leak through as labeled rows.
    for noise in ('Expiration preference', 'Profit taking framework', 'Source metadata',
                  'Created at', 'Sessions', 'Target delta profile', 'Max risk logic'):
        assert noise not in text

    html_out=narrative_html([setup])
    assert 'SPY put credit spread' in html_out and 'Expiration preference' not in html_out
    cell=item_cell_html(observed([setup],'Registered plan and isolated minute watcher',NOW,NOW))
    assert 'SPY put credit spread' in cell and 'Source metadata' not in cell

def test_decision_brief_flags_price_flow_conflict_and_names_the_clean_edge():
    """Leron, 2026-10-12: "all the decision making information and why should be at the
    beginning of every report, supporting information after" -- this is the exact walk-through
    he assembled by hand reading a live report end to end (regime, per-symbol gamma character,
    whether flow agrees or conflicts with the regime call, the one clean edge, Plan status),
    now automated as the report's lead section instead of chat-only."""
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Defensive price confirmation')
    blocks['gamma']['net_gex'] = item({'SPY': {'net_gex_b': 1.75}, 'QQQ': {'net_gex_b': -3.35}})
    blocks['day_strategy']['thesis'] = item({
        'SPY': {'read': 'upside pressure'}, 'QQQ': {'read': 'downside pressure'}})
    blocks['premium_selling']['suitability'] = item({'SPY': 'PREMIUM_RICH', 'QQQ': 'PREMIUM_FAIR'})
    blocks['morning_comparison']['regime_shift'] = item({
        'SPY': {'status': 'HOLDING'}, 'QQQ': {'status': 'HOLDING'}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'leaning defensive' in text
    assert 'SPY' in text and 'conflicts with the regime call' in text  # SPY flow fights the regime
    assert 'QQQ' in text and 'agrees with the regime call' in text  # QQQ flow confirms it
    # SPY is premium-rich AND conflicted -> no clean edge there; nothing else qualifies either.
    assert "nothing yet -- price and flow are fighting each other" in text
    assert 'holding since this morning' in text

    # Flip it: no conflict anywhere, SPY premium-rich and pinning -> names SPY as the clean edge.
    blocks['day_strategy']['thesis'] = item({
        'SPY': {'read': 'downside pressure'}, 'QQQ': {'read': 'downside pressure'}})
    lines2 = decision_brief_lines(blocks)
    text2 = ' '.join(lines2)
    assert 'agrees with the regime call' in text2
    assert 'the one clean edge right now is SPY premium-selling' in text2

    # No verdict yet -> nothing to synthesize, not a half-built section.
    assert decision_brief_lines(empty_blocks()) == []

def test_decision_brief_leads_both_renderers():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['gamma']['net_gex'] = item({'SPY': {'net_gex_b': 0.5}})
    payload = {'generated_at': NOW.isoformat(), 'kind': 'intraday', 'report_blocks': blocks,
               'report_completeness': 'INCOMPLETE'}
    md = render_markdown(payload)
    assert md.index('Decision brief') < md.index("Today’s mission")
    html_out = render_opening_html(payload)
    assert html_out.index('Decision brief') < html_out.index("Today’s mission")

def test_live_threshold_is_ten_minutes_not_ninety_seconds():
    """Leron, 2026-10-12: "i dont need them live at the exact instant as long as thier no
    older than 10 mins." Raised LIVE_MAX_AGE_SECONDS from 90 to 600 -- the shared constant
    report_policy.observed() and report_producers.observation() both key off, so a field
    refreshed by the last ~5-minute collection cycle now reads "live" instead of "historical"
    for display/completeness purposes. Deliberately NOT the same threshold as the
    options-execution BBO freshness gates (report_ledger.qualify_package,
    tradier_report_source's fill-sim check, intraday_watch.normalize_contract) -- those keep
    their own independent <=90s check; a quote too old to trust for a simulated fill and a
    report field too old to call "live" in the text are different risks."""
    assert LIVE_MAX_AGE_SECONDS == 600
    fresh_9min = observed(1.0, 'test', NOW - timedelta(seconds=540), NOW)
    assert fresh_9min['status'] == 'live'
    stale_11min = observed(1.0, 'test', NOW - timedelta(seconds=660), NOW)
    assert stale_11min['status'] == 'historical'

def test_week_ahead_outlook_connects_vol_catalysts_and_positioning():
    """Leron, 2026-10-12: 'the morning report has a lot of information and none of it is
    engaged' -- pre-market, most live sections are honestly empty/stale, so the writing alone
    can't fix it. This is a forward-looking, morning-only lead paragraph built from whatever
    IS real pre-market: last-known vol, the week-ahead IV read, upcoming catalysts, and
    carried-over gamma positioning -- 'outlook based' per his explicit ask, not a trade call.
    Re-added 2026-10-12 after a same-day revert (precautionary, during an unrelated outage)
    was never followed up with a re-ship."""
    blocks=empty_blocks()
    blocks['surface']['atm_iv']=item({'SPY':{'atm_iv':0.070}})
    blocks['surface']['term_21plus']=item({'SPY':{'iv_21_365dte':0.075}})
    blocks['near_forward_strategy']['thesis']=item({
        'direction':'INCONCLUSIVE: no verified directional trade-time flow',
        'volatility_context':{'SPY':{'median_iv':0.251,'expiries':['2026-10-14']}},
        'meaning':'Observed expiry-specific option pricing supplies forward risk context.'})
    blocks['event_calendar']['catalysts']=item([
        {'name':'CPI Report (Sep data)','datetime':'2026-10-14T12:30:00+00:00','impact':'HIGH'},
        {'name':'PPI Report (Sep data)','datetime':'2026-10-15T12:30:00+00:00','impact':'HIGH'}])
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.46}})
    blocks['gamma']['walls']=item({'SPY':{'walls':{'top_call':[{'strike':776.0}],'top_put':[{'strike':775.0}]}}})

    out=_week_ahead_outlook_html(blocks)
    assert '7.0% ATM' in out
    assert '25.1% median IV' in out and 'step up' in out  # connects the two vol reads, doesn't just list them
    assert 'CPI Report' in out and 'PPI Report' in out
    assert '776' in out and '775' in out
    assert 'invented ahead of the open' in out  # the honesty disclaimer stays

    # Nothing to synthesize -> no empty/half-built section.
    assert _week_ahead_outlook_html(empty_blocks())==''

    # Morning-only: the intraday report must never show this section.
    morning_payload={'kind':'morning','report_blocks':blocks}
    intraday_payload={'kind':'intraday','report_blocks':blocks}
    assert 'Week ahead outlook' in render_opening_html(morning_payload)
    assert 'Week ahead outlook' not in render_opening_html(intraday_payload)

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

def test_plain_value_caps_per_symbol_chain_list_not_raw_dump():
    """Same nested shape as the HTML _fmt_value fix (evidence.observed_expiry_points):
    field dict -> per-symbol dict -> list of ~100 chain-point dicts. Markdown/Discord
    rendering had no truncation at all for this shape (straight to json.dumps)."""
    big_list=[{'expiration':'2026-10-08','strike':float(700+i),'right':'call'} for i in range(80)]
    text=plain_value({'observed_expiry_points':{'SPY':big_list}})
    assert text.count('"expiration"')==0  # readable "key value" pairs, not raw json.dumps
    assert text.count('strike')==5  # exactly the 5 shown chain points, not all 80
    assert '+75 more' in text
