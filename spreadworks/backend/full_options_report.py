"""Shared report assembly, persistent evidence, real charts and delivery artifacts.

Collectors are isolated from the minute market-data pipeline. Read endpoints never
trigger trades or send notifications. Every field is mapped to observed evidence.
"""
from __future__ import annotations
import asyncio, base64, hashlib, html, json, logging, re
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, HTMLResponse, JSONResponse
from sqlalchemy import text
from .db import engine, SessionLocal
from . import market_structure as ms
from .report_contract import REQUIREMENTS, prepare_report_delivery, validate_rendered_report, FLOW_SOURCE
from .report_producers import observation, unavailable, number, collect_breadth, collect_profile, collect_macro, collect_study, stored_futures, UTC, ET
from .report_ledger import scorecard, qualify_package, mark_open_positions
from .report_policy import build_strategy_blocks, finite_tree, render_opening_html
from .report_assets import DELIVERY_VERSION, inspect_png, chart_id_from_ref, portable_pdf, portable_zip
logger=logging.getLogger(__name__)
router=APIRouter(prefix='/api/spreadworks/reports',tags=['Full Options Reports'])
CT=ZoneInfo('America/Chicago')
PUBLIC_BASE='https://spreadworks-backend.onrender.com/api/spreadworks/reports'

def encoded(value):return json.dumps(value,default=lambda x:x.isoformat() if isinstance(x,datetime) else str(x),allow_nan=False)

def ensure_tables():
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_report_evidence (name TEXT PRIMARY KEY, captured_at TIMESTAMP NOT NULL, payload_json TEXT NOT NULL)'))
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_full_reports (report_id TEXT PRIMARY KEY, generated_at TIMESTAMP NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)'))
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_report_charts (chart_id TEXT PRIMARY KEY, png_base64 TEXT NOT NULL, created_at TIMESTAMP NOT NULL)'))
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_report_deliveries (slot TEXT PRIMARY KEY, status TEXT NOT NULL, lease_until TIMESTAMP, attempts INTEGER NOT NULL DEFAULT 0, report_id TEXT, posted_at TIMESTAMP, error TEXT)'))

def save_evidence(name,value,now):
    ensure_tables()
    with engine.begin() as c:
        previous=c.execute(text('SELECT payload_json FROM sw_report_evidence WHERE name=:name'),{'name':name}).fetchone()
        old=json.loads(previous[0]) if previous else {}
        if value.get('reason') and not value.get('source_timestamp') and old.get('source_timestamp'):
            value=dict(old,last_attempt=value)
        if name=='macro':
            for key,item in old.items():
                if isinstance(item,dict) and item.get('value') is not None and value.get(key,{}).get('status')=='unavailable':
                    value[key]=dict(item,last_attempt=value[key])
        c.execute(text('INSERT INTO sw_report_evidence (name,captured_at,payload_json) VALUES (:name,:now,:payload) ON CONFLICT(name) DO UPDATE SET captured_at=excluded.captured_at,payload_json=excluded.payload_json'),
                  {'name':name,'now':now.replace(tzinfo=None),'payload':encoded(value)})

def load_evidence(name):
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT captured_at,payload_json FROM sw_report_evidence WHERE name=:name'),{'name':name}).fetchone()
    return dict(json.loads(row[1]),captured_at=row[0].replace(tzinfo=UTC).isoformat()) if row else {}

async def capture_context(app,now=None,force=False):
    now=now or datetime.now(UTC)
    if now.astimezone(CT).weekday()>=5 and not force:return {'captured':False,'reason':'Market closed'}
    from .morning_options_report import _latest_plan_payload
    plan=await asyncio.to_thread(_latest_plan_payload,now.astimezone(CT).date()) or {}
    symbols=['SPY','QQQ',*(plan.get('symbols') or [])]
    jobs={'breadth':collect_breadth(now,symbols),'macro':asyncio.to_thread(collect_macro,now)}
    # Profile is lower priority than IV/flow; one consolidated tape request per underlying.
    jobs.update({f'profile_{s}':asyncio.to_thread(collect_profile,s,now,load_evidence('profile_'+s)) for s in ('SPY','QQQ')})
    async def one(name,job):
        try:
            value=await asyncio.wait_for(job,100)
        except Exception as e:value={'reason':'Collector '+type(e).__name__,'source_timestamp':None}
        await asyncio.to_thread(save_evidence,name,value,datetime.now(UTC))
        return name,not bool(value.get('reason'))
    result=await asyncio.gather(*(one(n,j) for n,j in jobs.items()))
    return {'captured':True,'collectors':dict(result)}

async def capture_study():
    result=await asyncio.to_thread(collect_study,datetime.now(UTC))
    await asyncio.to_thread(save_evidence,'study',result,datetime.now(UTC))
    return result

def cached_core(now):
    failures={}
    def read(name, fn, fallback):
        try:
            value=fn()
            if not isinstance(value,dict) or not finite_tree(value):raise ValueError('Invalid provider value')
            return value
        except Exception as exc:
            failures[name]=type(exc).__name__
            return dict(fallback,reason=name+' collector failed: '+type(exc).__name__)
    result={'surface':{},'gamma':{},'flow':{},'volatility':read('volatility',lambda:ms._cached_vol_payload(now),{}),
            'cross_asset':read('cross_asset',lambda:ms.fetch_cross_asset(now),{'assets':{}}),
            'futures':read('futures',lambda:stored_futures(now),{}),'failures':failures}
    for symbol in ('SPY','QQQ'):
        for group,loader in (('surface',ms._latest_surface),('gamma',ms._latest_gamma),('flow',ms._latest_trade_quote_flow)):
            latest=read(group+'_'+symbol,lambda:loader(symbol) or {},{})
            row=latest
            if row.get('confidence') not in ('HIGH','MEDIUM'):
                last_good=read(group+'_'+symbol+'_historical',lambda:loader(symbol,verified_only=True) or {},{})
                if last_good:
                    row=dict(last_good,last_attempt={'reason':latest.get('reason'),'captured_at':latest.get('captured_at')},
                             historical_fallback=True)
            result[group][symbol]=dict(row,symbol=symbol)
    return result

def dated_item(value,row,now,reason=None):
    if row.get('confidence')=='LOW':return unavailable(row.get('reason') or 'Low-confidence evidence rejected')
    return observation(value,row.get('source') or 'Stored observed evidence',row.get('source_timestamp'),now,reason,
                       confidence=row.get('confidence') or 'MEDIUM')

def merge_symbols(rows,keys,now):
    values={};stamps=[];sources=[];missing=[]
    for symbol,row in rows.items():
        value={key:row.get(key) for key in keys}
        field_clocks=[ms._parse_ts((row.get('field_timestamps') or {}).get(key)) for key in keys]
        field_clocks=[s for s in field_clocks if s]
        if 'iv_minus_realized_vol' in keys or 'surface_read' in keys:
            rv_clock=ms._parse_ts(row.get('realized_vol_source_timestamp'))
            if rv_clock:field_clocks.append(rv_clock)
        ts=min(field_clocks) if field_clocks else ms._parse_ts(row.get('source_timestamp'))
        if row.get('confidence')=='LOW' or not ts or all(v is None for v in value.values()) or not finite_tree(value):
            missing.append(symbol+': '+str(row.get('reason') or 'Missing '+','.join(keys)+' or valid source clock'))
            continue
        values[symbol]=value;stamps.append(ts);sources.append(row.get('source') or 'Stored observation')
    item=observation(values if values else None,'; '.join(sorted(set(sources))),min(stamps) if stamps else None,now)
    if missing:
        item=dict(unavailable('Partial/missing source coverage: '+'; '.join(missing)),**({'value':values} if values else {}))
    return item

def market_comparison(core,baseline):
    result={}
    for symbol,row in core['surface'].items():
        old=((baseline.get('evidence') or {}).get('surface') or {}).get(symbol) or {}
        spot,ref=number(row.get('spot')),number(old.get('spot'))
        result[symbol]={'price_change_pct':(spot/ref-1)*100 if spot and ref else None,
             'morning_timestamp':baseline.get('generated_at'),'morning_spot':ref,'current_spot':spot,
             'frozen_expected_move':number(old.get('expected_move_dollars_1d')),
             'frozen_lower':number(old.get('expected_move_low')),'frozen_upper':number(old.get('expected_move_high')),
             'baseline_source_timestamp':old.get('source_timestamp'),
             'baseline_session_matches':bool(ms._parse_ts(old.get('source_timestamp')) and ms._parse_ts(row.get('source_timestamp')) and ms._parse_ts(old['source_timestamp']).astimezone(CT).date()==ms._parse_ts(row['source_timestamp']).astimezone(CT).date()),
             'current_source_timestamp':row.get('source_timestamp')}
    return result

def scheduled_events(now):
    """BLS official iCalendar for verified release times; local estimates retained as such."""
    from .economic_events import ECONOMIC_EVENTS_2026,is_market_holiday
    days=[];date=now.astimezone(CT).date()
    while len(days)<5:
        if date.weekday()<5 and not is_market_holiday(date):days.append(date)
        date+=timedelta(days=1)
    events=[]
    try:
        import requests
        url='https://www.bls.gov/schedule/news_release/bls.ics'
        r=requests.get(url,timeout=8);r.raise_for_status()
        raw=re.sub(r'\r?\n[ \t]','',r.text)
        for chunk in raw.split('BEGIN:VEVENT')[1:]:
            title=re.search(r'(?m)^SUMMARY:(.*)',chunk);dt=re.search(r'(?m)^DTSTART(?:;TZID=([^:\r\n]+))?:(\d{8}T\d{6})(Z?)',chunk)
            if not title or not dt:continue
            tz=UTC if dt[3] else ZoneInfo(dt[1] or 'America/New_York')
            start=datetime.strptime(dt[2],'%Y%m%dT%H%M%S').replace(tzinfo=tz)
            if start.astimezone(CT).date() in days and start>=now:
                events.append({'name':title[1].strip(),'datetime':start.isoformat(),'impact':'HIGH','source':url,'verified':True})
    except Exception as e:
        logger.warning('[FullReport] official calendar unavailable: %s',type(e).__name__)
    for item in ECONOMIC_EVENTS_2026:
        if item['datetime'].date() in days and item['datetime']>=now and not any(e['name'].lower()==item['name'].lower() for e in events):
            events.append({'name':item['name'],'datetime':item['datetime'].isoformat(),'impact':item['impact'],
                           'source':'Local estimated calendar; verify official agency schedule','verified':False})
    return days,sorted(events,key=lambda e:e['datetime'])

def _plan_and_runtime(now):
    from .morning_options_report import _latest_plan_payload
    from .intraday_watch import _load_runtime_status
    plan=_latest_plan_payload(now.astimezone(CT).date()) or {}
    return plan,_load_runtime_status()

_UNSET=object()

def report_blocks(core,context,plan,runtime,paper,study,comparison,events,now):
    blocks={name:{field:unavailable('No verified observation for '+name+'.'+field) for field in fields} for name,fields in REQUIREMENTS.items()}
    def put(name,field,value,row=None,source=None,ts=_UNSET,reason=None):
        blocks[name][field]=dated_item(value,row,now,reason) if row is not None else observation(value,source or 'Report ledger query',now if ts is _UNSET else ts,now,reason)
    surface=core['surface'];gamma=core['gamma'];flow=core['flow'];cross=core['cross_asset'];vol=core['volatility']
    for field,key in {'atm_iv':'atm_iv','skew_25d':'skew_25d','term_0dte':'iv_0dte','term_1_5dte':'iv_1_5dte',
                     'term_6_20dte':'iv_6_20dte','term_21plus':'iv_21_365dte','interpretation':'surface_read'}.items():
        blocks['surface'][field]=merge_symbols(surface,[key],now)
    rv_rows={s:dict(r,**(r.get('iv_rv_comparison') or {})) if (r.get('iv_rv_comparison') or {}).get('realized_vol_60m') is not None else r for s,r in surface.items()}
    blocks['surface']['iv_vs_realized']=merge_symbols(rv_rows,['atm_iv','realized_vol_60m','iv_minus_realized_vol','realized_vol_source_timestamp'],now)
    indices=vol.get('indices') or {}
    for field in ('vix_family',):
        vals={s:r for s,r in indices.items() if r.get('price') is not None}
        stamps=[ms._parse_ts(r.get('source_timestamp')) for r in vals.values()];stamps=[s for s in stamps if s]
        blocks['surface'][field]=observation(vals or None,vol.get('source') or 'Volatility index snapshots',min(stamps) if stamps else None,now)
    for field,key in {'expiry':'expiration','put_25d_iv':'put_25d_iv','atm_iv':'atm_iv','call_25d_iv':'call_25d_iv','delta_method':'method'}.items():
        rows={s:dict(r,**(r.get('smile') or {})) for s,r in surface.items()}
        blocks['smile'][field]=merge_symbols(rows,[key],now)
    blocks['smile']['strikes']=merge_symbols({s:dict(r,**(r.get('smile') or {})) for s,r in surface.items()},['put_strike','atm_strike','call_strike','put_delta','call_delta'],now)
    for field,key in {'percent':'expected_move_pct_1d','dollars':'expected_move_dollars_1d','lower':'expected_move_low',
                     'upper':'expected_move_high','reference_spot':'spot','method':'expected_move_method'}.items():
        blocks['expected_move'][field]=merge_symbols(surface,[key],now)
    blocks['expected_move']['expiry']=merge_symbols(surface,['atm_reference_dte'],now)
    put('expected_move','session','One trading-day annualized-IV estimate; not a calibrated remaining-session forecast',source='Expected move method definition')
    for field in ('budget_used','price_location'):
        vals={}
        for s,r in comparison.items():
            base=r.get('morning_spot');current=r.get('current_spot');em=number(r.get('frozen_expected_move'))
            if base and current and em and em>0 and r.get('baseline_session_matches'):vals[s]={'absolute_move_fraction':abs(current-base)/em,'signed_change':current-base,
                'frozen_expected_move_dollars':em,'frozen_lower':r.get('frozen_lower'),'frozen_upper':r.get('frozen_upper'),
                'reference':'Frozen first morning expected-move estimate; current IV shown separately'}
        put('expected_move',field,vals or None,source='Recorded morning baseline vs current underlying',ts=min([ms._parse_ts(r.get('source_timestamp')) for r in surface.values() if ms._parse_ts(r.get('source_timestamp'))],default=None),reason='No comparable morning baseline')
    for field,key in {'net_gex':'net_gex_b','flip':'gamma_flip','walls':'walls','expiry_buckets':'buckets','coverage':'n_rows'}.items():blocks['gamma'][field]=merge_symbols(gamma,[key],now)
    put('gamma','scope_comparability','Bounded near-spot <=60DTE estimated dealer gamma; compare only matching coverage. OI is daily, not intraminute.')
    for field in ('provider_provenance','exchange_timestamp','retrieval_timestamp','age','classified_coverage','unclassified_coverage',
                  'calls_bought','calls_sold','puts_bought','puts_sold','expiry_buckets'):
        vals={};stamps=[]
        for s,r in flow.items():
            ev=r.get('evidence') or {};ts=ms._parse_ts(r.get('source_timestamp'))
            if r.get('confidence')=='LOW' or not ts or not ev.get('buckets'):continue
            stamps.append(ts)
            if field in ('calls_bought','calls_sold','puts_bought','puts_sold'):vals[s]={b:v.get(field) for b,v in ev['buckets'].items()}
            else:vals[s]={'provider_provenance':ev.get('source'),'exchange_timestamp':ts.isoformat(),'retrieval_timestamp':ev.get('retrieval_timestamp'),
               'age':(now-ts).total_seconds(),'classified_coverage':ev.get('classified_contract_fraction'),
               'unclassified_coverage':{'contracts':ev.get('unclassified_contracts'),'premium':ev.get('unclassified_premium')},'expiry_buckets':ev['buckets']}.get(field)
        blocks['flow'][field]=observation(vals or None,FLOW_SOURCE,min(stamps) if stamps else None,now,reason='FLOW DATA UNAVAILABLE: '+ '; '.join(sorted({str(r.get('reason') or 'No verified trade-time bid/ask print evidence') for r in flow.values()})) if not vals else None)
    for field,key in {'expiries':'expiration','strikes':'strike','contracts':'contracts','premium':'premium','prints':'print_count',
                      'contemporaneous_bid_ask':'latest_print','initiation_estimate':'initiation'}.items():
        vals={s:[{key:r.get(key)} for r in (row.get('evidence') or {}).get('concentrations') or []] for s,row in flow.items()}
        vals={s:v for s,v in vals.items() if v}
        ts=min([ms._parse_ts(row.get('source_timestamp')) for row in flow.values() if ms._parse_ts(row.get('source_timestamp'))],default=None)
        put('forward_strikes',field,vals or None,source=FLOW_SOURCE,ts=ts,reason='No verified forward prints')
    # Who is in control: call-seller vs put-seller premium dominance, gated on classified coverage.
    control_rows={};control_ts=[];control_fractions={}
    for s,r in flow.items():
        ev=r.get('evidence') or {};ts=ms._parse_ts(r.get('source_timestamp'))
        if r.get('confidence')=='LOW' or not ts or not ev.get('buckets'):continue
        fraction=ev.get('classified_contract_fraction')
        per_bucket={}
        for bucket,cats in ev['buckets'].items():
            call_sell=float((cats.get('calls_sold') or {}).get('premium') or 0)
            put_sell=float((cats.get('puts_sold') or {}).get('premium') or 0)
            if fraction is None or fraction<0.5:side='inconclusive'
            elif call_sell<=0 and put_sell<=0:side='inconclusive'
            elif call_sell>put_sell*1.5:side='call_sellers'
            elif put_sell>call_sell*1.5:side='put_sellers'
            else:side='mixed'
            per_bucket[bucket]={'side':side,'call_sell_premium':call_sell,'put_sell_premium':put_sell}
        if per_bucket:
            control_rows[s]=per_bucket;control_ts.append(ts);control_fractions[s]=fraction
    put('market_control','control_evidence',control_rows or None,source=FLOW_SOURCE,
        ts=min(control_ts) if control_ts else None,reason='No verified classified call/put sell premium by expiry bucket')
    sides={s:{b:v['side'] for b,v in rows.items()} for s,rows in control_rows.items()}
    put('market_control','control_side',sides or None,
        source='Deterministic call-sell vs put-sell premium dominance by expiry bucket, gated on Sec.7 classified coverage (<0.5 forces inconclusive)',
        ts=min(control_ts) if control_ts else None,reason='No qualifying classified flow to score')
    confidence_labels={s:('HIGH' if (f or 0)>=0.7 else 'MEDIUM' if (f or 0)>=0.5 else 'LOW_FORCES_INCONCLUSIVE') for s,f in control_fractions.items()}
    confidence_values={s:{'classified_contract_fraction':control_fractions[s],'label':confidence_labels[s]} for s in confidence_labels}
    put('market_control','control_confidence',confidence_values or None,source='Section 7 classified-contract fraction gate',
        ts=min(control_ts) if control_ts else None,reason='No classified-coverage fraction available')
    assets=cross.get('assets') or {}
    relative={s:(r['price']/r['prev_close']-1)*100 for s,r in assets.items() if number(r.get('price')) and number(r.get('prev_close'))}
    cross_ts=min([ms._parse_ts(r.get('source_timestamp')) for r in assets.values() if ms._parse_ts(r.get('source_timestamp'))],default=None)
    put('sector_credit','relative_returns',relative or None,source='Consolidated ETF quotes vs prior close',ts=cross_ts)
    put('sector_credit','leadership',sorted(relative,key=relative.get,reverse=True) if relative else None,source='Relative-return ordering',ts=cross_ts)
    put('sector_credit','credit_confirmation',{s:relative[s] for s in ('HYG','LQD','TLT') if s in relative} or None,source='Credit/bond ETF proxies; not credit spreads',ts=cross_ts)
    # Deterministic price/VIX confirmation: does observed price direction agree with the
    # flow-implied lean (calls_bought+puts_sold premium vs calls_sold+puts_bought premium)?
    # VIX has no persisted prior-close baseline here, so its level is carried as context
    # only -- the confirmation verdict itself never depends on an unmeasured VIX direction.
    pv_confirmation={};pv_ts=[]
    for s in ('SPY','QQQ'):
        r=flow.get(s) or {};ev=r.get('evidence') or {};ts=ms._parse_ts(r.get('source_timestamp'))
        if r.get('confidence')=='LOW' or not ts or not ev.get('buckets') or s not in relative:continue
        up=sum(float((bk.get('calls_bought') or {}).get('premium') or 0)+float((bk.get('puts_sold') or {}).get('premium') or 0) for bk in ev['buckets'].values())
        down=sum(float((bk.get('calls_sold') or {}).get('premium') or 0)+float((bk.get('puts_bought') or {}).get('premium') or 0) for bk in ev['buckets'].values())
        if up<=0 and down<=0:continue
        flow_lean='upside' if up>down*1.2 else 'downside' if down>up*1.2 else 'balanced'
        price_dir='up' if relative[s]>0.05 else 'down' if relative[s]<-0.05 else 'flat'
        read=('inconclusive' if flow_lean=='balanced' or price_dir=='flat'
              else 'confirms' if (flow_lean=='upside')==(price_dir=='up') else 'conflicts')
        pv_confirmation[s]={'flow_lean':flow_lean,'price_direction':price_dir,'price_change_pct':round(relative[s],3),
            'vix_level':(indices.get('VIX') or {}).get('price'),'read':read}
        pv_ts.append(ts)
    put('flow','price_vix_confirmation',pv_confirmation or None,
        source='Deterministic comparison of flow-implied lean vs observed price direction; VIX level is context only, no persisted baseline for its own direction',
        ts=min(pv_ts) if pv_ts else None,reason='No qualifying classified flow plus fresh price observation to compare')
    breadth=context.get('breadth') or {};bts=breadth.get('source_timestamp')
    for field,keys in {'advance_decline':['advances','declines','unchanged','coverage_pct','universe'],
                       'up_down_volume':['advancing_issue_volume','declining_issue_volume','up_down_volume_ratio','volume_method'],
                       'new_highs_lows':['new_52w_highs','new_52w_lows','high_low_covered']}.items():
        vals={k:breadth.get(k) for k in keys}
        put('breadth',field,vals if breadth.get('covered') else None,source=breadth.get('source'),ts=bts,reason=breadth.get('reason'))
    vw=breadth.get('vwap') or {};vts=min([ms._parse_ts(r['source_timestamp']) for r in (vw.get('rows') or {}).values()],default=None)
    put('breadth','percent_above_vwap',vw if vw.get('covered') else None,source='Observed minute-bar VWAP; report-candidate sample',ts=vts)
    put('breadth','proxy_labels',{'constituent_scope':'SSGA SPY holdings','vwap_scope':vw.get('scope'),'volume_scope':breadth.get('volume_method')})
    profiles={s:context.get('profile_'+s) or {} for s in ('SPY','QQQ')}
    for field in ('poc','vah','val','hvn','lvn','method'):
        blocks['profile'][field]=merge_symbols(profiles,[field],now)
    acceptance={}
    for s,r in profiles.items():
        spot=number(surface[s].get('spot'));low=number(r.get('val'));high=number(r.get('vah'))
        if spot and low and high:acceptance[s]={'location':'above value' if spot>high else 'below value' if spot<low else 'inside value',
              'confirmation':'Location only; acceptance requires two fresh closes plus a held retest'}
    put('profile','acceptance_rejection',acceptance or None,source='Observed price/profile comparison',ts=min([ms._parse_ts(r.get('source_timestamp')) for r in profiles.values() if ms._parse_ts(r.get('source_timestamp'))],default=None))
    macro=context.get('macro') or {}
    for field,names in {'rates':['rates_13w','rates_2y','rates_5y','rates_10y','rates_30y'],'dollar':['dollar'],
                       'fx':['eurusd','usdjpy'],'commodities':['gold','oil'],'move':['move']}.items():
        vals={n:macro[n] for n in names if macro.get(n,{}).get('status')!='unavailable' and macro.get(n)}
        times=[ms._parse_ts(r['source_timestamp']) for r in vals.values()]
        blocks['macro'][field]=observation(vals or None,'Delayed indicative macro sources',min(times) if times else None,now,delayed=True)
    r5=(macro.get('rates_2y') or {}).get('value') or {};r10=(macro.get('rates_10y') or {}).get('value') or {}
    curve=(r10['price']-r5['price'])*100 if number(r10.get('price')) is not None and number(r5.get('price')) is not None else None
    blocks['macro']['curve']=observation({'10y_minus_2y_basis_points':curve} if curve is not None else None,'FRED daily Treasury 10y minus 2y yield',macro.get('rates_2y',{}).get('source_timestamp'),now,delayed=True)
    put('macro','proxy_labels','Delayed indicative rates/FX/commodity context. No ETF stand-in for MOVE; absent MOVE remains disclosed.')
    for field,names in {'es_mes':['es'],'nq':['nq'],'overnight_range':['es','nq']}.items():
        vals={n:macro[n] for n in names if macro.get(n,{}).get('value')};times=[ms._parse_ts(r['source_timestamp']) for r in vals.values()]
        blocks['futures_context'][field]=observation(vals or None,'Delayed ES/NQ continuous futures; ES price is MES reference, not an MES execution quote',min(times) if times else None,now,delayed=True)
    futures=core.get('futures') or {}
    for field,roots in {'es_mes':('MES','ES'),'nq':('MNQ','NQ'),'overnight_range':('MES','ES','MNQ','NQ')}.items():
        observed={r:futures[r] for r in roots if futures.get(r,{}).get('value')}
        if observed:
            times=[ms._parse_ts(r['source_timestamp']) for r in observed.values()]
            blocks['futures_context'][field]=observation(observed,'Persisted broker futures quote events; actual contract symbols retained',min(times),now)
    blocks['futures_context']['basis']=unavailable('Exact same-time futures vs cash-index basis unavailable; SPY is not substituted for SPX')
    blocks['futures_context']['index_confirmation']=merge_symbols(surface,['spot','source_timestamp'],now)
    for field in ('next_five_trading_days','catalysts','times','sources','risk_classes'):
        value=events if field!='sources' else sorted({e['source'] for e in events})
        put('event_calendar',field,value if value else None,source='Official BLS iCalendar plus labeled local estimated dates')
    if any(not e['verified'] for e in events):
        for f in blocks['event_calendar']:
            blocks['event_calendar'][f]['status']='unavailable'
            blocks['event_calendar'][f]['reason']='Calendar coverage is partial; local estimates are displayed explicitly and are not verified releases'
    setup_list=plan.get('setups') or [];states=runtime.get('per_symbol_state') or {}
    for field in ('trigger','confirmation','invalidation','status','two_minute_closes','successful_retest'):
        vals=[{'setup_id':s['setup_id'],'symbol':s['symbol'],'entry':s.get('entry'),'invalidation':s.get('invalidation'),
               'state':states.get(s['symbol']),'required_sequence':'Two completed 1-minute closes; then successful retest if required by setup'} for s in setup_list]
        put('entry_watches',field,vals,source='Registered plan and isolated minute watcher',ts=runtime.get('worker_heartbeat') or plan.get('generated_at'))
    packages=[]
    for rows in states.values():
        for row in rows:
            package=qualify_package(row.get('option_strike_selection') or {},now)
            if package:packages.append(dict(package,setup_id=row.get('setup_id'),setup_state=row.get('state')))
    package_fields={
        'expiry':lambda p:p.get('expiration'), 'strikes':lambda p:[l['strike'] for l in p['legs']],
        'legs':lambda p:p['legs'], 'bid_ask':lambda p:[{k:l.get(k) for k in ('symbol','bid','ask','bid_size','ask_size','exchange_timestamp')} for l in p['legs']],
        'greeks':lambda p:[{k:l.get(k) for k in ('symbol','delta','gamma','theta','vega','iv')} for l in p['legs']],
        'oi':lambda p:[{'symbol':l['symbol'],'open_interest':l.get('open_interest')} for l in p['legs']],
        'volume':lambda p:[{'symbol':l['symbol'],'volume':l.get('volume')} for l in p['legs']],
        'debit_credit':lambda p:{k:p.get(k) for k in ('natural_debit','natural_credit')},
        'max_risk_reward':lambda p:p.get('payoff'), 'breakeven':lambda p:(p.get('payoff') or {}).get('breakeven'),
        'liquidity':lambda p:[{'symbol':l['symbol'],'spread':round(l['ask']-l['bid'],4),'oi':l.get('open_interest'),'volume':l.get('volume')} for l in p['legs']]}
    for field,extract in package_fields.items():
        value=[{'setup_id':p['setup_id'],'strategy':p['strategy'],'value':extract(p)} for p in packages]
        put('contract_packages',field,value or None,source='Watcher fresh per-leg chain qualification',ts=min([ms._parse_ts(l['exchange_timestamp']) for p in packages for l in p['legs']],default=None),reason='No freshly qualified conditional package; options closed or trigger/chain pending')
    for field in REQUIREMENTS['paper_scorecard']:
        reason='No completed paper trades: win rate is undefined; this is not performance evidence' if field=='win_rate' and paper.get('win_rate') is None else None
        put('paper_scorecard',field,paper.get(field),source='Forward report-alert simulation ledger query',reason=reason)
    for field in REQUIREMENTS['trigger_accountability']:
        value={'registered_triggers':setup_list,'verified_occurrence':paper['entry_ready_alerts'],
               'confirmation_sequence':paper.get('trigger_events') or [],
               'mfe_mae':[{'event_key':t['event_key'],'mfe':t.get('mfe'),'mae':t.get('mae'),'scope':'Observed liquidation BBO marks, not tick-perfect extrema'} for t in paper['trade_details']],
               'outcome':{'trigger_events':paper.get('trigger_events') or [],'paper_trades':paper['trade_details']},'loss_clusters':paper.get('loss_clusters')}.get(field)
        put('trigger_accountability',field,value,source='Registered rules and observed paper ledger')
    for field in REQUIREMENTS['event_study']:
        value=study.get(field)
        if field=='validated_statistics':value={k:study.get(k) for k in ('validated_statistics','stall_fraction','wilson_95_interval','minimum_sample','loss_clusters','reason','failures')}
        put('event_study',field,value,source='Frozen historical 1-minute event study; source provenance retained',ts=study.get('captured_at'),reason=study.get('reason'))
    # Each comparison measures its named field, never duplicates a price delta.
    from .report_policy import HOLDING_PERIODS, business_dates
    holding_dates=business_dates(now.astimezone(CT).date(),21)
    put('event_study','holding_period_context',{'periods':{str(n):{'sessions':n,'label':label,'measurement':'Close-to-close underlying return; not option P&L','illustrative_exit_date':holding_dates[n].isoformat()} for n,label in HOLDING_PERIODS.items()},'comparison_rule':'Compare 10 versus 20 sessions only within the same verified entry cohort, costs and sample; unverified performance figures are not asserted as measured returns.'},source='Trading-session horizon definition')
    for field in REQUIREMENTS['morning_comparison']:
        values={}
        for symbol,row in comparison.items():
            old=((core.get('baseline_blocks') or {}).get(field) or {}).get(symbol)
            prior=((core.get('prior_blocks') or {}).get(field) or {}).get(symbol)
            if field=='morning_timestamp':values[symbol]=row.get('morning_timestamp')
            elif field=='price_location':values[symbol]={'morning_spot':row.get('morning_spot'),'now_spot':row.get('current_spot'),'change_pct':row.get('price_change_pct'),'morning_updated_at':row.get('baseline_source_timestamp'),'now_updated_at':row.get('current_source_timestamp')}
            elif field=='move_usage':values[symbol]={'morning':old,'prior_hour':prior,'now':blocks['expected_move']['budget_used'].get('value',{}).get(symbol),'same_session_reference':row.get('baseline_session_matches')}
            elif field=='chop_status':values[symbol]={'morning':old,'prior_hour':prior,'now':{k:blocks['range_stall'][k].get('value',{}).get(symbol) for k in ('chop_low','midpoint','chop_high','first_touch_watch')}}
            elif field=='stall_risk':values[symbol]={'morning':old,'prior_hour':prior,'now':states.get(symbol),'confirmation':'Touch alone remains WATCH; no validated probability is inferred'}
            elif field=='setup_status':values[symbol]={'morning':old,'prior_hour':prior,'now':[{'setup_id':r.get('setup_id'),'state':r.get('state')} for r in (runtime.get('per_symbol_state') or {}).get(symbol,[])]}
        stamps=[ms._parse_ts(r.get('current_source_timestamp')) for r in comparison.values()];stamps=[s for s in stamps if s]
        put('morning_comparison',field,values or None,source='Distinct persisted baseline-to-now observations',ts=min(stamps) if stamps else None,reason='First report: no earlier comparable baseline')
    for field in REQUIREMENTS['scanner']:
        value={'minute_cadence':runtime.get('poll_interval_seconds'),'heartbeat':runtime.get('worker_heartbeat'),
               'registered_setups':runtime.get('active_setup_count'),'delivery_status':{'enabled':runtime.get('discord_enabled'),'configured':runtime.get('discord_configured'),'last_alert':runtime.get('last_alert')}}.get(field)
        put('scanner',field,value,source='Isolated scanner heartbeat',ts=runtime.get('worker_heartbeat'))
    for field in REQUIREMENTS['candidate_analysis']:
        value={'symbols':plan.get('symbols') or [],'surface':{s:r for s,r in surface.items()},'catalysts':plan.get('news_sources'),
           'quote_chain_freshness':{'underlyings':plan.get('market_evidence'),'qualified_packages':packages},
           'liquidity':packages,'conditional_triggers':setup_list}.get(field)
        put('candidate_analysis',field,value,source='Report roster / observed chains / registered conditional rules',ts=plan.get('generated_at'))
    candidate_rows=(context.get('candidate_surfaces') or {}).get('symbols') or {}
    requested=plan.get('symbols') or []
    candidate_rows={s:candidate_rows.get(s) or {'reason':'No candidate surface observation yet'} for s in requested}
    blocks['candidate_analysis']['surface']=merge_symbols(candidate_rows,['atm_iv','skew_25d','smile','iv_0dte','iv_1_5dte','iv_6_20dte','iv_21_365dte','source_timestamp'],now)
    if requested and any(not ms._parse_ts(r.get('source_timestamp')) for r in candidate_rows.values()):
        blocks['candidate_analysis']['surface']=dict(unavailable('Candidate surface coverage is partial; per-symbol reasons retained'),value=candidate_rows)
    put('position_management','position_scope' ,'Report paper positions only; private broker holdings were not supplied')
    put('position_management','risk_exposure',{'open_max_defined_risk':sum(t['max_risk'] for t in paper['trade_details'] if t['state']=='OPEN'),'quantity_model':'One structure per qualifying signal'})
    put('position_management','hold_exit_conditions',paper['fill_rules'])
    put('position_management','chain_qualification',{'rule':'Fresh executable BBO required for every entry/exit; missing quotes leave unresolved positions','exceptions':paper['exceptions']})
    # Directional inference uses only current evidence. Historical context stays visible separately.
    fresh_returns={s:r for s,r in relative.items() if (assets.get(s) or {}).get('fresh')}
    if 'SPY' in fresh_returns and 'QQQ' in fresh_returns:
        risk=all(fresh_returns[s]>0 for s in ('SPY','QQQ'))
        defensive=all(fresh_returns[s]<0 for s in ('SPY','QQQ'))
        verdict='Risk-on price confirmation' if risk else 'Defensive price confirmation' if defensive else 'Mixed price confirmation'
        inputs={'returns':fresh_returns,'breadth':breadth if breadth.get('covered') else None,'flow':'Side estimates; not opening/closing inventory'}
        for field,value in {'verdict':verdict,'evidence':inputs,'conflicts':'Sector, breadth, volatility and flow may diverge; verdict is conditional price evidence, not a prediction','change_vs_baselines':comparison}.items():put('risk_on_defensive',field,value,source='Deterministic interpretation of current observed returns',ts=cross_ts)
    for field in REQUIREMENTS['premium_selling']:
        values={};stamps=[]
        for s,row in surface.items():
            read=row.get('surface_read') or {}
            if not read.get('available') or row.get('confidence')=='LOW':continue
            ts=ms._parse_ts(row.get('source_timestamp'));rts=ms._parse_ts(row.get('realized_vol_source_timestamp'))
            if not ts or not rts:continue
            stamps.extend([ts,rts])
            values[s]={'suitability':read.get('day_state'),
               'iv_rv_meaning_today':{'ratio':read.get('iv_realized_ratio'),'gap':read.get('iv_realized_gap'),'meaning':read.get('day_meaning')},
               'forward_implications':read.get('forward_meaning'),
               'credit_structure_fit':'Defined-risk credit only after range acceptance, liquid wings and event clearance; directional bias selects put vs call side',
               'avoid':'Confirmed expansion, realized volatility outrunning IV, unverified event risk, or a credit too small after costs'}.get(field)
        blocks['premium_selling'][field]=observation(values or None,'Observed IV / realized-volatility comparison; conditional suitability',min(stamps) if stamps else None,now)
    for field in REQUIREMENTS['range_stall']:
        value={}
        for s,r in profiles.items():
            if r.get('poc') is None:continue
            spot=number(surface[s].get('spot'))
            actual={
                'chop_low':r.get('val'),'midpoint':r.get('poc'),'chop_high':r.get('vah'),
                'room_to_edges':{'to_low':spot-r['val'],'to_high':r['vah']-spot} if spot else None,
                'two_fresh_confirmations':states.get(s),
                'actual_rejection':{'observed_sequence':states.get(s),'rule':'A touch alone is not a rejection; inspect completed close sequence'},
                'first_touch_watch':'Watch only. Profile value is a candidate balance range, not a validated chop forecast',
                'breakout_ends_chop':'Two completed closes outside value plus a held retest invalidate the balance assumption'}
            value[s]=actual[field]
        put('range_stall',field,value or None,source='Observed profile range + explicit confirmation rule',ts=min([ms._parse_ts(r.get('source_timestamp')) for r in profiles.values() if ms._parse_ts(r.get('source_timestamp'))],default=None))
    for field in REQUIREMENTS['engine_consensus']:
        value={'squeeze':plan.get('market_regime'),'trading_volatility_status':plan.get('trading_volatility'),
             'contradictions':'Compare engine evidence and timestamps; absent engine state is not consensus'}.get(field)
        put('engine_consensus',field,value,source='Recorded independent engine states',ts=plan.get('generated_at'))
    return blocks

def forward_control_outlook(blocks,now):
    """Compare today's dominant option-seller side against the §29 forward (1-4wk) initiation-pressure read.

    Runs after build_strategy_blocks populates forward_strategy; never infers persistence/flip
    from today's control side alone.
    """
    control=blocks.get('market_control',{}).get('control_side') or {}
    sides=control.get('value') or {}
    forward=blocks.get('forward_strategy',{}).get('thesis') or {}
    pressure=forward.get('value') if isinstance(forward.get('value'),dict) else {}
    out={}
    for symbol,buckets in sides.items():
        side=buckets.get('0dte') or next(iter(buckets.values()),None)
        if side not in ('call_sellers','put_sellers'):continue
        read=(pressure.get(symbol) or {}).get('read')
        if read in ('upside pressure','downside pressure'):
            consistent=(side=='call_sellers' and read=='downside pressure') or (side=='put_sellers' and read=='upside pressure')
            out[symbol]={'today_control':side,'forward_pressure_read':read,'outlook':'persists' if consistent else 'flips'}
        else:
            out[symbol]={'today_control':side,'forward_pressure_read':read,'outlook':'fades',
                         'basis':'Forward (1-4wk) initiation pressure is balanced/unclassified; no confirmed read to extend today control'}
    blocks['market_control']['forward_control_outlook']=observation(out or None,
        'Deterministic comparison of Sec.market_control control_side vs Sec.forward_strategy thesis.read',
        control.get('source_timestamp'),now,reason='No qualifying control side or forward pressure read to compare')

def previous_reports(now):
    ensure_tables();start=datetime.combine(now.astimezone(CT).date(),time(0),CT).astimezone(UTC).replace(tzinfo=None)
    with engine.begin() as c:
        rows=c.execute(text("SELECT kind,payload_json FROM sw_full_reports WHERE generated_at>=:start AND generated_at<=:now AND kind IN ('morning','market_open','intraday') ORDER BY generated_at"),{'start':start,'now':now.replace(tzinfo=None)}).fetchall()
    morning=next((json.loads(raw) for kind,raw in rows if kind=='morning'),{})
    prior=json.loads(rows[-1][1]) if rows else {}
    return morning,prior

async def assemble_report(app,*,kind='intraday',plan=None,now=None):
    started=now or datetime.now(UTC)
    read_failures={}
    async def read(name,fn,default,timeout=15):
        try:
            value=await asyncio.wait_for(asyncio.to_thread(fn),timeout)
            if not isinstance(value,type(default)) or not finite_tree(value):raise ValueError('Malformed stored evidence')
            return value
        except Exception as exc:
            read_failures[name]=type(exc).__name__
            logger.warning('[FullReport] optional read failed %s: %s',name,type(exc).__name__)
            return default
    from .report_refresh import refresh_context, refresh_core
    stored_plan,runtime=await read('plan_runtime',lambda:_plan_and_runtime(started),({},{}))
    plan=plan if plan is not None else stored_plan
    refresh_attempts=await refresh_context(started,plan)
    core=await read('core',lambda:cached_core(datetime.now(UTC)),{'surface':{'SPY':{},'QQQ':{}},'gamma':{},'flow':{},'volatility':{},'cross_asset':{'assets':{}},'futures':{}},timeout=60)
    context={name:await read(name,lambda n=name:load_evidence(n),{'reason':'Stored evidence read failed for '+name}) for name in ('breadth','macro','profile_SPY','profile_QQQ','study','candidate_surfaces')}
    paper=await read('paper',scorecard,{'entry_ready_alerts':None,'trade_details':[],'exceptions':[{'reason':'Paper ledger unavailable'}],
        'fill_rules':'Ledger failed; no paper performance or open risk may be inferred','loss_clusters':[]})
    morning,prior=await read('baselines',lambda:previous_reports(started),({},{}))
    days,events=await read('calendar',lambda:scheduled_events(started),([],[]))
    core,core_attempts=await refresh_core(core)
    refresh_attempts.extend(core_attempts)
    now=datetime.now(UTC)
    comparison=market_comparison(core,morning)
    prior_comparison=market_comparison(core,prior)
    def comparable(baseline):
        b=baseline.get('report_blocks') or {};result={}
        for field,section,key in [('move_usage','expected_move','budget_used'),('chop_status','range_stall','chop_low'),('stall_risk','range_stall','actual_rejection'),('setup_status','entry_watches','status')]:
            item=b.get(section,{}).get(key,{});value=item.get('value')
            if isinstance(value,list) and all(isinstance(r,dict) and r.get('symbol') for r in value):result[field]={symbol:[r for r in value if r['symbol']==symbol] for symbol in ('SPY','QQQ')}
            else:result[field]=value if isinstance(value,dict) else {'SPY':value,'QQQ':value}
        return result
    core.update(comparison=comparison,prior_comparison=prior_comparison,baseline_blocks=comparable(morning),prior_blocks=comparable(prior))
    blocks=report_blocks(core,context,plan,runtime,paper,context['study'],comparison,events,now)
    if kind=='morning' and not morning:
        morning={'generated_at':now.isoformat(),'evidence':core,'report_blocks':blocks}
        comparison=market_comparison(core,morning)
        core['comparison']=comparison
    prior_stamp=prior.get('generated_at')
    if prior_stamp:
        blocks['morning_comparison']['prior_hour_timestamp']=observation(prior_stamp,'Previous stored report',now,now)
    blocks['event_calendar']['next_five_trading_days']=observation([d.isoformat() for d in days],'Trading-calendar dates, excludes known holidays',now,now)
    build_strategy_blocks(blocks,core,plan,runtime,paper,morning,prior,now)
    forward_control_outlook(blocks,now)
    if 'paper' in read_failures:
        for name in ('paper_scorecard','trigger_accountability','position_management'):
            blocks[name]={field:unavailable('Paper ledger unavailable: '+read_failures['paper']) for field in REQUIREMENTS[name]}
    evidence=dict(core,generated_at=now.isoformat(),profiles={s:context['profile_'+s] for s in ('SPY','QQQ')},paper=paper,comparison=comparison,events=events)
    headline=blocks['risk_on_defensive']['verdict'].get('value') or 'Directional verdict pending verified fresh evidence'
    payload={'generated_at':now.isoformat(),'kind':kind,'advisory_only':True,'report_blocks':blocks,'evidence':evidence,
             'report_markdown':f'# {kind.title()} Options Report\n\n**{headline}**\n\nSource clocks and historical labels are preserved. Conditional watches are advisory; paper fills are simulated.',
             'refresh_attempts':refresh_attempts,
             'producer_status':{name:context[name].get('reason') or context[name].get('captured_at') or 'No capture yet' for name in context},
             'producer_failures':dict(core.get('failures') or {},**read_failures,**{name:{k:row.get(k) for k in ('reason','last_attempt','failures') if row.get(k)} for name,row in context.items() if row.get('reason') or row.get('last_attempt') or row.get('failures')}),
             'collector_coverage':{'breadth':'SPY constituents; VWAP candidate sample','profile':'Cumulative observed RTH tape, checkpointed in bounded windows; coverage timestamps disclosed','flow':'ThetaData Pro primary: up to four listed expirations <=60DTE, six listed strikes nearest spot per expiry (calls/puts), trailing 120-second window; completed/failed expirations in source evidence; not all-strike, all-expiration, whole-market or full-session flow; Tradier fallback unclassified','futures':'Broker MES/MNQ observations where recorded; delayed continuous ES/NQ fallback'}}
    from .report_charts import chart_png
    image_refs={};inspection=[]
    for chart in ('market_map','smile_term','surface','term_structure','flow','baseline_comparison','event_risk','paper_equity_drawdown','gamma_expiry','sector_credit','volume_profile'):
        png,plotted=await asyncio.to_thread(chart_png,chart,evidence)
        # Validate PNG decoding and dimensions before exposing an image reference.
        from PIL import Image
        import io
        with Image.open(io.BytesIO(png)) as im:
            im.load();width,height=im.size;dark=im.convert('RGB').getpixel((0,0))==(11,18,32)
        if width<1000 or height<600 or not dark:raise ValueError('Chart image verification failed')
        chart_id=hashlib.sha256(png).hexdigest()[:32]
        with engine.begin() as c:
            c.execute(text('INSERT INTO sw_report_charts (chart_id,png_base64,created_at) VALUES (:id,:png,:now) ON CONFLICT(chart_id) DO NOTHING'),
                      {'id':chart_id,'png':base64.b64encode(png).decode(),'now':now.replace(tzinfo=None)})
        ref=f'{PUBLIC_BASE}/charts/{chart_id}.png';image_refs[chart]=ref
        inspection.append({'panel':chart,'width':width,'height':height,'dark_background':dark,'observed_data_plotted':plotted})
        if chart+'_png' in blocks['visuals']:
            if plotted:
                # Charts retain the data's actual clock; generating a file does not refresh its data.
                group='surface' if chart in ('market_map','smile_term','surface','term_structure') else 'flow' if chart=='flow' else 'gamma' if chart=='gamma_expiry' else None
                stamps=[ms._parse_ts(r.get('source_timestamp')) for r in (core.get(group) or {}).values()] if group else []
                stamps=[s for s in stamps if s]
                if chart=='sector_credit':
                    stamps=[ms._parse_ts(r.get('source_timestamp')) for r in (core['cross_asset'].get('assets') or {}).values()]
                    stamps=[s for s in stamps if s]
                if chart=='volume_profile':
                    stamps=[ms._parse_ts(r.get('source_timestamp')) for r in evidence['profiles'].values()]
                    stamps=[s for s in stamps if s]
                if chart=='baseline_comparison':
                    stamps=[ms._parse_ts(r.get('current_source_timestamp')) for r in comparison.values()]
                    stamps=[s for s in stamps if s]
                data_time=min(stamps) if stamps else now
                blocks['visuals'][chart+'_png']=observation(ref,'Matplotlib chart of attached report evidence',data_time,now)
            else:blocks['visuals'][chart+'_png']=unavailable('No observed dataset for this chart; integrity panel displayed instead')
    blocks['visuals']['image_inspection']=observation(inspection,'Decoded PNG dimensions, palette, and plotted-data checks',now,now)
    blocks['visuals']['dark_theme']=observation({'background':'#0B1220','panels':'#111827','text':'#E5E7EB','renderer':'Matplotlib PNG; no Mermaid or generated imagery'},'Chart renderer configuration',now,now)
    payload['chart_urls']=image_refs
    # Verify persisted bytes, not just the pre-upload image or a syntactically valid URL.
    assets,failures=stored_chart_assets(image_refs)
    if failures:raise ValueError('Persisted chart verification failed: '+str(failures))
    blocks['visuals']['delivery_manifest']=observation(
        {'version':DELIVERY_VERSION,'transport':'self-contained HTML, verified PNG assets, PDF and ZIP',
         'images':[{k:v for k,v in asset.items() if k!='png_base64'} for asset in assets]},
        'Persistent report chart byte/checksum round-trip',now,now)
    prepare_report_delivery(payload)
    payload['report_validation']=validate_rendered_report(payload)
    if not payload['report_validation']['publishable']:
        raise ValueError('Final report renderer rejected: '+str(payload['report_validation']['errors']))
    payload['report_completeness']='COMPLETE' if payload['report_validation']['complete_live_data'] else 'INCOMPLETE'
    report_id=hashlib.sha256(encoded({'time':now.isoformat(),'kind':kind,'blocks':blocks}).encode()).hexdigest()[:24]
    payload.update(report_id=report_id,report_url=f'{PUBLIC_BASE}/{report_id}/view',markdown_url=f'{PUBLIC_BASE}/{report_id}.md',
                   chart_assets_url=f'{PUBLIC_BASE}/{report_id}/assets',
                   chart_pdf_url=f'{PUBLIC_BASE}/{report_id}/charts.pdf',
                   portable_report_url=f'{PUBLIC_BASE}/{report_id}/portable.zip')
    with engine.begin() as c:
        c.execute(text('INSERT INTO sw_full_reports (report_id,generated_at,kind,payload_json) VALUES (:id,:now,:kind,:payload) ON CONFLICT(report_id) DO NOTHING'),
                  {'id':report_id,'now':now.replace(tzinfo=None),'kind':kind,'payload':encoded(payload)})
    return payload

@router.get('/history')
def report_history(limit: int = Query(24, ge=1, le=100),
                   offset: int = Query(0, ge=0),
                   kind: str | None = Query(None, pattern='^(morning|market_open|intraday)$'),
                   trading_date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$')):
    """Read the durable published archive without collecting data or sending alerts."""
    from .report_archive import load_archive
    return JSONResponse(load_archive(engine, limit, offset, kind, trading_date),
                        headers={'Cache-Control': 'no-store'})

@router.get('/latest')
def latest_report():
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT payload_json FROM sw_full_reports ORDER BY generated_at DESC LIMIT 1')).fetchone()
    if not row:return {'available':False,'reason':'No full report generated yet'}
    payload=json.loads(row[0])
    from .report_policy import parse_clock
    clock=parse_clock(payload.get('generated_at'))
    payload['retrieved_at']=datetime.now(UTC).isoformat()
    payload['report_age_seconds']=(datetime.now(UTC)-clock).total_seconds() if clock else None
    payload['snapshot_notice']='Immutable stored report. Re-reading it does not refresh any observation; source clocks must be rechecked.'
    return payload

@router.get('/producer-status')
def producer_status():
    now=datetime.now(UTC)
    names=('breadth','macro','profile_SPY','profile_QQQ','study')
    result={name:load_evidence(name) for name in names}
    return {'retrieved_at':now.isoformat(),'implemented_collectors':list(names),'evidence':result,
            'paper':scorecard(),'delivery_validation':'Shared final rendered-report validator with embedded PNG checks'}

@router.get('/charts/{chart_id}.png')
def get_chart(chart_id:str):
    if not re.fullmatch(r'[a-f0-9]{32}',chart_id):raise HTTPException(404)
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT png_base64 FROM sw_report_charts WHERE chart_id=:id'),{'id':chart_id}).fetchone()
    if not row:raise HTTPException(404)
    png=base64.b64decode(row[0],validate=True);inspect_png(png,chart_id)
    return Response(png,media_type='image/png',headers={'Cache-Control':'public, max-age=31536000, immutable','X-Content-Type-Options':'nosniff'})

def stored_chart_assets(refs):
    """One DB read; all report kinds and old reports get the same durable delivery."""
    ids={name:chart_id_from_ref(ref) for name,ref in refs.items()}
    if not ids:return [],{'images':'Report contains no chart references'}
    with engine.begin() as c:
        from sqlalchemy import bindparam
        query=text('SELECT chart_id,png_base64 FROM sw_report_charts WHERE chart_id IN :ids').bindparams(bindparam('ids',expanding=True))
        rows=dict(c.execute(query,{'ids':list(ids.values())}).all())
    assets=[];failures={}
    for name,chart_id in ids.items():
        try:
            if not re.fullmatch(r'[a-z][a-z0-9_]*',name):raise ValueError('Invalid chart name')
            data=base64.b64decode(rows[chart_id],validate=True)
            assets.append(dict(name=name,chart_id=chart_id,filename=name+'.png',png_base64=rows[chart_id],**inspect_png(data,chart_id)))
        except (KeyError,ValueError,OSError) as exc:
            failures[name]='Persisted image missing or corrupt: '+type(exc).__name__
    return assets,failures

def stored_report(report_id):
    if not re.fullmatch(r'[a-f0-9]{24}',report_id):raise HTTPException(404)
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT payload_json FROM sw_full_reports WHERE report_id=:id'),{'id':report_id}).fetchone()
    if not row:raise HTTPException(404)
    return json.loads(row[0])

@router.get('/{report_id}.md')
def get_markdown(report_id:str):return Response(stored_report(report_id)['report_markdown'],media_type='text/markdown')

@router.get('/{report_id}/data')
def report_data(report_id: str):
    """Immutable original evidence for the web reader; retrieval never refreshes it."""
    return JSONResponse(stored_report(report_id), headers={'Cache-Control': 'no-store'})

@router.get('/{report_id}/assets')
def get_assets(report_id:str):
    payload=stored_report(report_id);assets,failures=stored_chart_assets(payload.get('chart_urls') or {})
    inspection=(payload.get('report_blocks',{}).get('visuals',{}).get('image_inspection',{}).get('value') or [])
    plotted={row['panel']:row.get('observed_data_plotted',False) for row in inspection}
    for asset in assets:
        field=payload.get('report_blocks',{}).get('visuals',{}).get(asset['name']+'_png',{})
        asset.update(source_timestamp=field.get('source_timestamp'),data_status=field.get('status','unavailable'),
                     has_observed_data=plotted.get(asset['name'],False))
    return {'report_id':report_id,'generated_at':payload['generated_at'],'delivery_version':DELIVERY_VERSION,
            'complete':not failures,'failures':failures,'images':assets}

@router.get('/{report_id}/charts.pdf')
def get_chart_pdf(report_id:str):
    assets=get_assets(report_id)
    if not assets['complete']:raise HTTPException(503,detail=assets['failures'])
    return Response(portable_pdf(assets['images']),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="options-report-{report_id}-charts.pdf"'})

@router.get('/{report_id}/portable.zip')
def get_portable_report(report_id:str):
    payload=stored_report(report_id);assets=get_assets(report_id)
    if not assets['complete']:raise HTTPException(503,detail=assets['failures'])
    return Response(portable_zip(payload,assets['images'],report_view(report_id)),media_type='application/zip',
                    headers={'Content-Disposition':f'attachment; filename="options-report-{report_id}.zip"'})

_SYM_KEY_RE=re.compile(r'^[A-Z]{1,5}$')

def _fmt_primitive(v):
    if isinstance(v,bool):return '<span class="bool-'+('yes' if v else 'no')+'">'+('yes' if v else 'no')+'</span>'
    if isinstance(v,float):return html.escape(f'{v:.4g}' if abs(v)<1e6 else str(v))
    return html.escape(str(v))

def _fmt_value(v,depth=0):
    """Render a field's raw value for a human: per-symbol lines, small key/value blocks for
    structured data, and a contained scrollable JSON block only as a last resort for shapes
    too irregular to summarize — never a bare, unformatted json.dumps() wall of text."""
    if v is None:return '<span class="muted">&mdash;</span>'
    if isinstance(v,dict):
        if v and all(isinstance(k,str) and _SYM_KEY_RE.match(k) for k in v):
            return ' <span class="sep">&middot;</span> '.join(
                f'<b>{html.escape(sym)}</b>: {_fmt_value(sv,depth+1)}' for sym,sv in v.items())
        if v and len(v)<=10 and depth<3:
            rows=''.join(f'<div class="kv"><span class="k">{html.escape(str(k).replace("_"," "))}</span>'
                         f'<span class="v">{_fmt_value(vv,depth+1)}</span></div>' for k,vv in v.items())
            return f'<div class="kvblock">{rows}</div>'
        return f'<pre class="raw">{html.escape(json.dumps(v,indent=2,ensure_ascii=False))}</pre>'
    if isinstance(v,list):
        if not v:return '<span class="muted">none</span>'
        if len(v)<=12 and all(not isinstance(x,(dict,list)) for x in v):
            return ', '.join(_fmt_value(x,depth+1) for x in v)
        if len(v)<=8 and depth<2 and all(isinstance(x,dict) and len(x)<=6 for x in v):
            return ''.join(f'<div class="kvblock listitem">{_fmt_value(x,depth+1)}</div>' for x in v)
        return f'<pre class="raw">{html.escape(json.dumps(v,indent=2,ensure_ascii=False))}</pre>'
    return _fmt_primitive(v)

_STATUS_PILL={'live':('live','LIVE'),'historical':('hist','LAST KNOWN'),'unavailable':('unavail','UNAVAILABLE')}

# Display order only — never changes REQUIREMENTS/the data contract. A day/swing options
# trader reads this top to bottom for "what's the regime, who's in control, what's the
# trade" first; supporting evidence and bookkeeping sections follow. Any block not listed
# here (e.g. a future contract addition) still renders, just after everything listed.
_SECTION_DISPLAY_ORDER=[
    'risk_on_defensive','market_control','gamma','flow','premium_selling',
    'day_strategy','near_forward_strategy','forward_strategy','contract_packages','entry_watches',
    'expected_move','smile','surface','forward_strikes',
    'range_stall','breadth','profile','sector_credit','macro','futures_context','event_calendar','candidate_analysis',
    'position_management','trigger_accountability','paper_scorecard','scanner','event_study','engine_consensus',
    'morning_comparison','horizon_comparison','adaptation_rules',
    'visuals','data_integrity',
]
def _ordered_blocks(report_blocks):
    rank={name:i for i,name in enumerate(_SECTION_DISPLAY_ORDER)}
    return sorted(report_blocks.items(),key=lambda kv:rank.get(kv[0],len(_SECTION_DISPLAY_ORDER)))

def _field_row(field,item):
    status=item.get('status','unavailable')
    value=item.get('value')
    pill_cls,pill_label=_STATUS_PILL.get(status,('unavail',status.upper()))
    content=_fmt_value(value) if value is not None else f'<span class="muted">{html.escape(item.get("reason") or "No verified observation")}</span>'
    meta=[]
    if item.get('source'):meta.append(html.escape(str(item['source'])))
    if item.get('source_timestamp'):meta.append(html.escape(str(item['source_timestamp'])))
    age=item.get('age_seconds')
    if isinstance(age,(int,float)):meta.append(f'age {age:.0f}s' if age<120 else f'age {age/60:.1f}m')
    meta_html=f'<div class="meta">{" &middot; ".join(meta)}</div>' if meta else ''
    reason_html=f'<div class="reason">{html.escape(item["reason"])}</div>' if status=='unavailable' and item.get('reason') and value is not None else ''
    return (f'<div class="field"><div class="fieldtop"><span class="fieldname">{html.escape(field.replace("_"," "))}</span>'
            f'<span class="pill {pill_cls}">{pill_label}</span></div>'
            f'<div class="fieldval">{content}</div>{meta_html}{reason_html}</div>')

@router.get('/{report_id}/view',response_class=HTMLResponse)
def report_view(report_id:str):
    payload=stored_report(report_id);parts=[];nav=[]
    images=payload.get('chart_urls') or {}
    assets,failures=stored_chart_assets(images)
    inline={asset['name']:'data:image/png;base64,'+asset['png_base64'] for asset in assets}
    groups={'expected_move':'market_map','smile':'smile_term','flow':'flow','gamma':'gamma_expiry',
            'surface':'surface',
            'sector_credit':'sector_credit','event_calendar':'event_risk','paper_scorecard':'paper_equity_drawdown',
            'morning_comparison':'baseline_comparison','profile':'volume_profile'}
    for name,block in _ordered_blocks(payload['report_blocks']):
        anchor='sec-'+name.replace('_','-')
        title=name.replace('_',' ').title()
        nav.append(f'<a href="#{anchor}">{html.escape(title)}</a>')
        fields_html=''.join(_field_row(field,item) for field,item in block.items())
        chart_names=[groups.get(name)]
        if name=='surface':chart_names+=['term_structure']
        image=''.join(f'<img src="{inline[n]}" alt="{html.escape(n)} chart" decoding="async">' if n in inline
                      else f'<p role="alert">VISUAL DELIVERY FAILED: {html.escape(n or "chart")}. {html.escape(failures.get(n,""))}</p>'
                      for n in chart_names if n in images)
        parts.append(f'<section class="card" id="{anchor}"><h2>{html.escape(title)}</h2>'
                     f'{"<div class=\'chart\'>"+image+"</div>" if image else ""}'
                     f'<div class="fields">{fields_html}</div></section>')
    from .report_policy import display
    bottom=('<section class="card bottomline"><h2>Bottom line</h2>'
           +''.join('<p>'+html.escape(line)+'</p>' for line in [
               'Regime: '+display(payload['report_blocks']['risk_on_defensive']['verdict']),
               'Opportunity / premium: '+display(payload['report_blocks']['premium_selling']['suitability']),
               'Next test: recorded entry confirmation plus fresh per-leg BBO; dated context alone cannot activate a trade.'])
           +'</section>')
    downloads=(f'<a href="{PUBLIC_BASE}/{report_id}/charts.pdf">Chart PDF</a>'
              f'<a href="{PUBLIC_BASE}/{report_id}/portable.zip">Offline ZIP</a>'
              f'<a href="{payload["markdown_url"]}">Markdown</a>')
    style='''
:root{--bg:#0b0e13;--surface:#141a23;--surface2:#1b2330;--border:#2a3341;--fg:#e8ecf1;--muted:#8b97a8;
--accent:#35d0ba;--call:#34d399;--put:#f87171;--warn:#fbbf24}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
margin:0;padding:0}
.wrap{max-width:900px;margin:0 auto;padding:16px}
header.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--border);
padding:14px 16px;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline}
header.top h1{font-size:1.05rem;margin:0}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}
.chip{font-size:.7rem;border:1px solid var(--border);border-radius:999px;padding:3px 10px;color:var(--muted);white-space:nowrap}
.chip.warn{color:var(--warn);border-color:var(--warn)}
.downloads{display:flex;gap:10px;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--border)}
.downloads a{color:var(--accent);text-decoration:none;font-size:.82rem;border:1px solid var(--border);border-radius:6px;padding:4px 10px}
nav.jump{display:flex;flex-wrap:wrap;gap:6px 10px;padding:14px 0;margin-bottom:8px;border-bottom:1px solid var(--border)}
nav.jump a{color:var(--muted);text-decoration:none;font-size:.78rem;border:1px solid var(--border);border-radius:5px;padding:3px 8px}
nav.jump a:hover{color:var(--accent);border-color:var(--accent)}
h1,h2{font-weight:700}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin:14px 0}
.card h2{font-size:1.02rem;margin:0 0 12px}
.chart{margin-bottom:14px}
.chart img{max-width:100%;border-radius:6px;display:block;background:#0b0e13}
.chart p[role=alert]{color:var(--warn);font-size:.85rem}
.fields{display:flex;flex-direction:column}
.field{padding:10px 0;border-top:1px solid var(--border)}
.field:first-child{border-top:none;padding-top:0}
.fieldtop{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px}
.fieldname{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.fieldval{font-size:.92rem;overflow-wrap:anywhere}
.pill{font-size:.65rem;border-radius:5px;padding:2px 7px;letter-spacing:.03em;white-space:nowrap;flex-shrink:0}
.pill.unavail{background:rgba(139,151,168,.18);color:var(--muted);border:1px solid var(--border)}
.pill.hist{background:rgba(251,191,36,.16);color:var(--warn);border:1px solid rgba(251,191,36,.45)}
.pill.live{background:rgba(52,211,153,.16);color:var(--call);border:1px solid rgba(52,211,153,.45)}
.meta{color:var(--muted);font-size:.74rem;margin-top:4px;overflow-wrap:anywhere}
.reason{color:var(--muted);font-size:.82rem;margin-top:4px}
.muted{color:var(--muted)}
.sep{color:var(--muted)}
.kvblock{background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-top:4px}
.kvblock.listitem{margin-bottom:6px}
.kv{display:flex;justify-content:space-between;gap:10px;padding:3px 0;font-size:.85rem}
.kv .k{color:var(--muted)}
pre.raw{background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px;
overflow-x:auto;font-size:.78rem;color:var(--fg);white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%}
.bool-yes{color:var(--call)}
.bool-no{color:var(--put)}
table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}
th,td{padding:10px 8px;border-bottom:1px solid var(--border);text-align:left;overflow-wrap:anywhere;vertical-align:top;font-size:.85rem}
th{width:34%;color:var(--muted);font-weight:600}
tr:last-child td,tr:last-child th{border-bottom:none}
p{color:var(--muted)}
a{color:var(--accent)}
.bottomline p{color:var(--fg);font-size:.92rem;margin:6px 0}
@media (max-width:600px){.wrap{padding:12px}}
'''
    head=(f'<!doctype html><html><head><meta charset="utf-8">'
          f'<meta name="viewport" content="width=device-width,initial-scale=1">'
          f'<title>{html.escape(payload["kind"].title())} Options Report</title><style>{style}</style></head><body>')
    header=(f'<header class="top"><h1>{html.escape(payload["kind"].title())} Options Report</h1>'
           f'<div class="chips"><span class="chip">{html.escape(payload["generated_at"])}</span>'
           f'<span class="chip {"warn" if payload["report_completeness"]=="INCOMPLETE" else ""}">{html.escape(payload["report_completeness"])}</span>'
           f'<span class="chip">immutable snapshot</span></div></header>'
           f'<div class="downloads">{downloads}</div>')
    body=(f'<div class="wrap"><nav class="jump">{"".join(nav)}</nav>'
         f'{render_opening_html(payload)}{"".join(parts)}{bottom}</div>')
    return head+header+body+'</body></html>'

def claim_delivery(kind,now):
    """Atomic per-checkpoint lease. Successful sends are never normally resent."""
    ensure_tables()
    slot=kind+':'+now.astimezone(CT).strftime('%Y-%m-%dT%H')
    stamp=now.replace(tzinfo=None)
    with engine.begin() as c:
        c.execute(text("INSERT INTO sw_report_deliveries (slot,status) VALUES (:slot,'PENDING') ON CONFLICT(slot) DO NOTHING"),{'slot':slot})
        claimed=c.execute(text("UPDATE sw_report_deliveries SET status='SENDING',lease_until=:lease,attempts=attempts+1,error=NULL WHERE slot=:slot AND status!='POSTED' AND (lease_until IS NULL OR lease_until<:now)"),
            {'slot':slot,'lease':stamp+timedelta(minutes=4),'now':stamp}).rowcount
    return slot if claimed else None

def finish_delivery(slot,report_id,posted,error=None):
    with engine.begin() as c:
        c.execute(text('UPDATE sw_report_deliveries SET status=:status,lease_until=NULL,report_id=:report,posted_at=:posted,error=:error WHERE slot=:slot'),
            {'status':'POSTED' if posted else 'FAILED','report':report_id,'posted':datetime.now(UTC).replace(tzinfo=None) if posted else None,'error':error,'slot':slot})

async def scheduled_intraday(app,kind='intraday'):
    now=datetime.now(UTC)
    from .economic_events import is_market_holiday
    if now.astimezone(CT).weekday()>=5 or is_market_holiday(now.astimezone(CT).date()):return
    slot=await asyncio.to_thread(claim_delivery,kind,now)
    if not slot:return {'delivery':'already posted or leased'}
    try:
        report=await assemble_report(app,kind=kind)
    except Exception as exc:
        await asyncio.to_thread(finish_delivery,slot,None,False,'Assembly failed: '+type(exc).__name__)
        logger.exception('[FullReport] checkpoint assembly failed')
        return {'delivery':'failed','reason':type(exc).__name__}
    # Existing approved advisory channel; delivery remains on. No brokerage calls.
    from . import _send_intraday_webhook_sync
    embed={'title':'Intraday Options Report','description':f'[{report["report_completeness"]} — Open the full dark report]({report["report_url"]})',
           'color':0x22D3EE,'timestamp':report['generated_at'],'image':{'url':report['chart_urls']['market_map']},
           'fields':[{'name':'Data integrity','value':f'{len(report["report_validation"]["unavailable_fields"])} fields historical/unavailable; all sections included.'}]}
    posted=False;error=None
    try:
        check=prepare_report_delivery(report)
        if not check['publishable']:raise ValueError('Final publication gate rejected delivery')
        posted=await asyncio.to_thread(_send_intraday_webhook_sync,embed)
        if not posted:error='Notification transport returned failure'
    except Exception as exc:
        error=type(exc).__name__;logger.exception('[FullReport] notification delivery failed')
    try:
        from .report_email import send_report_email_sync
        await asyncio.to_thread(send_report_email_sync,report,kind)
    except Exception:
        logger.exception('[FullReport] email delivery failed; Discord lease unaffected')
    await asyncio.to_thread(finish_delivery,slot,report['report_id'],bool(posted),error)
    save_evidence('intraday_delivery',{'posted':bool(posted),'report_id':report['report_id']},datetime.now(UTC))
    return report

def register(scheduler,app):
    ensure_tables()
    from .report_ledger import ensure_tables as ensure_paper
    ensure_paper()
    scheduler.add_job(study_bootstrap,'date',run_date=datetime.now(UTC)+timedelta(seconds=20),id='report_study_bootstrap',replace_existing=True,misfire_grace_time=300)
    async def bootstrap():
        await capture_context(app,force=True)
        await assemble_report(app,kind='verification')
    scheduler.add_job(bootstrap,'date',run_date=datetime.now(UTC)+timedelta(seconds=15),id='full_report_verification',replace_existing=True,misfire_grace_time=300)
    scheduler.add_job(lambda:mark_open_positions(), 'interval',seconds=60,id='report_paper_marks',replace_existing=True,max_instances=1,coalesce=True)
    async def context_tick():await capture_context(app)
    async def hourly():await scheduled_intraday(app)
    async def study():await capture_study()
    scheduler.add_job(candidate_surface_tick,'cron',hour='8-15',minute='*',second=35,day_of_week='mon-fri',id='report_candidate_surfaces',replace_existing=True,max_instances=1,coalesce=True)
    async def opening():await scheduled_intraday(app,kind='market_open')
    scheduler.add_job(context_tick,'cron',hour='7-15',minute='1,6,11,16,21,26,31,36,41,46,51,56',day_of_week='mon-fri',id='full_report_context',replace_existing=True,max_instances=1,coalesce=True)
    scheduler.add_job(hourly,'cron',hour='9-15',minute=0,day_of_week='mon-fri',id='full_intraday_report',replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=300)
    scheduler.add_job(hourly,'cron',hour='9-15',minute='5,10',day_of_week='mon-fri',id='full_intraday_report_recovery',replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=300)
    scheduler.add_job(opening,'cron',hour=8,minute=30,day_of_week='mon-fri',id='full_open_report',replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=300)
    scheduler.add_job(opening,'cron',hour=8,minute='35,40',day_of_week='mon-fri',id='full_open_report_recovery',replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=300)
    scheduler.add_job(study,'cron',hour=17,minute=15,day_of_week='mon-fri',id='report_historical_study',replace_existing=True,max_instances=1,coalesce=True)

async def study_bootstrap():
    prior=await asyncio.to_thread(load_evidence,'study')
    captured=ms._parse_ts(prior.get('captured_at'))
    if not captured or (datetime.now(UTC)-captured).total_seconds()>86400:
        await capture_study()

async def candidate_surface_tick():
    now=datetime.now(UTC);et=now.astimezone(ET)
    if et.weekday()>=5 or not time(9,30)<=et.time().replace(tzinfo=None)<time(16):return
    from .morning_options_report import _latest_plan_payload,FALLBACK_UNIVERSE
    plan=await asyncio.to_thread(_latest_plan_payload,et.date()) or {}
    symbols=plan.get('symbols') or list(FALLBACK_UNIVERSE)
    if not symbols:return
    symbol=symbols[int(now.timestamp()//60)%len(symbols)]
    row=await asyncio.to_thread(ms.build_volatility_surface,symbol,now,background=True)
    prior=await asyncio.to_thread(load_evidence,'candidate_surfaces')
    values=prior.get('symbols') or {}
    if row.get('confidence') in ('HIGH','MEDIUM') or symbol not in values:values[symbol]=row
    else:values[symbol]['last_attempt']=row
    await asyncio.to_thread(save_evidence,'candidate_surfaces',{'symbols':values,'roster':symbols},datetime.now(UTC))
