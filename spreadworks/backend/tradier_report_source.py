"""Tradier-only report adapter. Receipt time never refreshes exchange BBO.

IV is a Black-Scholes midpoint estimate, not Tradier's periodically refreshed
Greeks. American exercise/dividends are model limitations. OI is daily inventory.
"""
import math
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import requests
import os

UTC=timezone.utc
ET=ZoneInfo('America/New_York')

def get(path, params):
    token=os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_API_KEY')
    if not token: raise RuntimeError('TRADIER_TOKEN missing')
    r=requests.get('https://api.tradier.com/v1/markets'+path,params=params,
                   headers={'Authorization':'Bearer '+token,'Accept':'application/json'},timeout=15)
    r.raise_for_status()
    return r.json()

def clock(value):
    try:return datetime.fromtimestamp(float(value)/1000,UTC)
    except (ValueError,TypeError,OverflowError):return None

def implied_vol(spot,strike,t,right,mid):
    if min(spot,strike,t,mid)<=0:return None
    def price(iv):
        sig=iv*math.sqrt(t);d1=(math.log(spot/strike)+(.05+.5*iv*iv)*t)/sig;d2=d1-sig
        cdf=lambda x:(1+math.erf(x/math.sqrt(2)))/2
        return spot*cdf(d1)-strike*math.exp(-.05*t)*cdf(d2) if right=='call' else strike*math.exp(-.05*t)*cdf(-d2)-spot*cdf(-d1)
    lo,hi=.001,5.
    if not price(lo)<=mid<=price(hi):return None
    for _ in range(60):
        m=(lo+hi)/2
        if price(m)<mid:lo=m
        else:hi=m
    return (lo+hi)/2

def option_rows(symbol,now):
    from .market_structure import fetch_spot
    spot=fetch_spot(symbol,now)
    if not spot.get('fresh'):return [],spot.get('reason')
    try:
        expiries=(get('/options/expirations',{'symbol':symbol}).get('expirations') or {}).get('date') or []
        if isinstance(expiries,str):expiries=[expiries]
        # Representative front and forward expiries: bounded six chain requests.
        selected=[]
        for lo,hi in [(0,0),(1,5),(6,10),(11,20),(21,35),(36,90)]:
            candidates=[e for e in expiries if lo<=(datetime.fromisoformat(e).date()-now.astimezone(ET).date()).days<=hi]
            if candidates:selected.append(min(candidates))
        rows=[]
        for expiry in selected:
            data=(get('/options/chains',{'symbol':symbol,'expiration':expiry,'greeks':'false'}).get('options') or {}).get('option') or []
            if isinstance(data,dict):data=[data]
            received=datetime.now(UTC)
            for q in data:
                bid_at,ask_at=clock(q.get('bid_date')),clock(q.get('ask_date'))
                if not bid_at or not ask_at or not all(0<=(received-ts).total_seconds()<=90 for ts in [bid_at,ask_at,spot['source_timestamp']]):continue
                bid,ask=q.get('bid'),q.get('ask');strike=q.get('strike');right=q.get('option_type')
                if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in [bid,ask,strike]) or bid<=0 or ask<bid or right not in ['call','put']:continue
                if (ask-bid)/((ask+bid)/2)>.30:continue
                t=max(60,(datetime.combine(datetime.fromisoformat(expiry).date(),time(16),ET)-now).total_seconds())/(365*86400)
                iv=implied_vol(spot['price'],strike,t,right,(bid+ask)/2)
                if iv is None:continue
                rows.append(dict(strike=strike,right=right,iv=iv,expiration=expiry,dte=(datetime.fromisoformat(expiry).date()-now.astimezone(ET).date()).days,
                                 timestamp=min(bid_at,ask_at,spot['source_timestamp']),tte_years=t,open_interest=q.get('open_interest')))
        return rows,None if rows else 'No qualified fresh Tradier BBO rows'
    except Exception as exc:return [],'Tradier chain failure: '+type(exc).__name__
