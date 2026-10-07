from datetime import datetime, timezone, timedelta
from backend import market_structure as ms
from backend import tradier_report_source as src
from backend.report_policy import normalize_item

NOW=datetime(2026,10,5,16,tzinfo=timezone.utc)

def test_no_theta_fallback_for_missing_indices(monkeypatch):
    monkeypatch.setattr(ms,'_tradier_vol_quotes',lambda symbols:{})
    monkeypatch.setattr(ms,'_index_prices',lambda *a: (_ for _ in ()).throw(AssertionError('Theta called')))
    result=ms.fetch_vol_indices(NOW)
    assert result['source']=='Tradier'
    assert not result['available']

def test_surface_uses_tradier_adapter(monkeypatch):
    monkeypatch.setattr(src,'option_rows',lambda s,n:([{'iv':.2}],None))
    monkeypatch.setattr(ms,'_theta_rows',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Theta called')))
    assert ms._surface_rows('SPY',NOW)[0][0]['iv']==.2

def test_flow_does_not_fabricate_initiation_or_call_theta(monkeypatch):
    monkeypatch.setattr(ms,'_theta_rows',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Theta called')))
    result=ms.fetch_trade_quote_flow('SPY',NOW)
    assert result['source']=='Tradier' and not result['available']
    assert result['buckets']=={}
    assert 'contemporaneous' in result['reason']

def test_legacy_theta_cache_is_rejected():
    assert normalize_item(dict(value=1,source='ThetaData snapshots',confidence='HIGH',status='live',source_timestamp=NOW.isoformat()),NOW)['status']=='unavailable'

def test_iv_inversion_and_bounds():
    # Independently known ATM zero-ish horizon price: 5% rate, 20% vol, 1y.
    iv=src.implied_vol(100,100,1,'call',10.450583572185565)
    assert abs(iv-.2)<1e-8
    assert src.implied_vol(100,100,1,'call',200) is None

def test_old_bbo_rejected_even_if_fetched_now(monkeypatch):
    monkeypatch.setattr(ms,'fetch_spot',lambda *a:dict(price=100,fresh=True,source_timestamp=NOW))
    old=(NOW-timedelta(minutes=5)).timestamp()*1000
    def feed(path,params):
        if path=='/options/expirations':return {'expirations':{'date':['2026-10-06']}}
        return {'options':{'option':[dict(bid=1,ask=1.1,strike=100,option_type='call',bid_date=old,ask_date=old)]}}
    monkeypatch.setattr(src,'get',feed)
    rows,reason=src.option_rows('SPY',NOW)
    assert rows==[] and reason


def test_professional_contract_uses_fresh_tradier_bbo_and_modeled_greeks(monkeypatch):
    monkeypatch.setattr(ms,'fetch_spot',lambda *a:dict(price=100.0,fresh=True,source_timestamp=NOW))
    fresh=(NOW-timedelta(seconds=2)).timestamp()*1000
    raw=dict(symbol='QQQ261009C00100000',bid=2.0,ask=2.2,strike=100,
             option_type='call',bid_date=fresh,ask_date=fresh,
             open_interest=1200,volume=400,bidsize=25,asksize=30)
    row=src.normalize_professional_contract(raw,'QQQ','2026-10-09',
                                             dict(price=100.0,fresh=True,source_timestamp=NOW),NOW)
    assert row is not None
    assert row['right']=='C' and row['option_type']=='call'
    assert row['bid']==2.0 and row['ask']==2.2 and row['mid']==2.1
    assert 0 < row['delta'] < 1 and row['gamma'] > 0
    assert row['theta'] < 0 and row['vega'] > 0 and row['iv'] > 0
    assert row['greeks_source']=='Tradier production BBO + local Black-Scholes'
    assert row['age_seconds'] <= 2.1

def test_professional_contract_rejects_stale_bbo():
    old=(NOW-timedelta(seconds=91)).timestamp()*1000
    raw=dict(symbol='QQQ261009C00100000',bid=2.0,ask=2.2,strike=100,
             option_type='call',bid_date=old,ask_date=old)
    assert src.normalize_professional_contract(
        raw,'QQQ','2026-10-09',
        dict(price=100.0,fresh=True,source_timestamp=NOW),NOW
    ) is None

def test_professional_chain_requests_tradier_and_persists_normalized_rows(monkeypatch):
    monkeypatch.setattr(ms,'fetch_spot',lambda *a:dict(price=100.0,fresh=True,source_timestamp=NOW))
    fresh=(NOW-timedelta(seconds=1)).timestamp()*1000
    seen=[]
    def feed(path,params):
        seen.append((path,dict(params)))
        assert path=='/options/chains'
        return {'options':{'option':[dict(
            symbol='QQQ261009C00100000',bid=2.0,ask=2.2,strike=100,
            option_type='call',bid_date=fresh,ask_date=fresh,
            open_interest=1000,volume=500,bidsize=10,asksize=12
        )]}}
    saved=[]
    monkeypatch.setattr(src,'get',feed)
    monkeypatch.setattr(src,'_persist_chain',lambda symbol,expiry,rows,now:saved.append((symbol,expiry,rows)))
    rows,reason=src.professional_chain('QQQ','2026-10-09',NOW)
    assert reason is None and len(rows)==1
    assert seen[0][1]['greeks']=='true'
    assert saved and saved[0][0:2]==('QQQ','2026-10-09')
    assert rows[0]['open_interest']==1000 and rows[0]['volume']==500
