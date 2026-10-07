"""Tradier-only professional options adapter.

All executable contract fields originate from fresh Tradier production BBO and
the corresponding fresh underlying quote. Receipt time never refreshes an
exchange clock. IV/Greeks are deterministically modeled from the fresh BBO
midpoint so stale/missing provider-Greek timestamps cannot silently qualify an
otherwise executable package. Provider daily OI remains daily inventory.
"""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import requests

UTC=timezone.utc
ET=ZoneInfo('America/New_York')
CHAIN_SCHEMA_VERSION='2026-10-07.1'


def get(path, params):
    token=os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_API_KEY')
    if not token:
        raise RuntimeError('TRADIER_TOKEN missing')
    r=requests.get(
        'https://api.tradier.com/v1/markets'+path,
        params=params,
        headers={'Authorization':'Bearer '+token,'Accept':'application/json'},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def clock(value):
    try:
        return datetime.fromtimestamp(float(value)/1000,UTC)
    except (ValueError,TypeError,OverflowError,OSError):
        return None


def _cdf(x):
    return (1+math.erf(x/math.sqrt(2)))/2


def _pdf(x):
    return math.exp(-.5*x*x)/math.sqrt(2*math.pi)


def implied_vol(spot,strike,t,right,mid):
    if min(spot,strike,t,mid)<=0:
        return None
    def price(iv):
        sig=iv*math.sqrt(t)
        d1=(math.log(spot/strike)+(.05+.5*iv*iv)*t)/sig
        d2=d1-sig
        return (
            spot*_cdf(d1)-strike*math.exp(-.05*t)*_cdf(d2)
            if right=='call'
            else strike*math.exp(-.05*t)*_cdf(-d2)-spot*_cdf(-d1)
        )
    lo,hi=.001,5.
    if not price(lo)<=mid<=price(hi):
        return None
    for _ in range(60):
        m=(lo+hi)/2
        if price(m)<mid:
            lo=m
        else:
            hi=m
    return (lo+hi)/2


def modeled_greeks(spot,strike,t,right,iv):
    """Black-Scholes Greeks from the same fresh Tradier BBO used for IV.

    Theta is returned per calendar day and vega per one volatility point.
    These are model values, not exchange-observed Greeks.
    """
    if min(spot,strike,t,iv)<=0:
        return None
    root=math.sqrt(t)
    d1=(math.log(spot/strike)+(.05+.5*iv*iv)*t)/(iv*root)
    d2=d1-iv*root
    delta=_cdf(d1) if right=='call' else _cdf(d1)-1
    gamma=_pdf(d1)/(spot*iv*root)
    vega=spot*_pdf(d1)*root/100
    first=-(spot*_pdf(d1)*iv)/(2*root)
    if right=='call':
        annual_theta=first-.05*strike*math.exp(-.05*t)*_cdf(d2)
    else:
        annual_theta=first+.05*strike*math.exp(-.05*t)*_cdf(-d2)
    return {
        'delta':delta,
        'gamma':gamma,
        'theta':annual_theta/365,
        'vega':vega,
    }


def _safe_number(value):
    if isinstance(value,bool):
        return None
    try:
        result=float(value)
    except (TypeError,ValueError):
        return None
    return result if math.isfinite(result) else None


def _expiry_tte(expiry,now):
    expiry_date=datetime.fromisoformat(str(expiry)).date()
    seconds=(datetime.combine(expiry_date,time(16),ET)-now.astimezone(ET)).total_seconds()
    return max(60,seconds)/(365*86400)


def normalize_professional_contract(raw,symbol,expiry,spot,now,*,max_spread_ratio=.50):
    """Normalize one Tradier contract using fresh BBO + modeled Greeks only."""
    bid_at,ask_at=clock(raw.get('bid_date')),clock(raw.get('ask_date'))
    spot_at=spot.get('source_timestamp')
    if not isinstance(spot_at,datetime):
        try:
            spot_at=datetime.fromisoformat(str(spot_at).replace('Z','+00:00'))
        except (TypeError,ValueError):
            spot_at=None
    if spot_at is not None and spot_at.tzinfo is None:
        spot_at=spot_at.replace(tzinfo=UTC)
    if not bid_at or not ask_at or not spot_at:
        return None
    if any(not 0<=(now-ts.astimezone(UTC)).total_seconds()<=90 for ts in (bid_at,ask_at,spot_at)):
        return None
    bid=_safe_number(raw.get('bid'));ask=_safe_number(raw.get('ask'))
    strike=_safe_number(raw.get('strike'));spot_price=_safe_number(spot.get('price'))
    right=str(raw.get('option_type') or '').lower()
    if bid is None or ask is None or strike is None or spot_price is None:
        return None
    if bid<0 or ask<=0 or bid>ask or right not in ('call','put'):
        return None
    mid=(bid+ask)/2
    spread_ratio=(ask-bid)/mid if mid>0 else None
    if spread_ratio is None or spread_ratio>max_spread_ratio:
        return None
    t=_expiry_tte(expiry,now)
    iv=implied_vol(spot_price,strike,t,right,mid)
    if iv is None:
        return None
    greeks=modeled_greeks(spot_price,strike,t,right,iv)
    if greeks is None:
        return None
    exchange_ts=min(bid_at,ask_at,spot_at.astimezone(UTC))
    option_symbol=raw.get('symbol')
    if not option_symbol:
        return None
    return {
        'symbol':option_symbol,
        'underlying_symbol':symbol,
        'expiration':str(expiry),
        'strike':strike,
        'right':'C' if right=='call' else 'P',
        'option_type':right,
        'bid':bid,
        'ask':ask,
        'mid':mid,
        'bid_size':raw.get('bidsize'),
        'ask_size':raw.get('asksize'),
        'last':_safe_number(raw.get('last')),
        'delta':greeks['delta'],
        'gamma':greeks['gamma'],
        'theta':greeks['theta'],
        'vega':greeks['vega'],
        'iv':iv,
        'open_interest':raw.get('open_interest'),
        'volume':raw.get('volume'),
        'spread_ratio':spread_ratio,
        'exchange_timestamp':exchange_ts.isoformat(),
        'retrieval_timestamp':now.astimezone(UTC).isoformat(),
        'age_seconds':max((now-ts.astimezone(UTC)).total_seconds() for ts in (bid_at,ask_at,spot_at)),
        'greeks_source':'Tradier production BBO + local Black-Scholes',
        'oi_scope':'Tradier daily open interest; publication time unavailable',
        'tte_years':t,
        'dte':(datetime.fromisoformat(str(expiry)).date()-now.astimezone(ET).date()).days,
        # Compatibility with surface collector.
        'timestamp':exchange_ts,
    }


def _persist_chain(symbol,expiry,rows,now):
    if not rows:
        return
    try:
        from sqlalchemy import text
        from .db import engine
        payload={
            'schema_version':CHAIN_SCHEMA_VERSION,
            'source':'Tradier production option chain',
            'underlying_symbol':symbol,
            'expiration':str(expiry),
            'source_timestamp':min(r['exchange_timestamp'] for r in rows),
            'retrieval_timestamp':now.astimezone(UTC).isoformat(),
            'greeks_source':'Tradier production BBO + local Black-Scholes',
            'options':rows,
        }
        with engine.begin() as c:
            c.execute(text('''CREATE TABLE IF NOT EXISTS chain_cache (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                expiration VARCHAR(12) NOT NULL,
                chain_json TEXT,
                fetched_at TIMESTAMP,
                UNIQUE(symbol,expiration)
            )'''))
            c.execute(text('''INSERT INTO chain_cache(symbol,expiration,chain_json,fetched_at)
                VALUES (:symbol,:expiration,:payload,:fetched_at)
                ON CONFLICT(symbol,expiration) DO UPDATE
                SET chain_json=excluded.chain_json,fetched_at=excluded.fetched_at'''),
                {
                    'symbol':symbol,
                    'expiration':str(expiry),
                    'payload':json.dumps(payload,default=str,allow_nan=False),
                    'fetched_at':now.astimezone(UTC).replace(tzinfo=None),
                })
    except Exception:
        # Persistence is a durability enhancement, never a reason to relabel
        # otherwise valid fresh BBO as unavailable.
        return


def professional_chain(symbol,expiry,now,*,persist=True,max_spread_ratio=.50):
    """Return a fresh executable-grade normalized chain for one expiration."""
    from .market_structure import fetch_spot
    spot=fetch_spot(symbol,now)
    if not spot.get('fresh'):
        return [],spot.get('reason') or 'Underlying quote is not fresh'
    try:
        raw=(get('/options/chains',{
            'symbol':symbol,
            'expiration':str(expiry),
            'greeks':'true',
        }).get('options') or {}).get('option') or []
        if isinstance(raw,dict):
            raw=[raw]
        rows=[
            row for q in raw
            if (row:=normalize_professional_contract(
                q,symbol,str(expiry),spot,now,max_spread_ratio=max_spread_ratio
            )) is not None
        ]
        if persist:
            _persist_chain(symbol,expiry,rows,now)
        return rows,None if rows else 'No qualified fresh Tradier BBO contracts'
    except Exception as exc:
        return [],'Tradier professional chain failure: '+type(exc).__name__


def option_rows(symbol,now):
    """Representative rows for surface/gamma; persisted professional chain is shared."""
    from .market_structure import fetch_spot
    spot=fetch_spot(symbol,now)
    if not spot.get('fresh'):
        return [],spot.get('reason')
    try:
        expiries=(get('/options/expirations',{'symbol':symbol,'includeAllRoots':'true'}).get('expirations') or {}).get('date') or []
        if isinstance(expiries,str):
            expiries=[expiries]
        selected=[]
        for lo,hi in [(0,0),(1,5),(6,10),(11,20),(21,35),(36,90)]:
            candidates=[e for e in expiries if lo<=(datetime.fromisoformat(e).date()-now.astimezone(ET).date()).days<=hi]
            if candidates:
                selected.append(min(candidates))
        rows=[]
        def chain(expiry):
            # Minute surface collection shares normalization but does not
            # rewrite large full-chain blobs every minute. On-demand scans and
            # watcher contract packages persist the chain when it matters.
            return expiry,professional_chain(symbol,expiry,now,persist=False,max_spread_ratio=.30)
        with ThreadPoolExecutor(max_workers=3) as pool:
            chains=list(pool.map(chain,selected))
        reasons=[]
        for expiry,(data,reason) in chains:
            # Surface/gamma analytics historically use the words call/put,
            # while the executable selector uses C/P. Keep that interface
            # stable rather than forcing analytics to understand order-leg
            # notation.
            rows.extend([
                dict(row, right=row['option_type'], timestamp=datetime.fromisoformat(row['exchange_timestamp']))
                for row in data
            ])
            if reason:
                reasons.append(str(expiry)+': '+reason)
        return rows,None if rows else 'No qualified fresh Tradier BBO rows'
    except Exception as exc:
        return [],'Tradier chain failure: '+type(exc).__name__
