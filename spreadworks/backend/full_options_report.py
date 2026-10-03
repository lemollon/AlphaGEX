"""Shared report assembly, persistent evidence, real charts and delivery artifacts.

Collectors are isolated from the minute Theta IV pipeline. Read endpoints never
trigger trades or send notifications. Every field is mapped to observed evidence.
"""
from __future__ import annotations
import asyncio, base64, hashlib, html, json, logging, re
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import text
from .db import engine, SessionLocal
from . import market_structure as ms
from .report_contract import REQUIREMENTS, prepare_report_delivery, validate_rendered_report
from .report_producers import observation, unavailable, number, collect_breadth, collect_profile, collect_macro, collect_study, stored_futures, UTC, ET
from .report_ledger import scorecard, qualify_package, mark_open_positions
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
    result={'surface':{},'gamma':{},'flow':{},'volatility':ms._cached_vol_payload(now),
            'cross_asset':ms.fetch_cross_asset(now),'futures':stored_futures(now)}
    for symbol in ('SPY','QQQ'):
        for group,loader in (('surface',ms._latest_surface),('gamma',ms._latest_gamma),('flow',ms._latest_trade_quote_flow)):
            latest=loader(symbol) or {}
            row=latest
            if row.get('confidence') not in ('HIGH','MEDIUM'):
                last_good=loader(symbol,verified_only=True)
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
    values={};stamps=[];sources=[]
    for symbol,row in rows.items():
        value={key:row.get(key) for key in keys}
        ts=ms._parse_ts(row.get('source_timestamp'))
        if row.get('confidence')=='LOW' or not ts or all(v is None for v in value.values()):continue
        values[symbol]=value;stamps.append(ts);sources.append(row.get('source') or 'Stored observation')
    return observation(values if values else None,'; '.join(sorted(set(sources))),min(stamps) if stamps else None,now)

def market_comparison(core,baseline):
    result={}
    for symbol,row in core['surface'].items():
        old=((baseline.get('evidence') or {}).get('surface') or {}).get(symbol) or {}
        spot,ref=number(row.get('spot')),number(old.get('spot'))
        result[symbol]={'price_change_pct':(spot/ref-1)*100 if spot and ref else None,
             'morning_timestamp':baseline.get('generated_at'),'morning_spot':ref,'current_spot':spot,
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
    blocks['surface']['iv_vs_realized']=merge_symbols(surface,['atm_iv','realized_vol_60m','iv_minus_realized_vol','realized_vol_source_timestamp'],now)
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
            base=r.get('morning_spot');current=r.get('current_spot');em=number(surface[s].get('expected_move_dollars_1d'))
            if base and current and em:vals[s]={'absolute_move_fraction':abs(current-base)/em,'signed_change':current-base,'reference':'Morning baseline; current IV estimate denominator'}
        put('expected_move',field,vals or None,source='Recorded morning baseline vs current underlying',ts=min([ms._parse_ts(r.get('source_timestamp')) for r in surface.values() if ms._parse_ts(r.get('source_timestamp'))],default=None),reason='No comparable morning baseline')
    for field,key in {'net_gex':'net_gex_b','flip':'gamma_flip','walls':'walls','expiry_buckets':'buckets','coverage':'n_rows'}.items():blocks['gamma'][field]=merge_symbols(gamma,[key],now)
    put('gamma','scope_comparability','Bounded near-spot <=60DTE estimated dealer gamma; compare only matching coverage. OI is daily, not intraminute.')
    for field in ('theta_provenance','exchange_timestamp','retrieval_timestamp','age','classified_coverage','unclassified_coverage',
                  'calls_bought','calls_sold','puts_bought','puts_sold','expiry_buckets'):
        vals={};stamps=[]
        for s,r in flow.items():
            ev=r.get('evidence') or {};ts=ms._parse_ts(r.get('source_timestamp'))
            if r.get('confidence')=='LOW' or not ts or not ev.get('buckets'):continue
            stamps.append(ts)
            if field in ('calls_bought','calls_sold','puts_bought','puts_sold'):vals[s]={b:v.get(field) for b,v in ev['buckets'].items()}
            else:vals[s]={'theta_provenance':ev.get('source'),'exchange_timestamp':ts.isoformat(),'retrieval_timestamp':ev.get('retrieval_timestamp'),
               'age':(now-ts).total_seconds(),'classified_coverage':ev.get('classified_contract_fraction'),
               'unclassified_coverage':{'contracts':ev.get('unclassified_contracts'),'premium':ev.get('unclassified_premium')},'expiry_buckets':ev['buckets']}.get(field)
        blocks['flow'][field]=observation(vals or None,'ThetaData trades + contemporaneous quotes; representative expiries / 120s window',min(stamps) if stamps else None,now)
    for field,key in {'expiries':'expiration','strikes':'strike','contracts':'contracts','premium':'premium','prints':'print_count',
                      'contemporaneous_bid_ask':'latest_print','initiation_estimate':'initiation'}.items():
        vals={s:[{key:r.get(key)} for r in (row.get('evidence') or {}).get('concentrations') or []] for s,row in flow.items()}
        vals={s:v for s,v in vals.items() if v}
        ts=min([ms._parse_ts(row.get('source_timestamp')) for row in flow.values() if ms._parse_ts(row.get('source_timestamp'))],default=None)
        put('forward_strikes',field,vals or None,source='ThetaData observed strike concentrations',ts=ts,reason='No verified forward prints')
    assets=cross.get('assets') or {}
    relative={s:(r['price']/r['prev_close']-1)*100 for s,r in assets.items() if number(r.get('price')) and number(r.get('prev_close'))}
    cross_ts=min([ms._parse_ts(r.get('source_timestamp')) for r in assets.values() if ms._parse_ts(r.get('source_timestamp'))],default=None)
    put('sector_credit','relative_returns',relative or None,source='Consolidated ETF quotes vs prior close',ts=cross_ts)
    put('sector_credit','leadership',sorted(relative,key=relative.get,reverse=True) if relative else None,source='Relative-return ordering',ts=cross_ts)
    put('sector_credit','credit_confirmation',{s:relative[s] for s in ('HYG','LQD','TLT') if s in relative} or None,source='Credit/bond ETF proxies; not credit spreads',ts=cross_ts)
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
    for field in REQUIREMENTS['paper_scorecard']:put('paper_scorecard',field,paper.get(field),source='Forward report-alert simulation ledger query')
    for field in REQUIREMENTS['trigger_accountability']:
        value={'registered_triggers':setup_list,'verified_occurrence':paper['entry_ready_alerts'],
               'confirmation_sequence':paper.get('trigger_events') or [],
               'mfe_mae':[{'event_key':t['event_key'],'mfe':t.get('mfe'),'mae':t.get('mae'),'scope':'Observed liquidation BBO marks, not tick-perfect extrema'} for t in paper['trade_details']],
               'outcome':{'trigger_events':paper.get('trigger_events') or [],'paper_trades':paper['trade_details']},'loss_clusters':paper.get('loss_clusters')}.get(field)
        put('trigger_accountability',field,value,source='Registered rules and observed paper ledger')
    for field in REQUIREMENTS['event_study']:
        value=study.get(field)
        if field=='validated_statistics':value={k:study.get(k) for k in ('validated_statistics','stall_fraction','wilson_95_interval','minimum_sample','loss_clusters','reason','failures')}
        put('event_study',field,value,source='Frozen historical ThetaData 1-minute event study',ts=study.get('captured_at'),reason=study.get('reason'))
    for field in REQUIREMENTS['morning_comparison']:
        put('morning_comparison',field,comparison if comparison and any(r.get('morning_timestamp') for r in comparison.values()) else None,
            source='Persisted morning and prior-hour report baselines',ts=now,reason='First report: no earlier comparable baseline')
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
        value={'risk':blocks['risk_on_defensive']['verdict'],'session':now.astimezone(ET).isoformat(),'squeeze':plan.get('market_regime'),
             'hunt':plan.get('best_setup'),'trading_volatility_status':plan.get('trading_volatility'),
             'contradictions':'Compare engine evidence and timestamps; absent engine state is not consensus'}.get(field)
        put('engine_consensus',field,value,source='Recorded independent engine states',ts=plan.get('generated_at'))
    return blocks

def previous_reports(now):
    ensure_tables();start=datetime.combine(now.astimezone(CT).date(),time(0),CT).astimezone(UTC).replace(tzinfo=None)
    with engine.begin() as c:
        rows=c.execute(text('SELECT kind,payload_json FROM sw_full_reports WHERE generated_at>=:start ORDER BY generated_at'),{'start':start}).fetchall()
    morning=next((json.loads(raw) for kind,raw in rows if kind=='morning'),{})
    prior=json.loads(rows[-1][1]) if rows else {}
    return morning,prior

async def assemble_report(app,*,kind='intraday',plan=None,now=None):
    started=now or datetime.now(UTC)
    core=await asyncio.to_thread(cached_core,started)
    context={name:await asyncio.to_thread(load_evidence,name) for name in ('breadth','macro','profile_SPY','profile_QQQ','study','candidate_surfaces')}
    stored_plan,runtime=await asyncio.to_thread(_plan_and_runtime,started)
    plan=plan if plan is not None else stored_plan
    paper=await asyncio.to_thread(scorecard)
    morning,prior=await asyncio.to_thread(previous_reports,started)
    days,events=await asyncio.to_thread(scheduled_events,started)
    now=datetime.now(UTC)
    comparison=market_comparison(core,morning)
    blocks=report_blocks(core,context,plan,runtime,paper,context['study'],comparison,events,now)
    prior_stamp=prior.get('generated_at')
    if prior_stamp:
        blocks['morning_comparison']['prior_hour_timestamp']=observation(prior_stamp,'Previous stored report',now,now)
    blocks['event_calendar']['next_five_trading_days']=observation([d.isoformat() for d in days],'Trading-calendar dates, excludes known holidays',now,now)
    evidence=dict(core,profiles={s:context['profile_'+s] for s in ('SPY','QQQ')},paper=paper,comparison=comparison,events=events)
    headline=blocks['risk_on_defensive']['verdict'].get('value') or 'Directional verdict pending verified fresh evidence'
    payload={'generated_at':now.isoformat(),'kind':kind,'advisory_only':True,'report_blocks':blocks,'evidence':evidence,
             'report_markdown':f'# {kind.title()} Options Report\n\n**{headline}**\n\nSource clocks and historical labels are preserved. Conditional watches are advisory; paper fills are simulated.',
             'producer_status':{name:context[name].get('reason') or context[name].get('captured_at') or 'No capture yet' for name in context},
             'collector_coverage':{'breadth':'SPY constituents; VWAP candidate sample','profile':'Cumulative observed RTH tape, checkpointed in bounded windows; coverage timestamps disclosed','flow':'Representative expirations / 120-second window','futures':'Broker MES/MNQ observations where recorded; delayed continuous ES/NQ fallback'}}
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
    prepare_report_delivery(payload)
    # Real image embeds are present in the delivered artifact, not only filenames in metadata.
    payload['report_markdown']+='\n\n## Data charts\n\n'+'\n\n'.join(f'![{name.replace("_"," ").title()}]({ref})' for name,ref in image_refs.items())
    payload['report_original_markdown']=payload['report_markdown'].split('## Supplemental analysis',1)[-1]
    payload['report_validation']=validate_rendered_report(payload)
    if not payload['report_validation']['publishable']:
        raise ValueError('Final report renderer rejected: '+str(payload['report_validation']['errors']))
    payload['report_completeness']='COMPLETE' if payload['report_validation']['complete_live_data'] else 'INCOMPLETE'
    report_id=hashlib.sha256(encoded({'time':now.isoformat(),'kind':kind,'blocks':blocks}).encode()).hexdigest()[:24]
    payload.update(report_id=report_id,report_url=f'{PUBLIC_BASE}/{report_id}/view',markdown_url=f'{PUBLIC_BASE}/{report_id}.md')
    with engine.begin() as c:
        c.execute(text('INSERT INTO sw_full_reports (report_id,generated_at,kind,payload_json) VALUES (:id,:now,:kind,:payload) ON CONFLICT(report_id) DO NOTHING'),
                  {'id':report_id,'now':now.replace(tzinfo=None),'kind':kind,'payload':encoded(payload)})
    return payload

@router.get('/latest')
def latest_report():
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT payload_json FROM sw_full_reports ORDER BY generated_at DESC LIMIT 1')).fetchone()
    return json.loads(row[0]) if row else {'available':False,'reason':'No full report generated yet'}

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
    return Response(base64.b64decode(row[0]),media_type='image/png',headers={'Cache-Control':'public, max-age=31536000, immutable'})

def stored_report(report_id):
    if not re.fullmatch(r'[a-f0-9]{24}',report_id):raise HTTPException(404)
    ensure_tables()
    with engine.begin() as c:
        row=c.execute(text('SELECT payload_json FROM sw_full_reports WHERE report_id=:id'),{'id':report_id}).fetchone()
    if not row:raise HTTPException(404)
    return json.loads(row[0])

@router.get('/{report_id}.md')
def get_markdown(report_id:str):return Response(stored_report(report_id)['report_markdown'],media_type='text/markdown')

@router.get('/{report_id}/view',response_class=HTMLResponse)
def report_view(report_id:str):
    payload=stored_report(report_id);parts=[]
    images=payload.get('chart_urls') or {}
    groups={'expected_move':'market_map','smile':'smile_term','flow':'flow','gamma':'gamma_expiry',
            'surface':'surface',
            'sector_credit':'sector_credit','event_calendar':'event_risk','paper_scorecard':'paper_equity_drawdown',
            'morning_comparison':'baseline_comparison','profile':'volume_profile'}
    for name,block in payload['report_blocks'].items():
        rows=[]
        for field,item in block.items():
            val=item.get('value')
            content=json.dumps(val,indent=2,ensure_ascii=False) if isinstance(val,(dict,list)) else str(val) if val is not None else item.get('reason') or 'Unavailable'
            clock=item.get('source_timestamp') or ''
            rows.append(f'<details><summary>{html.escape(field.replace("_"," "))} <small>{html.escape(item["status"].upper())}</small></summary><pre>{html.escape(content)}</pre><p>{html.escape(str(item.get("source") or ""))} {html.escape(clock)} | age {item.get("age_seconds","n/a")}s</p></details>')
        img=images.get(groups.get(name,''));image=f'<img src="{html.escape(img,quote=True)}" alt="{html.escape(name)} chart">' if img else ''
        parts.append(f'<section><h2>{html.escape(name.replace("_"," ").title())}</h2>{image}{"".join(rows)}</section>')
    return '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Full Options Report</title><style>body{background:#0B1220;color:#E5E7EB;font:16px system-ui;max-width:1200px;margin:auto;padding:24px}section{background:#111827;border:1px solid #374151;border-radius:16px;padding:20px;margin:20px 0}h1,h2{color:#22D3EE}img{max-width:100%;border-radius:12px}details{border-top:1px solid #374151;padding:12px 0}summary{cursor:pointer}small{float:right;color:#FBBF24}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#E5E7EB}p{color:#9CA3AF;font-size:13px}a{color:#22D3EE}</style></head><body>'+f'<h1>{html.escape(payload["kind"].title())} Options Report</h1><p>{html.escape(payload["generated_at"])} | {payload["report_completeness"]}</p><a href="{payload["markdown_url"]}">Download complete report</a>'+''.join(parts)+'</body></html>'

async def scheduled_intraday(app,kind='intraday'):
    now=datetime.now(UTC)
    from .economic_events import is_market_holiday
    if now.astimezone(CT).weekday()>=5 or is_market_holiday(now.astimezone(CT).date()):return
    report=await assemble_report(app,kind=kind)
    # Existing approved advisory channel; delivery remains on. No brokerage calls.
    from . import _send_intraday_webhook_sync
    embed={'title':'Intraday Options Report','description':f'[{report["report_completeness"]} — Open the full dark report]({report["report_url"]})',
           'color':0x22D3EE,'timestamp':report['generated_at'],'image':{'url':report['chart_urls']['market_map']},
           'fields':[{'name':'Data integrity','value':f'{len(report["report_validation"]["unavailable_fields"])} fields historical/unavailable; all sections included.'}]}
    posted=await asyncio.to_thread(_send_intraday_webhook_sync,embed)
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
    scheduler.add_job(opening,'cron',hour=8,minute=30,day_of_week='mon-fri',id='full_open_report',replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=300)
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
