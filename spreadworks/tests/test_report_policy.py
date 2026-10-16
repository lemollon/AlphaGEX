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
                                   options_flow_story, dealer_positioning_story, surface_smile_story,
                                   expected_move_story, breadth_sector_story, macro_futures_story,
                                   since_this_morning_story, trade_volatility_scan_story,
                                   contract_packages_and_entry_watches_story, candidates_tracked_story,
                                   position_and_trigger_audit_story,
                                   edge_board, ranked_edge_board, scoreboard, biggest_traps, if_then_day_plan, SECTION_SUMMARY_SECTIONS,
                                   render_markdown, render_opening_html, plain_value, field_label, display,
                                   ct_str, fmt_number, narrative_html, positioning_panel_html,
                                   narrative_package_html, item_cell_html, narrative_setup_html,
                                   decision_brief_lines, _week_ahead_outlook_html, _what_changed_today_html,
                                   _control_side_narrative, _narrative_entry_watches,
                                   catalyst_vol_narrative, catalyst_vol_narrative_html,
                                   _structure_family_hint, _structure_family, _tv_structure_check,
                                   _thesis_sentence, _thesis_display_item,
                                   _narrative_strategy, _price_path_read)

NOW=datetime(2026,10,6,16,5,tzinfo=timezone.utc)

def empty_blocks():
    return {n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}

def item(value=1,age=0):
    return observed(value,'Observed provider feed',NOW-timedelta(seconds=age),NOW)

def test_schema_retains_all_legacy_fields_and_new_strategy_policy():
    assert len(REQUIREMENTS)==34
    # 243 + regime_label (risk_on_defensive) + regime_label_shift (morning_comparison), 2026-10-12,
    # + 5 trade_volatility_scan fields (top_long_setups, top_short_setups, income_setups,
    # put_call_ratio, expected_move_trend), 2026-10-13, + tv_structure_check (day_strategy
    # only -- reuses trade_volatility_scan's existing top_long_setups/top_short_setups
    # "structures" field, no new collector field needed), 2026-10-14, + profile.vwap, 2026-10-16.
    assert sum(map(len,REQUIREMENTS.values()))==252
    assert 'regime_shift' in REQUIREMENTS['morning_comparison']
    assert 'delivery_manifest' in REQUIREMENTS['visuals']
    assert all(n in REQUIREMENTS for n in ('day_strategy','near_forward_strategy','forward_strategy','horizon_comparison','adaptation_rules','data_integrity','market_control'))
    assert len(REQUIREMENTS['visuals'])==14
    assert REQUIREMENTS['market_control']==['control_side','control_evidence','control_confidence','forward_control_outlook']
    assert 'tv_structure_check' in REQUIREMENTS['day_strategy']
    assert 'tv_structure_check' not in REQUIREMENTS['near_forward_strategy']
    assert 'tv_structure_check' not in REQUIREMENTS['forward_strategy']

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

def test_narrative_flow_reads_the_real_nested_bucket_shape():
    """Live bug, found 2026-10-12 (Leron: "why is flow not working"): calls_bought/calls_sold/
    puts_bought/puts_sold's real per-symbol shape (confirmed against a live report) is
    {bucket: {'contracts': N, 'premium': P}} -- a dict per bucket, not a flat premium number.
    _narrative_flow summed row.values() through _num() directly, which is always False for a
    dict, so every symbol's total came out 0 and the section silently fell back to the generic
    mechanical summary (provider/timestamp metadata, no actual flow read) on every real report.
    This exact shape was missing from test_section_summary_narrative_builders_cover_the_money_
    sections above, which is how it shipped unnoticed."""
    block={'calls_bought':item({'SPY':{'0dte':{'contracts':2939,'premium':119089.0},
                                         '1_5dte':{'contracts':7,'premium':2062.0}},
                                 'QQQ':{'0dte':{'contracts':2781,'premium':171237.0}}}),
           'calls_sold':item({'SPY':{'0dte':{'contracts':5209,'premium':120240.0}}}),
           'puts_bought':item({'SPY':{'0dte':{'contracts':3186,'premium':145792.0}}}),
           'puts_sold':item({'SPY':{'0dte':{'contracts':4488,'premium':294719.0},
                                     '1_5dte':{'contracts':54,'premium':15413.0},
                                     '6_20dte':{'contracts':227,'premium':144415.0}}}),
           'price_vix_confirmation':item({'SPY':{'read':'conflicts'},'QQQ':{'read':'confirms'}})}
    summary=section_summary('flow',block)
    assert 'SPY flow is dominated by puts sold' in summary and '$454,547' in summary
    assert 'fighting the flow' in summary  # SPY read=conflicts
    assert 'QQQ flow is dominated by calls bought' in summary and '$171,237' in summary
    assert 'this one' in summary.lower() and 'clean' in summary.lower()  # QQQ read=confirms
    # Never the old fallback: provider/timestamp metadata is not a flow direction.
    assert 'provider provenance' not in summary.lower()

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

def test_market_story_carries_market_control_tie_in_to_mission_call():
    """Leron, 2026-10-10: "each section should flow into each [other]" -- market_control's
    agree/conflict callback to the mission verdict already existed (section_meaning), it just
    never reached the flagship Market story paragraph. Risk-on mission + call-sellers-dominant
    market_control is a genuine conflict; the tie-in sentence must say so, not just restate
    "call sellers dominate" in isolation."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Risk-on price confirmation')
    blocks['market_control']['control_side']=item({'SPY':{'horizon':'call_sellers'},'QQQ':{'horizon':'call_sellers'}})
    story=market_story(blocks,mission_side='risk-on',regime_label=None)
    assert 'Call sellers dominate' in story
    assert 'tension with the risk-on mission call above' in story

def _price_path_blocks(vwap):
    blocks=empty_blocks()
    blocks['profile']['val']=item({'SPY':{'val':776}})
    blocks['profile']['vah']=item({'SPY':{'vah':780}})
    blocks['profile']['poc']=item({'SPY':{'poc':778}})
    blocks['profile']['vwap']=item({'SPY':{'vwap':vwap}})
    blocks['expected_move']['reference_spot']=item({'SPY':{'spot':778}})
    return blocks

def test_price_path_read_flags_bullish_bias_when_spot_holds_above_vwap():
    story=_price_path_read(_price_path_blocks(750), 'SPY')
    assert 'Session VWAP is 750' in story
    assert 'holding above it' in story and 'bullish line' in story

def test_price_path_read_flags_bearish_bias_when_spot_sits_below_vwap():
    story=_price_path_read(_price_path_blocks(810), 'SPY')
    assert 'Session VWAP is 810' in story
    assert 'stuck below it' in story and 'bearish line' in story

def test_price_path_read_flags_no_edge_when_spot_is_glued_to_vwap():
    story=_price_path_read(_price_path_blocks(778), 'SPY')
    assert 'glued to it' in story and 'no intraday edge' in story

def test_options_flow_story_promotes_narrative_flow_to_top_level():
    """_narrative_flow's per-symbol dominant-flow-type + $ premium + price-confirms/conflicts
    read already existed and was already covered by test_narrative_flow_reads_the_real_nested_
    bucket_shape, but only ever surfaced in the per-field appendix under "### Flow" -- this
    promotes the same read (zero new producer fields) into its own top-level section."""
    blocks=empty_blocks()
    blocks['flow']['calls_bought']=item({'SPY':{'0dte':{'contracts':2939,'premium':119089.0}}})
    blocks['flow']['puts_sold']=item({'SPY':{'0dte':{'contracts':4488,'premium':294719.0}}})
    blocks['flow']['price_vix_confirmation']=item({'SPY':{'read':'confirms'}})
    story=options_flow_story(blocks)
    assert 'SPY flow is dominated by puts sold' in story and '$294,719' in story
    assert 'clean' in story.lower()

def test_options_flow_story_falls_back_when_coverage_too_thin():
    """_narrative_flow returns None when classified coverage can't support a direction --
    the top-level section must still render a plain disclosure, never an empty heading."""
    blocks=empty_blocks()
    story=options_flow_story(blocks)
    assert story=='Classified options flow coverage is too thin to read a direction right now.'

def test_render_markdown_and_html_carry_the_options_flow_section():
    blocks=empty_blocks()
    blocks['flow']['calls_bought']=item({'SPY':{'0dte':{'contracts':2939,'premium':119089.0}}})
    blocks['flow']['price_vix_confirmation']=item({'SPY':{'read':'confirms'}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 📊 Options flow' in md
    assert 'SPY flow is dominated by calls bought' in md
    html_out=render_opening_html(payload)
    assert '<h2>📊 Options flow</h2>' in html_out
    assert 'SPY flow is dominated by calls bought' in html_out

def test_dealer_positioning_story_promotes_narrative_market_control_to_top_level():
    """_narrative_market_control's per-symbol "who's running this today, how confident, does
    forward flow agree" read already existed and was already covered by section_summary's
    market_control test, but only ever surfaced in the per-field appendix under "### Market
    Control" -- this promotes the same read into its own top-level section, distinct from
    Market story's market_control fragment (that one is section_meaning's single aggregate
    agree/conflict sentence, not this per-symbol breakdown)."""
    blocks=empty_blocks()
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'call_sellers','1_5dte':'call_sellers'}})
    blocks['market_control']['control_confidence']=item({'SPY':{'classified_contract_fraction':0.8,'label':'HIGH'}})
    blocks['market_control']['forward_control_outlook']=item({'SPY':{'outlook':'persists'}})
    story=dealer_positioning_story(blocks)
    assert 'SPY is being run by call sellers today' in story
    assert 'high-confidence read' in story
    assert 'Forward flow agrees' in story

def test_dealer_positioning_story_falls_back_when_coverage_too_thin():
    """_narrative_market_control returns None when control_side is unavailable -- the
    top-level section must still render a plain disclosure, never an empty heading."""
    blocks=empty_blocks()
    story=dealer_positioning_story(blocks)
    assert story=="Dealer positioning is unclear today; classified flow coverage is too thin to say who's in control."

def test_render_markdown_and_html_carry_the_dealer_positioning_section():
    blocks=empty_blocks()
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'put_sellers'}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🏛️ Dealer positioning' in md
    assert 'SPY is being run by put sellers today' in md
    html_out=render_opening_html(payload)
    assert '<h2>🏛️ Dealer positioning</h2>' in html_out
    assert 'SPY is being run by put sellers today' in html_out

def test_surface_smile_story_combines_both_narrative_builders():
    """_narrative_surface's term-structure-shape + IV-vs-realized read and _narrative_smile's
    skew-lean read already existed and were already tested (section_summary coverage), but
    only ever surfaced separately in the per-field appendix under "### Surface" and "###
    Smile" -- this combines both into one top-level section, same promotion pattern as
    options_flow_story/dealer_positioning_story."""
    blocks=empty_blocks()
    blocks['surface']['atm_iv']=item({'SPY':{'atm_iv':.088}})
    blocks['surface']['term_0dte']=item({'SPY':{'iv_0dte':.15}})
    blocks['surface']['term_21plus']=item({'SPY':{'iv_21_365dte':.12}})
    blocks['smile']['atm_iv']=item({'SPY':{'atm_iv':.088}})
    blocks['smile']['put_25d_iv']=item({'SPY':{'put_25d_iv':.1}})
    blocks['smile']['call_25d_iv']=item({'SPY':{'call_25d_iv':.09}})
    story=surface_smile_story(blocks)
    assert "SPY's vol surface" in story and 'term structure' in story
    assert "SPY's skew" in story and 'puts are bid harder' in story

def test_surface_smile_story_falls_back_when_both_builders_return_none():
    blocks=empty_blocks()
    story=surface_smile_story(blocks)
    assert story=='Vol surface and skew coverage is too thin to read a shape right now.'

def test_render_markdown_and_html_carry_the_surface_smile_section():
    blocks=empty_blocks()
    blocks['surface']['atm_iv']=item({'SPY':{'atm_iv':.088}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 📐 Surface, smile & term structure' in md
    assert "SPY's vol surface" in md
    html_out=render_opening_html(payload)
    assert '<h2>📐 Surface, smile & term structure</h2>' in html_out
    assert 'vol surface: ATM IV 8.8%' in html_out  # escape() turns "SPY's" into "SPY&#x27;s"

def test_expected_move_story_promotes_narrative_expected_move_to_top_level():
    """_narrative_expected_move's per-symbol $/%/band read plus its budget-used framing
    already existed and was already tested (section_summary coverage), but only ever
    surfaced in the per-field appendix under "### Expected Move" -- same promotion pattern
    as options_flow_story/dealer_positioning_story/surface_smile_story."""
    blocks=empty_blocks()
    blocks['expected_move']['dollars']=item({'SPY':{'expected_move_dollars_1d':5.52}})
    blocks['expected_move']['percent']=item({'SPY':{'expected_move_pct_1d':0.71}})
    blocks['expected_move']['lower']=item({'SPY':{'expected_move_low':772.00}})
    blocks['expected_move']['upper']=item({'SPY':{'expected_move_high':783.04}})
    blocks['expected_move']['budget_used']=item({'SPY':{'absolute_move_fraction':0.92}})
    story=expected_move_story(blocks)
    assert "SPY's one-day expected move is $5.52" in story and '772.00-783.04 band' in story
    assert "already burned 92% of this morning's frozen move" in story

def test_expected_move_story_falls_back_when_coverage_too_thin():
    blocks=empty_blocks()
    story=expected_move_story(blocks)
    assert story=='Expected move coverage is too thin to read a band right now.'

def test_render_markdown_and_html_carry_the_expected_move_section():
    blocks=empty_blocks()
    blocks['expected_move']['dollars']=item({'SPY':{'expected_move_dollars_1d':5.52}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 📏 Expected move' in md
    assert "SPY's one-day expected move is $5.52" in md
    html_out=render_opening_html(payload)
    assert '<h2>📏 Expected move</h2>' in html_out
    assert 'one-day expected move is $5.52' in html_out  # escape() turns "SPY's" into "SPY&#x27;s"

def test_breadth_sector_story_combines_both_narrative_builders():
    """_narrative_breadth's advancers/decliners + up-down-volume + 52-week highs/lows read
    and _narrative_sector_credit's leaders/laggards + HYG-credit-confirmation read already
    existed and were already tested (section_summary coverage), but only ever surfaced
    separately in the per-field appendix under "### Breadth" and "### Sector Credit" --
    combines both into one top-level section, same pattern as surface_smile_story."""
    blocks=empty_blocks()
    blocks['breadth']['advance_decline']=item({'advances':2800,'declines':700})
    blocks['sector_credit']['relative_returns']=item({'XLK':1.2,'XLF':0.8,'XLE':0.3,'XLU':-0.9,'XLP':-0.5,'XLY':-0.1})
    story=breadth_sector_story(blocks)
    assert '2800 stocks are advancing against 700 declining' in story and 'broad and convincing' in story
    assert 'Leading today: XLK +1.20%' in story and 'Lagging: XLU -0.90%' in story

def test_breadth_sector_story_falls_back_when_both_builders_return_none():
    blocks=empty_blocks()
    story=breadth_sector_story(blocks)
    assert story=='Breadth and sector/credit coverage is too thin to read participation right now.'

def test_render_markdown_and_html_carry_the_breadth_sector_section():
    blocks=empty_blocks()
    blocks['breadth']['advance_decline']=item({'advances':2800,'declines':700})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🌐 Breadth, sectors & credit' in md
    assert '2800 stocks are advancing against 700 declining' in md
    html_out=render_opening_html(payload)
    assert '<h2>🌐 Breadth, sectors & credit</h2>' in html_out
    assert '2800 stocks are advancing against 700 declining' in html_out

def test_macro_futures_story_combines_both_narrative_builders():
    """_narrative_macro's 10-year yield + 2s10s curve + MOVE + dollar-index read and
    _narrative_futures_context's ES/NQ overnight-range read already existed and were already
    tested (section_summary coverage), but only ever surfaced separately in the per-field
    appendix under "### Macro" and "### Futures Context" -- combines both into one top-level
    section, same pattern as surface_smile_story/breadth_sector_story."""
    blocks=empty_blocks()
    blocks['macro']['rates']=item({'rates_10y':{'symbol':'DGS10','price':4.12}})
    blocks['macro']['curve']=item({'10y_minus_2y_basis_points':-25})
    blocks['futures_context']['es_mes']=item({'ES':{'price':5820.25}})
    story=macro_futures_story(blocks)
    assert 'Macro backdrop: the 10-year yield is 4.12%' in story and 'curve is inverted' in story
    assert 'ES is at 5820.25' in story

def test_macro_futures_story_falls_back_when_both_builders_return_none():
    blocks=empty_blocks()
    story=macro_futures_story(blocks)
    assert story=='Macro and futures coverage is too thin to read a backdrop right now.'

def test_render_markdown_and_html_carry_the_macro_futures_section():
    blocks=empty_blocks()
    blocks['macro']['rates']=item({'rates_10y':{'symbol':'DGS10','price':4.12}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🏦 Macro & futures context' in md
    assert 'the 10-year yield is 4.12%' in md
    html_out=render_opening_html(payload)
    assert '<h2>🏦 Macro & futures context</h2>' in html_out
    assert 'the 10-year yield is 4.12%' in html_out

def test_since_this_morning_story_promotes_narrative_morning_comparison_to_top_level():
    """_narrative_morning_comparison's per-symbol HOLDING/CHANGED/FIRST_REPORT regime-shift
    read already existed and was already tested (section_summary coverage), but only ever
    surfaced in the per-field appendix under "### Morning Comparison" -- same promotion
    pattern as options_flow_story/dealer_positioning_story."""
    blocks=empty_blocks()
    blocks['morning_comparison']['regime_shift']=item({'SPY':{'status':'CHANGED','changed':['flipped from risk-on to defensive']},
                                                         'QQQ':{'status':'HOLDING'}})
    story=since_this_morning_story(blocks)
    assert 'SPY has moved since this morning: flipped from risk-on to defensive' in story
    assert 'QQQ is holding the same read as this morning' in story

def test_since_this_morning_story_falls_back_when_no_prior_checkpoint():
    blocks=empty_blocks()
    story=since_this_morning_story(blocks)
    assert story=='No prior checkpoint to compare against yet this report.'

def test_render_markdown_and_html_carry_the_since_this_morning_section():
    blocks=empty_blocks()
    blocks['morning_comparison']['regime_shift']=item({'SPY':{'status':'HOLDING'}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🕒 Since this morning' in md
    assert 'SPY is holding the same read as this morning' in md
    html_out=render_opening_html(payload)
    assert '<h2>🕒 Since this morning</h2>' in html_out
    assert 'SPY is holding the same read as this morning' in html_out

def test_trade_volatility_scan_story_promotes_narrative_to_top_level():
    """_narrative_trade_volatility_scan's best-long/best-short/best-income setup + put/call-
    ratio + expected-move-trend read already existed and was already tested (section_summary
    coverage), but only ever surfaced in the per-field appendix under "### Trade Volatility
    Scan" -- this is literally answering Leron's own questions ("which stock shows the best
    opportunity to go long", "is [put/call] widening or collapsing") that were buried there."""
    blocks=empty_blocks()
    blocks['trade_volatility_scan']['top_long_setups']=item([
        {'ticker':'AUPH','opportunity_score':7.3,'opportunity_tier':'moderate',
         'structures':['long_equity','long_calls'],'entry_trigger':'Buy pullbacks toward the 20-day average while it holds'},
    ])
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.36,'change_30day':-0.43}})
    story=trade_volatility_scan_story(blocks)
    assert 'Best long setup: AUPH (7.3/10, moderate)' in story
    assert 'SPY put/call ratio (OI) is 1.36, down 0.43 over 30 days' in story

def test_trade_volatility_scan_story_falls_back_when_coverage_too_thin():
    blocks=empty_blocks()
    story=trade_volatility_scan_story(blocks)
    assert story=='TradingVolatility scan coverage is too thin to surface a ranked setup right now.'

def test_render_markdown_and_html_carry_the_trade_volatility_scan_section():
    blocks=empty_blocks()
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.36}})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🔭 TradingVolatility top setups' in md
    assert 'SPY put/call ratio (OI) is 1.36' in md
    html_out=render_opening_html(payload)
    assert '<h2>🔭 TradingVolatility top setups</h2>' in html_out
    assert 'SPY put/call ratio (OI) is 1.36' in html_out

def test_contract_packages_and_entry_watches_story_combines_both_builders():
    """_narrative_contract_packages's qualified-structure (strikes, credit/debit, max risk/
    reward) read and _narrative_entry_watches's per-setup trigger-lifecycle read already
    existed and were already tested, but only ever surfaced separately in the per-field
    appendix under "### Contract Packages" and "### Entry Watches" -- combines both into one
    top-level section, same pattern as surface_smile_story."""
    blocks=empty_blocks()
    blocks['contract_packages']['legs']=item([{'setup_id':'day','strategy':'put_credit_spread','value':[{'strike':780},{'strike':775}]}])
    blocks['contract_packages']['debit_credit']=item([{'setup_id':'day','value':{'natural_credit':1.25}}])
    blocks['contract_packages']['max_risk_reward']=item([{'setup_id':'day','value':{'max_risk':375,'max_reward':125}}])
    blocks['entry_watches']['trigger']=item([{'symbol':'SPY','setup_id':'day','state':'ENTRY_READY'}])
    story=contract_packages_and_entry_watches_story(blocks)
    assert 'Put Credit Spread at 775/780' in story and 'collects $1.25' in story and 'risking $375 to make $125' in story
    assert 'SPY setup day is just confirmed and ready' in story

def test_contract_packages_and_entry_watches_story_falls_back_when_both_builders_return_none():
    blocks=empty_blocks()
    story=contract_packages_and_entry_watches_story(blocks)
    assert story=='No qualified contract packages or registered entry watches right now.'

def test_render_markdown_and_html_carry_the_contract_packages_entry_watches_section():
    blocks=empty_blocks()
    blocks['entry_watches']['trigger']=item([{'symbol':'SPY','setup_id':'day','state':'WATCH'}])
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 📦 Contract packages & entry watches' in md
    assert 'SPY setup day is still on watch, not confirmed yet' in md
    html_out=render_opening_html(payload)
    assert '<h2>📦 Contract packages & entry watches</h2>' in html_out
    assert 'SPY setup day is still on watch, not confirmed yet' in html_out

def test_candidates_tracked_story_promotes_narrative_candidate_analysis_to_top_level():
    """_narrative_candidate_analysis's symbol-roster + qualified-package-count + registered-
    trigger-count read already existed and was already tested, but only ever surfaced in the
    per-field appendix under "### Candidate Analysis"."""
    blocks=empty_blocks()
    blocks['candidate_analysis']['symbols']=item(['SPY','QQQ'])
    blocks['candidate_analysis']['liquidity']=item([{'strategy':'put_credit_spread'}])
    blocks['candidate_analysis']['conditional_triggers']=item([{'setup_id':'s1'}])
    story=candidates_tracked_story(blocks)
    assert story=='Tracking 2 symbols: SPY, QQQ. 1 qualified contract package currently live. 1 registered conditional trigger on file.'

def test_candidates_tracked_story_falls_back_when_coverage_too_thin():
    blocks=empty_blocks()
    story=candidates_tracked_story(blocks)
    assert story=='No candidates currently being tracked.'

def test_render_markdown_and_html_carry_the_candidates_tracked_section():
    blocks=empty_blocks()
    blocks['candidate_analysis']['symbols']=item(['SPY','QQQ'])
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 🔍 Candidates tracked' in md
    assert 'Tracking 2 symbols: SPY, QQQ' in md
    html_out=render_opening_html(payload)
    assert '<h2>🔍 Candidates tracked</h2>' in html_out
    assert 'Tracking 2 symbols: SPY, QQQ' in html_out

def test_position_and_trigger_audit_story_combines_both_builders():
    """_narrative_position_management's open-paper-risk + quote-exception read and
    _narrative_trigger_accountability's registered/verified-trigger + loss-cluster read
    already existed and were already tested, but only ever surfaced separately in the
    per-field appendix under "### Position Management" and "### Trigger Accountability"."""
    blocks=empty_blocks()
    blocks['position_management']['risk_exposure']=item({'open_max_defined_risk':420.0,'quantity_model':'x'})
    blocks['trigger_accountability']['registered_triggers']=item([{'setup_id':'s1'},{'setup_id':'s2'}])
    blocks['trigger_accountability']['verified_occurrence']=item(1)
    story=position_and_trigger_audit_story(blocks)
    assert '$420 of paper capital is at risk across open positions right now' in story
    assert '2 registered triggers on file, 1 verified ENTRY_READY alert fired' in story

def test_position_and_trigger_audit_story_falls_back_when_both_builders_return_none():
    blocks=empty_blocks()
    story=position_and_trigger_audit_story(blocks)
    assert story=='No open paper positions or registered triggers to audit right now.'

def test_render_markdown_and_html_carry_the_position_trigger_audit_section():
    blocks=empty_blocks()
    blocks['position_management']['risk_exposure']=item({'open_max_defined_risk':420.0})
    payload={'report_blocks':blocks,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','chart_urls':{}}
    md=render_markdown(payload)
    assert '## 📋 Position & trigger audit' in md
    assert '$420 of paper capital is at risk' in md
    html_out=render_opening_html(payload)
    assert '<h2>📋 Position & trigger audit</h2>' in html_out
    assert '$420 of paper capital is at risk' in html_out

def test_market_story_carries_premium_selling_narrative_not_flat_label():
    """market_story's premium fragment was just the flat suitability label ("SPY:
    PREMIUM_RICH"); _narrative_premium_selling's richer per-symbol IV/realized-ratio +
    forward-implications read already existed and was already tested, same pattern as the
    risk_on_defensive/market_control fragments added in the original enrichment."""
    blocks=empty_blocks()
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH'})
    blocks['premium_selling']['iv_rv_meaning_today']=item({'SPY':{'ratio':1.35}})
    story=market_story(blocks)
    assert 'premium is rich' in story and 'IV/realized ratio 1.35' in story

def test_market_story_edge_board_traps_and_plan_use_real_block_values():
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH'})
    blocks['gamma']['net_gex']=item({'SPY':0.5})
    assert 'leaning defensive' in market_story(blocks)  # derived from the literal verdict's "Defensive"
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
    # Leron (Texas): "the report should be on central time." biggest_traps() used a raw
    # str() on the catalyst datetime, leaking the unlabeled ISO offset ("...-05:00") straight
    # onto the page instead of the same "HH:MM AM/PM CT" format every other clock in the
    # report uses.
    assert any('2026-10-14 07:30:00 AM CT' in t for t in traps)
    assert not any('-05:00' in t for t in traps)
    blocks['adaptation_rules']['activate']=item('Require the registered trigger')
    plan=if_then_day_plan(blocks)
    assert any(k=='Activate' and 'Require the registered trigger' in v for k,v in plan)

def test_edge_board_carries_the_qualified_contract_strike_and_expiration():
    """Leron: "the edge board is not providing strike or expirations." Each horizon's
    build_strategy_blocks()-computed contracts field already carries the qualified package;
    the Edge Board table (markdown and HTML) just never rendered it."""
    blocks=empty_blocks()
    blocks['day_strategy']['trigger']=item('No registered trigger')
    blocks['day_strategy']['invalidation']=item('No observed setup')
    blocks['day_strategy']['status']=item('WATCH')
    blocks['day_strategy']['contracts']=item([{'strategy':'put_credit_spread','expiration':'2026-10-06',
        'legs':[{'strike':580,'action':'sell'},{'strike':575,'action':'buy'}],'natural_credit':1.25}])
    rows=edge_board(blocks)
    assert len(rows)==3 and len(rows[0])==5
    assert '580' in rows[0][4] and '575' in rows[0][4]
    # The ranked Edge Board (2026-10-14) replaced the old 3-row table with a ranked,
    # multi-candidate list that has no separate Contracts column -- the strikes now live in
    # the candidate's Evidence text instead, never dropped.
    ranked=ranked_edge_board(blocks)
    day_row=next(r for r in ranked if 'put credit spread' in r[1])
    assert '580' in day_row[2] and '575' in day_row[2]
    html_out=render_opening_html({'kind':'intraday','generated_at':NOW.isoformat(),'report_blocks':blocks})
    assert '<th>Evidence</th>' in html_out and '580' in html_out and '575' in html_out

def test_ranked_edge_board_ranks_a_confirmed_registered_setup_above_a_range_idea_above_no_trade():
    """Leron, 2026-10-14 (a ChatGPT mockup he's building toward): the Edge Board should be a
    RANKED list of competing ideas across symbols, with "No trade" an explicit, ranked
    competitor instead of an unstated default. ENTRY_READY beats a contained-range read,
    which beats "No trade" -- same ordering the mockup showed."""
    blocks=empty_blocks()
    blocks['day_strategy']['status']=item('ENTRY_READY')
    blocks['day_strategy']['trigger']=item([{'symbol':'QQQ','level':742.75,'direction':'above'}])
    blocks['day_strategy']['contracts']=item([{'strategy':'call_debit_spread','expiration':'2026-10-14','legs':[]}])
    blocks['day_strategy']['thesis']=item('Risk-on price confirmation')
    blocks['profile']['val']=item({'SPY':{'val':776.9},'QQQ':{'val':741.5}})
    blocks['profile']['vah']=item({'SPY':{'vah':778.3},'QQQ':{'vah':743.75}})
    blocks['profile']['poc']=item({'SPY':{'poc':777.65},'QQQ':{'poc':743.125}})
    blocks['gamma']['walls']=item({'SPY':{'walls':{'top_call':[{'strike':778.0}],'top_put':[{'strike':777.0}]}},
                                    'QQQ':{'walls':{'top_call':[{'strike':744.0}],'top_put':[{'strike':741.0}]}}})
    ranked=ranked_edge_board(blocks)
    statuses=[r[5] for r in ranked]
    assert statuses[0]=='ENTRY_READY'  # the confirmed setup ranks first
    assert statuses[-1]=='READY'  # No trade ranks last when real candidates exist
    assert ranked[0][0]==1 and ranked[-1][0]==len(ranked)  # Rank column is sequential
    assert any(r[1]=='No trade' for r in ranked)
    assert any('SPY range structure' in r[1] for r in ranked)
    assert any('QQQ range structure' in r[1] for r in ranked)

def test_ranked_edge_board_puts_no_trade_first_when_nothing_else_qualifies():
    blocks=empty_blocks()  # every field unavailable -- no registered setup, no profile/gamma coverage
    ranked=ranked_edge_board(blocks)
    assert len(ranked)==1
    assert ranked[0]==(1,'No trade','Evidence and executable packages incomplete.',
                        'Remains the default while other triggers conflict or remain unconfirmed.',
                        'Opportunity cost.','READY')

def test_ranked_edge_board_skips_pending_evidence_but_keeps_watch():
    blocks=empty_blocks()
    blocks['day_strategy']['status']=item('PENDING EVIDENCE')
    blocks['near_forward_strategy']['status']=item('WATCH')
    blocks['near_forward_strategy']['thesis']=item('Defensive price confirmation')
    ranked=ranked_edge_board(blocks)
    setups=[r[1] for r in ranked]
    assert not any('day strategy' in s for s in setups)  # PENDING EVIDENCE has nothing to rank
    assert any('near forward strategy' in s for s in setups)  # WATCH still competes

def test_scoreboard_adds_live_price_rows_from_change_vs_baselines_but_not_iwm():
    """Leron, 2026-10-14 (ChatGPT mockup): live SPY/QQQ/VIX price rows on the 30-second
    scoreboard -- "778.37, +0.09% from baseline; fresh at ...". Built entirely from
    risk_on_defensive.change_vs_baselines, already required and populated for exactly this.
    IWM has no row -- market_comparison() only ever iterates core['surface'], SPY/QQQ-only;
    an honest IWM number doesn't exist yet."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['change_vs_baselines']=item({
        'SPY':{'current_spot':778.37,'price_change_pct':0.0915,'current_source_timestamp':'2026-10-02T14:59:23+00:00'},
        'QQQ':{'current_spot':743.59,'price_change_pct':0.41,'current_source_timestamp':'2026-10-02T14:59:22+00:00'},
        'VIX':{'current_spot':15.18,'price_change_pct':-0.85,'current_source_timestamp':'2026-10-02T14:59:46+00:00'},
    })
    rows=scoreboard(blocks)
    labels=[r[0] for r in rows]
    assert 'SPY' in labels and 'QQQ' in labels and 'VIX' in labels and 'IWM' not in labels
    spy_text=next(r[1] for r in rows if r[0]=='SPY')
    assert spy_text=='778.37, +0.09% from baseline; fresh at 09:59:23 AM CT'
    html_out=render_opening_html({'report_blocks':blocks})
    assert '778.37, +0.09% from baseline' in html_out

def test_scoreboard_no_trade_condition_mirrors_the_top_ranked_edge_board_candidate():
    """The No-trade condition row must never drift out of sync with the ranked Edge Board
    it summarizes -- it IS that board's own top candidate, not a separately-computed read."""
    blocks=empty_blocks()
    rows=scoreboard(blocks)
    no_trade_row=next(r for r in rows if r[0]=='No-trade condition')
    top=ranked_edge_board(blocks)[0]
    assert no_trade_row[1]==f"Top-ranked: {top[1]} ({top[5]}). {top[3]} {top[2]}".strip()
    assert no_trade_row[1]=='Top-ranked: No trade (READY). Remains the default while other triggers conflict or remain unconfirmed. Evidence and executable packages incomplete.'
    html_out=render_opening_html({'report_blocks':blocks})
    assert 'No-trade condition' in html_out and 'Top-ranked: No trade' in html_out

def test_macro_yield_shows_day_over_day_change_not_just_a_snapshot():
    """Leron, 2026-10-13: "what is the yield on treasury how has it changed... what does it
    mean for today and the future" -- a bare level answers "what" but not "changed". Reuses
    the same 14-day FRED window collect_macro() already fetches; no new data source."""
    blocks=empty_blocks()
    blocks['macro']['rates']=item({'rates_10y':{'symbol':'DGS10','price':4.12,'unit':'percent annual yield',
        'change_1day_bp':3.0,'prior_observation_date':'2026-10-10'}})
    summary=section_summary('macro',blocks['macro'])
    assert 'up 3bp day-over-day' in summary

def test_macro_and_futures_context_summaries_use_real_numbers_not_a_field_dump():
    """Leron: macro/futures read as "a wall of words." Both sections had no bespoke narrative
    builder and fell to the generic field:value recap, which recited the raw nested
    observation dicts (symbol/price/unit/observation_date per tenor) as a run-on sentence."""
    blocks=empty_blocks()
    blocks['macro']['rates']=item({'rates_10y':{'symbol':'DGS10','price':4.12,'unit':'percent annual yield'}})
    blocks['macro']['curve']=item({'10y_minus_2y_basis_points':-25})
    blocks['macro']['move']=item({'move':{'symbol':'^MOVE','price':95.3}})
    blocks['macro']['dollar']=item({'dollar':{'symbol':'DX-Y.NYB','price':103.2}})
    macro_summary=section_summary('macro',blocks['macro'])
    assert '4.12' in macro_summary and 'inverted' in macro_summary and '95.3' in macro_summary and '103.2' in macro_summary
    assert 'symbol' not in macro_summary.lower()  # no raw field-name leakage from the old generic fallback

    blocks['futures_context']['es_mes']=item({'ES':{'price':5820.25}})
    blocks['futures_context']['overnight_range']=item({'ES':{'overnight_low':5800.0,'overnight_high':5840.0}})
    blocks['futures_context']['nq']=item({'NQ':{'price':20500.5}})
    futures_summary=section_summary('futures_context',blocks['futures_context'])
    assert '5820.25' in futures_summary and '5800.00' in futures_summary and '20500.50' in futures_summary

def test_bookkeeping_sections_get_real_counts_not_boilerplate_meaning():
    """Leron: candidate_analysis/position_management/trigger_accountability "tell me nothing."
    Their section_meaning always fell straight to the fixed role sentence, never the section's
    own real values, even though real counts (open risk, registered triggers, confirmed
    setups) were already computed and sitting right there."""
    blocks=empty_blocks()
    blocks['candidate_analysis']['symbols']=item(['SPY','QQQ'])
    blocks['candidate_analysis']['liquidity']=item([{'strategy':'put_credit_spread'}])
    blocks['candidate_analysis']['conditional_triggers']=item([{'setup_id':'s1'}])
    assert '2 tracked symbols' in section_meaning('candidate_analysis',blocks['candidate_analysis'])
    assert 'Tracking 2 symbols: SPY, QQQ' in section_summary('candidate_analysis',blocks['candidate_analysis'])

    blocks['position_management']['risk_exposure']=item({'open_max_defined_risk':420.0,'quantity_model':'x'})
    blocks['position_management']['chain_qualification']=item({'rule':'x','exceptions':[{'reason':'y'}]})
    assert '$420' in section_meaning('position_management',blocks['position_management'])
    assert '$420' in section_summary('position_management',blocks['position_management'])

    blocks['trigger_accountability']['registered_triggers']=item([{'setup_id':'s1'},{'setup_id':'s2'}])
    blocks['trigger_accountability']['verified_occurrence']=item(1)
    blocks['trigger_accountability']['loss_clusters']=item([[{'a':1},{'a':2}]])
    # verified_occurrence is a cumulative all-time count, not bounded to today's n registered
    # triggers -- live production showed 8 verified alerts against only 5 registered (verified
    # > registered), so the meaning line must not phrase this as an "X of N" fraction.
    assert '2 registered triggers on file; 1 verified alert' in section_meaning('trigger_accountability',blocks['trigger_accountability'])
    assert '1 verified ENTRY_READY alert' in section_summary('trigger_accountability',blocks['trigger_accountability'])

    blocks['entry_watches']['trigger']=item([{'state':'ENTRY_READY'},{'state':'WATCH'}])
    assert '1 of 2 registered setups just confirmed ENTRY_READY' in section_meaning('entry_watches',blocks['entry_watches'])

def test_entry_watches_never_dumps_a_corrupted_nonscalar_state():
    """Live bug, found 2026-10-13 on a real intraday report: the watcher's persisted
    per_symbol_state occasionally carries a non-scalar 'state' (the raw tick-history list)
    instead of one row's enum string. str(state) on that blob produced the exact "wall of
    words" complaint -- a run-on dump of nested confirmation-evidence bars. Any non-string
    state must degrade to "status unclear", never get stringified."""
    blocks=empty_blocks()
    corrupted_state=[{'confirmation_evidence':[{'close':741.7,'timestamp':'2026-10-13T15:05:00+00:00'}],
                       'option_strike_selection':None,'reason':'waiting','setup_id':'x','state':'NEAR_TRIGGER'}]
    blocks['entry_watches']['trigger']=item([{'symbol':'QQQ','setup_id':'s1','state':corrupted_state}])
    summary=section_summary('entry_watches',blocks['entry_watches'])
    assert 'status unclear' in summary
    assert 'confirmation_evidence' not in summary and 'NEAR_TRIGGER' not in summary
    meaning=section_meaning('entry_watches',blocks['entry_watches'])
    assert 'status is unclear' in meaning

def test_futures_context_unwraps_the_extra_observation_layer_some_producer_paths_leave():
    """Live bug, found 2026-10-13 on a real intraday report: the macro-fallback producer path
    (used when stored_futures() has no quality quote) leaves one extra observation()-wrapper
    layer on each symbol's row -- {'es': {'value': {'price':...}, 'status':...}} -- instead of
    the single-wrapped {'ES': {'price':...}} shape stored_futures() produces. Both must read."""
    blocks=empty_blocks()
    blocks['futures_context']['es_mes']=item({'es':{'value':{'symbol':'ES=F','price':7844.0},
        'status':'historical','source':'Yahoo Finance delayed 5-minute bars','confidence':'MEDIUM'}})
    summary=section_summary('futures_context',blocks['futures_context'])
    assert '7844.00' in summary
    assert 'symbol' not in summary.lower() and 'confidence' not in summary.lower()

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

def test_render_markdown_threads_the_flat_regime_label_into_put_call_tie_in():
    """2026-10-14: render_markdown computes regime_label the same way decision_brief_lines
    already does and must pass it into section_meaning, not just mission_side -- otherwise the
    trade_volatility_scan tie-in silently falls back to the old hedged wording on every real
    report even though regime_label is sitting right there in risk_on_defensive."""
    blocks=empty_blocks()
    blocks['risk_on_defensive']['verdict']=item('Defensive price confirmation')
    blocks['risk_on_defensive']['regime_label']=item('DEFENSIVE')
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.4}})
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)
    tv_section=markdown.split('### Trade Volatility Scan')[1].split('###')[0]
    assert 'flat DEFENSIVE regime call' in tv_section

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

def test_control_side_narrative_groups_buckets_instead_of_listing_them():
    """Leron, 2026-10-12, content review: rated the report 8/10 but flagged the positioning
    panel's "Who's selling: 0 DTE mixed, 1-5 DTE call sellers" line as the one spot still
    reading like a raw field dump next to everything else now being prose. Same-side buckets
    now merge into one clause instead of listing every bucket mechanically."""
    assert _control_side_narrative({'0dte':'mixed','1_5dte':'call_sellers'})== \
        '0 DTE too mixed to call a side; Call sellers control 1-5 DTE'
    assert _control_side_narrative({'0dte':'put_sellers','1_5dte':'put_sellers','6_20dte':'put_sellers'})== \
        'Put sellers control 0 DTE, 1-5 DTE, and 6-20 DTE'
    assert _control_side_narrative({'0dte':'call_sellers','1_5dte':'put_sellers'})== \
        'Call sellers control 0 DTE; Put sellers control 1-5 DTE'
    assert _control_side_narrative({})is None

    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':{'net_gex_b':0.5}})
    blocks['market_control']['control_side']=item({'SPY':{'0dte':'mixed','1_5dte':'call_sellers'}})
    panel=positioning_panel_html(blocks)
    assert '0 DTE too mixed to call a side; Call sellers control 1-5 DTE' in panel
    assert '0 DTE mixed, 1-5 DTE call sellers' not in panel  # the old mechanical join is gone

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

def test_decision_brief_vix_contradiction_risk_on_up_blocks_clean_edge():
    """Leron, 2026-10-12: "build the contradiction-calling" -- VIX up while price rallies is a
    hedging-demand contradiction. Also confirms it overrides a clean edge that gamma/suitability
    would otherwise have named (SPY premium-rich + pinning + no SPY/QQQ flow conflict)."""
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['gamma']['net_gex'] = item({'SPY': {'net_gex_b': 1.75}, 'QQQ': {'net_gex_b': 0.5}})
    blocks['day_strategy']['thesis'] = item({
        'SPY': {'read': 'upside pressure'}, 'QQQ': {'read': 'upside pressure'}})
    blocks['premium_selling']['suitability'] = item({'SPY': 'PREMIUM_RICH', 'QQQ': 'PREMIUM_FAIR'})
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': 5.0, 'baseline_session_matches': True}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX: up +5.0% while price rallies -- hedging demand against the move, a real contradiction.' in text
    # Without the VIX override, SPY would be named the one clean edge -- confirm it is not.
    assert 'the one clean edge right now is SPY' not in text
    assert "nothing yet -- price and flow are fighting each other" in text

def test_decision_brief_vix_contradiction_defensive_down():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Defensive price confirmation')
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': -4.2, 'baseline_session_matches': True}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX: down -4.2% while price sells off -- no fear behind the drop, a real contradiction.' in text

def test_decision_brief_vix_move_below_threshold_no_contradiction():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': 1.5, 'baseline_session_matches': True}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX:' not in text

def test_decision_brief_vix_stale_baseline_gated_out_even_if_pct_is_large():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': 9.0, 'baseline_session_matches': False}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX:' not in text

def test_decision_brief_vix_neutral_regime_gated_out():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Mixed signal')
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': 9.0, 'baseline_session_matches': True}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX:' not in text

def test_decision_brief_vix_row_missing_entirely_no_exception():
    # Old reports before this change, or still-building change_vs_baselines without 'VIX'.
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'SPY': {'price_change_pct': 2.0}})

    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert 'VIX:' not in text
    assert 'leaning bullish' in text  # rest of the brief unaffected

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

def test_decision_brief_flat_regime_label_no_shift():
    """Leron, 2026-10-12: "come out and say if its risk on day, choppy day, defensive day" --
    with a real regime_label and no recorded shift, the opening line is the bare flat label,
    not the old hedge phrasing."""
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['risk_on_defensive']['regime_label'] = item('RISK-ON')
    lines = decision_brief_lines(blocks)
    assert lines[0] == 'RISK-ON.'

def test_decision_brief_flat_regime_label_changed_since_morning():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Mixed signal')
    blocks['risk_on_defensive']['regime_label'] = item('CHOPPY')
    blocks['morning_comparison']['regime_label_shift'] = item({
        'morning_label': 'RISK-ON', 'prior_hour_label': 'RISK-ON', 'current_label': 'CHOPPY',
        'changed_since_morning': True, 'changed_since_prior_hour': True})
    lines = decision_brief_lines(blocks)
    assert lines[0] == 'CHOPPY -- changed from RISK-ON since this morning.'

def test_decision_brief_flat_regime_label_changed_since_prior_hour_only():
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Defensive price confirmation')
    blocks['risk_on_defensive']['regime_label'] = item('DEFENSIVE')
    blocks['morning_comparison']['regime_label_shift'] = item({
        'morning_label': 'DEFENSIVE', 'prior_hour_label': 'CHOPPY', 'current_label': 'DEFENSIVE',
        'changed_since_morning': False, 'changed_since_prior_hour': True})
    lines = decision_brief_lines(blocks)
    assert lines[0] == 'DEFENSIVE -- changed from CHOPPY last hour.'

def test_decision_brief_without_regime_label_falls_back_to_hedged_mood():
    """Old-shape blocks (or regime_label left unavailable) must keep the pre-existing hedged
    phrasing, and regime_side must still resolve off the verdict text so every other branch
    (flow-conflict detection, the VIX-contradiction block) is unaffected."""
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Defensive price confirmation')
    lines = decision_brief_lines(blocks)
    assert lines[0] == 'Regime: price is leaning defensive.'

def test_decision_brief_regime_label_mapping_still_gates_vix_contradiction():
    """regime_label='RISK-ON' must map to regime_side='risk-on' exactly like the old
    verdict-text parse did -- the VIX-contradiction block (gated on regime_side != 'neutral')
    must still fire with an explicit regime_label present, not just the legacy verdict text."""
    blocks = empty_blocks()
    blocks['risk_on_defensive']['verdict'] = item('Risk-on price confirmation')
    blocks['risk_on_defensive']['regime_label'] = item('RISK-ON')
    blocks['gamma']['net_gex'] = item({'SPY': {'net_gex_b': 1.75}, 'QQQ': {'net_gex_b': 0.5}})
    blocks['day_strategy']['thesis'] = item({
        'SPY': {'read': 'upside pressure'}, 'QQQ': {'read': 'upside pressure'}})
    blocks['premium_selling']['suitability'] = item({'SPY': 'PREMIUM_RICH', 'QQQ': 'PREMIUM_FAIR'})
    blocks['risk_on_defensive']['change_vs_baselines'] = item({'VIX': {
        'price_change_pct': 5.0, 'baseline_session_matches': True}})
    lines = decision_brief_lines(blocks)
    text = ' '.join(lines)
    assert lines[0] == 'RISK-ON.'
    assert 'VIX: up +5.0% while price rallies -- hedging demand against the move, a real contradiction.' in text
    assert 'the one clean edge right now is SPY' not in text

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

def test_what_changed_today_reports_morning_and_prior_hour_price_moves():
    """Leron, 2026-10-12: 'share what has changed of the course of the day from morning to
    the prior hourly reports.' Pulls the real market_comparison() output horizon_comparison.
    changes already computes against both baselines -- verified against today's actual live
    report data, shape included verbatim here (horizon_comparison.changes.value is
    {'morning': {sym: {...}}, 'prior_hour': {sym: {...}}}, each with price_change_pct,
    morning_spot/current_spot and a morning_timestamp -- 'morning' in the prior_hour dict
    means "that baseline's own timestamp", not literally this morning)."""
    blocks=empty_blocks()
    blocks['horizon_comparison']['changes']=item({
        'morning':{'SPY':{'price_change_pct':-0.0565,'morning_spot':778.57,'current_spot':778.13,
                           'morning_timestamp':'2026-10-12T12:35:05.608853+00:00'},
                   'QQQ':{'price_change_pct':-0.6036,'morning_spot':751.27,'current_spot':746.735,
                           'morning_timestamp':'2026-10-12T12:35:05.608853+00:00'}},
        'prior_hour':{'SPY':{'price_change_pct':-0.0892,'morning_spot':778.825,'current_spot':778.13,
                              'morning_timestamp':'2026-10-12T16:10:40.386640+00:00'},
                      'QQQ':{'price_change_pct':-0.1064,'morning_spot':747.53,'current_spot':746.735,
                             'morning_timestamp':'2026-10-12T16:10:40.386640+00:00'}}})
    blocks['morning_comparison']['regime_shift']=item({
        'SPY':{'status':'CHANGED','changed':['control shifted from call_sellers to put_sellers']},
        'QQQ':{'status':'HOLDING','changed':[]}})

    out=_what_changed_today_html(blocks)
    assert '-0.06% since the' in out and '778.57' in out and '778.13' in out
    assert '-0.09% since the' in out and 'checkpoint' in out
    assert '-0.60%' in out and '-0.11%' in out  # QQQ both deltas present
    assert 'control shifted from call_sellers to put_sellers' in out  # SPY CHANGED surfaces
    assert out.count('positioning shifted') == 1  # only SPY (CHANGED), not QQQ (HOLDING)

    # No comparable baseline yet (first report of the day) -> no half-built section.
    assert _what_changed_today_html(empty_blocks()) == ''

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

def test_render_markdown_section_summary_sections_read_as_prose_not_raw_field_dump():
    """2026-10-12 fix, Leron repeatedly: "a long boring ass scroll of data that means nothing
    to me." The raw "- **field**: value" bullet for every field of every section used to print
    BEFORE the one-line narrative summary each section already had; now a section in
    SECTION_SUMMARY_SECTIONS gets only the narrative + "What it means for the day" line, no
    raw per-field wall underneath it."""
    blocks=empty_blocks()
    blocks['surface']['atm_iv']=item({'SPY':{'atm_iv':.088},'QQQ':{'atm_iv':.091}})
    blocks['surface']['term_0dte']=item({'SPY':{'iv_0dte':.15},'QQQ':{'iv_0dte':.14}})
    blocks['surface']['term_21plus']=item({'SPY':{'iv_21_365dte':.12},'QQQ':{'iv_21_365dte':.11}})
    blocks['smile']['atm_iv']=item({'SPY':{'atm_iv':.088}})
    blocks['smile']['put_25d_iv']=item({'SPY':{'put_25d_iv':.1}})
    blocks['smile']['call_25d_iv']=item({'SPY':{'call_25d_iv':.09}})
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)

    surface_section=markdown.split('### Surface')[1].split('###')[0]
    assert 'Section summary: '+section_summary('surface',blocks['surface']) in surface_section
    assert 'What it means for the day: ' in surface_section
    assert "ATM IV 8.8%" in surface_section  # the real narrative sentence, not a field dump
    assert '- **atm_iv**:' not in surface_section
    assert '- **term_0dte**:' not in surface_section

    smile_section=markdown.split('### Smile')[1].split('###')[0]
    assert 'Section summary: '+section_summary('smile',blocks['smile']) in smile_section
    assert '- **atm_iv**:' not in smile_section
    assert '- **put_25d_iv**:' not in smile_section

    # Every one of the 33 REQUIREMENTS sections is currently in SECTION_SUMMARY_SECTIONS, so
    # the raw-field-bullet `else` branch never fires anywhere -- the old dump pattern should
    # not survive in ANY "### "-headed section. (The "## Ifthen day plan" bullets use the same
    # "- **" markdown syntax but a different, unrelated, untouched loop over adaptation_rules
    # keys -- that text sits in the chunk BEFORE the first "### " split, never inside one.)
    assert set(SECTION_SUMMARY_SECTIONS)==set(REQUIREMENTS)
    for chunk in markdown.split('### ')[1:]:
        assert '- **' not in chunk
    assert len(markdown) < 20000  # a real populated report used to run 250k+ chars on this dump

def test_render_markdown_empty_section_gets_generic_fallback_not_unavailable_wall():
    """A section with zero populated data must still read as one honest sentence via
    _generic_narrative_summary's fallback, never a wall of "UNAVAILABLE" bullets -- the whole
    point of the fix was removing exactly that wall."""
    blocks=empty_blocks()
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)
    profile_section=markdown.split('### Profile')[1].split('###')[0]
    assert 'No verified observation yet this checkpoint.' in profile_section
    assert 'UNAVAILABLE' not in profile_section
    assert '- **' not in profile_section

def test_narrative_entry_watches_normal_states_read_as_prose():
    block={'trigger':item([
        {'symbol':'SPY','setup_id':'s1','state':'ENTRY_READY'},
        {'symbol':'QQQ','setup_id':'s2','state':'WATCH'}])}
    summary=_narrative_entry_watches(block)
    assert 'SPY setup s1 is just confirmed and ready.' in summary
    assert 'QQQ setup s2 is still on watch, not confirmed yet.' in summary

def test_narrative_entry_watches_tolerates_state_as_list_dict_or_none():
    """Production bug, 2026-10-13: the entry_watches producer in full_options_report.py was
    assigning the WHOLE per-symbol state list (runtime['per_symbol_state'][symbol], a list of
    every setup's state row for that symbol) into the single 'state' field instead of this
    setup's own scalar state. GET /api/spreadworks/reports/{id}/view then 500'd with
    `TypeError: cannot use 'list' as a dict key` inside state_word.get(state, ...). This must
    never crash regardless of what shape 'state' arrives in, and must still produce a sane
    (if unglamorous) sentence -- not blow up the whole report render."""
    for bad_state in ([{'setup_id':'s1','state':'WATCH'}], {'setup_id':'s1'}, None):
        block={'trigger':item([{'symbol':'SPY','setup_id':'s1','state':bad_state}])}
        summary=_narrative_entry_watches(block)  # must not raise TypeError
        assert summary is not None
        assert 'SPY setup s1 is' in summary
    # None specifically falls back to the explicit "status unclear" wording.
    none_block={'trigger':item([{'symbol':'SPY','setup_id':'s1','state':None}])}
    assert 'status unclear' in _narrative_entry_watches(none_block)
    # section_summary (the real call path from render_markdown/report_view) must also survive
    # end-to-end through the exact same dict-shaped bug state.
    blocks=empty_blocks()
    blocks['entry_watches']['trigger']=item([{'symbol':'SPY','setup_id':'s1','state':{'bad':'shape'}}])
    assert section_summary('entry_watches',blocks['entry_watches']) is not None

def test_catalyst_vol_narrative_names_the_catalyst_and_favors_selling_premium_when_rich():
    """Leron, 2026-10-13: "what future events... is the market going to be paused until the
    catalyst, is it best to sell premium, if so what strikes and expirations." This is the new
    morning-only narrative paragraph answering that -- built entirely from already-computed
    fields (event_calendar, risk_on_defensive.regime_label, profile.acceptance_rejection,
    surface, premium_selling), never a new number, and it must point at the Edge Board for the
    actual strike/expiration rather than inventing one here."""
    blocks=empty_blocks()
    blocks['event_calendar']['catalysts']=item([
        {'name':'CPI Report','impact':'HIGH','datetime':'2026-10-15T07:30:00-05:00'},
        {'name':'Low impact thing','impact':'LOW','datetime':'2026-10-14T07:30:00-05:00'},
    ])
    blocks['risk_on_defensive']['regime_label']=item('CHOPPY')
    blocks['profile']['acceptance_rejection']=item({'SPY':{'location':'inside value'},'QQQ':{'location':'inside value'}})
    blocks['premium_selling']['suitability']=item({'SPY':'PREMIUM_RICH'})
    narrative=catalyst_vol_narrative(blocks)
    assert 'CPI Report' in narrative and '2026-10-15' in narrative
    assert 'Low impact thing' not in narrative  # LOW impact never leads the catalyst call
    assert 'chopping inside' in narrative
    # Favors selling premium, but points at the Edge Board for the real strike/expiration
    # rather than computing one here -- it never picks its own level.
    assert 'sell-the-quiet-before-the-event' in narrative
    assert 'Edge Board' in narrative

    html_out=catalyst_vol_narrative_html(blocks)
    assert 'Catalyst' in html_out and 'CPI Report' in html_out

def test_trade_volatility_scan_narrative_and_meaning_surface_tv_ranked_opportunities():
    """Leron, 2026-10-13: "which stock show the best opprotunity to go long... what are the
    strikes and expirations", "put call ratio does is support the read", "is it widenening or
    collapsing". Confirms the new trade_volatility_scan section reads as prose with real
    TradingVolatility numbers, and is clearly attributed as their engine's call, not this
    report's own signal."""
    blocks=empty_blocks()
    blocks['trade_volatility_scan']['top_long_setups']=item([
        {'ticker':'AUPH','opportunity_score':7.3,'opportunity_tier':'moderate',
         'structures':['long_equity','long_calls'],'entry_trigger':'Buy pullbacks toward the 20-day average while it holds'},
    ])
    blocks['trade_volatility_scan']['top_short_setups']=item([
        {'ticker':'CANE','opportunity_score':6.7,'opportunity_tier':'moderate',
         'structures':['long_puts'],'entry_trigger':'As momentum stalls and the stretch starts to fade'},
    ])
    blocks['trade_volatility_scan']['income_setups']=item([
        {'ticker':'GME','strategy':'csp','strike':21.5,'dte':30,'annualized_yield':0.249,'income_score':9},
    ])
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.36,'change_30day':-0.43}})
    blocks['trade_volatility_scan']['expected_move_trend']=item({'SPY':{'trend':'collapsing','iv_rank_now':9.1,'iv_rank_30d_ago':16.2}})

    summary=section_summary('trade_volatility_scan',blocks['trade_volatility_scan'])
    assert 'AUPH' in summary and '7.3/10' in summary and 'long equity' in summary
    assert 'CANE' in summary and 'long puts' in summary
    assert 'GME 21.5 CSP' in summary and '24.9% annualized yield' in summary
    assert 'put/call ratio' in summary.lower() and '1.36' in summary and 'down 0.43' in summary
    assert 'collapsing' in summary

    meaning=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'])
    assert 'AUPH' in meaning and 'CANE' in meaning
    assert "not this report's own signal" in meaning  # third-party attribution, never claimed as our call

def test_structure_family_hint_is_textbook_vol_regime_not_a_fabricated_edge():
    """Leron, 2026-10-13: "what are the option strateiges to trade today based on market
    condition butterflies, calendar, ircon condor, debit or credit spreads." Standard
    options-theory correspondence only (rich+contained -> defined-risk premium selling,
    cheap -> long premium) -- never a directional pick, never a backtested claim."""
    blocks = empty_blocks()
    # No premium_selling data at all -> no hint, not a guess.
    assert _structure_family_hint(blocks) is None

    blocks['premium_selling']['suitability'] = item({'SPY': 'PREMIUM_RICH'})
    blocks['profile']['acceptance_rejection'] = item({'SPY': {'location': 'inside value'}})
    hint = _structure_family_hint(blocks)
    assert 'iron condor' in hint and 'contained range' in hint

    blocks['profile']['acceptance_rejection'] = item({'SPY': {'location': 'above value'}})
    hint = _structure_family_hint(blocks)
    assert 'directional credit spread' in hint and "isn't contained" in hint

    blocks['premium_selling']['suitability'] = item({'SPY': 'PREMIUM_CHEAP'})
    assert 'debit spread' in _structure_family_hint(blocks)

def test_structure_family_normalizes_vendor_vs_registered_naming():
    """TradingVolatility's own vocabulary ("credit_spread") and our registered setup vocabulary
    ("put_credit_spread") are the same structure family and must not read as a disagreement."""
    assert _structure_family('credit_spread') == _structure_family('put_credit_spread')
    assert _structure_family('Iron Condor') == _structure_family('iron_condor')
    assert _structure_family('calendar') == _structure_family('double_calendar')
    assert _structure_family('debit_spread') != _structure_family('iron_condor')
    assert _structure_family(None) is None

def test_tv_structure_check_flags_disagreement_without_touching_the_registered_setup():
    """Leron, 2026-10-14: reuse TradingVolatility's own per-ticker structure pick (the
    top_long_setups/top_short_setups "structures" field trade_volatility_scan/engine_consensus
    already surface -- /market-structure does not carry one) for SPY/QQQ's day plan, and flag
    -- never overwrite -- when it disagrees with the registered Edge Board setup."""
    blocks = empty_blocks()
    blocks['trade_volatility_scan']['top_long_setups'] = item([
        {'ticker': 'SPY', 'structures': ['iron_condor'], 'opportunity_score': 6.1},
        {'ticker': 'QQQ', 'structures': ['long_call'], 'opportunity_score': 7.4},
    ])
    setup_list = [{'symbol': 'SPY', 'strategy': 'put_credit_spread'},
                  {'symbol': 'QQQ', 'strategy': 'calendar'}]
    original_setup_list = copy.deepcopy(setup_list)
    check = _tv_structure_check(blocks, setup_list)

    # SPY: TradingVolatility says iron_condor, registered setup is put_credit_spread -- same
    # family, agrees.
    assert check['SPY']['agreement'] == 'agrees'
    assert check['SPY']['tv_structure'] == 'iron_condor'
    assert check['SPY']['registered_structure'] == 'put_credit_spread'

    # QQQ: TradingVolatility says long_call, registered setup is calendar -- different
    # families, disagrees, and the note names both calls explicitly.
    assert check['QQQ']['agreement'] == 'disagrees'
    assert "TradingVolatility's engine suggests long_call" in check['QQQ']['note']
    assert 'registered setup is calendar' in check['QQQ']['note']

    # The registered setup list itself is never mutated -- comparison only, no silent override.
    assert setup_list == original_setup_list

def test_tv_structure_check_checks_both_long_and_short_ranked_lists():
    """SPY/QQQ can surface in either /top-setups ranking (long or short); both are TradingVolatility's
    own engine output and must be checked, not just the long list."""
    blocks = empty_blocks()
    blocks['trade_volatility_scan']['top_short_setups'] = item([
        {'ticker': 'QQQ', 'structures': ['put_debit_spread'], 'opportunity_score': 8.0},
    ])
    check = _tv_structure_check(blocks, [{'symbol': 'QQQ', 'strategy': 'call_credit_spread'}])
    assert check['QQQ']['tv_structure'] == 'put_debit_spread'
    assert check['QQQ']['agreement'] == 'disagrees'

def test_tv_structure_check_is_honest_when_one_side_is_missing():
    blocks = empty_blocks()  # TradingVolatility unavailable / SPY and QQQ didn't rank into either list
    check = _tv_structure_check(blocks, [{'symbol': 'SPY', 'strategy': 'iron_condor'}])
    assert check['SPY']['agreement'] == 'tv_unavailable'
    assert check['SPY']['registered_structure'] == 'iron_condor'

    blocks['trade_volatility_scan']['top_long_setups'] = item([{'ticker': 'SPY', 'structures': ['calendar']}])
    check = _tv_structure_check(blocks, [])  # no registered setup at all
    assert check['SPY']['agreement'] == 'no_registered_setup'
    assert check['SPY']['registered_structure'] is None
    assert check['QQQ']['agreement'] == 'no_data'

def test_tv_structure_check_defaults_include_vix():
    """Leron, 2026-10-14: "add VIX structure" -- VIX rarely has a registered Edge Board
    setup, so it almost always lands in no_data/no_registered_setup, same as any other
    ticker with no registration; that's expected, not a bug."""
    blocks = empty_blocks()
    check = _tv_structure_check(blocks, [])
    assert 'VIX' in check
    assert check['VIX']['agreement'] == 'no_data'

    blocks['trade_volatility_scan']['top_long_setups'] = item([{'ticker': 'VIX', 'structures': ['long_call']}])
    check = _tv_structure_check(blocks, [{'symbol': 'VIX', 'strategy': 'iron_condor'}])
    assert check['VIX']['tv_structure'] == 'long_call'
    assert check['VIX']['agreement'] == 'disagrees'

def test_day_strategy_only_carries_tv_structure_check_not_near_or_forward():
    """The vendor's structure pick reflects today's regime, not the 2-5 session or 1-4 week
    horizons -- the comparison field is day_strategy-only by contract."""
    blocks = empty_blocks()
    blocks['trade_volatility_scan']['top_long_setups'] = item([
        {'ticker': 'SPY', 'structures': ['iron_condor']}, {'ticker': 'QQQ', 'structures': ['calendar']}])
    build_strategy_blocks(blocks, {'surface': {}, 'flow': {}}, {}, {}, {'trade_details': []}, {}, {}, NOW)
    assert blocks['day_strategy']['tv_structure_check']['status'] == 'live'
    assert 'tv_structure_check' not in blocks['near_forward_strategy']
    assert 'tv_structure_check' not in blocks['forward_strategy']

def test_narrative_strategy_surfaces_disagreement_sentence_only_when_structures_differ():
    block = {'status': item('WATCH'),
             'tv_structure_check': item({
                 'SPY': {'agreement': 'disagrees',
                         'note': "SPY: TradingVolatility's engine suggests iron_condor while the registered setup is calendar."}})}
    sentence = _narrative_strategy(block)
    assert "TradingVolatility's engine suggests iron_condor while the registered setup is calendar" in sentence

    agreeing_block = {'status': item('WATCH'),
                       'tv_structure_check': item({'SPY': {'agreement': 'agrees', 'note': 'SPY: agrees.'}})}
    agreeing_sentence = _narrative_strategy(agreeing_block)
    assert 'TradingVolatility' not in agreeing_sentence

def test_trade_volatility_scan_meaning_ties_put_call_ratio_to_the_mission_call():
    """Leron, 2026-10-13: "put call ratio does is support the read on the markets future
    positioning" -- same cross-section tie-in pattern market_control already does against
    mission_side, applied to SPY's put/call ratio."""
    blocks=empty_blocks()
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.4}})
    tension=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'],mission_side='risk-on')
    assert 'put-heavy' in tension and 'in tension with' in tension

    agree=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'],mission_side='defensive')
    assert 'put-heavy' in agree and 'agreeing with' in agree

def test_trade_volatility_scan_meaning_names_the_flat_regime_label_not_both_sides():
    """2026-10-14: the tie-in sentence always printed "the defensive/risk-on mission call
    above" verbatim, regardless of which side actually applied -- a real bug, found reading a
    live report. With regime_label given, the sentence must name that flat label instead of the
    hedged mission_side wording, and only the side that's real, never both."""
    blocks=empty_blocks()
    blocks['trade_volatility_scan']['put_call_ratio']=item({'SPY':{'pcr_oi':1.4}})
    tension=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'],
                             mission_side='risk-on',regime_label='RISK-ON')
    assert 'put-heavy' in tension and 'in tension with' in tension
    assert 'flat RISK-ON regime call' in tension
    assert 'defensive/risk-on' not in tension  # the old bug: both words, every time

    agree=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'],
                           mission_side='defensive',regime_label='DEFENSIVE')
    assert 'put-heavy' in agree and 'agreeing with' in agree
    assert 'flat DEFENSIVE regime call' in agree
    assert 'defensive/risk-on' not in agree

    # No regime_label given at all -> falls back to the prior hedged mission_side wording,
    # naming only that one side, same as before this change (CHOPPY/no field is unavailable).
    bare=section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'],mission_side='risk-on')
    assert 'the risk-on mission call above' in bare and 'defensive/risk-on' not in bare

def test_trade_volatility_scan_is_honest_when_vendor_unavailable():
    blocks=empty_blocks()  # every field unavailable, as if TV credentials/data are missing
    assert section_summary('trade_volatility_scan',blocks['trade_volatility_scan']) is not None
    assert 'No TradingVolatility opportunities cleared this checkpoint.' in section_meaning('trade_volatility_scan',blocks['trade_volatility_scan'])

def test_catalyst_vol_narrative_is_honest_when_nothing_favors_selling():
    blocks=empty_blocks()
    narrative=catalyst_vol_narrative(blocks)
    assert narrative=='No flagged high-impact catalyst on the board right now.'
    assert 'No flagged high-impact catalyst' in catalyst_vol_narrative_html(blocks)

def test_thesis_sentence_turns_the_pressure_dict_into_a_sentence_not_a_raw_dump():
    """Leron, 2026-10-14: "Today vs forward... tells me nothing about what the strategy for
    the day should be" -- the real live report's Today vs forward table showed thesis's raw
    pressure dict as a labeled field dump ("Upside initiation premium: 306,147...") instead of
    a sentence. One classified symbol."""
    pressure={'SPY':{'upside_initiation_premium':306147.0,'downside_initiation_premium':161809.0,
                      'read':'upside pressure','scope':'Observed retained strike concentrations only'},
               'QQQ':{'upside_initiation_premium':5.0,'downside_initiation_premium':5.0,
                      'read':'balanced or unclassified','scope':'x'}}
    sentence=_thesis_sentence(pressure)
    assert sentence=='Thesis: SPY flow leans upside pressure.'
    assert '306147' not in sentence and 'Upside initiation premium' not in sentence  # no raw dump

def test_thesis_sentence_handles_the_plain_regime_string_and_empty_pressure():
    assert _thesis_sentence('Defensive price confirmation')=='Today\'s price read is leaning defensive.'
    assert _thesis_sentence('Risk-on price confirmation')=='Today\'s price read is leaning bullish.'
    all_balanced={'SPY':{'read':'balanced or unclassified'}}
    assert _thesis_sentence(all_balanced)=='Thesis: no classified directional flow yet for this horizon.'
    assert _thesis_sentence(None) is None

def test_thesis_display_item_swaps_the_table_value_but_keeps_inconclusive_dict_as_labeled_lines():
    """The INCONCLUSIVE forward-horizon dict (direction/volatility_context/meaning) must stay
    untouched -- a 2026-10-10 fix specifically requires it to render as separate labeled lines,
    not collapse into one sentence that drops the volatility context and meaning fields."""
    pressure_item=item({'SPY':{'upside_initiation_premium':306147.0,'downside_initiation_premium':161809.0,
                                'read':'upside pressure','scope':'x'}})
    swapped=_thesis_display_item(pressure_item)
    assert swapped['value']=='Thesis: SPY flow leans upside pressure.'
    assert swapped['status']==pressure_item['status']  # metadata untouched

    inconclusive_item=item({'direction':'INCONCLUSIVE: no verified directional trade-time flow',
                             'volatility_context':{'SPY':{'median_iv':0.151}},
                             'meaning':'Observed expiry-specific option pricing supplies forward risk context.'})
    assert _thesis_display_item(inconclusive_item) is inconclusive_item  # untouched, not swapped

    unavailable_item={'status':'unavailable','reason':'No source observation'}
    assert _thesis_display_item(unavailable_item) is unavailable_item

def test_today_vs_forward_html_table_shows_the_thesis_sentence_not_the_raw_pressure_dict():
    blocks=empty_blocks()
    blocks['day_strategy']['thesis']=item({'SPY':{'upside_initiation_premium':306147.0,
        'downside_initiation_premium':161809.0,'read':'upside pressure','scope':'x'}})
    blocks['day_strategy']['status']=item('WATCH')
    opening=render_opening_html({'report_blocks':blocks})
    assert 'SPY flow leans upside pressure' in opening
    assert 'Upside initiation premium' not in opening
    assert '306147' not in opening and '306,147' not in opening
