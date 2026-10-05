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
