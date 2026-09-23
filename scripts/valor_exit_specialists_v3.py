"""Cache-only contract-specific development research; never sends orders.

Signals and order levels use completed bars; next-bar market fills are scenarios.
2023-24 select candidates. 2025 is an already-seen chronological check, not OOS.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import Counter
import numpy as np
import pandas as pd

STUDY='valor-exit-specialists-v3-20260923'
BASE_STUDY='valor-contract-v2-20260923'
BASE_HASH='69d32ce2d6899a378a892b4e46c88b9484dcf30e2e9b838bf52514bf7cbfda1c'
LOCK=63260923
PRODUCTS={
 'MES':('MES.v.0',5.,.25,510,900), 'MNQ':('MNQ.v.0',2.,.25,510,900),
 'RTY':('M2K.v.0',5.,.10,510,900), 'MGC':('MGC.v.0',10.,.10,440,750),
 'NG':('MNG.v.0',1000.,.001,480,810), 'CL':('MCL.v.0',100.,.01,480,810),
}

@dataclass(frozen=True)
class Spec:
    name:str
    source:str
    exit_mode:str
    horizon:int
    start_delay:int=30
    efficiency:str='any'

SPECS={
 'MES':(Spec('opening_rejection_to_mid','opening_rejection','opening_mid',90,30,'range'),
        Spec('lowvol_reversal_to_vwap','lowvol_reversal','vwap',60,45,'range')),
 'MNQ':(Spec('trend_pullback_runner','trend_pullback','trail',180,30,'trend'),
        Spec('trend_breakout_3r','trend_breakout','3r',120,30,'trend')),
 'RTY':(Spec('opening_rejection_to_mid','opening_rejection','opening_mid',90,30,'range'),
        Spec('range_reentry_to_mid','range_reentry','range_mid',60,45,'range')),
 'MGC':(Spec('trend_pullback_runner','trend_pullback','trail',240,30,'trend'),
        Spec('trend_breakout_3r','trend_breakout','3r',180,30,'trend')),
 'NG':(Spec('expansion_runner','expansion_breakout','trail',180,30,'trend'),
       Spec('trend_breakout_3r','trend_breakout','3r',120,30,'trend')),
 'CL':(Spec('opening_breakout_runner','opening_breakout','trail',120,30,'trend'),
       Spec('expansion_3r','expansion_breakout','3r',180,30,'trend')),
}


def context(d,ticker):
    """Features available at minute CLOSE; incomplete five-minute bars excluded."""
    seg=d.segment; close=d.close; prev=close.groupby(seg).shift()
    def roll(s,n,method='mean'):
        return s.groupby(seg,sort=False).transform(lambda z:getattr(z.rolling(n,min_periods=n),method)())
    hi=roll(d.high,30,'max'); lo=roll(d.low,30,'min')
    er=(close-close.groupby(seg).shift(30)).abs()/roll((close-prev).abs(),30,'sum').replace(0,np.nan)
    x=d.assign(bucket=d.timestamp.dt.floor('5min'),raw_index=np.arange(len(d)))
    b=x.groupby('bucket',sort=True).agg(high=('high','max'),low=('low','min'),close=('close','last'),
        count=('close','size'),segment_count=('segment','nunique'),first=('timestamp','first'),
        last=('timestamp','last'),instrument_id=('instrument_id','first'),raw_index=('raw_index','last'))
    b=b[(b['count']==5)&(b.segment_count==1)&(b['first']==b.index)&
        (b['last']==b.index+pd.Timedelta(minutes=4))].copy()
    b['bs']=((b.index.to_series().diff()!=pd.Timedelta(minutes=5))|
        b.instrument_id.ne(b.instrument_id.shift())).cumsum()
    bp=b.close.groupby(b.bs).shift()
    tr=pd.concat([b.high-b.low,(b.high-bp).abs(),(b.low-bp).abs()],axis=1).max(axis=1)
    ba=tr.groupby(b.bs,sort=False).transform(lambda z:z.rolling(14,min_periods=14).mean())
    a=pd.Series(np.nan,index=d.index,dtype=float)
    a.loc[b.raw_index.to_numpy()]=ba.to_numpy()
    a=a.groupby(seg,sort=False).ffill()
    start,end=PRODUCTS[ticker][3:]; key=d.date+':'+d.instrument_id.astype(str)
    active=d.minute.ge(start)&d.minute.lt(end)
    volume=d.volume.where(active,0.)
    numerator=(((d.high+d.low+d.close)/3)*volume).groupby(key).cumsum()
    vwap=numerator/volume.groupby(key).cumsum().replace(0,np.nan)
    seed=d.minute.ge(start)&d.minute.lt(start+30)
    count=seed.astype(int).groupby(key).cumsum()
    oh=d.high.where(seed).groupby(key).cummax().groupby(key).ffill()
    ol=d.low.where(seed).groupby(key).cummin().groupby(key).ffill()
    om=((oh+ol)/2).where(count.eq(30)&d.minute.ge(start+30))
    return {k:s.to_numpy(float) for k,s in dict(atr5=a,high30=hi,low30=lo,
        efficiency=er,vwap=vwap,opening_mid=om,range_mid=(hi+lo)/2).items()}


def fill(price,side,tick,ticks):
    import math
    q=price/tick+side*ticks
    return (math.ceil(q-1e-8) if side>0 else math.floor(q+1e-8))*tick


def simulate(d,ticker,signal,ctx,spec):
    """Single-position, next-minute fills, two attempts/date, 15-minute cooldown.

    Eligibility and initial levels use signal-bar CLOSE, never next-bar OPEN.
    Normal/stress scenarios share raw paths. Trail updates activate next minute.
    Gaps censor unresolved positions; subsequent segments restart flat (research).
    """
    _,pv,tick,start,end=PRODUCTS[ticker]
    ts=pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op,hi,lo,cl=(d[c].to_numpy(float) for c in ('open','high','low','close'))
    seg=d.segment.to_numpy(); mins=d.minute.to_numpy(); dates=d.date.to_numpy()
    cost=3/pv+4*tick; busy=-1; cooldown=-1
    attempts=Counter(); rejected=Counter(); trades=[]; censored=[]; a5=ctx['atr5']
    for i in np.flatnonzero(signal):
        if i<=busy or ts[i]<cooldown: continue
        # This calendar eligibility is known before the next price is observed.
        if attempts[dates[i]]>=2 or not start+spec.start_delay<=mins[i]+1<end-30: continue
        a=float(a5[i]); er=float(ctx['efficiency'][i])
        if not np.isfinite(a) or a<=0 or not np.isfinite(er):
            rejected['incomplete_context']+=1; continue
        if spec.efficiency=='range' and er>.35: continue
        if spec.efficiency=='trend' and er<.30: continue
        side=int(signal[i]); ref=float(cl[i])
        if side not in (-1,1): raise ValueError('Invalid side')
        if spec.exit_mode in ('vwap','opening_mid','range_mid'):
            target=float(ctx[spec.exit_mode][i])
            if np.isfinite(target):
                target=(np.floor(target/tick) if side==1 else np.ceil(target/tick))*tick
            extreme=ctx['low30'][i] if side==1 else ctx['high30'][i]
            stop=float(extreme)-side*.25*a
            stop=(np.floor(stop/tick) if side==1 else np.ceil(stop/tick))*tick
            risk=side*(ref-stop); reward=side*(target-ref)
            if not all(np.isfinite(z) for z in (stop,target,risk,reward)) or risk<=0:
                rejected['invalid_structure']+=1; continue
            if risk>3*a or reward<1.25*risk or reward<5*cost:
                rejected['structure_or_cost_gate']+=1; continue
        else:
            risk=np.ceil(max(1.5*a,2*cost,4*tick)/tick)*tick
            stop=ref-side*risk
            target=ref+side*3*risk if spec.exit_mode=='3r' else None
        e=i+1
        if e>=len(d) or seg[e]!=seg[i] or ts[e]-ts[i]!=60_000_000_000:
            rejected['missing_next_bar']+=1; continue
        entry=float(op[e]); attempts[dates[e]]+=1
        deadline=ts[e]+spec.horizon*60_000_000_000; best=entry; closed=False; j=e
        while j<len(d) and seg[j]==seg[e]:
            reason=None; raw=None
            if j==e and (side*(entry-stop)<=0 or (target is not None and side*(entry-target)>=0)):
                # The market order was already committed: flatten, pay both costs.
                reason,raw='entry_gap_outside_bracket',entry
            elif side*(op[j]-stop)<=0: reason,raw='gap_stop',op[j]
            elif (side==1 and lo[j]<=stop) or (side==-1 and hi[j]>=stop): reason,raw='stop',stop
            elif target is not None and ((side==1 and hi[j]>=target) or (side==-1 and lo[j]<=target)):
                reason,raw='target',target
            elif ts[j]+60_000_000_000>=deadline or mins[j]>=end-1:
                reason,raw='time_or_session',cl[j]
            if reason:
                trades.append(dict(entry=d.timestamp.iloc[e].isoformat(),
                    exit=(d.timestamp.iloc[j]+pd.Timedelta(minutes=1)).isoformat(),side=side,
                    signal_reference=ref,entry_raw=entry,exit_raw=float(raw),reason=reason,
                    initial_risk_points=float(risk),raw_price_pnl=float(side*(raw-entry)*pv)))
                busy=j; cooldown=ts[j]+15*60_000_000_000; closed=True; break
            if spec.exit_mode=='trail':
                best=max(best,hi[j]) if side==1 else min(best,lo[j])
                current_a=a5[j] if np.isfinite(a5[j]) and a5[j]>0 else a
                if side*(best-ref)>=2*risk:
                    new=best-side*2*current_a
                    new=(np.floor(new/tick) if side==1 else np.ceil(new/tick))*tick
                    stop=max(stop,new) if side==1 else min(stop,new)
            j+=1
        if not closed:
            last=max(e,j-1)
            censored.append(dict(entry=d.timestamp.iloc[e].isoformat(),side=side,
                last_seen=d.timestamp.iloc[last].isoformat(),last_price=float(cl[last]),
                raw_price_mark=float(side*(cl[last]-entry)*pv),reason='gap_roll_or_end',
                initial_risk_points=float(risk)))
            busy=last; cooldown=ts[last]+15*60_000_000_000
    return trades,censored,dict(rejected)


def summarize(trades,censored,rejected,ticker,ticks,spec):
    _,pv,tick,*_=PRODUCTS[ticker]; ledger=[]
    for t in trades:
        entry=fill(t['entry_raw'],t['side'],tick,ticks)
        exit_=fill(t['exit_raw'],-t['side'],tick,ticks)
        ledger.append(dict(t,entry_fill=entry,exit_fill=exit_,net=round(t['side']*(exit_-entry)*pv-3,6)))
    p=np.array([t['net'] for t in ledger],dtype=float); eq=np.r_[0.,p.cumsum()]
    wins=p[p>0].sum(); losses=-p[p<0].sum(); months={}
    for t in ledger:
        m=t['exit'][:7]; months[m]=round(months.get(m,0.)+t['net'],6)
    return dict(spec=spec.name,source_signal=spec.source,exit_mode=spec.exit_mode,horizon_min=spec.horizon,
        cost_ticks_each_side=ticks,round_trip_fee_assumed=3.,trades=len(p),net_dollars=round(float(p.sum()),6),
        avg_trade=round(float(p.mean()),6) if len(p) else None,
        profit_factor=round(float(wins/losses),6) if losses else None,
        gross_wins=round(float(wins),6),gross_losses=round(float(losses),6),
        closed_trade_max_drawdown=round(float(np.max(np.maximum.accumulate(eq)-eq)),6),
        raw_path_price_pnl=round(sum(t['raw_price_pnl'] for t in trades),6),censored_positions=len(censored),
        censored_fraction=len(censored)/(len(p)+len(censored)) if len(p)+len(censored) else None,
        monthly=months,rejected=rejected,exit_reasons=dict(Counter(t['reason'] for t in trades)),
        trade_ledger=ledger,censored_ledger=censored,gex_used=False,live_ready=False)


def evaluate(frame,ticker,selected=None):
    from scripts import valor_contract_research_v2 as base
    base_hash=hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest()
    if base_hash!=BASE_HASH: raise ValueError('Base research source changed')
    d,manifest=base.prepare(frame,ticker); f=base.features(d,ticker); ctx=context(d,ticker); rows=[]
    for spec in SPECS[ticker]:
        if selected is not None and spec.name!=selected: continue
        trades,censored,rejected=simulate(d,ticker,f[spec.source],ctx,spec)
        for ticks in (2,4): rows.append(summarize(trades,censored,rejected,ticker,ticks,spec))
    manifest.update(study=STUDY,base_source_sha256=base_hash,specs=[asdict(s) for s in SPECS[ticker]],
        gex_used=False,live_ready=False,source_signal_scope='v2 daytime signals; new exits and entry gates',
        execution='completed-bar decisions; next open; stop-first; identical raw paths across friction scenarios',
        max_entries_per_day=2,cooldown_minutes=15,
        selection='positive 2023 AND 2024 under stress; >=100 trades/year; <=1% censored/year',
        new_vendor_downloads=0,drawdown_scope='closed trades only; unresolved positions excluded from realized PnL')
    return manifest,rows


def select_candidate(year_rows):
    """Only 2023/24 select; 2025 outcomes are ignored."""
    names=sorted({r['spec'] for y,rs in year_rows.items() if y in (2023,2024) for r in rs}); choices=[]
    for name in names:
        rows=[]
        for y in (2023,2024):
            rows.extend([r for r in year_rows.get(y,[]) if r['spec']==name and r['cost_ticks_each_side']==4])
        if len(rows)!=2: continue
        if not all(r['trades']>=100 and r['net_dollars']>0 and r['censored_fraction'] is not None
                   and r['censored_fraction']<=.01 for r in rows): continue
        score=min(r['net_dollars']/max(1.,r['closed_trade_max_drawdown']) for r in rows)
        choices.append((score,sum(r['net_dollars'] for r in rows),name))
    return sorted(choices,key=lambda z:(-z[0],-z[1],z[2]))[0][2] if choices else None


def run():
    """Research tables and existing caches ONLY; no vendor/broker API calls."""
    import psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=15)
    conn.autocommit=True; cur=conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)',(LOCK,))
    if not cur.fetchone()[0]: conn.close(); return
    code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status,**detail):
        cur.execute('''INSERT INTO valor_research_v3_state(study_id,status,detail) VALUES(%s,%s,%s)
            ON CONFLICT(study_id) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=now()''',
            (STUDY,status,Json(dict(detail,source_sha256=code_hash,new_vendor_downloads=0))))
    def store(ticker,year,manifest,rows):
        summary=[{k:v for k,v in r.items() if k not in ('trade_ledger','censored_ledger')} for r in rows]
        manifest.update(source_sha256=code_hash)
        evidence=gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)
        cur.execute('''INSERT INTO valor_research_v3_results(study_id,ticker,year,manifest,summary,evidence_gzip)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (STUDY,ticker,year,Json(manifest),Json(summary),psycopg2.Binary(evidence)))
        return summary
    def cached(ticker,year):
        key=f'GLBX.MDP3:ohlcv-1m:{PRODUCTS[ticker][0]}:{year}'
        cur.execute('SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s',(key,))
        r=cur.fetchone()
        if not r: raise ValueError('Required existing cache unavailable')
        body=bytes(r[1])
        if hashlib.sha256(body).hexdigest()!=r[0]: raise ValueError('Cache checksum mismatch')
        return pd.read_parquet(io.BytesIO(body)),r[0]
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_research_v3_state(study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
            CREATE TABLE IF NOT EXISTS valor_research_v3_results(study_id text,ticker text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,ticker,year));
            CREATE TABLE IF NOT EXISTS valor_research_v3_selections(study_id text,ticker text,spec text,status text,detail jsonb,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,ticker));''')
        cur.execute('SELECT status FROM valor_research_v3_state WHERE study_id=%s',(STUDY,))
        if cur.fetchone()==('completed',): return
        cur.execute("SELECT COUNT(*) FROM valor_research_v3_results WHERE study_id=%s AND manifest->>'source_sha256' IS DISTINCT FROM %s",(STUDY,code_hash))
        if cur.fetchone()[0]: state('blocked_source_version'); return
        cur.execute('SELECT status FROM valor_research_v2_state WHERE study_id=%s',(BASE_STUDY,))
        if cur.fetchone()!=('completed',): state('blocked_v2_not_complete'); return
        cur.execute('SELECT pg_database_size(current_database())')
        if cur.fetchone()[0]>12_000_000_000: state('blocked_storage'); return
        selected_count=0
        for ticker in PRODUCTS:
            dev={}
            for year in (2023,2024):
                cur.execute('SELECT summary FROM valor_research_v3_results WHERE study_id=%s AND ticker=%s AND year=%s',(STUDY,ticker,year))
                row=cur.fetchone()
                if row: dev[year]=row[0]; continue
                state('evaluating_development',ticker=ticker,year=year)
                frame,cache_hash=cached(ticker,year); manifest,rows=evaluate(frame,ticker)
                manifest.update(cache_sha256=cache_hash,phase='development',validation='2025 already seen; not blind OOS')
                dev[year]=store(ticker,year,manifest,rows); del frame,rows
            selected=select_candidate(dev)
            cur.execute('''INSERT INTO valor_research_v3_selections(study_id,ticker,spec,status,detail)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (STUDY,ticker,selected,'selected_for_chronological_check' if selected else 'no_candidate_passed',
                 Json(dict(selected_using_years=[2023,2024],test_year=2025,blind_holdout=False))))
            cur.execute('SELECT 1 FROM valor_research_v3_results WHERE study_id=%s AND ticker=%s AND year=2025',(STUDY,ticker))
            if cur.fetchone(): selected_count+=int(selected is not None); continue
            if selected is None:
                store(ticker,2025,dict(phase='not_tested',reason='no_development_candidate_passed',gex_used=False,live_ready=False),[])
                continue
            selected_count+=1; state('evaluating_chronological_check',ticker=ticker,year=2025,spec=selected)
            frame,cache_hash=cached(ticker,2025); manifest,rows=evaluate(frame,ticker,selected)
            manifest.update(cache_sha256=cache_hash,phase='chronological_check',selection_frozen=selected,blind_holdout=False)
            store(ticker,2025,manifest,rows); del frame,rows
        state('completed',development_jobs=12,chronological_jobs=selected_count,chronological_skipped=6-selected_count,
              selection_years=[2023,2024],blind_holdout=False,gex_used=False,live_ready=False)
    except Exception as exc:
        try: state('failed',error_type=type(exc).__name__,ticker=locals().get('ticker'),year=locals().get('year'))
        except Exception: pass
        logging.getLogger(__name__).error('VALOR cache-only v3 failed: %s',type(exc).__name__)
    finally:
        try: cur.execute('SELECT pg_advisory_unlock(%s)',(LOCK,))
        finally: conn.close()


def launch_if_enabled():
    flag=os.getenv('VALOR_EXIT_RESEARCH_AUTORUN',os.getenv('VALOR_CONTRACT_RESEARCH_AUTORUN','false'))
    if flag.lower() not in {'1','true','yes','on'}: return False
    import threading
    threading.Thread(target=run,name='valor-exit-specialists-v3',daemon=True).start()
    return True


if __name__=='__main__': run()
