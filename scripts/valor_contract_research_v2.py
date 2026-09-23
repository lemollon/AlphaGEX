"""Cached, bounded futures-native research, NOT a GEX or live-trading engine.

Signals use completed bars; execution is next-bar, single-position and adverse.
No broker imports. 2025 was previously examined: not an untouched holdout.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import logging
import math
import os
import threading
from pathlib import Path
import numpy as np
import pandas as pd

STUDY = 'valor-contract-v2-20260923'
LOCK = 63260923
# symbol, dollars/point, tick, session start/end minutes in America/Chicago.
# MNG multiplier is 1,000 MMBtu: CME tick .001 is $1, NOT $.10.
PRODUCTS = {
 'MES': ('MES.v.0', 5., .25, 510, 900),
 'MNQ': ('MNQ.v.0', 2., .25, 510, 900),
 'RTY': ('M2K.v.0', 5., .10, 510, 900),
 'MGC': ('MGC.v.0', 10., .10, 440, 750),
 'NG': ('MNG.v.0', 1000., .001, 480, 810),
 'CL': ('MCL.v.0', 100., .01, 480, 810),
}
RULES = {
 'MES': ('range_reentry', 'lowvol_reversal', 'opening_rejection'),
 'MNQ': ('trend_breakout', 'opening_breakout', 'trend_pullback'),
 'RTY': ('range_reentry', 'opening_rejection', 'expansion_breakout'),
 'MGC': ('trend_pullback', 'trend_breakout', 'range_reentry'),
 'NG': ('expansion_breakout', 'trend_breakout', 'opening_breakout'),
 'CL': ('opening_breakout', 'trend_pullback', 'expansion_breakout'),
}


def prepare(frame, ticker):
    d = frame.copy()
    if 'timestamp' not in d:
        if 'ts_event' not in d:
            d = d.reset_index()
        d['timestamp'] = d['ts_event']
    d['timestamp'] = pd.to_datetime(d['timestamp'], utc=True, errors='raise')
    cols = ['timestamp','instrument_id','open','high','low','close','volume']
    if d.empty or not set(cols).issubset(d):
        raise ValueError('Nonempty OHLCV with exact instrument_id required')
    d = d[cols].sort_values('timestamp').reset_index(drop=True)
    if d.timestamp.isna().any() or d.instrument_id.isna().any() or d.timestamp.duplicated().any():
        raise ValueError('Null/duplicate timestamp or null contract')
    for c in cols[2:]:
        d[c] = pd.to_numeric(d[c], errors='raise')
    a = d[cols[2:]].to_numpy(float)
    if not np.isfinite(a).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any():
        raise ValueError('Invalid OHLCV values')
    if ((d.high<d[['open','close','low']].max(axis=1)) | (d.low>d[['open','close','high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC')
    tick = PRODUCTS[ticker][2]
    if not np.allclose(a[:,:4]/tick, np.rint(a[:,:4]/tick), atol=1e-5, rtol=0):
        raise ValueError('Off-tick-grid prices')
    dt = d.timestamp.diff().dt.total_seconds()
    roll = d.instrument_id.ne(d.instrument_id.shift())
    d['segment'] = ((dt!=60)|roll).cumsum()
    local = d.timestamp.dt.tz_convert('America/Chicago')
    d['minute'] = local.dt.hour*60+local.dt.minute
    d['date'] = local.dt.strftime('%Y-%m-%d')
    manifest = dict(bars=len(d),first_bar=d.timestamp.iloc[0].isoformat(),last_bar=d.timestamp.iloc[-1].isoformat(),
        observed_dates=int(d.date.nunique()),contract_switches=int(roll.sum())-1,
        noncontiguous_intervals=int((dt.iloc[1:]!=60).sum()),point_value=PRODUCTS[ticker][1],tick_size=tick,
        gaps_include_no_trade_minutes_and_scheduled_closures=True,gex_used=False,live_ready=False)
    return d, manifest


def features(d, ticker):
    _, _, _, start, end = PRODUCTS[ticker]
    seg, close, high, low = d.segment, d.close, d.high, d.low
    g = close.groupby(seg,sort=False)
    prev = g.shift()
    tr = pd.concat([high-low,(high-prev).abs(),(low-prev).abs()],axis=1).max(axis=1)
    def rolling(s,n,method='mean'):
        # Rolling windows cannot cross missing minutes or contract switches.
        return s.groupby(seg,sort=False).transform(lambda x:getattr(x.rolling(n,min_periods=n),method)())
    atr = rolling(tr,14)
    vol = atr/rolling(tr,60).replace(0,np.nan)
    e20 = g.transform(lambda x:x.ewm(span=20,min_periods=20,adjust=False).mean())
    e80 = g.transform(lambda x:x.ewm(span=80,min_periods=80,adjust=False).mean())
    hi,lo = rolling(high.groupby(seg).shift(),30,'max'),rolling(low.groupby(seg).shift(),30,'min')
    hi60,lo60 = rolling(high.groupby(seg).shift(),60,'max'),rolling(low.groupby(seg).shift(),60,'min')
    def signed(up,down):
        return pd.Series(np.where(up.fillna(False),1,np.where(down.fillna(False),-1,0)),index=d.index)
    def event(s):
        return s.where(s.ne(s.groupby(seg).shift().fillna(0)),0)
    br = signed(close>hi,close<lo)
    trend = br.where(((br==1)&(e20>e80))|((br==-1)&(e20<e80)),0)
    expansion = signed(close>hi60,close<lo60).where(vol>1.1,0)
    reentry = signed((prev<lo.groupby(seg).shift())&(close>lo),(prev>hi.groupby(seg).shift())&(close<hi))
    pullback = signed((prev<=e20.groupby(seg).shift())&(close>e20)&(e20>e80),
                      (prev>=e20.groupby(seg).shift())&(close<e20)&(e20<e80))
    ret = close-g.shift(15)
    reversal = signed((ret < -2*atr)&(close>prev),(ret > 2*atr)&(close<prev)).where(vol<.95,0)
    key = d.date+':'+d.instrument_id.astype(str)
    seed = d.minute.ge(start)&d.minute.lt(start+30)
    orhi = high.where(seed).groupby(key).cummax().groupby(key).ffill()
    orlo = low.where(seed).groupby(key).cummin().groupby(key).ffill()
    active = d.minute.ge(start+30)&seed.astype(int).groupby(key).cumsum().eq(30)
    orb = signed(active&(close>orhi),active&(close<orlo))
    reject = signed(active&(prev<orlo)&(close>=orlo),active&(prev>orhi)&(close<=orhi))
    signals = dict(trend_breakout=event(trend),expansion_breakout=event(expansion),range_reentry=reentry,
                   trend_pullback=pullback,lowvol_reversal=event(reversal),opening_breakout=event(orb),opening_rejection=reject)
    valid = atr.notna()&d.minute.ge(start)&d.minute.lt(end-10)
    out = {k:signals[k].where(valid,0).fillna(0).astype('int8').to_numpy() for k in RULES[ticker]}
    out['atr'] = atr.to_numpy(float)
    return out


def adverse_fill(price,side,tick,ticks):
    v = price/tick+side*ticks
    return (math.ceil(v-1e-8) if side>0 else math.floor(v+1e-8))*tick


def replay(d,ticker,signal,atr,horizon,cost_ticks=2):
    """OHLC scenarios, NOT executable quote data. Stop-first for ambiguous bars.

    4 ATR stop, 2R target, time/session cap. Friction 2 ticks per side base,
    4 stress, plus $3 assumed round trip. Gaps censor unresolved positions;
    each subsequent contiguous segment restarts flat for research only.
    """
    _,pv,tick,start,end = PRODUCTS[ticker]
    ts = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op,hi,lo,cl = (d[c].to_numpy(float) for c in ('open','high','low','close'))
    seg,minute = d.segment.to_numpy(),d.minute.to_numpy()
    trades,censored,skipped,busy = [],[],0,-1
    for i in np.flatnonzero(signal):
        if i<=busy: continue
        e = i+1
        if e>=len(d) or seg[e]!=seg[i] or ts[e]-ts[i]!=60_000_000_000:
            skipped+=1; continue
        if not start<=minute[e]<end-5 or not np.isfinite(atr[i]) or atr[i]<=0:
            skipped+=1; continue
        side = int(signal[i])
        entry = adverse_fill(op[e],side,tick,cost_ticks)
        dist = math.ceil(max(4*atr[i],4*tick)/tick)*tick
        stop,target = entry-side*dist,entry+side*2*dist
        deadline = ts[e]+horizon*60_000_000_000
        j,closed = e,False
        while j<len(d) and seg[j]==seg[e]:
            reason,raw = None,None
            if (side==1 and op[j]<=stop) or (side==-1 and op[j]>=stop): reason,raw='gap_stop',op[j]
            elif (side==1 and lo[j]<=stop) or (side==-1 and hi[j]>=stop): reason,raw='stop',stop
            elif (side==1 and hi[j]>=target) or (side==-1 and lo[j]<=target): reason,raw='target',target
            elif ts[j]+60_000_000_000>=deadline or minute[j]>=end-1: reason,raw='time_or_session',cl[j]
            if reason:
                exit_price = adverse_fill(float(raw),-side,tick,cost_ticks)
                trades.append(dict(entry=d.timestamp.iloc[e].isoformat(),
                    exit=(d.timestamp.iloc[j]+pd.Timedelta(minutes=1)).isoformat(),
                    side=side,entry_price=entry,exit_price=exit_price,reason=reason,
                    net=round(side*(exit_price-entry)*pv-3.,6)))
                busy,closed = j,True
                break
            j+=1
        if not closed:
            censored.append(dict(entry=d.timestamp.iloc[e].isoformat(),side=side,reason='gap_roll_or_end'))
            busy=max(e,j-1)
    pnl=np.array([x['net'] for x in trades],float)
    equity=np.r_[0.,pnl.cumsum()]
    wins,losses=pnl[pnl>0].sum(),-pnl[pnl<0].sum()
    monthly={}
    for x in trades:
        month=x['exit'][:7]; monthly[month]=round(monthly.get(month,0.)+x['net'],6)
    return dict(trades=len(trades),net_dollars=round(float(pnl.sum()),4),
        avg_trade=round(float(pnl.mean()),4) if len(pnl) else None,
        win_rate=round(float((pnl>0).mean()*100),3) if len(pnl) else None,
        profit_factor=round(float(wins/losses),4) if losses else None,
        gross_wins=round(float(wins),4),gross_losses=round(float(losses),4),
        closed_trade_max_drawdown=round(float(np.max(np.maximum.accumulate(equity)-equity)),4),
        censored_positions=len(censored),unfilled_signals=skipped,monthly=monthly,
        trade_ledger=trades,censored_ledger=censored,cost_ticks_each_side=cost_ticks,
        round_trip_fee_assumed=3.,gex_used=False,live_ready=False)


def evaluate(frame,ticker):
    d,manifest=prepare(frame,ticker); f=features(d,ticker); rows=[]
    for rule in RULES[ticker]:
        for horizon in (60,120):
            for ticks in (2,4):
                row=replay(d,ticker,f[rule],f['atr'],horizon,ticks)
                row.update(rule=rule,horizon_min=horizon); rows.append(row)
    return manifest,rows


def launch_if_enabled():
    flag=os.getenv('VALOR_RESEARCH_V2_AUTORUN',os.getenv('VALOR_CONTRACT_RESEARCH_AUTORUN','false'))
    if flag.lower() not in {'1','true','yes','on'}: return False
    threading.Thread(target=run,name='valor-contract-research-v2',daemon=True).start()
    return True


def run():
    """Singleton with persistent cache and paid-request reservations.

    New estimated downloads capped at $25; cumulative previous-run estimates
    plus headroom bounded by the existing $125 cap. Neither is a credit balance.
    Uncertain interrupted downloads NEVER retry automatically.
    """
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=15)
    conn.autocommit=True; cur=conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)',(LOCK,))
    if not cur.fetchone()[0]: conn.close(); return
    code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute('''INSERT INTO valor_research_v2_state(study_id,status,detail) VALUES (%s,%s,%s)
        ON CONFLICT(study_id) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=now()''',
        (STUDY,status,Json(dict(detail,source_sha256=code_hash))))
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_research_v2_state(study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
        CREATE TABLE IF NOT EXISTS valor_research_bar_cache(cache_key text PRIMARY KEY,sha256 text NOT NULL,parquet_zstd bytea NOT NULL,created_at timestamptz DEFAULT now());
        CREATE TABLE IF NOT EXISTS valor_research_download_ledger(cache_key text PRIMARY KEY,estimated_usd numeric NOT NULL,status text NOT NULL,created_at timestamptz DEFAULT now());
        CREATE TABLE IF NOT EXISTS valor_research_v2_results(study_id text,ticker text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,ticker,year));''')
        cur.execute('SELECT COUNT(*) FROM valor_research_v2_results WHERE study_id=%s',(STUDY,))
        if cur.fetchone()[0]==18: return
        import databento as db
        client=db.Historical(os.environ['DATABENTO_API_KEY'])
        cur.execute('SELECT pg_database_size(current_database())')
        if cur.fetchone()[0]>12_000_000_000: state('blocked_storage'); return
        cur.execute('SELECT COALESCE(SUM(estimated_cost_usd),0) FROM valor_three_year_research_runs')
        prior=float(cur.fetchone()[0])
        cap=float(os.getenv('VALOR_RESEARCH_MAX_COST_USD','125'))
        new_cap=min(25.,float(os.getenv('VALOR_RESEARCH_V2_MAX_NEW_USD','25')))
        if not all(math.isfinite(x) and x>=0 for x in (prior,cap,new_cap)): raise ValueError('Invalid budget')
        for ticker,cfg in PRODUCTS.items():
            for year in (2023,2024,2025):
                cur.execute('SELECT 1 FROM valor_research_v2_results WHERE study_id=%s AND ticker=%s AND year=%s',(STUDY,ticker,year))
                if cur.fetchone(): continue
                key=f'GLBX.MDP3:ohlcv-1m:{cfg[0]}:{year}'
                cur.execute('SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s',(key,))
                cached=cur.fetchone()
                if cached:
                    body=bytes(cached[1])
                    if hashlib.sha256(body).hexdigest()!=cached[0]: raise ValueError('Cache checksum mismatch')
                    frame=pd.read_parquet(io.BytesIO(body))
                else:
                    cur.execute('SELECT status FROM valor_research_download_ledger WHERE cache_key=%s',(key,))
                    if cur.fetchone(): state('blocked_uncertain_download',ticker=ticker,year=year); return
                    args=dict(dataset='GLBX.MDP3',schema='ohlcv-1m',symbols=cfg[0],stype_in='continuous',start=f'{year}-01-01',end=f'{year+1}-01-01')
                    quote=float(client.metadata.get_cost(**args))
                    if not math.isfinite(quote) or quote<0: raise ValueError('Invalid cost estimate')
                    cur.execute('SELECT COALESCE(SUM(estimated_usd),0) FROM valor_research_download_ledger')
                    used=float(cur.fetchone()[0]); reserve=quote*1.10
                    if used+reserve>new_cap or prior*1.25+used+reserve>cap:
                        state('blocked_budget',prior_estimates=prior,new_reservations=used,next_estimate=quote,credit_balance_verified=False); return
                    cur.execute('INSERT INTO valor_research_download_ledger(cache_key,estimated_usd,status) VALUES (%s,%s,%s)',(key,reserve,'reserved_before_request'))
                    state('downloading',ticker=ticker,year=year,prior_estimates=prior,new_reserved_usd=used+reserve,credit_balance_verified=False)
                    data=client.timeseries.get_range(**args); frame=data.to_df().reset_index()
                    buf=io.BytesIO(); frame.to_parquet(buf,index=False,compression='zstd'); body=buf.getvalue()
                    cur.execute('INSERT INTO valor_research_bar_cache(cache_key,sha256,parquet_zstd) VALUES (%s,%s,%s)',(key,hashlib.sha256(body).hexdigest(),psycopg2.Binary(body)))
                    cur.execute('UPDATE valor_research_download_ledger SET status=%s WHERE cache_key=%s',('cached',key))
                state('evaluating',ticker=ticker,year=year,credit_balance_verified=False)
                manifest,rows=evaluate(frame,ticker)
                summaries=[{k:v for k,v in r.items() if k not in ('trade_ledger','censored_ledger')} for r in rows]
                manifest.update(source_sha256=code_hash,validation='2023-24 development; 2025 already-seen chronological check',
                    execution='next-bar open; stop-first; unresolved gaps censored and subsequent segments restart flat',
                    scope='futures-native only, not a GEX backtest',historical_coverage='MNG starts Nov 2023; no invented missing minutes')
                evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
                cur.execute('INSERT INTO valor_research_v2_results(study_id,ticker,year,manifest,summary,evidence_gzip) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (STUDY,ticker,year,Json(manifest),Json(summaries),psycopg2.Binary(evidence)))
                del frame,body,rows
        state('completed',ticker_year_jobs=18,gex_used=False,live_ready=False)
    except Exception as exc:
        msg=str(exc).replace(os.getenv('DATABENTO_API_KEY','__unset__'),'[redacted]')
        try: state('failed',error_type=type(exc).__name__,message=msg[:600])
        except Exception: pass
        logging.getLogger(__name__).error('VALOR research v2 failed: %s',type(exc).__name__)
    finally:
        try: cur.execute('SELECT pg_advisory_unlock(%s)',(LOCK,))
        finally: conn.close()


if __name__=='__main__': run()
