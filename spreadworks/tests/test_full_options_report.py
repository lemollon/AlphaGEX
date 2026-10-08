from datetime import datetime,timedelta,timezone
import io,json
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.pool import StaticPool
from freezegun import freeze_time
from PIL import Image
from backend import report_producers as p,report_ledger as ledger,full_options_report as report
from backend.report_contract import REQUIREMENTS,validate_rendered_report
UTC=timezone.utc
NOW=datetime(2026,10,2,15,0,tzinfo=UTC)

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
    assert 'Observed IV provider' in report.report_view(result['report_id'])
    assert report.latest_report()['report_id']==result['report_id']
    view=report.report_view(result['report_id'])
    assert 'src="data:image/png;base64,' in view
    assert 'src="https://' not in view
    assets=report.get_assets(result['report_id'])
    assert assets['complete'];assert len(assets['images'])==11
    assert all(row['validated'] and row['sha256'][:32]==row['chart_id'] for row in assets['images'])
    assert report.get_chart_pdf(result['report_id']).body.startswith(b'%PDF-')
    import zipfile
    archive=zipfile.ZipFile(io.BytesIO(report.get_portable_report(result['report_id']).body))
    assert {'report.html','report.md','manifest.json','charts.pdf'}<=set(archive.namelist())
    assert 'src="https://' not in archive.read('report.html').decode()
    assert len([name for name in archive.namelist() if name.endswith('.png')])==11
    # Preparing delivery again preserves embeds; callers cannot bypass rendered checks.
    from backend.report_contract import prepare_report_delivery
    assert prepare_report_delivery(result)['publishable']
    assert result['report_markdown'].count(result['chart_urls']['smile_term'])==2  # field value plus image


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
