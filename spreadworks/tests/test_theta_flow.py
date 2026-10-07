"""Theta flow evidence, provider failure, stale reads and report integration."""
from datetime import datetime, timedelta, timezone
import pytest
import requests
from freezegun import freeze_time
from backend import market_structure as ms, report_policy as policy, report_refresh as refresh
from backend.report_contract import FLOW_SOURCE

NOW = datetime(2026, 10, 7, 18, 35, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_selection_spot(monkeypatch):
    monkeypatch.setattr(ms,'fetch_spot',lambda *a,**k:{'price':770,'fresh':True})


def tape(**changes):
    return dict(symbol='SPY', expiration='2026-10-09', strike='770', right='call',
                trade_timestamp='2026-10-07T14:34:59.500', quote_timestamp='2026-10-07T14:34:59',
                price='1.10', bid='1.00', ask='1.10', size='10', condition='18', **changes)


def test_live_theta_request_and_provenance_reach_policy(monkeypatch):
    calls=[]
    def theta(path, params, **kwargs):
        calls.append((path,params,kwargs))
        return [tape()]
    monkeypatch.setattr(ms, '_theta_rows', theta)
    row=ms.fetch_trade_quote_flow('SPY', NOW)
    assert row['available'] and row['source']==FLOW_SOURCE
    assert row['n_trades']==1 and row['evidence']['classified_contracts']==10
    assert row['source_timestamp']==(NOW-timedelta(milliseconds=500)).isoformat()
    assert row['evidence']['buckets']['1_5dte']['calls_bought']['premium']==1100
    assert calls[0][0]=='/v3/option/list/expirations'
    assert calls[1][0]=='/v3/option/list/strikes'
    params=calls[2][1]
    assert params['exclusive'] and params['expiration']=='2026-10-09' and params['max_dte']==60
    assert params['strike']=='770.000'
    assert row['evidence']['completed_expirations']==['2026-10-09']
    assert params['start_time']=='14:33:00.000' and params['end_time']=='14:35:00.000'
    assert refresh.verified(row)
    item=policy.normalize_item(policy.observed(row['evidence'],FLOW_SOURCE,row['source_timestamp'],NOW),NOW)
    assert item['status']=='live' and item['source']==FLOW_SOURCE


def test_expiration_sample_uses_only_listed_dates_in_supported_horizons():
    rows=[{'expiration':d} for d in ['2026-10-06','2026-10-07','2026-10-09',
          '2026-10-16','2026-10-23','2026-11-20','2026-12-18','bad']]
    assert ms._flow_expiration_candidates(NOW.astimezone(ms.ET),rows)==[
        '2026-10-07','2026-10-09','2026-10-23','2026-11-20']


def test_partial_expiration_failures_preserve_real_prints_and_scope(monkeypatch):
    calls=[]
    def theta(path,params,**kwargs):
        calls.append(params)
        if path.endswith('/expirations'):
            return [{'expiration':'2026-10-07'},{'expiration':'2026-10-09'}]
        if params['expiration']=='2026-10-07':
            response=requests.Response();response.status_code=429
            raise requests.HTTPError(response=response)
        return [tape()]
    monkeypatch.setattr(ms,'_theta_rows',theta)
    row=ms.fetch_trade_quote_flow('SPY',NOW)
    assert row['available'] and row['n_trades']==1
    assert row['evidence']['completed_expirations']==['2026-10-09']
    assert row['evidence']['failed_expirations']=={'2026-10-07':'HTTP 429'}
    assert row['evidence']['partial_coverage']
    assert all(c.get('expiration')!='*' for c in calls)


def test_contract_requests_sample_nearest_listed_strikes_and_never_bulk(monkeypatch):
    contracts=[]
    def theta(path,params,**kwargs):
        if path.endswith('/expirations'):return [{'expiration':'2026-10-09'}]
        if path.endswith('/strikes'):return [{'strike':s} for s in [760,765,770,775,780]]
        contracts.append(params)
        row=tape();row['strike']=params['strike'];return [row]
    monkeypatch.setattr(ms,'_theta_rows',theta)
    flow=ms.fetch_trade_quote_flow('SPY',NOW)
    assert flow['available'] and flow['n_trades']==3
    assert [r['strike'] for r in contracts]==['770.000','765.000','775.000']
    assert len(flow['evidence']['completed_contracts'])==3


def test_missing_selection_spot_fails_without_requesting_option_contracts(monkeypatch):
    monkeypatch.setattr(ms,'fetch_spot',lambda *a,**k:{'fresh':False,'price':None})
    monkeypatch.setattr(ms,'_theta_rows',lambda *a,**k:pytest.fail('No spot for bounded selection'))
    assert not ms.fetch_trade_quote_flow('SPY',NOW)['available']


@pytest.mark.parametrize('changes',[
    {'quote_timestamp':None}, {'quote_timestamp':'2026-10-07T14:34:59.500'},
    {'quote_timestamp':'2026-10-07T14:34:58'}, {'condition':'130'}, {'condition':None},
    {'bid':'1.10'}, {'ask':'0.90'}, {'bid':'nan'}, {'ask':'inf'}, {'price':'5.00'}, {'price':'1.05'},
])
def test_bad_quote_or_complex_trade_stays_in_unclassified_denominator(changes):
    row=tape();row.update(changes)
    result=ms.summarize_flow_evidence([row],NOW.astimezone(ms.ET),NOW)
    assert result['total_contracts']==10 and result['classified_contracts']==0
    assert result['unclassified_contracts']==10
    assert result['total_premium']==result['unclassified_premium']


def test_cancel_stale_future_and_nonfinite_rows_excluded():
    rows=[]
    for changes in ({'condition':'40'},{'trade_timestamp':'2026-10-07T14:30:00'},
                    {'trade_timestamp':'2026-10-07T14:36:00'},{'price':'nan'}):
        row=tape();row.update(changes);rows.append(row)
    result=ms.summarize_flow_evidence(rows,NOW.astimezone(ms.ET),NOW)
    assert result['total_contracts']==0 and result['n_trades']==0 and result['rejected_rows']==4


@pytest.mark.parametrize('status',[401,403,429,502,504])
def test_provider_failures_use_explicit_unclassified_tradier_fallback(monkeypatch,status):
    def fail(*args,**kwargs):
        response=requests.Response();response.status_code=status
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(ms,'_theta_rows',fail)
    row=ms.fetch_trade_quote_flow('SPY',NOW)
    assert not row['available'] and row['confidence']=='LOW'
    assert row['source'].startswith('Tradier fallback') and row['buckets']=={}
    assert 'HTTP '+str(status) in row['reason'] and 'contemporaneous' in row['reason']


@freeze_time(NOW)
def test_cached_flow_endpoint_never_marks_old_tape_live(monkeypatch):
    old={'confidence':'MEDIUM','source_timestamp':(NOW-timedelta(seconds=91)).isoformat()}
    monkeypatch.setattr(ms,'_latest_trade_quote_flow',lambda *args:dict(old))
    assert not ms.trade_quote_flow_symbol('SPY')['available']
    assert not ms.latest_trade_quote_flow_symbol('SPY')['available']


def test_premarket_does_not_request_or_relabel_yesterday_tape(monkeypatch):
    monkeypatch.setattr(ms,'_theta_rows',lambda *a,**k:pytest.fail('Premarket flow request'))
    assert not ms.fetch_trade_quote_flow('SPY',NOW.replace(hour=12))['available']


def test_flow_reads_allow_only_versioned_theta_and_do_not_collect_on_empty_cache(monkeypatch):
    queries=[]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):queries.append((str(sql),params));return self
        def fetchone(self):return None
    class Engine:
        def begin(self):return Connection()
    monkeypatch.setattr(ms,'engine',Engine())
    monkeypatch.setattr(ms,'ensure_tables',lambda:None)
    monkeypatch.setattr(ms,'fetch_trade_quote_flow',lambda *a:pytest.fail('Read triggered collector'))
    assert ms._latest_trade_quote_flow('SPY') is None
    assert queries[0][1]['flow_source']==FLOW_SOURCE


def test_flow_report_fields_and_forward_prints_keep_theta_provenance(monkeypatch):
    from backend import full_options_report as report
    from backend.report_policy import normalize_blocks
    monkeypatch.setattr(ms,'_theta_rows',lambda *a,**k:[tape()])
    flow=ms.fetch_trade_quote_flow('SPY',NOW)
    core={'surface':{'SPY':{},'QQQ':{}},'gamma':{},'flow':{'SPY':flow},'cross_asset':{},'volatility':{}}
    blocks=report.report_blocks(core,{}, {}, {}, {'entry_ready_alerts':0,'trade_details':[],'exceptions':[],'fill_rules':'One-contract report simulation','loss_clusters':[]}, {}, {}, [], NOW)
    normalized=normalize_blocks(blocks,NOW)
    assert normalized['flow']['calls_bought']['status']=='live'
    assert normalized['flow']['provider_provenance']['value']['SPY']==FLOW_SOURCE
    assert normalized['forward_strikes']['contemporaneous_bid_ask']['status']=='live'
    assert normalized['forward_strikes']['strikes']['source']==FLOW_SOURCE
