"""Authoritative replacement for the v2-v6 research RUNNERS (not live traders).

Never calls their run/launch functions. Recalculates from raw cached bars;
old result tables are only a reconciliation reference. No vendor/broker API.
Every existing year is diagnostic, including already-seen 2025. No live approval.
"""
from __future__ import annotations
import gzip
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import date, datetime
from bisect import bisect_left

PROTOCOL = 'valor-all-affected-repair-v7-20260923'
LOCK = 63260923
YEARS = (2023, 2024, 2025)
FAMILIES = ('v2_recomputed', 'v3_recomputed', 'v4_recomputed',
            'v5_regenerated', 'v6_recomputed', 'initial_grid_corrected')
MODULES = {
 'v2': ('scripts.valor_contract_research_v2', '69d32ce2d6899a378a892b4e46c88b9484dcf30e2e9b838bf52514bf7cbfda1c'),
 'v3': ('scripts.valor_exit_specialists_v3', '50c8dd0c3ee949365b085638d6363bf1d128c7b6b501eda55184b3e7297d2002'),
 'v4': ('scripts.valor_mes_rebuild_v4', 'a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c'),
 'v5': ('scripts.valor_mes_gex_overlay_v5', '29631d32438470918e6155f1c8a965646792ced0fb06373025527af9efe032af'),
 'v6': ('scripts.valor_mes_session_v6', 'd3de6fbd29767a0c89c3816ffbbbcdb17f188952f9cecd75a2f8dea6892aceb0'),
}
PRODUCTS = {
 'MES': ('MES.v.0', 5., .25, 510, 900),
 'MNQ': ('MNQ.v.0', 2., .25, 510, 900),
 'RTY': ('M2K.v.0', 5., .10, 510, 900),
 'MGC': ('MGC.v.0', 10., .10, 440, 750),
 'NG': ('MNG.v.0', 1000., .001, 480, 810),
 'CL': ('MCL.v.0', 100., .01, 480, 810),
}
CONFIG = dict(years=YEARS, products=PRODUCTS, families=FAMILIES,
 costs=dict(round_trip_fee_assumed=3., adverse_ticks_each_side=[2, 4]),
 legacy_horizons=[30,60,120,180,240],
 gex_sources=['SPX_ORATS_7DTE_PROXY','SPY_BASELINE_PROXY'],
 gex_filters=['all_matched','positive_only','negative_only'],gex_lags=[1,2],
 gex_regenerates_eligible_entries=True, all_years_diagnostic=True,
 missing_minutes='unresolved_without_trade_or_quote_evidence',
 actual_fees_verified=False, live_ready=False, production_mnq_changed=False)
LEDGER_KEYS = {'ledger','trade_ledger','censored_ledger','unresolved_ledger'}


class IntegrityError(RuntimeError):
    pass


def canonical(value):
    # PostgreSQL JSONB normalizes IEEE signed zero. Its sign is not economic
    # information: preserve exact nonzero values and reject nonfinite numbers.
    def normalize(item):
        if isinstance(item, float) and item == 0.0:
            return 0.0
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [normalize(v) for v in item]
        return item
    return json.dumps(normalize(value), sort_keys=True, separators=(',',':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def check_bytes(body, expected):
    if not isinstance(body, bytes):
        body=bytes(body)
    actual=hashlib.sha256(body).hexdigest()
    if actual!=expected:
        raise IntegrityError('Input or result byte checksum mismatch')
    return body


def pack(rows):
    return gzip.compress(canonical(rows),mtime=0)


def summaries(rows):
    return [{k:v for k,v in r.items() if k not in LEDGER_KEYS} for r in rows]


def scenario_key(row):
    return (row.get('rule',row.get('spec')),row.get('horizon_min'),row.get('session'),
            row.get('view'),row.get('source'),row.get('lag_sessions'),row.get('filter'),
            row.get('cost_ticks_each_side'))


def validate_rows(rows, expected_count):
    if len(rows)!=expected_count or len({scenario_key(r) for r in rows})!=expected_count:
        raise IntegrityError('Incomplete or duplicated scenario coverage')
    for row in rows:
        n=int(row.get('trades',0)); net=float(row['net_dollars'])
        if not math.isfinite(net) or n<0:
            raise IntegrityError('Invalid result values')
        ledger=row.get('ledger',row.get('trade_ledger'))
        if ledger is not None:
            if len(ledger)!=n or abs(sum(float(t['net']) for t in ledger)-net)>.001:
                raise IntegrityError('Trade ledger does not reconcile')
        if 'gross_wins' in row and abs(row['gross_wins']-row['gross_losses']-net)>.001:
            raise IntegrityError('Gross trade amounts do not reconcile')
    return rows


def validated_cached_job(saved, fingerprint, expected_count):
    """ALL checks precede reuse, even when a parent run says completed."""
    if saved is None:
        return None
    manifest,summary,expected_hash,body=saved
    if manifest.get('fingerprint')!=fingerprint:
        raise IntegrityError('Result fingerprint mismatch')
    rows=json.loads(gzip.decompress(check_bytes(body,expected_hash)))
    validate_rows(rows,expected_count)
    if digest(summaries(rows))!=digest(summary):
        raise IntegrityError('Persisted summary differs from evidence')
    return summary


def job_fingerprint(family,ticker,year,source_hashes,input_hashes,runtime,config=None):
    return digest(dict(protocol=PROTOCOL,family=family,ticker=ticker,year=year,
        source_hashes=source_hashes,input_hashes=input_hashes,runtime=runtime,
        config=CONFIG if config is None else config))


def job_plan():
    jobs=[]
    for ticker in PRODUCTS:
        for year in YEARS:
            for family in FAMILIES:
                if family in ('v4_recomputed','v5_regenerated','v6_recomputed') and ticker!='MES':
                    continue
                jobs.append((family,ticker,year))
    return jobs


def expected_rows(family):
    return {'v2_recomputed':12,'v3_recomputed':4,'v4_recomputed':6,
            'v5_regenerated':72,'v6_recomputed':18,'initial_grid_corrected':150}[family]


def load_engines():
    engines={}; source_hashes={}
    for key,(name,pinned_hash) in MODULES.items():
        module=importlib.import_module(name)
        actual=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        if actual!=pinned_hash:
            raise IntegrityError('Evaluator source changed: '+key)
        engines[key]=module;source_hashes[name]=actual
    source_hashes['scripts.valor_research_repair_v7']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return engines,source_hashes


def sanitize_source(rows):
    result=[]
    for day,value in rows:
        day=day if isinstance(day,date) else date.fromisoformat(str(day))
        value=float(value)
        if not math.isfinite(value):
            raise IntegrityError('Nonfinite gamma source')
        result.append((day,value))
    result.sort()
    if not result or len(set(d for d,v in result))!=len(result):
        raise IntegrityError('Empty/duplicate GEX source')
    return result


def filter_orders(orders, source, lag, filter_name):
    """Filter BEFORE the position/day limit; rejected early entries consume no slot."""
    from zoneinfo import ZoneInfo
    if lag not in (1,2) or filter_name not in CONFIG['gex_filters']:
        raise ValueError('Unknown GEX specification')
    days=[d for d,v in source]; accepted=[]; missing=0; blocked=0
    for order in orders:
        ts=datetime.fromisoformat(order['signal_time'].replace('Z','+00:00'))
        if ts.tzinfo is None:raise ValueError('Naive decision timestamp')
        day=ts.astimezone(ZoneInfo('America/Chicago')).date()
        i=bisect_left(days,day)-lag
        if i<0 or (day-days[i]).days>(4 if lag==1 else 7):
            missing+=1;continue
        value=source[i][1]
        keep=filter_name=='all_matched' or (filter_name=='positive_only' and value>0) or (filter_name=='negative_only' and value<0)
        if not keep:blocked+=1;continue
        accepted.append(dict(order,gex_source_date=days[i].isoformat(),gex_value=value))
    return accepted,dict(candidate_orders=len(orders),eligible_orders=len(accepted),missing_gex_orders=missing,filtered_orders=blocked)


def regenerated_gex(frame, engines, sources):
    m=engines['v4'];d=m.prepare(frame);orders=m.candidates(d);out=[]
    for name,horizon in m.SPECS.items():
        for source_name,source in sources.items():
            for lag in (1,2):
                for filter_name in CONFIG['gex_filters']:
                    eligible,counts=filter_orders(orders[name],source,lag,filter_name)
                    trades,unresolved,rejected=m.replay(d,eligible,horizon)
                    for ticks in (2,4):
                        row=m.summarize(trades,unresolved,rejected,name,ticks)
                        row.update(source=source_name,lag_sessions=lag,filter=filter_name,
                            horizon_min=horizon,gex_used=True,gex_resolution='lagged_daily_proxy',
                            source_vintage_verified=False,entry_regenerated_from_raw=True,**counts)
                        out.append(row)
    return out


def initial_grid(frame,ticker,engines):
    """Corrected version of the initial five-rule screen, not a GEX strategy.

    Complete-bar signals, next open, exact clock exits, no overlapping positions,
    no trading through unknown intervals or roll price jumps. Session selects ENTRY.
    No daily performance filter; unresolved observations never become zero trades.
    """
    import numpy as np
    import pandas as pd
    base=engines['v2'];d,_=base.prepare(frame,ticker)
    _,pv,tick,start,end=PRODUCTS[ticker]
    close=d.close;g=close.groupby(d.segment,sort=False)
    hi=d.high.groupby(d.segment,sort=False).transform(lambda s:s.shift().rolling(30,min_periods=30).max())
    lo=d.low.groupby(d.segment,sort=False).transform(lambda s:s.shift().rolling(30,min_periods=30).min())
    ema20=g.transform(lambda s:s.ewm(span=20,min_periods=20,adjust=False).mean())
    ema80=g.transform(lambda s:s.ewm(span=80,min_periods=80,adjust=False).mean())
    rules={'momentum_15m':np.sign(close-g.shift(15)),
           'mean_reversion_15m':-np.sign(close-g.shift(15)),
           'momentum_30m':np.sign(close-g.shift(30)),
           'breakout_30m':np.where(close>hi,1,np.where(close<lo,-1,0)),
           'ema_trend_20_80':np.sign(ema20-ema80)}
    ts=pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op=d.open.to_numpy(float);cl=d.close.to_numpy(float);seg=d.segment.to_numpy()
    minute=d.minute.to_numpy();dates=d.date.to_numpy();n=len(d)
    # Segment ends identify the last actually observed price before an unknown gap.
    boundaries=np.r_[np.flatnonzero(seg[1:]!=seg[:-1])+1,n]
    segment_end=boundaries[np.searchsorted(boundaries,np.arange(n),side='right')]-1
    out=[]
    for name,values in rules.items():
        values=np.asarray(values,float);signals=np.flatnonzero(np.isfinite(values)&(values!=0))
        for horizon in (30,60,120,180,240):
            for session in ('ALL','RTH','OVERNIGHT'):
                trades=[];unresolved=[];busy=-1;blocked_day=None
                for i in signals:
                    if i<=busy or dates[i]==blocked_day:continue
                    e=i+1; entry_clock=(int(minute[i])+1)%1440
                    is_rth=start<=entry_clock<end
                    if session!='ALL' and is_rth!=(session=='RTH'):continue
                    side=int(values[i]);target=ts[i]+(horizon+1)*60_000_000_000
                    if e>=n or seg[e]!=seg[i]:
                        unresolved.append(dict(signal_index=int(i),reason='missing_entry_or_contract_switch'))
                        blocked_day=dates[i];continue
                    j=int(np.searchsorted(ts,target))
                    if j>=n or ts[j]!=target or seg[j]!=seg[e]:
                        k=int(segment_end[e]);
                        unresolved.append(dict(signal_index=int(i),entry_index=int(e),
                            last_index=k,entry_raw=float(op[e]),last_raw=float(cl[k]),side=side,
                            reason='unknown_gap_roll_or_missing_exit'))
                        busy=k;blocked_day=dates[i];continue
                    trades.append((int(e),int(j),side,float(op[e]),float(op[j])))
                    busy=j
                # Raw trades appear once in evidence, not duplicated under both costs.
                for ticks in (2,4):
                    pnl=np.array([side*(exit_-entry)*pv-(3+2*ticks*tick*pv) for e,j,side,entry,exit_ in trades],float)
                    eq=np.r_[0.,pnl.cumsum()];win=float(pnl[pnl>0].sum());loss=float(-pnl[pnl<0].sum())
                    monthly={f'{int(d.timestamp.iloc[0].year)}-{month:02d}':0. for month in range(1,13)}
                    for trade,net in zip(trades,pnl):
                        key=dates[trade[0]][:7];monthly[key]=monthly.get(key,0.)+float(net)
                    row=dict(rule=name,horizon_min=horizon,session=session,cost_ticks_each_side=ticks,
                        trades=len(trades),net_dollars=round(float(pnl.sum()),6),
                        avg_trade=round(float(pnl.mean()),6) if len(pnl) else None,
                        win_rate=round(float((pnl>0).mean()*100),4) if len(pnl) else None,
                        profit_factor=round(win/loss,6) if loss else None,gross_wins=round(win,6),gross_losses=round(loss,6),
                        closed_trade_max_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()),6),
                        unresolved=len(unresolved),unresolved_fraction=len(unresolved)/max(1,len(pnl)+len(unresolved)),
                        monthly={k:round(v,6) for k,v in monthly.items()},round_trip_fee_assumed=3.,
                        raw_price_pnl=round(sum(side*(exit_-entry)*pv for e,j,side,entry,exit_ in trades),6),
                        live_ready=False,gex_used=False,exact_initial_screen_comparison=False,
                        ledger_format='entry_index,exit_index,side,entry_raw,exit_raw',
                        raw_ledger=trades if ticks==2 else [],unresolved_ledger=unresolved if ticks==2 else [])
                    out.append(row)
    # Compact raw_ledger is evidence only, excluded from summaries by global helper.
    return out


LEDGER_KEYS.add('raw_ledger')


def evaluate_family(family,frame,ticker,year,engines,sources):
    if family=='v2_recomputed':
        manifest,rows=engines['v2'].evaluate(frame,ticker)
    elif family=='v3_recomputed':
        manifest,rows=engines['v3'].evaluate(frame,ticker)
    elif family=='v4_recomputed':
        manifest,rows=engines['v4'].evaluate(frame)
    elif family=='v5_regenerated':
        manifest={};rows=regenerated_gex(frame,engines,sources)
    elif family=='v6_recomputed':
        manifest,rows=engines['v6'].evaluate(frame,year)
    elif family=='initial_grid_corrected':
        manifest={};rows=initial_grid(frame,ticker,engines)
    else:raise ValueError('Unknown family')
    for row in rows:
        row.update(year=year,ticker=ticker,family=family,live_ready=False)
    manifest.update(year=year,ticker=ticker,family=family,diagnostic_not_holdout=True,
        previous_promotion_gates_do_not_skip_years=True,production_settings_changed=False,
        new_vendor_downloads=0,source_quote_audit_done=False,broker_fees_verified=False)
    validate_rows(rows,expected_rows(family))
    return manifest,rows


def gap_audit(frame,ticker,engines):
    """Classify what bars alone establish; never invent why a bar is missing."""
    d,manifest=engines['v2'].prepare(frame,ticker)
    import pandas as pd
    dt=d.timestamp.diff().dt.total_seconds();roll=d.instrument_id.ne(d.instrument_id.shift())
    _,pv,tick,start,end=PRODUCTS[ticker]
    intra=(dt>60)&~roll&d.date.eq(d.date.shift())&d.minute.between(start,end-1)&d.minute.shift().between(start,end-1)
    sample=d.loc[intra,['timestamp','instrument_id','minute']].copy()
    sample['previous_timestamp']=d.timestamp.shift()[intra]
    sample['missing_minutes']=(dt[intra]/60-1).astype(int)
    records=[dict(timestamp=str(r.timestamp),previous_timestamp=str(r.previous_timestamp),
        instrument_id=int(r.instrument_id),missing_minutes=int(r.missing_minutes),
        classification='unverified_no_trade_or_feed_gap') for r in sample.itertuples()]
    return dict(manifest,intrasession_gap_count=len(records),intrasession_gaps=records,
        independent_source_comparison=False,no_trade_cause_verified=False)


def legacy_comparison(cur,family,ticker,year,new_summary):
    table={'v2_recomputed':'valor_research_v2_results','v3_recomputed':'valor_research_v3_results',
           'v4_recomputed':'valor_mes_v4_results','v6_recomputed':'valor_mes_session_v6_results'}.get(family)
    if not table:return dict(comparison='new_replay_definition_not_same_as_old')
    query='SELECT summary FROM '+table+' WHERE year=%s'
    args=[year]
    if family in ('v2_recomputed','v3_recomputed'):
        query+=' AND ticker=%s';args.append(ticker)
    query+=' ORDER BY created_at DESC LIMIT 1'
    cur.execute(query,args);r=cur.fetchone()
    if not r or not r[0]:return dict(comparison='previously_not_tested_or_absent')
    old={scenario_key(x):x for x in r[0]};matched=identical=0;deltas=[]
    for row in new_summary:
        previous=old.get(scenario_key(row))
        if previous is None:continue
        matched+=1;delta=round(float(row['net_dollars'])-float(previous['net_dollars']),6)
        if abs(delta)<.001 and row['trades']==previous['trades']:identical+=1
        else:deltas.append(dict(key=list(scenario_key(row)),net_change=delta,old_trades=previous['trades'],new_trades=row['trades']))
    return dict(comparison='exact_pure_evaluator_recomputation',matched=matched,identical=identical,differences=deltas)


def run():
    """Only new versioned tables are written; no trading tables ever modified."""
    if hasattr(os,'nice'):os.nice(10)
    import pandas as pd
    import psycopg2
    from psycopg2.extras import Json
    engines,source_hashes=load_engines()
    runtime=dict(python=platform.python_version(),pandas=pd.__version__,
        numpy=importlib.metadata.version('numpy'),pyarrow=importlib.metadata.version('pyarrow'))
    conn=psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=15)
    conn.autocommit=True;cur=conn.cursor();run_id=None
    cur.execute('SELECT pg_try_advisory_lock(%s)',(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    def state(status,**detail):
        cur.execute('UPDATE valor_repair_v7_runs SET status=%s,detail=%s,updated_at=now() WHERE run_id=%s',
            (status,Json(detail),run_id))
        print('VALOR_REPAIR_V7 '+status+' '+json.dumps(detail,default=str),flush=True)
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_repair_v7_runs(
         run_id text PRIMARY KEY,status text NOT NULL,manifest jsonb NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
         CREATE TABLE IF NOT EXISTS valor_repair_v7_jobs(
         job_key text PRIMARY KEY,run_id text NOT NULL,family text NOT NULL,ticker text NOT NULL,year integer NOT NULL,
         manifest jsonb NOT NULL,summary jsonb NOT NULL,artifact_sha256 text NOT NULL,evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now());''')
        cur.execute('SELECT pg_database_size(current_database())')
        if cur.fetchone()[0]>12_000_000_000:raise IntegrityError('Database storage budget exceeded')
        cur.execute("SELECT cache_key,sha256,encode(sha256(parquet_zstd),'hex'),octet_length(parquet_zstd) FROM valor_research_bar_cache ORDER BY cache_key")
        inventory={key:dict(sha256=stored,bytes=size) for key,stored,actual,size in cur.fetchall()
                   if stored==actual}
        for ticker,cfg in PRODUCTS.items():
            for year in YEARS:
                if f'GLBX.MDP3:ohlcv-1m:{cfg[0]}:{year}' not in inventory:
                    raise IntegrityError('Missing or corrupted required raw cache')
        cur.execute("SELECT trade_date,net_gamma FROM gex_structure_daily WHERE symbol='SPX' AND trade_date>='2022-01-01' AND trade_date<'2026-01-01' ORDER BY trade_date")
        spx=sanitize_source(cur.fetchall())
        cur.execute("SELECT trade_date,net_gex FROM sw_gamma_daily WHERE trade_date>='2022-01-01' AND trade_date<'2026-01-01' ORDER BY trade_date")
        sources={'SPX_ORATS_7DTE_PROXY':spx,'SPY_BASELINE_PROXY':sanitize_source(cur.fetchall())}
        source_rows={name:[(day.isoformat(),value) for day,value in rows] for name,rows in sources.items()}
        gex_hash=digest(source_rows)
        run_manifest=dict(protocol=PROTOCOL,source_hashes=source_hashes,runtime=runtime,config=CONFIG,
            raw_inventory=inventory,gex_input_sha256=gex_hash,expected_jobs=len(job_plan()),
            no_old_completion_shortcut=True,all_results_diagnostic=True)
        run_id=PROTOCOL+'-'+digest(run_manifest)[:20]
        cur.execute('INSERT INTO valor_repair_v7_runs(run_id,status,manifest,detail) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (run_id,'verifying',Json(run_manifest),Json({})))
        # No early return on status=completed. Every job and every raw byte hash is verified.
        state('verifying_and_replaying',expected_jobs=len(job_plan()),new_vendor_downloads=0)
        loaded_key=None;frame=None;qa=None;done=0;fresh=0
        for family,ticker,year in job_plan():
            key=f'GLBX.MDP3:ohlcv-1m:{PRODUCTS[ticker][0]}:{year}'
            inputs={'raw':inventory[key]['sha256']}
            if family=='v5_regenerated':inputs['gex']=gex_hash
            fingerprint=job_fingerprint(family,ticker,year,source_hashes,inputs,runtime)
            job_key=run_id+':'+family+':'+ticker+':'+str(year)+':'+fingerprint
            cur.execute('SELECT manifest,summary,artifact_sha256,evidence_gzip FROM valor_repair_v7_jobs WHERE job_key=%s',(job_key,))
            saved=cur.fetchone()
            if validated_cached_job(saved,fingerprint,expected_rows(family)) is not None:
                done+=1;continue
            if loaded_key!=key:
                cur.execute('SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s',(key,))
                r=cur.fetchone();body=check_bytes(r[1],inputs['raw'])
                frame=pd.read_parquet(io.BytesIO(body));loaded_key=key;del body
                qa=gap_audit(frame,ticker,engines)
            state('evaluating',family=family,ticker=ticker,year=year,done=done,total=len(job_plan()))
            manifest,rows=evaluate_family(family,frame,ticker,year,engines,sources)
            summary=summaries(rows)
            manifest.update(fingerprint=fingerprint,source_hashes=source_hashes,input_hashes=inputs,
                runtime=runtime,raw_audit=qa,reconciliation=legacy_comparison(cur,family,ticker,year,summary),
                expected_scenarios=expected_rows(family))
            if family=='v5_regenerated':manifest['gex_source_snapshot']=source_rows
            evidence=pack(rows);h=hashlib.sha256(evidence).hexdigest()
            cur.execute('INSERT INTO valor_repair_v7_jobs(job_key,run_id,family,ticker,year,manifest,summary,artifact_sha256,evidence_gzip) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (job_key,run_id,family,ticker,year,Json(manifest),Json(summary),h,psycopg2.Binary(evidence)))
            cur.execute('SELECT manifest,summary,artifact_sha256,evidence_gzip FROM valor_repair_v7_jobs WHERE job_key=%s',(job_key,))
            validated_cached_job(cur.fetchone(),fingerprint,expected_rows(family))
            done+=1;fresh+=1;del rows,evidence,summary
        cur.execute('SELECT count(*),sum(jsonb_array_length(summary)) FROM valor_repair_v7_jobs WHERE run_id=%s',(run_id,))
        n,scenarios=cur.fetchone()
        if int(n)!=len(job_plan()):raise IntegrityError('Completed coverage mismatch')
        state('completed',jobs=int(n),scenario_summaries=int(scenarios),fresh_jobs=fresh,
            live_ready=False,mnq_production_changed=False,new_vendor_downloads=0,
            actual_fees_verified=False,quote_validation_done=False,
            missing_bars_not_silently_filled=True,not_a_blind_holdout=True)
    except Exception as exc:
        if run_id:
            state('blocked_integrity' if isinstance(exc,IntegrityError) else 'failed',error_type=type(exc).__name__,message=str(exc)[:300])
        print('VALOR_REPAIR_V7_FAILURE '+type(exc).__name__+' '+str(exc)[:300],flush=True)
        raise
    finally:
        try:cur.execute('SELECT pg_advisory_unlock(%s)',(LOCK,))
        finally:conn.close()


def launch_if_enabled():
    flags=('VALOR_RESEARCH_REPAIR_V7_AUTORUN','VALOR_MES_SESSION_V6_AUTORUN',
        'VALOR_MES_GEX_V5_AUTORUN','VALOR_MES_V4_AUTORUN','VALOR_EXIT_RESEARCH_AUTORUN',
        'VALOR_CONTRACT_RESEARCH_AUTORUN')
    flag=next((os.environ[k] for k in flags if k in os.environ),'false')
    if flag.lower() not in {'true','1','yes','on'}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    subprocess.Popen([sys.executable,'-m','scripts.valor_research_repair_v7'],
        env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True


if __name__=='__main__':run()
