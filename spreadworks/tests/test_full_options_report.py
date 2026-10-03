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
    ts=NOW.astimezone(p.ET).replace(tzinfo=None).isoformat()
    rows=[{'timestamp':ts,'price':100.02,'size':50},{'timestamp':ts,'price':100.12,'size':200},{'timestamp':ts,'price':100.32,'size':50},
          {'timestamp':ts,'price':float('nan'),'size':100}]
    result=p.volume_profile(rows,.1,NOW-timedelta(minutes=30),NOW)
    assert result['total_volume']==300;assert sum(r['volume'] for r in result['bins'])==300
    assert result['val']<=result['poc']<=result['vah'];assert result['rejected_rows']==1
    assert 'not full session' in result['method']


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
    # Preparing delivery again preserves embeds; callers cannot bypass rendered checks.
    from backend.report_contract import prepare_report_delivery
    assert prepare_report_delivery(result)['publishable']
    assert result['report_markdown'].count(result['chart_urls']['smile_term'])==2  # field value plus image


def test_missing_clocks_never_become_live_context():
    blocks=report.report_blocks(core(),{}, {},{},ledger_empty(),{}, {},[],NOW)
    assert blocks['contract_packages']['legs']['status']=='unavailable'
    assert blocks['breadth']['advance_decline']['status']=='unavailable'
    assert blocks['macro']['rates']['status']=='unavailable'

def ledger_empty():
    return {'entry_ready_alerts':0,'trade_details':[],'exceptions':[],'fill_rules':'test','loss_clusters':[]}

@freeze_time(NOW)
@pytest.mark.parametrize('offset',[None,-91,1])
def test_iv_receipt_cannot_refresh_missing_stale_or_future_nbbo(monkeypatch,offset):
    from backend import market_structure as ms
    rows=[{'strike':100+i,'right':'call','implied_vol':.2,'expiration':'2026-10-09',
           **({'timestamp':(NOW+timedelta(seconds=offset)).astimezone(p.ET).replace(tzinfo=None).isoformat()} if offset is not None else {})} for i in range(25)]
    monkeypatch.setattr(ms,'_theta_rows',lambda path,params:rows)
    valid,reason=ms._surface_rows('SPY',NOW)
    assert valid==[];assert reason=='thin_theta_iv_snapshot_after_retry'

@freeze_time(NOW)
def test_iv_preserves_oldest_actual_quote_underlying_clock(monkeypatch):
    from backend import market_structure as ms
    rows=[{'strike':100+i,'right':'call','implied_vol':.2,'expiration':'2026-10-09',
           'timestamp':(NOW-timedelta(seconds=20)).astimezone(p.ET).replace(tzinfo=None).isoformat(),
           'underlying_timestamp':(NOW-timedelta(seconds=30)).astimezone(p.ET).replace(tzinfo=None).isoformat()} for i in range(25)]
    monkeypatch.setattr(ms,'_theta_rows',lambda path,params:rows)
    valid,reason=ms._surface_rows('SPY',NOW)
    assert len(valid)==25;assert reason is None
    assert all(row['timestamp']==NOW-timedelta(seconds=30) for row in valid)


def test_session_profile_checkpoint_merges_observed_bins_without_new_trades():
    start=NOW-timedelta(minutes=30);middle=NOW-timedelta(minutes=15)
    old=p.volume_profile([{'price':100.1,'size':50,'timestamp':(middle-timedelta(seconds=1)).isoformat()}],.1,start,middle)
    new=p.volume_profile([{'price':100.2,'size':100,'timestamp':(NOW-timedelta(seconds=1)).isoformat()}],.1,middle,NOW)
    merged=p.merge_profiles(old,new,.1)
    assert merged['trade_count']==2;assert merged['total_volume']==150
    assert merged['window_start']==start.isoformat();assert merged['window_end']==NOW.isoformat()
    assert sum(r['volume'] for r in merged['bins'])==150
