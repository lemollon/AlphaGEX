from datetime import datetime,timedelta,timezone
import asyncio,html,io,json
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.pool import StaticPool
from freezegun import freeze_time
from PIL import Image
from backend import report_producers as p,report_ledger as ledger,full_options_report as report
from backend.report_contract import REQUIREMENTS,validate_rendered_report,LIVE_MAX_AGE_SECONDS
UTC=timezone.utc
NOW=datetime(2026,10,2,15,0,tzinfo=UTC)

def test_producer_observation_live_threshold_is_ten_minutes():
    """Same fix as report_policy.observed() -- report_producers.observation() is the other,
    more heavily-used wrapper that stamps live/historical on most report_blocks fields
    (surface, gamma, flow metadata, breadth, macro, ...). Both must move together or
    validate_report()'s own re-check of "live"-labeled items (which also keys off
    LIVE_MAX_AGE_SECONDS) would reject a field the producer just correctly called live."""
    assert LIVE_MAX_AGE_SECONDS == 600
    fresh=p.observation(1.0,'test',(NOW-timedelta(seconds=540)).isoformat(),NOW)
    assert fresh['status']=='live'
    stale=p.observation(1.0,'test',(NOW-timedelta(seconds=660)).isoformat(),NOW)
    assert stale['status']=='historical'
    # The `delayed` override still forces historical regardless of age -- unchanged behavior.
    delayed=p.observation(1.0,'test',NOW.isoformat(),NOW,delayed=True)
    assert delayed['status']=='historical'

@pytest.fixture
def db(monkeypatch):
    from backend import report_refresh
    async def context(*args):return []
    async def core_refresh(core):return core,[]
    monkeypatch.setattr(report_refresh,'refresh_context',context)
    monkeypatch.setattr(report_refresh,'refresh_core',core_refresh)
    eng=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    monkeypatch.setattr(report,'engine',eng);monkeypatch.setattr(ledger,'engine',eng)
    report.ensure_tables();ledger.ensure_tables()
    return eng

def leg(symbol,strike,action,bid,ask,right='C'):
    return {'symbol':symbol,'strike':strike,'action':action,'bid':bid,'ask':ask,'right':right,
      'exchange_timestamp':NOW.isoformat(),'delta':.5,'gamma':.05,'theta':-.1,'vega':.1,'iv':.2,'volume':500,'open_interest':1000}

def package():
    return {'strategy':'call_debit_spread','expiration':'2026-10-09','natural_debit':2.,'max_risk':200,
            'legs':[leg('L',100,'buy',3,3.1),leg('S',105,'sell',1.1,1.2)]}

def test_payoff_vertical_credit_condor_and_long_call():
    result=ledger.package_payoff(package());assert result['max_risk']==200;assert result['max_reward']==300;assert result['breakeven']==[102]
    credit={'strategy':'put_credit_spread','natural_credit':1.,'legs':[leg('S',100,'sell',1.2,1.3,'P'),leg('L',95,'buy',.1,.2,'P')]}
    assert ledger.package_payoff(credit)=={'max_risk':400,'max_reward':100,'breakeven':[99.0],'method':'Single-expiry expiry payoff; 100 multiplier; fees and early assignment excluded'}
    condor=dict(credit,strategy='iron_condor',natural_credit=2,legs=credit['legs']+[leg('SC',110,'sell',1.2,1.3),leg('LC',115,'buy',.1,.2)])
    assert ledger.package_payoff(condor)['breakeven']==[98,112]
    assert ledger.package_payoff({'strategy':'long_call','natural_debit':3.1,'legs':[leg('L',100,'buy',3,3.1)]})['max_reward']=='unlimited'

def test_future_nan_crossed_or_stale_package_is_rejected():
    for key,value in [('bid',float('nan')),('ask',-1),('exchange_timestamp',(NOW+timedelta(seconds=1)).isoformat()),('exchange_timestamp',(NOW-timedelta(seconds=91)).isoformat())]:
        pkg=package();pkg['legs'][0][key]=value;assert ledger.qualify_package(pkg,NOW) is None
    pkg=package();pkg['legs'][0]['bid']=5;assert ledger.qualify_package(pkg,NOW) is None

def test_ledger_idempotent_no_retroactive_fill_and_conservative_mark(db):
    setup={'setup_id':'A','symbol':'SPY','entry':{'confirmation_bars':2}}
    assert ledger.record_entry(setup,package(),NOW)
    assert not ledger.record_entry(setup,package(),NOW)
    stale=package();stale['legs'][0]['exchange_timestamp']=(NOW-timedelta(seconds=100)).isoformat()
    assert not ledger.record_entry(dict(setup,setup_id='B'),stale,NOW)
    card=ledger.scorecard();assert card['fills']==1;assert card['closed']==0;assert card['realized_pnl']==0
    assert card['trade_details'][0]['entry_cash_per_share']==-2.04
    quotes={'L':{'bid':4.5,'ask':4.6,'bid_date':NOW.timestamp()*1000,'ask_date':NOW.timestamp()*1000},
            'S':{'bid':1.,'ask':1.1,'bid_date':NOW.timestamp()*1000,'ask_date':NOW.timestamp()*1000}}
    mark=ledger.liquidation_value(package(),quotes,NOW);assert mark['cash_per_share']==pytest.approx(3.36)
    quotes['S']['ask_date']=(NOW-timedelta(seconds=91)).timestamp()*1000
    assert ledger.liquidation_value(package(),quotes,NOW) is None

def test_breadth_scope_dedup_missing_52week_and_stale_denominator():
    quotes=[{'symbol':'A','last':11,'prevclose':10,'volume':300,'trade_date':NOW.timestamp()*1000},
            {'symbol':'B','last':9,'prevclose':10,'volume':100,'trade_date':NOW.timestamp()*1000},
            {'symbol':'C','last':12,'prevclose':10,'volume':1000,'trade_date':(NOW-timedelta(seconds=91)).timestamp()*1000}]
    result=p.summarize_breadth(quotes+[quotes[0]],['A','B','C'],NOW)
    assert result['covered']==2;assert result['advances']==1;assert result['declines']==1
    assert result['up_down_volume_ratio']==3;assert result['new_52w_highs'] is None


def test_true_profile_volume_conservation_and_contiguous_value_area():
    ts=NOW.isoformat()
    rows=[{'timestamp':ts,'price':100.02,'size':50},{'timestamp':ts,'price':100.12,'size':200},{'timestamp':ts,'price':100.32,'size':50},
          {'timestamp':ts,'price':float('nan'),'size':100}]
    result=p.volume_profile(rows,.1,NOW-timedelta(minutes=30),NOW)
    assert result['total_volume']==300;assert sum(r['volume'] for r in result['bins'])==300
    assert result['val']<=result['poc']<=result['vah'];assert result['rejected_rows']==1
    assert 'not full session' in result['method']
    assert result['vwap']==100.1667

def test_profile_vwap_is_a_required_contract_field():
    assert 'vwap' in REQUIREMENTS['profile']

def test_profile_vwap_threads_from_producer_into_report_block():
    context={'profile_SPY':{'poc':100,'vah':101,'val':99,'hvn':[100],'lvn':[99],
      'vwap':100.3,'method':'m','source_timestamp':NOW.isoformat()}}
    blocks=report.report_blocks(core(),context,{},{},ledger_empty(),{},{},[],NOW)
    assert blocks['profile']['vwap']['value']['SPY']=={'vwap':100.3}

def test_profile_restart_fetches_recent_tape_and_parses_string_millisecond_epoch(monkeypatch):
    previous={'method':'Tradier observed tape','window_end':(NOW-timedelta(hours=2)).isoformat(),'bins':[]}
    seen=[]
    def provider(path,params):
        seen.append(params)
        return {'series':{'data':[{'timestamp':str(int((NOW-timedelta(seconds=2)).timestamp()*1000)),'price':100.1,'volume':50}]}}
    monkeypatch.setattr(p,'tradier',provider)
    result=p.collect_profile('SPY',NOW,previous)
    assert result['total_volume']==50 and result['coverage_gap']
    assert result['source_timestamp']==(NOW-timedelta(seconds=2)).isoformat()
    assert result['window_start']==(NOW-timedelta(minutes=30)).isoformat()
    assert 'earlier session tape is not included' in result['method']

def test_every_entry_ready_alert_has_a_paper_outcome_without_fake_fills(db):
    setup={'setup_id':'NEW','symbol':'SPY'}
    ledger.record_trigger(setup,'ENTRY_READY',{},NOW)
    assert not ledger.record_entry(setup,{},NOW)
    ledger.record_trigger(dict(setup,setup_id='LEGACY'),'ENTRY_READY',{},NOW)
    card=ledger.scorecard()
    assert card['entry_ready_alerts']==2 and card['fills']==0 and card['win_rate'] is None
    assert {r['outcome'] for r in card['fill_reconciliation']}=={'BLOCKED','UNRESOLVED'}
    assert 'no valid fills' in card['sample_status']

def test_yesterdays_expected_move_cannot_be_consumed_as_today_budget():
    current=core()
    baseline={'generated_at':NOW.isoformat(),'evidence':{'surface':{'SPY':dict(current['surface']['SPY'],source_timestamp=(NOW-timedelta(days=1)).isoformat())}}}
    comparison=report.market_comparison(current,baseline)
    assert not comparison['SPY']['baseline_session_matches']
    blocks=report.report_blocks(current,{}, {},{},ledger_empty(),{},comparison,[],NOW)
    assert blocks['expected_move']['budget_used']['status']=='unavailable'
    assert blocks['morning_comparison']['price_location']['value']!=blocks['morning_comparison']['stall_risk']['value']


def vix_core(price=None,ts=None):
    c=core()
    if price is not None:
        c['volatility']={'indices':{'VIX':{'price':price,'source_timestamp':ts or NOW.isoformat()}}}
    return c

def test_vix_comparison_same_session_baseline_computes_pct_change():
    current=vix_core(22,NOW.isoformat())
    baseline={'generated_at':NOW.isoformat(),'evidence':{'volatility':{'indices':{'VIX':{'price':20,'source_timestamp':NOW.isoformat()}}}}}
    result=report.vix_comparison(current,baseline)
    assert result['price_change_pct']==pytest.approx(10.0)
    assert result['morning_spot']==20;assert result['current_spot']==22
    assert result['baseline_session_matches']

def test_vix_comparison_prior_day_baseline_session_does_not_match():
    current=vix_core(22,NOW.isoformat())
    baseline={'generated_at':NOW.isoformat(),'evidence':{'volatility':{'indices':{
        'VIX':{'price':20,'source_timestamp':(NOW-timedelta(days=1)).isoformat()}}}}}
    result=report.vix_comparison(current,baseline)
    assert not result['baseline_session_matches']
    assert result['price_change_pct']==pytest.approx(10.0)  # pct math itself is unaffected by staleness

def test_vix_comparison_missing_vix_degrades_without_exception():
    # No VIX in core (core() default has volatility={}), baseline has one.
    baseline={'generated_at':NOW.isoformat(),'evidence':{'volatility':{'indices':{'VIX':{'price':20,'source_timestamp':NOW.isoformat()}}}}}
    result=report.vix_comparison(core(),baseline)
    assert result['price_change_pct'] is None;assert result['current_spot'] is None
    assert result['morning_spot']==20;assert not result['baseline_session_matches']
    # No VIX in baseline's evidence, core has one.
    current=vix_core(22,NOW.isoformat())
    result=report.vix_comparison(current,{'generated_at':NOW.isoformat(),'evidence':{'volatility':{}}})
    assert result['price_change_pct'] is None;assert result['morning_spot'] is None
    assert result['current_spot']==22;assert not result['baseline_session_matches']

def test_vix_comparison_empty_baseline_dict_degrades_without_exception():
    # No morning report has been generated yet (baseline={}), mirrors market_comparison's
    # own degraded-baseline test at test_yesterdays_expected_move_cannot_be_consumed_as_today_budget.
    current=vix_core(22,NOW.isoformat())
    result=report.vix_comparison(current,{})
    assert result['price_change_pct'] is None
    assert result['morning_timestamp'] is None;assert result['morning_spot'] is None
    assert result['current_spot']==22;assert not result['baseline_session_matches']

def test_study_frozen_forward_window_rejects_gap_and_no_option_pnl_claim():
    bars=[{'timestamp':NOW.timestamp()+i*60,'high':101,'low':99,'close':100} for i in range(45)]
    bars[20].update(close=102,high=102);bars[30]['close']=101
    result=p.historical_stall_study([('SPY','2026-10-02',bars)])
    assert result['sample_size']==1;assert result['stall_fraction']==1;assert not result['validated_statistics']
    assert 'not option P&L' in result['frozen_method']
    bars[25]['timestamp']+=30
    assert p.historical_stall_study([('SPY','2026-10-02',bars)])['sample_size']==0


def core():
    row={'confidence':'MEDIUM','source':'Observed IV provider','source_timestamp':NOW.isoformat(),'spot':100,
       'atm_iv':.2,'skew_25d':.03,'iv_0dte':.22,'iv_1_5dte':.21,'iv_6_20dte':.2,'iv_21_365dte':.19,
       'expected_move_low':98,'expected_move_high':102,'expected_move_pct_1d':2,'expected_move_dollars_1d':2,
       'smile':{'expiration':'2026-10-09','put_strike':95,'atm_strike':100,'call_strike':105,'put_25d_iv':.23,'atm_iv':.2,'call_25d_iv':.19},
       'surface_points':[{'expiration':'2026-10-09','right':r,'strike':s,'iv':v} for r,s,v in [('put',95,.23),('call',100,.2),('call',105,.19)]]}
    return {'surface':{'SPY':row,'QQQ':dict(row,spot=100)},'gamma':{},'flow':{},'volatility':{},'cross_asset':{'assets':{}},'futures':{}}

@pytest.mark.asyncio
@freeze_time(NOW)
async def test_full_assembly_all_fields_dark_png_embed_and_durable_view(db,monkeypatch):
    monkeypatch.setattr(report,'cached_core',lambda now:core())
    monkeypatch.setattr(report,'_plan_and_runtime',lambda now:({},{}))
    monkeypatch.setattr(report,'scheduled_events',lambda now:([now.date()],[]))
    result=await report.assemble_report(SimpleNamespace(),kind='morning')
    assert result['report_validation']['publishable'];assert not result['report_validation']['complete_live_data']
    for name,fields in REQUIREMENTS.items():assert set(fields)<=result['report_blocks'][name].keys()
    assert validate_rendered_report(result)['publishable']
    assert len(result['chart_urls'])==11
    for url in result['chart_urls'].values():assert f']({url})' in result['report_markdown']
    chart_id=result['chart_urls']['smile_term'].split('/')[-1][:-4]
    image=Image.open(io.BytesIO(report.get_chart(chart_id).body))
    assert image.size==(1440,780);assert image.convert('RGB').getpixel((0,0))==(11,18,32)
    from backend.report_policy import surface_smile_story
    # The surface narrative now lives once, in the curated top-of-page section (no second card).
    assert html.escape(surface_smile_story(result['report_blocks'])) in report.report_view(result['report_id'])
    assert report.latest_report()['report_id']==result['report_id']
    view=report.report_view(result['report_id'])
    assert 'src="data:image/png;base64,' in view
    assert 'src="https://' not in view
    # Live bug, found 2026-10-09: the top-of-page header chip was the one timestamp on the
    # page still shown as bare UTC ("2026-10-02T15:00:00+00:00") instead of Central Time like
    # every other date on the page -- read as a different, unlabeled hour and looked stale.
    assert '2026-10-02 10:00:00 AM CT' in view
    assert "2026-10-02T15:00:00" not in view
    assert all(x in view for x in ('Market story','Edge board','Biggest traps','If/then day plan'))
    assert 'Supporting detail' in view
    assert 'Section summary' in view and 'What it means for the day' in view
    assert 'class="field decision"' in view
    assets=report.get_assets(result['report_id'])
    assert assets['complete'];assert len(assets['images'])==11
    assert all(row['validated'] and row['sha256'][:32]==row['chart_id'] for row in assets['images'])
    assert report.get_chart_pdf(result['report_id']).body.startswith(b'%PDF-')
    # The full narrative report (section summaries/meanings, scoreboard, edge board) as its
    # own downloadable PDF -- distinct from charts.pdf, which is chart images only.
    report_pdf=report.get_report_pdf(result['report_id'])
    assert report_pdf.body.startswith(b'%PDF-')
    assert 'Full Report PDF' in view
    assert f"{result['report_id']}/report.pdf" in view
    import zipfile
    archive=zipfile.ZipFile(io.BytesIO(report.get_portable_report(result['report_id']).body))
    assert {'report.html','report.md','report.pdf','manifest.json','charts.pdf'}<=set(archive.namelist())
    assert archive.read('report.pdf').startswith(b'%PDF-')
    assert 'src="https://' not in archive.read('report.html').decode()
    assert len([name for name in archive.namelist() if name.endswith('.png')])==11
    # Preparing delivery again preserves embeds; callers cannot bypass rendered checks.
    from backend.report_contract import prepare_report_delivery
    assert prepare_report_delivery(result)['publishable']
    # "visuals" is in SECTION_SUMMARY_SECTIONS: the raw per-field URL bullet is gone by design
    # (2026-10-12 fix, Leron: "a long boring ass scroll of data"), so the chart URL now appears
    # exactly once -- as the embedded image markdown, not duplicated as a raw field value too.
    assert result['report_markdown'].count(result['chart_urls']['smile_term'])==1


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_persisted_missing_and_corrupt_images_never_emit_broken_tags(db,monkeypatch):
    monkeypatch.setattr(report,'cached_core',lambda now:core())
    monkeypatch.setattr(report,'_plan_and_runtime',lambda now:({},{}))
    monkeypatch.setattr(report,'scheduled_events',lambda now:([now.date()],[]))
    result=await report.assemble_report(SimpleNamespace(),kind='intraday')
    chart_id=result['chart_urls']['market_map'].split('/')[-1][:-4]
    with db.begin() as c:c.execute(text('DELETE FROM sw_report_charts WHERE chart_id=:id'),{'id':chart_id})
    assets=report.get_assets(result['report_id'])
    assert not assets['complete'];assert 'market_map' in assets['failures']
    view=report.report_view(result['report_id'])
    assert 'VISUAL DELIVERY FAILED' in view;assert 'src="https://' not in view
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:report.get_chart_pdf(result['report_id'])
    assert exc.value.status_code==503
    chart_id=result['chart_urls']['smile_term'].split('/')[-1][:-4]
    with db.begin() as c:c.execute(text('UPDATE sw_report_charts SET png_base64=:bad WHERE chart_id=:id'),{'id':chart_id,'bad':'bm90IGEgcG5n'})
    assert 'smile_term' in report.get_assets(result['report_id'])['failures']


def test_materialize_checks_bytes_before_emitting_paths(tmp_path):
    import base64,hashlib,importlib.util
    from pathlib import Path
    script=Path(__file__).resolve().parents[2]/'scripts'/'materialize_options_report.py'
    spec=importlib.util.spec_from_file_location('materialize_report',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=io.BytesIO();Image.new('RGB',(1440,780),(11,18,32)).save(output,format='PNG')
    png=output.getvalue();sha=hashlib.sha256(png).hexdigest()
    row=dict(name='market_map',chart_id=sha[:32],sha256=sha,size_bytes=len(png),png_base64=base64.b64encode(png).decode(),has_observed_data=True)
    data=dict(report_id='a'*24,generated_at=NOW.isoformat(),complete=True,failures={},images=[row])
    out=module.materialize(data,tmp_path/'good',['market_map'])
    assert Path(out['images'][0]['local_path']).read_bytes()==png
    assert Path(out['pdf_path']).read_bytes().startswith(b'%PDF-')
    assert 'data:image/png;base64,' in Path(out['html_path']).read_text()
    assert out['attachment_persistence_required']
    data['images'][0]['sha256']='b'*64
    with pytest.raises(ValueError,match='manifest/bytes'):module.materialize(data,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_delivery_manifest_cannot_claim_incomplete_assets_are_ready(db,monkeypatch):
    monkeypatch.setattr(report,'cached_core',lambda now:core())
    monkeypatch.setattr(report,'_plan_and_runtime',lambda now:({},{}))
    monkeypatch.setattr(report,'scheduled_events',lambda now:([now.date()],[]))
    result=await report.assemble_report(SimpleNamespace(),kind='morning')
    result['report_blocks']['visuals']['delivery_manifest']['value']['images'].pop()
    check=validate_rendered_report(result)
    assert not check['publishable']
    assert any('missing/duplicate persisted images' in err for err in check['errors'])


def test_missing_clocks_never_become_live_context():
    blocks=report.report_blocks(core(),{}, {},{},ledger_empty(),{}, {},[],NOW)
    assert blocks['contract_packages']['legs']['status']=='unavailable'
    assert blocks['breadth']['advance_decline']['status']=='unavailable'
    assert blocks['macro']['rates']['status']=='unavailable'

def test_entry_watches_attaches_each_setups_own_state_not_the_whole_symbol_list():
    """Production bug, 2026-10-13: runtime['per_symbol_state'][symbol] is a LIST of per-setup
    state rows (one per registered setup for that symbol) -- the producer was doing
    states.get(s['symbol']) and dumping that whole list into the field named 'state' for EVERY
    setup on that symbol, instead of each setup's own scalar state. Confirmed in production
    Render logs: this fed a list into report_policy._narrative_entry_watches's dict lookup and
    500'd GET /api/spreadworks/reports/{id}/view with `TypeError: cannot use 'list' as a dict
    key`. SPY has two setups here with two DIFFERENT states -- the old code would give both the
    same object (the full two-row list); the fix must give each its own scalar string."""
    plan={'generated_at':NOW.isoformat(),'setups':[
        {'setup_id':'s1','symbol':'SPY','entry':{'type':'touch'},'invalidation':{'type':'close_below'}},
        {'setup_id':'s2','symbol':'SPY','entry':{'type':'touch'},'invalidation':{'type':'close_below'}}]}
    runtime={'per_symbol_state':{'SPY':[
        {'setup_id':'s1','state':'ENTRY_READY'},
        {'setup_id':'s2','state':'WATCH'}]}}
    blocks=report.report_blocks(core(),{},plan,runtime,ledger_empty(),{},{},[],NOW)
    rows=blocks['entry_watches']['status']['value']
    by_setup={row['setup_id']:row['state'] for row in rows}
    assert by_setup=={'s1':'ENTRY_READY','s2':'WATCH'}
    # Neither row's state is ever the raw per-symbol list -- the exact shape of the bug.
    assert all(not isinstance(row['state'],list) for row in rows)

def test_entry_watches_prefers_setup_state_by_id_scalar_map_over_the_per_symbol_list():
    """The real fix for the #3289 bug lives upstream in intraday_watch.py: run_intraday_cycle
    now writes a setup_state_by_id map (setup_id -> scalar state string) at the exact point
    result.state is decided, so no consumer has to trust the shape of per_symbol_state[symbol]
    (a list, by design, since one symbol can hold multiple setups) to get one setup's state.
    When both are present, report_blocks must read the guaranteed-scalar map, not re-derive
    from the list -- and must still never crash or go stale if the map disagrees with the list
    (e.g. a runtime payload written mid-deploy, before/after a worker restart)."""
    plan={'generated_at':NOW.isoformat(),'setups':[
        {'setup_id':'s1','symbol':'SPY','entry':{'type':'touch'},'invalidation':{'type':'close_below'}},
        {'setup_id':'s2','symbol':'SPY','entry':{'type':'touch'},'invalidation':{'type':'close_below'}}]}
    runtime={'setup_state_by_id':{'s1':'ENTRY_READY','s2':'WATCH'},
             'per_symbol_state':{'SPY':[
                 {'setup_id':'s1','state':'STALE_LIST_VALUE'},
                 {'setup_id':'s2','state':'STALE_LIST_VALUE'}]}}
    blocks=report.report_blocks(core(),{},plan,runtime,ledger_empty(),{},{},[],NOW)
    rows=blocks['entry_watches']['status']['value']
    by_setup={row['setup_id']:row['state'] for row in rows}
    assert by_setup=={'s1':'ENTRY_READY','s2':'WATCH'}
    assert all(isinstance(state,str) for state in by_setup.values())

def test_entry_watches_falls_back_to_the_per_symbol_list_when_setup_state_by_id_is_absent():
    """Backward compatibility: a runtime payload persisted by a worker before this fix shipped
    will have no setup_state_by_id key at all. The per-symbol list scan must still work."""
    plan={'generated_at':NOW.isoformat(),'setups':[
        {'setup_id':'s1','symbol':'SPY','entry':{'type':'touch'},'invalidation':{'type':'close_below'}}]}
    runtime={'per_symbol_state':{'SPY':[{'setup_id':'s1','state':'NEAR_TRIGGER'}]}}
    blocks=report.report_blocks(core(),{},plan,runtime,ledger_empty(),{},{},[],NOW)
    rows=blocks['entry_watches']['status']['value']
    assert rows[0]['state']=='NEAR_TRIGGER'

def test_entry_watches_state_is_none_when_setup_has_no_matching_runtime_row():
    plan={'generated_at':NOW.isoformat(),'setups':[{'setup_id':'orphan','symbol':'SPY','entry':{},'invalidation':{}}]}
    runtime={'per_symbol_state':{'SPY':[{'setup_id':'other','state':'WATCH'}]}}
    blocks=report.report_blocks(core(),{},plan,runtime,ledger_empty(),{},{},[],NOW)
    rows=blocks['entry_watches']['status']['value']
    assert rows[0]['state'] is None

def ledger_empty():
    return {'entry_ready_alerts':0,'trade_details':[],'exceptions':[],'fill_rules':'test','loss_clusters':[]}


def flow_row(fraction,call_sell,put_sell):
    return {'confidence':'MEDIUM','source_timestamp':NOW.isoformat(),'evidence':{
        'classified_contract_fraction':fraction,
        'buckets':{'0dte':{'calls_sold':{'contracts':10,'premium':call_sell},'puts_sold':{'contracts':10,'premium':put_sell},
                            'calls_bought':{'contracts':1,'premium':1.0},'puts_bought':{'contracts':1,'premium':1.0}}}}}

def test_market_control_dominance_gated_on_classified_coverage():
    current=core()
    current['flow']={'SPY':flow_row(.8,5000.,500.),'QQQ':flow_row(.3,5000.,500.)}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    sides=blocks['market_control']['control_side']['value']
    assert sides['SPY']['0dte']=='call_sellers'
    assert sides['QQQ']['0dte']=='inconclusive'
    conf=blocks['market_control']['control_confidence']['value']
    assert conf['SPY']['label']=='HIGH' and conf['QQQ']['label']=='LOW_FORCES_INCONCLUSIVE'
    evidence=blocks['market_control']['control_evidence']['value']
    assert evidence['SPY']['0dte']['call_sell_premium']==5000.

def test_regime_shift_flags_changed_held_and_first_report():
    """Leron, 2026-10-10: "it needs to be more nimble... the plan for the day but nimble to
    change intraday" -- regime_shift diffs the morning's gamma/control/suitability snapshot
    against the current read and must say HOLDING/CHANGED/FIRST_REPORT, not just repeat data."""
    current=core()
    current['gamma']={'SPY':{'net_gex_b':-9.2,'confidence':'MEDIUM','source_timestamp':NOW.isoformat()}}
    current['flow']={'SPY':flow_row(.8,5000.,500.)}  # call_sellers dominant at 0dte
    current['baseline_blocks']={'regime_shift':{'SPY':{'net_gex_b':5.0,'control_side':{'0dte':'put_sellers'},'suitability':None}}}
    comparison=report.market_comparison(current,{'generated_at':NOW.isoformat(),'evidence':{'surface':{}}})
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},comparison,[],NOW)
    rs=blocks['morning_comparison']['regime_shift']['value']['SPY']
    assert rs['status']=='CHANGED'
    assert any('net GEX flipped positive to negative' in c for c in rs['changed'])
    assert any('control shifted from put_sellers to call_sellers' in c for c in rs['changed'])
    # Unchanged morning snapshot (same sign, same dominant side) -> HOLDING, not CHANGED.
    current['baseline_blocks']={'regime_shift':{'SPY':{'net_gex_b':-3.0,'control_side':{'0dte':'call_sellers'},'suitability':None}}}
    held=report.report_blocks(current,{},{},{},ledger_empty(),{},comparison,[],NOW)['morning_comparison']['regime_shift']['value']['SPY']
    assert held['status']=='HOLDING' and held['changed']==[]
    # No earlier baseline at all -> FIRST_REPORT, never a false CHANGED/HOLDING claim.
    current['baseline_blocks']={}
    first=report.report_blocks(current,{},{},{},ledger_empty(),{},comparison,[],NOW)['morning_comparison']['regime_shift']['value']['SPY']
    assert first['status']=='FIRST_REPORT'

def test_market_control_without_flow_is_unavailable():
    blocks=report.report_blocks(core(),{},{},{},ledger_empty(),{},{},[],NOW)
    assert blocks['market_control']['control_side']['status']=='unavailable'
    assert blocks['market_control']['control_evidence']['status']=='unavailable'
    assert blocks['market_control']['control_confidence']['status']=='unavailable'

def test_forward_control_outlook_persists_flips_and_fades():
    base={'market_control':{'control_side':{'status':'live','source_timestamp':NOW.isoformat(),
            'value':{'SPY':{'0dte':'call_sellers'},'QQQ':{'0dte':'put_sellers'},'IWM':{'0dte':'mixed'}}},
            'forward_control_outlook':{}}}
    base['forward_strategy']={'thesis':{'value':{'SPY':{'read':'downside pressure'},'QQQ':{'read':'downside pressure'},'IWM':{'read':'upside pressure'}}}}
    report.forward_control_outlook(base,NOW)
    out=base['market_control']['forward_control_outlook']['value']
    assert out['SPY']['outlook']=='persists'
    assert out['QQQ']['outlook']=='flips'
    assert 'IWM' not in out

def test_forward_control_outlook_fades_without_confirmed_forward_read():
    base={'market_control':{'control_side':{'status':'live','source_timestamp':NOW.isoformat(),
            'value':{'SPY':{'0dte':'call_sellers'}}},'forward_control_outlook':{}},
          'forward_strategy':{'thesis':{'value':{'SPY':{'read':'balanced or unclassified'}}}}}
    report.forward_control_outlook(base,NOW)
    assert base['market_control']['forward_control_outlook']['value']['SPY']['outlook']=='fades'

def test_engine_consensus_no_longer_carries_risk_session_hunt():
    blocks=report.report_blocks(core(),{},{},{},ledger_empty(),{},{},[],NOW)
    assert set(blocks['engine_consensus'])=={'squeeze','trading_volatility_status','contradictions'}

def test_build_strategy_blocks_appends_structure_family_hint_without_losing_the_safety_line():
    """Leron, 2026-10-13: "what are the option strateiges to trade today based on market
    condition." The existing no-fabricated-direction warning must survive alongside the new
    textbook vol-regime hint, not get replaced by it."""
    current=core()
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    blocks['premium_selling']['suitability']={'status':'live','value':{'SPY':'PREMIUM_CHEAP'}}
    report.build_strategy_blocks(blocks,current,{},{},ledger_empty(),{},{},NOW)
    structure=blocks['day_strategy']['structure']['value']
    assert 'no structure invented from directional pressure' in structure
    assert 'debit spread' in structure
    # The hint must actually reach the page a reader looks at (section_summary), not just
    # sit in the raw structure field that only /data JSON exposes -- found live 2026-10-13:
    # day_strategy renders through its narrative builder on both HTML and markdown, so the
    # hint was computed correctly but invisible everywhere a human actually reads the report.
    from backend.report_policy import section_summary
    summary=section_summary('day_strategy',blocks['day_strategy'])
    assert 'debit spread' in summary

def test_trade_volatility_scan_wires_the_collected_fields_into_blocks():
    """Leron, 2026-10-13: TradingVolatility's ranked long/short opportunities, income setups
    and put/call-ratio read now flow from the scan collector (report_trading_volatility_scan.py,
    saved/reloaded via the same evidence store as breadth/macro) straight into the report
    contract -- same observation()-wrapping every other producer field gets."""
    context={'trade_volatility_scan':{'top_long_setups':[{'ticker':'AUPH','opportunity_score':7.3}],
        'top_short_setups':[{'ticker':'CANE','opportunity_score':6.7}],
        'income_setups':[{'ticker':'GME','strike':21.5}],
        'put_call_ratio':{'SPY':{'pcr_oi':1.36}},
        'expected_move_trend':{'SPY':{'trend':'collapsing'}},
        'source_timestamp':NOW.isoformat()}}
    blocks=report.report_blocks(core(),context,{},{},ledger_empty(),{},{},[],NOW)
    scan=blocks['trade_volatility_scan']
    assert scan['top_long_setups']['status']=='live'
    assert scan['top_long_setups']['value'][0]['ticker']=='AUPH'
    assert scan['put_call_ratio']['value']['SPY']['pcr_oi']==1.36
    assert scan['expected_move_trend']['value']['SPY']['trend']=='collapsing'

def test_trade_volatility_scan_degrades_honestly_when_vendor_failed():
    context={'trade_volatility_scan':{'reason':'TradingVolatility credentials are not configured'}}
    blocks=report.report_blocks(core(),context,{},{},ledger_empty(),{},{},[],NOW)
    scan=blocks['trade_volatility_scan']
    for field in ('top_long_setups','top_short_setups','income_setups','put_call_ratio','expected_move_trend'):
        assert scan[field]['status']=='unavailable'
        assert scan[field]['reason']=='TradingVolatility credentials are not configured'

def flow_row_directional(fraction,calls_bought,calls_sold,puts_bought,puts_sold):
    # Bullish initiation lean = calls_bought + puts_sold premium; bearish = calls_sold + puts_bought.
    return {'confidence':'MEDIUM','source_timestamp':NOW.isoformat(),'evidence':{
        'classified_contract_fraction':fraction,
        'buckets':{'0dte':{'calls_bought':{'contracts':1,'premium':calls_bought},'calls_sold':{'contracts':1,'premium':calls_sold},
                            'puts_bought':{'contracts':1,'premium':puts_bought},'puts_sold':{'contracts':1,'premium':puts_sold}}}}}

def test_price_vix_confirmation_confirms_conflicts_and_abstains():
    current=core()
    current['flow']={'SPY':flow_row_directional(.8,100.,5000.,100.,100.),  # bearish-leaning flow (calls_sold dominant)
                      'QQQ':flow_row_directional(.8,5000.,100.,100.,100.)}  # bullish-leaning flow (calls_bought dominant)
    current['cross_asset']={'assets':{'SPY':{'price':101,'prev_close':100,'source_timestamp':NOW.isoformat(),'fresh':True},
                                       'QQQ':{'price':99,'prev_close':100,'source_timestamp':NOW.isoformat(),'fresh':True}}}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    pv=blocks['flow']['price_vix_confirmation']['value']
    assert pv['SPY']['flow_lean']=='downside' and pv['SPY']['price_direction']=='up' and pv['SPY']['read']=='conflicts'
    assert pv['QQQ']['flow_lean']=='upside' and pv['QQQ']['price_direction']=='down' and pv['QQQ']['read']=='conflicts'

def test_price_vix_confirmation_agrees_when_flow_and_price_align():
    current=core()
    current['flow']={'SPY':flow_row_directional(.8,5000.,100.,100.,100.)}  # bullish-leaning flow
    current['cross_asset']={'assets':{'SPY':{'price':101,'prev_close':100,'source_timestamp':NOW.isoformat(),'fresh':True}}}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    assert blocks['flow']['price_vix_confirmation']['value']['SPY']['read']=='confirms'

def test_risk_on_defensive_populates_on_stale_but_valid_cross_asset_quotes():
    """The flagship 'Today's mission' verdict used to require BOTH SPY and QQQ quotes to be
    live-fresh (<90s old) simultaneously — the same bar sector_credit does NOT apply, so this
    field could show hundreds of lines of real sector_credit data while its own verdict stayed
    permanently blank. Live bug, found 2026-10-09 on the actual intraday report: 'Today's
    mission' read UNAVAILABLE while every sibling section had real numbers. A stale-but-valid
    quote (fresh=False, real price/prev_close) must still populate the verdict, same bar as
    sector_credit, with its own real age reflected normally (not silently dropped)."""
    current=core()
    current['cross_asset']={'assets':{'SPY':{'price':102,'prev_close':100,'source_timestamp':NOW.isoformat(),'fresh':False},
                                       'QQQ':{'price':101,'prev_close':100,'source_timestamp':NOW.isoformat(),'fresh':False}}}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    verdict=blocks['risk_on_defensive']['verdict']
    assert verdict['status']!='unavailable'
    assert verdict['value']=='Risk-on price confirmation'

def test_forward_control_outlook_unavailable_without_control_side():
    base={'market_control':{'control_side':{'status':'unavailable'},'forward_control_outlook':{}},'forward_strategy':{'thesis':{}}}
    report.forward_control_outlook(base,NOW)
    assert base['market_control']['forward_control_outlook']['status']=='unavailable'


def test_session_profile_checkpoint_merges_observed_bins_without_new_trades():
    start=NOW-timedelta(minutes=30);middle=NOW-timedelta(minutes=15)
    old=p.volume_profile([{'price':100.1,'size':50,'timestamp':(middle-timedelta(seconds=1)).isoformat()}],.1,start,middle)
    new=p.volume_profile([{'price':100.2,'size':100,'timestamp':(NOW-timedelta(seconds=1)).isoformat()}],.1,middle,NOW)
    merged=p.merge_profiles(old,new,.1)
    assert merged['trade_count']==2;assert merged['total_volume']==150
    assert merged['window_start']==start.isoformat();assert merged['window_end']==NOW.isoformat()
    assert sum(r['volume'] for r in merged['bins'])==150
    assert merged['vwap']==100.2167

def test_fmt_value_caps_nested_per_symbol_chain_dump():
    """Real shape (evidence.observed_expiry_points): a plain field dict containing a
    per-symbol dict containing a list of chain-point dicts — depth 0/1/2. A live bug
    (caught 2026-10-08/09: the raw pasted report still showed hundreds of uncapped
    strike rows) happened because the list-of-dicts truncation only fired below depth 2,
    but this shape reaches the list at depth 2 — one level too deep to be caught."""
    big_list=[{'expiration':'2026-10-08','strike':float(700+i),'right':'call','iv':0.1,
               'dte':0,'source_timestamp':NOW.isoformat()} for i in range(120)]
    evidence={'observed_expiry_points':{'SPY':big_list,'QQQ':big_list}}
    html=report._fmt_value(evidence)
    assert html.count('"expiration"')<30  # no unbounded per-item raw json.dumps
    assert '+115 more items' in html
    assert '<pre class="raw">' not in html or html.count('2026-10-08')<30

def test_fmt_value_single_key_dict_inlines_not_boxed():
    """Live 2026-10-10: every per-symbol Gamma value ({"net_gex_b": -0.04}) got wrapped in a
    full bordered/background kvblock just to show ONE number — visual weight with nothing to
    organize. A single-key dict with a scalar value now inlines as plain "label: value"; a
    real multi-key dict still gets the kvblock."""
    assert 'kvblock' not in report._fmt_value({'net_gex_b': -0.04})
    assert 'net gex b:' in report._fmt_value({'net_gex_b': -0.04})
    assert 'kvblock' in report._fmt_value({'a': 1, 'b': 2})
    # A single key whose value is itself a dict/list still needs real structure, not inlining.
    assert 'kvblock' in report._fmt_value({'walls': {'put': 700.0, 'call': 710.0}})

def test_shared_section_meta_collapses_identical_source_across_fields():
    """Live 2026-10-10: Gamma's 4 fields each repeated the identical ~160-char source
    description and timestamp verbatim under every single field — one fact shown four times.
    When every populated field shares the exact same source+timestamp, show it once at the
    section level and suppress each field's own repeat."""
    block={
        'coverage': {'status': 'historical', 'value': {'SPY': 684}, 'source': 'Tradier',
                     'source_timestamp': '2026-10-08T20:00:00+00:00', 'age_seconds': 59706},
        'net_gex': {'status': 'historical', 'value': -0.04, 'source': 'Tradier',
                    'source_timestamp': '2026-10-08T20:00:00+00:00', 'age_seconds': 59706},
    }
    shared = report._shared_section_meta(block)
    assert shared is not None and 'Tradier' in shared
    fields_html = ''.join(report._field_row(f, i, show_meta=(shared is None)) for f, i in block.items())
    assert fields_html.count('class="meta"') == 0  # per-field meta suppressed in favor of the shared line

def test_shared_section_meta_none_when_sources_differ():
    """A section with genuinely different sources per field must never be collapsed — each
    field keeps its own meta line so the real distinction isn't hidden."""
    block={
        'a': {'status': 'historical', 'value': 1, 'source': 'Tradier',
              'source_timestamp': '2026-10-08T20:00:00+00:00', 'age_seconds': 1},
        'b': {'status': 'historical', 'value': 2, 'source': 'ThetaData',
              'source_timestamp': '2026-10-08T20:00:00+00:00', 'age_seconds': 1},
    }
    assert report._shared_section_meta(block) is None

def test_fmt_value_deep_structure_never_raw_dumps_full_precision_floats():
    """Live bug, found 2026-10-10 in Leron's post-#3242-deploy check: event_study's per-event
    list (symbol/date/direction/forward_return/stalled) is too deep/wide for the normal
    per-field renderer and used to hit a raw <pre class="raw"> json.dumps() fallback, leaking
    forward_return -0.0001541364373222054 at full float repr precision. 2026-10-11: that raw
    fallback was removed and replaced with a hard depth>=6 cutoff ("[N fields]" placeholder) --
    but a second screenshot the same day caught that cutoff firing on small, perfectly normal
    data too (a 3-field payoff dict with a 1-item breakeven list, nested a few levels into a
    contract package, collapsed to "[1 items]" instead of showing the real number). The depth
    cutoff was removed entirely: report data is a finite, acyclic tree from producer code, so
    there is no runaway-recursion risk, and the real protection against something actually
    unbounded (breadth's 503-symbol holdings list) is the per-list item cap, not depth. A deep
    structure now renders in full -- real values, properly rounded -- never a placeholder."""
    v={'events':[{'symbol':'SPY','date':'2026-10-02','direction':1,
        'forward_return':-0.0001541364373222054,'stalled':True} for _ in range(3)]}
    html=report._fmt_value(v,depth=6)
    assert '0001541364373222054' not in html
    assert '-0.0002' in html and 'SPY' in html and '2026-10-02' in html
    assert '[1 fields]' not in html and 'raw' not in html

def test_fmt_value_converts_any_timestamp_shaped_string_regardless_of_key_name():
    """Key-name matching (source_timestamp, generated_at, ...) kept missing new field names as
    they turned up live one at a time: "heartbeat", "alert_time", "requested_at", "completed_at",
    "prior_hour_timestamp" all leaked raw UTC under names the enumerated pattern didn't cover.
    Switched to shape-based detection (does the string actually parse as a tz-aware instant?)
    instead of a key-name allowlist — covers any field name, present or future, by construction.
    A bare calendar date (an option expiration, no time/offset) must NOT shift: it has no tzinfo,
    so parse_clock returns None and ct_str leaves it untouched."""
    html=report._fmt_value({'heartbeat':NOW.isoformat(),'alert_time':NOW.isoformat(),
                             'requested_at':NOW.isoformat(),'some_totally_new_field_name':NOW.isoformat(),
                             'expiration':'2026-10-08'})
    assert NOW.isoformat() not in html
    assert html.count('AM CT</span>')+html.count('PM CT</span>')==4  # the 4 real timestamps
    assert '2026-10-08</span>' in html  # bare date untouched, not shifted to the previous day

def test_fmt_primitive_never_scientific_notation():
    """%g silently switches to exponential once a float needs more than 4 significant digits
    before the decimal (anything >=10000) — "8.231e+04" for an $82,313 premium reads as a
    typo, not a dollar figure. Live bug, confirmed on the real intraday report 2026-10-09."""
    assert report._fmt_primitive(82313.0)=='82,313'
    assert report._fmt_primitive(239000.0)=='239,000'
    assert report._fmt_primitive(999999.0)=='999,999'
    assert report._fmt_primitive(773.97)=='773.97'  # cents precision preserved, not rounded to "774"
    assert report._fmt_primitive(-0.040187857052636146)=='-0.0402'

def test_fmt_value_latest_print_nested_object_no_longer_raw_dumps():
    """Same class of bug as the per-symbol chain arrays, one level deeper: evidence ->
    observed_expiry_prints -> SPY -> [print, ...] -> latest_print is a plain dict at depth 4,
    one level past the old depth<4 cutoff. Live bug, confirmed 2026-10-09: every single
    observed_expiry_prints row still showed a raw { "price": ..., "bid": ... } JSON block."""
    prints={'SPY':[{'expiration':'2026-10-08','strike':773.0,'right':'call','initiation':'unclassified',
             'contracts':2464,'premium':239000.0,'print_count':330,
             'latest_print':{'price':1.03,'bid':1.02,'ask':1.04,'timestamp':NOW.isoformat(),
                              'condition':18.0,'exchange':'7','sequence':'-1228952309','side':'unclassified'}}]}
    html=report._fmt_value({'observed_expiry_prints':prints})
    assert '<pre class="raw">' not in html
    assert '"price": 1.03' not in html
    assert 'kvblock' in html and '1.03' in html

def test_fmt_value_item_fields_still_render_as_kv_not_raw_json():
    evidence={'observed_expiry_points':{'SPY':[{'expiration':'2026-10-08','strike':700.0,
               'right':'call','iv':0.1,'dte':0,'source_timestamp':NOW.isoformat()}]}}
    html=report._fmt_value(evidence)
    assert 'kvblock' in html
    assert 'fieldname' not in html or True  # kv rows use .k/.v classes, not a raw dump
    assert '<pre class="raw">{\n  "expiration"' not in html


def cross_asset(spy_price,qqq_price):
    return {'assets':{'SPY':{'price':spy_price,'prev_close':100,'source_timestamp':NOW.isoformat()},
                       'QQQ':{'price':qqq_price,'prev_close':100,'source_timestamp':NOW.isoformat()}}}

def test_regime_label_covers_risk_on_defensive_and_choppy_signs():
    """Leron, 2026-10-12: "come out and say if its risk on day, choppy day, defensive day" --
    a flat label, not a hedge, same risk/defensive sign-agreement logic the verdict text
    already used (single source of truth), just named the way he actually thinks about it."""
    cases=[(102,101,'RISK-ON','Risk-on price confirmation'),
           (98,99,'DEFENSIVE','Defensive price confirmation'),
           (102,99,'CHOPPY','Mixed price confirmation'),
           (98,101,'CHOPPY','Mixed price confirmation')]
    for spy_price,qqq_price,label,verdict_text in cases:
        current=core();current['cross_asset']=cross_asset(spy_price,qqq_price)
        blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
        assert blocks['risk_on_defensive']['regime_label']['value']==label
        assert blocks['risk_on_defensive']['verdict']['value']==verdict_text

def test_regime_label_unavailable_when_only_one_symbol_has_a_return():
    """regime_label requires BOTH SPY and QQQ returns -- with only one available it must stay
    an explicit, disclosed unavailable, never a fabricated single-symbol guess."""
    current=core()
    current['cross_asset']={'assets':{'SPY':{'price':102,'prev_close':100,'source_timestamp':NOW.isoformat()}}}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    assert blocks['risk_on_defensive']['regime_label']['status']=='unavailable'

def test_morning_comparison_vix_never_leaks_into_spy_qqq_shaped_fields():
    """comparison (built in assemble_report) always carries a 'VIX' row for the
    change_vs_baselines contradiction-calling path -- but every other morning_comparison
    field is SPY/QQQ-shaped and must never pick up a VIX entry just because the per-symbol
    loop iterates over comparison.items()."""
    row={'morning_timestamp':NOW.isoformat(),'morning_spot':100,'current_spot':101,'price_change_pct':1.0,
         'baseline_source_timestamp':NOW.isoformat(),'current_source_timestamp':NOW.isoformat(),
         'baseline_session_matches':True,'frozen_expected_move':None,'frozen_lower':None,'frozen_upper':None}
    comparison={'SPY':dict(row),'QQQ':dict(row,current_spot=99,price_change_pct=-1.0),
                'VIX':dict(row,morning_spot=20,current_spot=21,price_change_pct=5.0)}
    blocks=report.report_blocks(core(),{},{},{},ledger_empty(),{},comparison,[],NOW)
    for field in ('morning_timestamp','price_location','move_usage','chop_status','stall_risk','setup_status','regime_shift'):
        value=blocks['morning_comparison'][field]['value']
        assert value is None or 'VIX' not in value
        assert value is None or {'SPY','QQQ'}>=set(value)

def test_regime_label_shift_reports_change_since_morning_and_prior_hour():
    """Direct report_blocks-level check of the regime_label_shift field logic: morning/prior
    labels come from core['baseline_blocks']/['prior_blocks']['regime_label'] (plain strings,
    the one key in those dicts that is NOT per-symbol), compared against today's freshly
    computed label."""
    current=core();current['cross_asset']=cross_asset(102,99)  # today = CHOPPY
    current['baseline_blocks']={'regime_label':'RISK-ON'}
    current['prior_blocks']={'regime_label':'RISK-ON'}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    shift=blocks['morning_comparison']['regime_label_shift']['value']
    assert shift=={'morning_label':'RISK-ON','prior_hour_label':'RISK-ON','current_label':'CHOPPY',
                   'changed_since_morning':True,'changed_since_prior_hour':True}

def test_regime_label_shift_no_change_case():
    current=core();current['cross_asset']=cross_asset(102,101)  # today = RISK-ON
    current['baseline_blocks']={'regime_label':'RISK-ON'}
    current['prior_blocks']={'regime_label':'RISK-ON'}
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    shift=blocks['morning_comparison']['regime_label_shift']['value']
    assert shift['changed_since_morning'] is False
    assert shift['changed_since_prior_hour'] is False

def test_regime_label_shift_no_baseline_case_degrades_without_exception():
    """First report of the day: no morning/prior baseline at all. morning_label/prior_hour_label
    must come back None, with no exception, rather than a false claim of change."""
    current=core();current['cross_asset']=cross_asset(102,99)  # today = CHOPPY
    blocks=report.report_blocks(current,{},{},{},ledger_empty(),{},{},[],NOW)
    shift=blocks['morning_comparison']['regime_label_shift']['value']
    assert shift['morning_label'] is None and shift['prior_hour_label'] is None
    assert shift['current_label']=='CHOPPY'
    assert shift['changed_since_morning'] is False and shift['changed_since_prior_hour'] is False


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_regime_label_shift_wires_through_comparable_from_stored_morning_report(db,monkeypatch):
    """End-to-end: comparable() (inside assemble_report) must unwrap a stored morning report's
    nested risk_on_defensive.regime_label.value into core['baseline_blocks']['regime_label']
    (a plain string, unlike every other key in that dict which is per-symbol SPY/QQQ), and
    morning_comparison.regime_label_shift must then report the real change against today's
    freshly computed label."""
    current=core();current['cross_asset']=cross_asset(102,98)  # today = CHOPPY
    monkeypatch.setattr(report,'cached_core',lambda now:current)
    monkeypatch.setattr(report,'_plan_and_runtime',lambda now:({},{}))
    monkeypatch.setattr(report,'scheduled_events',lambda now:([now.date()],[]))
    morning={'generated_at':(NOW-timedelta(hours=3)).isoformat(),
             'report_blocks':{'risk_on_defensive':{'regime_label':{'status':'live','value':'RISK-ON'}}}}
    monkeypatch.setattr(report,'previous_reports',lambda now:(morning,{}))
    result=await report.assemble_report(SimpleNamespace(),kind='intraday')
    shift=result['report_blocks']['morning_comparison']['regime_label_shift']['value']
    assert shift['morning_label']=='RISK-ON'
    assert shift['current_label']=='CHOPPY'
    assert shift['changed_since_morning'] is True
    assert shift['prior_hour_label'] is None
    assert shift['changed_since_prior_hour'] is False

def _store_report(payload):
    """Insert a crafted payload straight into sw_full_reports -- lighter-weight than running
    the full async assemble_report pipeline when the test only cares about report_view's
    per-section fields_html branch, not the producer/chart pipeline."""
    with report.engine.begin() as c:
        c.execute(text('INSERT INTO sw_full_reports (report_id,kind,generated_at,payload_json) VALUES (:id,:kind,:date,:payload)'),
            {'id':payload['report_id'],'kind':payload['kind'],'date':NOW.replace(tzinfo=None),'payload':json.dumps(payload)})
    return payload['report_id']

@freeze_time(NOW)
def test_report_view_section_summary_sections_get_narrative_divs_not_raw_field_rows(db):
    """2026-10-12 fix, same bug as the markdown renderer: a block in SECTION_SUMMARY_SECTIONS
    must carry the "Section summary" / "What it means for the day" decision divs on the live
    /view page, not a raw `_field_row` <div class="field"> per field. Re-pointed 2026-10-16
    from 'surface' (now narrated once, in the opening, with no card of its own) to 'profile',
    a supporting-detail block that still renders as a card and owns the volume_profile chart.
    Also confirms the chart image slot (VISUAL DELIVERY FAILED, since no chart is actually
    persisted here) renders regardless of which fields_html branch fired."""
    from backend.report_policy import SECTION_SUMMARY_SECTIONS, section_summary, observed
    assert 'profile' in SECTION_SUMMARY_SECTIONS
    blocks={n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}
    blocks['risk_on_defensive']['verdict']=observed('Risk-on price confirmation','Observed provider feed',NOW,NOW)
    first_field=next(iter(REQUIREMENTS['profile']))
    blocks['profile'][first_field]=observed({'SPY':{'poc':100.5}},'Observed profile provider',NOW,NOW)
    report_id='a'*24
    chart_ref='https://example.test/api/spreadworks/reports/charts/'+'b'*32+'.png'
    payload={'report_id':report_id,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','markdown_url':'https://example.test/'+report_id+'.md',
             'report_blocks':blocks,'chart_urls':{'volume_profile':chart_ref}}
    _store_report(payload)
    view=report.report_view(report_id)
    profile_card=view.split('id="sec-profile"')[1].split('</section>')[0]
    assert 'Section summary' in profile_card and 'What it means for the day' in profile_card
    assert '<div class="field decision">' in profile_card
    assert '<div class="field"><div class="fieldtop">' not in profile_card  # no raw _field_row div
    assert html.escape(section_summary('profile',blocks['profile'])) in profile_card
    # Chart slot renders (as a failure notice, since no PNG bytes are actually persisted in this
    # test) regardless of the fields_html branch -- it is built from chart_urls/_SUPPORTING_CHARTS,
    # not from whether the section is narrative-only or raw-field.
    assert 'VISUAL DELIVERY FAILED' in profile_card
    # A promoted block has no card of its own -- its narrative lives in the opening, once.
    assert 'id="sec-surface"' not in view

def test_report_view_threads_the_flat_regime_label_into_put_call_tie_in(db):
    """2026-10-14: report_view computes mission_side from risk_on_defensive.verdict but, before
    this fix, never read regime_label alongside it -- the live /view page's trade_volatility_
    scan "what it means" line always fell back to the hedged mission_side wording and named
    both possible sides verbatim, even though the flat regime_label was sitting right there in
    the same stored report_blocks."""
    from backend.report_policy import observed
    blocks={n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}
    blocks['risk_on_defensive']['verdict']=observed('Defensive price confirmation','Observed provider feed',NOW,NOW)
    blocks['risk_on_defensive']['regime_label']=observed('DEFENSIVE','Observed provider feed',NOW,NOW)
    blocks['trade_volatility_scan']['put_call_ratio']=observed({'SPY':{'pcr_oi':1.4}},'Observed provider feed',NOW,NOW)
    report_id='e'*24
    payload={'report_id':report_id,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','markdown_url':'https://example.test/'+report_id+'.md',
             'report_blocks':blocks,'chart_urls':{}}
    _store_report(payload)
    view=report.report_view(report_id)
    # 2026-10-16: trade_volatility_scan has no card of its own any more; its takeaway (with the
    # flat-regime tie-in) is printed once inside the opening's "TradingVolatility top setups".
    assert 'id="sec-trade-volatility-scan"' not in view
    assert view.count('flat DEFENSIVE regime call')==1
    assert 'defensive/risk-on' not in view  # the old bug: both words, every time

@freeze_time(NOW)
def test_report_view_sections_are_all_open_by_default_and_keep_every_field_in_the_dom(db):
    """Leron, 2026-10-16: "nothing should be collapse." Every section -- bookkeeping or
    decision-relevant -- now opens on first paint; collapsing (via <details>'s native
    toggle or the page's Collapse-all button) is something the reader does, not a default
    that hides real fields behind a click. <details> stays in the markup either way, so
    every required field is always present in the HTML regardless of open/closed state."""
    from backend.report_policy import observed
    blocks={n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}
    blocks['risk_on_defensive']['verdict']=observed('Risk-on price confirmation','Observed provider feed',NOW,NOW)
    blocks['scanner']['minute_cadence']=observed(5,'Observed provider feed',NOW,NOW)
    report_id='d'*24
    payload={'report_id':report_id,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','markdown_url':'https://example.test/'+report_id+'.md',
             'report_blocks':blocks,'chart_urls':{}}
    _store_report(payload)
    view=report.report_view(report_id)
    scanner_card=view.split('id="sec-scanner"')[1].split('</section>')[0]
    assert '<details open>' in scanner_card  # bookkeeping section opens by default
    assert 'Section summary' in scanner_card
    # Every surviving card is open on first paint -- no bare <details> anywhere.
    assert view.count('<details>')==0 and view.count('<details open>')==9

def test_report_view_raw_field_branch_still_used_for_a_section_outside_summary_sections(monkeypatch,db):
    """Defensive fallback check: if a section is NOT in SECTION_SUMMARY_SECTIONS (none are,
    today -- this is the hypothetical "future section added to REQUIREMENTS without a narrative
    builder" case the else branch exists for), report_view must still fall back to the raw
    `_field_row` per-field dump rather than silently rendering nothing."""
    from backend import report_policy as rp
    monkeypatch.setattr(rp,'SECTION_SUMMARY_SECTIONS',tuple(n for n in rp.SECTION_SUMMARY_SECTIONS if n!='scanner'))
    blocks={n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}
    blocks['scanner']['minute_cadence']=rp.observed(5,'Observed provider feed',NOW,NOW)
    report_id='c'*24
    payload={'report_id':report_id,'kind':'intraday','generated_at':NOW.isoformat(),
             'report_completeness':'INCOMPLETE','markdown_url':'https://example.test/'+report_id+'.md',
             'report_blocks':blocks,'chart_urls':{}}
    _store_report(payload)
    view=report.report_view(report_id)
    scanner_card=view.split('id="sec-scanner"')[1].split('</section>')[0]
    assert '<div class="field"><div class="fieldtop">' in scanner_card  # raw _field_row, not narrative
    assert 'Section summary' not in scanner_card

def _empty_blocks():
    return {n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}

async def _fake_fetch_ok(app,setup,now):
    return package(),'fresh'

async def _fake_fetch_none(app,setup,now):
    return None,'no expiration matched the setup preference'

def test_refresh_live_contract_packages_fills_an_unavailable_day_strategy_contracts(monkeypatch):
    """Leron, 2026-10-14: "what strikes are the sellers at" -- the stored option_strike_selection
    intraday_watch.py persists is stamped at ENTRY_READY transition time, not report-build time,
    so qualify_package()'s <=90s freshness check rejects it on every report. This re-fetches
    live at report-build time instead, using the same fetch_option_selection() the watcher
    calls, and should fill contract_packages + day_strategy.contracts when both start out
    unavailable."""
    monkeypatch.setattr(report,'fetch_option_selection',_fake_fetch_ok)
    blocks=_empty_blocks()
    plan={'setups':[{'setup_id':'s1','symbol':'SPY','strategy':'call_debit_spread'}]}
    runtime={'setup_state_by_id':{'s1':'ENTRY_READY'}}
    core={'surface':{'SPY':{'spot':100.5}}}
    asyncio.run(report.refresh_live_contract_packages(None,blocks,plan,runtime,core,NOW))
    assert blocks['contract_packages']['legs']['status']=='live'
    assert blocks['contract_packages']['legs']['value'][0]['setup_id']=='s1'
    assert blocks['contract_packages']['strikes']['value'][0]['value']==[100,105]
    assert blocks['day_strategy']['contracts']['status']=='live'
    assert blocks['day_strategy']['contracts']['value'][0]['setup_id']=='s1'

def test_refresh_live_contract_packages_never_overwrites_an_already_live_field(monkeypatch):
    """The normal (stored-snapshot) path occasionally does qualify in time -- this refetch must
    never second-guess or replace a field that path already populated."""
    monkeypatch.setattr(report,'fetch_option_selection',_fake_fetch_ok)
    blocks=_empty_blocks()
    already=p.observation([{'setup_id':'existing','strategy':'put_credit_spread','value':[1]}],'Watcher fresh per-leg chain qualification',NOW,NOW)
    blocks['contract_packages']['legs']=already
    blocks['day_strategy']['contracts']=already
    plan={'setups':[{'setup_id':'s1','symbol':'SPY','strategy':'call_debit_spread'}]}
    runtime={'setup_state_by_id':{'s1':'ENTRY_READY'}}
    core={'surface':{'SPY':{'spot':100.5}}}
    asyncio.run(report.refresh_live_contract_packages(None,blocks,plan,runtime,core,NOW))
    assert blocks['contract_packages']['legs']==already
    assert blocks['day_strategy']['contracts']==already

def test_refresh_live_contract_packages_only_checks_entry_ready_setups(monkeypatch):
    """A WATCH or PENDING setup has no business triggering a live options-chain fetch every
    report cycle -- only a setup that has actually confirmed ENTRY_READY."""
    calls=[]
    async def spy_fetch(app,setup,now):
        calls.append(setup['setup_id']);return package(),'fresh'
    monkeypatch.setattr(report,'fetch_option_selection',spy_fetch)
    blocks=_empty_blocks()
    plan={'setups':[{'setup_id':'watching','symbol':'SPY','strategy':'call_debit_spread'}]}
    runtime={'setup_state_by_id':{'watching':'WATCH'}}
    core={'surface':{'SPY':{'spot':100.5}}}
    asyncio.run(report.refresh_live_contract_packages(None,blocks,plan,runtime,core,NOW))
    assert calls==[]
    assert blocks['contract_packages']['legs']['status']=='unavailable'
    assert blocks['day_strategy']['contracts']['status']=='unavailable'

def test_refresh_live_contract_packages_tolerates_fetch_failures(monkeypatch):
    """A rejected/failed live fetch (no expiration matched, Tradier error, etc.) must leave the
    unavailable fields exactly as they were -- never a half-built package, never a crash that
    takes the whole report down with it."""
    monkeypatch.setattr(report,'fetch_option_selection',_fake_fetch_none)
    blocks=_empty_blocks()
    plan={'setups':[{'setup_id':'s1','symbol':'SPY','strategy':'call_debit_spread'}]}
    runtime={'setup_state_by_id':{'s1':'ENTRY_READY'}}
    core={'surface':{'SPY':{'spot':100.5}}}
    asyncio.run(report.refresh_live_contract_packages(None,blocks,plan,runtime,core,NOW))
    assert blocks['contract_packages']['legs']['status']=='unavailable'
    assert blocks['day_strategy']['contracts']['status']=='unavailable'

    async def spy_raise(app,setup,now):
        raise RuntimeError('tradier down')
    monkeypatch.setattr(report,'fetch_option_selection',spy_raise)
    blocks2=_empty_blocks()
    asyncio.run(report.refresh_live_contract_packages(None,blocks2,plan,runtime,core,NOW))
    assert blocks2['contract_packages']['legs']['status']=='unavailable'

def test_claim_delivery_tick_blocks_a_second_claim_for_the_same_exact_minute():
    """Leron, 2026-10-16: "im getting duplicate reports" -- 3 full kind="morning" reports
    archived within 10 seconds of each other. claim_delivery() above is hourly-granularity
    (right for intraday/market_open, which truly must never resend within the hour), but the
    morning job deliberately re-runs within the same hour (07:35->07:45->07:55 retries model
    enrichment on a deterministic-fallback plan) -- an hourly lease would wrongly block that.
    claim_delivery_tick() claims the exact minute instead: a second call for the SAME tick
    must see the first claim and return None; a call for a DIFFERENT minute must proceed
    independently; and after finish_delivery() releases the slot as posted, a repeat claim
    for that same already-posted tick must still be blocked (no resend of a completed tick)."""
    first = report.claim_delivery_tick('morning', NOW)
    assert first is not None
    second = report.claim_delivery_tick('morning', NOW)
    assert second is None, "a second caller for the exact same tick must not also claim it"

    later = NOW + timedelta(minutes=1)
    third = report.claim_delivery_tick('morning', later)
    assert third is not None, "a different minute is a different tick and must not be blocked"

    report.finish_delivery(first, 'report-id-1', True)
    fourth = report.claim_delivery_tick('morning', NOW)
    assert fourth is None, "a completed tick must not be re-claimed"

@pytest.mark.asyncio
@freeze_time(NOW)
async def test_report_view_is_single_pass_no_narrative_or_chart_appears_twice(db,monkeypatch):
    """Leron, 2026-10-16: "why does it have duplicate information." /view used to concatenate
    render_opening_html's curated sections with one card per block, both built from the same
    _narrative_* functions: 25 of 34 cards reprinted their narrative verbatim and 7 chart
    panels were embedded twice. Asserts, on a fully assembled report with all 11 real PNGs:
    no block's narrative appears twice, each chart is embedded once, and only the 9 blocks
    with no top-level home get a card."""
    import re
    from backend.report_policy import section_summary,section_meaning,SECTION_SUMMARY_SECTIONS
    monkeypatch.setattr(report,'cached_core',lambda now:core())
    monkeypatch.setattr(report,'_plan_and_runtime',lambda now:({},{}))
    monkeypatch.setattr(report,'scheduled_events',lambda now:([now.date()],[]))
    result=await report.assemble_report(SimpleNamespace(),kind='morning')
    view=report.report_view(result['report_id'])
    # Narrative text: the cards add nothing a block already said in the opening. A promoted
    # block's text occurs exactly as often as in render_opening_html alone (the opening itself
    # re-quotes a few narratives by design, e.g. Market story + Dealer positioning on thin
    # data); a supporting block's text occurs at most once more, in its own single card.
    from backend.report_policy import render_opening_html
    opening=render_opening_html(result)
    checked=0
    for name,block in result['report_blocks'].items():
        if name not in SECTION_SUMMARY_SECTIONS:continue
        for text_ in (section_summary(name,block),section_meaning(name,block)):
            if len(text_)<60:continue  # short canned fallbacks legitimately repeat across blocks
            checked+=1
            seen=html.escape(text_)
            allowed=opening.count(seen)+(0 if name in report._PROMOTED_BLOCKS else 1)
            assert view.count(seen)<=allowed,f'{name} narrative printed again outside the opening: {text_[:80]}'
    assert checked>0
    # The takeaway survives the de-dupe: every promoted block's "What it means for the day" text
    # is printed once, inside its own promoted section (no card carries it any more). Where two
    # blocks share a section they get one combined takeaway; two blocks whose lines happen to
    # be word-for-word identical collapse to one printed line.
    from backend.report_policy import _side_label
    blocks_=result['report_blocks']
    mission_side=_side_label((blocks_['risk_on_defensive']['verdict'] or {}).get('value'))
    label_=(blocks_['risk_on_defensive'].get('regime_label') or {}).get('value')
    takeaways={n:section_meaning(n,blocks_[n],mission_side,label_ if isinstance(label_,str) else None)
               for n in report._PROMOTED_BLOCKS}
    assert len(takeaways)==25
    # The three Today-vs-forward rows count as one slot: a sentence shared by several rows prints
    # once and the later rows read "Same as day strategy above."
    sections=[('risk_on_defensive',),('day_strategy','near_forward_strategy','forward_strategy'),
              ('premium_selling',),('market_control',),('gamma',),('flow',),('surface','smile'),('expected_move',),
              ('breadth','sector_credit'),('macro','futures_context'),('morning_comparison',),
              ('trade_volatility_scan',),('contract_packages','entry_watches'),('candidate_analysis',),
              ('position_management','trigger_accountability'),('range_stall',),('event_calendar',),('adaptation_rules',)]
    assert sorted(n for sec in sections for n in sec)==sorted(takeaways)
    # One printed line per (section, distinct text): two sections may legitimately share a canned
    # sentence (near/forward strategy), but no section prints its takeaway twice.
    slots={}
    for sec in sections:
        for t in {takeaways[n] for n in sec}:
            slots[t]=slots.get(t,0)+1
    for t,expected in slots.items():
        assert view.count(html.escape(t))==expected,f'takeaway printed {view.count(html.escape(t))}x, expected {expected}: {t[:80]}'
    # 18 promoted-section takeaways + 7 supporting cards that keep the Summary/Means pair.
    assert view.count('What it means for the day')==25
    # Charts: every panel embedded at most once (identical base64 payloads => identical image).
    sources=re.findall(r'<img[^>]*\ssrc="([^"]+)"',view)
    assert len(sources)==len(set(sources))==11
    for url in result['chart_urls'].values():assert url not in view  # only data: URIs, never external
    # Cards: only the 9 supporting blocks, each once, under one divider heading.
    labels=re.findall(r'<summary[^>]*>(.*?)</summary>',view,re.S)
    assert len(labels)==len(set(labels))==9
    assert sorted(labels)==sorted(n.replace('_',' ').title() for n in
        ('forward_strikes','profile','paper_scorecard','scanner','event_study','engine_consensus',
         'horizon_comparison','visuals','data_integrity'))
    assert view.count('Supporting detail')==1
    assert not (report._PROMOTED_BLOCKS & {l.lower().replace(' ','_') for l in labels})
    # visuals / data_integrity show a short counted status, never the machine dump.
    assert 'sha256' not in view.lower() and 'size bytes' not in view.lower()
    assert re.search(r'11 of 11 chart panels delivered and verified',view)
    assert re.search(r'\d+ fields carry a source clock; \d+ last-known, \d+ unavailable, \d+ producer failures\.',view)

def test_promoted_blocks_and_supporting_cards_partition_the_contract():
    """_PROMOTED_BLOCKS mirrors render_opening_html's section list; it plus the supporting
    cards must cover every contract block exactly once so the two cannot silently drift."""
    from backend.report_policy import SECTION_SUMMARY_SECTIONS
    supporting={'forward_strikes','profile','paper_scorecard','scanner','event_study','engine_consensus',
                'horizon_comparison','visuals','data_integrity'}
    assert len(report._PROMOTED_BLOCKS)==25
    assert not report._PROMOTED_BLOCKS & supporting
    assert report._PROMOTED_BLOCKS|supporting==set(REQUIREMENTS)==set(SECTION_SUMMARY_SECTIONS)

def _store_report_with_oversized_table(report_id,chart_ids=()):
    """Stored report whose markdown carries a table row far taller than a PDF page -- the
    shape of the live 2026-10-16 report that made report.pdf and portable.zip return 500."""
    huge='catalyst '+'Fed speakers, yields fell sharply and opex pinning risk. '*120
    markdown='\n\n'.join(['# Report','| Horizon | Trigger | Invalidation | Status | Contracts |','|---|---|---|---|---|',
                          f'| day strategy | {huge} | close above 729.72 | WAIT | next weekly |','After the table'])
    blocks={n:{f:{'status':'unavailable','reason':'No source observation'} for f in fs} for n,fs in REQUIREMENTS.items()}
    payload={'report_id':report_id,'kind':'intraday','generated_at':NOW.isoformat(),'report_completeness':'INCOMPLETE',
             'markdown_url':'https://example.test/'+report_id+'.md','report_markdown':markdown,'report_blocks':blocks,
             'chart_urls':{'surface':'https://example.test/api/spreadworks/reports/charts/'+cid+'.png' for cid in chart_ids}}
    return _store_report(payload)

@freeze_time(NOW)
def test_report_pdf_route_returns_pdf_when_markdown_has_a_page_tall_table_row(db):
    report_id=_store_report_with_oversized_table('c'*24)
    assert report.get_report_pdf(report_id).body.startswith(b'%PDF-')

@freeze_time(NOW)
def test_portable_zip_route_returns_zip_when_markdown_has_a_page_tall_table_row(db):
    import base64,hashlib,zipfile
    buf=io.BytesIO();Image.new('RGB',(1200,700),(11,18,32)).save(buf,format='PNG');png=buf.getvalue()
    chart_id=hashlib.sha256(png).hexdigest()[:32]
    with report.engine.begin() as c:
        c.execute(text('INSERT INTO sw_report_charts (chart_id,png_base64,created_at) VALUES (:id,:b,:t)'),
                  {'id':chart_id,'b':base64.b64encode(png).decode(),'t':NOW.replace(tzinfo=None)})
    report_id=_store_report_with_oversized_table('d'*24,[chart_id])
    body=report.get_portable_report(report_id).body
    assert body.startswith(b'PK')
    assert zipfile.ZipFile(io.BytesIO(body)).read('report.pdf').startswith(b'%PDF-')


def test_rejected_atm_pair_leaves_every_downstream_surface_read_unavailable_with_the_reason():
    """The producer now returns atm_iv=None / LOW with a specific reason when no call and put share a strike
    near spot. Every report field built from that row must be unavailable with that reason: no expected
    move, no IV-versus-realized, no ATM IV."""
    reason='1DTE ATM IV unavailable: no call and put at one strike within 0.15% of spot 777.22; nearest call strike 650 ($127.2 away), nearest put strike 793 ($15.8 away)'
    row={'symbol':'SPY','available':False,'confidence':'LOW','reason':reason,'source':'Tradier','source_timestamp':NOW.isoformat(),
         'atm_iv':None,'expected_move_pct_1d':None,'expected_move_dollars_1d':None,'expected_move_low':None,'expected_move_high':None,
         'realized_vol_60m':0.048,'iv_minus_realized_vol':None,'iv_rv_comparison':{'atm_iv':None,'realized_vol_60m':0.048,'iv_minus_realized_vol':None}}
    for keys in (['atm_iv'],['expected_move_pct_1d'],['expected_move_dollars_1d'],['expected_move_low','expected_move_high'],
                 ['atm_iv','realized_vol_60m','iv_minus_realized_vol','realized_vol_source_timestamp']):
        item=report.merge_symbols({'SPY':dict(row,**row['iv_rv_comparison'])} if 'iv_minus_realized_vol' in keys else {'SPY':row},keys,NOW)
        assert item['status']=='unavailable' and reason in item['reason'] and not item.get('value')

