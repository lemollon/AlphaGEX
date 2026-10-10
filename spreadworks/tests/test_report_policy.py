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
                                   validate_semantics, section_summary, section_meaning, market_story,
                                   edge_board, biggest_traps, if_then_day_plan, SECTION_SUMMARY_SECTIONS,
                                   render_markdown, render_opening_html, plain_value, field_label, display,
                                   ct_str, fmt_number, narrative_html)

NOW=datetime(2026,10,6,16,5,tzinfo=timezone.utc)

def empty_blocks():
    return {n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}

def item(value=1,age=0):
    return observed(value,'Observed provider feed',NOW-timedelta(seconds=age),NOW)

def test_schema_retains_all_legacy_fields_and_new_strategy_policy():
    assert len(REQUIREMENTS)==33
    assert sum(map(len,REQUIREMENTS.values()))==242
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
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':0.12,'QQQ':-3.1})
    blocks['gamma']['flip']=item({'SPY':775.3,'QQQ':758.8})
    summary=section_summary('gamma',blocks['gamma'])
    assert 'net gex' in summary and 'flip' in summary
    assert section_summary('profile',empty_blocks()['profile'])=='No verified observation yet this checkpoint.'

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

def test_render_markdown_adds_decision_lines_only_for_included_sections():
    blocks=empty_blocks()
    blocks['gamma']['net_gex']=item({'SPY':0.12})
    payload={'generated_at':NOW.isoformat(),'kind':'intraday','report_blocks':blocks,'report_completeness':'INCOMPLETE'}
    markdown=render_markdown(payload)
    gamma_section=markdown.split('### Gamma')[1].split('###')[0]
    assert 'Section summary:' in gamma_section and 'What it means for the day:' in gamma_section
    paper_section=markdown.split('### Paper Scorecard')[1].split('###')[0]
    assert 'Section summary:' not in paper_section and 'What it means for the day:' not in paper_section
    assert set(SECTION_SUMMARY_SECTIONS) <= set(REQUIREMENTS)
    assert 'paper_scorecard' not in SECTION_SUMMARY_SECTIONS

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
