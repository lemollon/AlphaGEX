"""Report-alert simulation ledger. No broker orders and no assumed backfills."""
from __future__ import annotations
import json, os
from datetime import datetime, time, timezone
from sqlalchemy import text
from .db import engine
from .report_producers import number, ET, tradier
from .market_structure import _parse_ts
UTC=timezone.utc
TABLE='sw_report_paper_positions'
RULES=('One simulated structure per qualified ENTRY_READY setup/date. Enter at fresh executable natural BBO '
       'plus adverse $0.02/leg; exit at fresh liquidation BBO less $0.02/leg. $0.65/contract/leg/side fees. '
       'Quotes are a simulation, not confirmed fills. No retroactive fills. 50% premium target, '
       '100% premium loss stop capped by defined maximum risk; flatten after 15:55 ET when fresh quotes exist. '
       'Missing exit quotes keep an unresolved open position, never an invented close.')

def ensure_tables():
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_report_fill_attempts (event_key TEXT PRIMARY KEY, observed_at TIMESTAMP NOT NULL, outcome TEXT NOT NULL, reason TEXT NOT NULL)'))
        c.execute(text('''CREATE TABLE IF NOT EXISTS sw_report_trigger_events (
          event_key TEXT PRIMARY KEY, observed_at TIMESTAMP NOT NULL,
          setup_id TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL)'''))
        c.execute(text(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
          event_key TEXT PRIMARY KEY, setup_id TEXT NOT NULL, symbol TEXT NOT NULL,
          entered_at TIMESTAMP NOT NULL, exited_at TIMESTAMP, state TEXT NOT NULL,
          payload_json TEXT NOT NULL)'''))

def record_trigger(setup,state,proof,now):
    ensure_tables()
    event=f"{now.astimezone(ET).date()}:{setup['setup_id']}:{state}"
    with engine.begin() as c:
        c.execute(text('''INSERT INTO sw_report_trigger_events (event_key,observed_at,setup_id,state,payload_json)
          VALUES (:event,:now,:setup,:state,:payload) ON CONFLICT(event_key) DO NOTHING'''),
          {'event':event,'now':now.replace(tzinfo=None),'setup':setup['setup_id'],'state':state,
           'payload':json.dumps({'symbol':setup['symbol'],'entry_rule':setup.get('entry'),
                               'invalidation':setup.get('invalidation'),'evidence':proof})})

def package_payoff(selection):
    """Expiry payoff for single-expiry long/vertical/condor packages."""
    legs=selection.get('legs') or []
    if not legs:return None
    if selection.get('strategy') in ('calendar','double_calendar'):
        return {'max_risk':selection.get('max_risk'),'max_reward':None,'breakeven':None,
                'method':'Calendar reward/breakeven depend on back-expiry IV and time; no exact expiry payoff asserted'}
    credit=number(selection.get('natural_credit'));debit=number(selection.get('natural_debit'))
    if credit is None and debit is None:return None
    entry=credit if credit is not None else -debit
    strikes=sorted({float(l['strike']) for l in legs})
    def payoff(spot):
        return entry+sum((1 if l['action']=='buy' else -1)*
               (max(spot-float(l['strike']),0) if l['right']=='C' else max(float(l['strike'])-spot,0)) for l in legs)
    points=[0,*strikes,max(strikes)*2+100];values=[payoff(s) for s in points]
    slope=sum((1 if l['action']=='buy' else -1) for l in legs if l['right']=='C')
    roots=[]
    for a,b in zip(points,points[1:]):
        pa,pb=payoff(a),payoff(b)
        if pa==0:roots.append(a)
        if pa*pb<0:roots.append(a+(b-a)*(-pa)/(pb-pa))
    return {'max_risk':round(max(0,-min(values))*100,2) if slope>=0 else None,
            'max_reward':'unlimited' if slope>0 else round(max(values)*100,2),
            'breakeven':sorted({round(r,4) for r in roots}),
            'method':'Single-expiry expiry payoff; 100 multiplier; fees and early assignment excluded'}

def qualify_package(selection,now):
    legs=selection.get('legs') or []
    if not legs or selection.get('liquidity_status')=='BLOCKED':return None
    for leg in legs:
        ts=_parse_ts(leg.get('exchange_timestamp'));bid=number(leg.get('bid'));ask=number(leg.get('ask'))
        if not ts or not 0<=(now-ts).total_seconds()<=90 or bid is None or ask is None or not 0<=bid<=ask or ask<=0:return None
        if not leg.get('symbol') or leg.get('action') not in ('buy','sell'):return None
        executable_size=number(leg.get('ask_size') if leg['action']=='buy' else leg.get('bid_size'))
        if executable_size is not None and executable_size<=0:return None
    return dict(selection,payoff=package_payoff(selection),qualification='Fresh per-leg BBO; conditional advisory package, not a submitted order')

def record_fill_attempt(setup,now,outcome,reason):
    ensure_tables()
    key=f"{now.astimezone(ET).date()}:{setup['setup_id']}"
    with engine.begin() as c:
        c.execute(text('INSERT INTO sw_report_fill_attempts (event_key,observed_at,outcome,reason) VALUES (:key,:now,:outcome,:reason) ON CONFLICT(event_key) DO UPDATE SET observed_at=excluded.observed_at,outcome=excluded.outcome,reason=excluded.reason'),{'key':key,'now':now.replace(tzinfo=None),'outcome':outcome,'reason':reason})

def record_entry(setup,selection,now):
    def blocked(reason):
        record_fill_attempt(setup,now,'BLOCKED',reason);return False
    package=qualify_package(selection,now)
    if not package:return blocked('No qualified fresh per-leg BBO: missing selection, stale/crossed quote, blocked liquidity or invalid executable side')
    # Calendars require an IV/time-dependent liquidation model; defer rather than force vertical exits.
    if package.get('strategy') in ('calendar','double_calendar'):return blocked('Calendar has no configured IV/time-dependent paper liquidation model')
    credit=number(package.get('natural_credit'));debit=number(package.get('natural_debit'))
    if credit is None and debit is None:return blocked('Qualified package has no recorded executable natural debit/credit')
    n=len(package['legs']);entry=(credit if credit is not None else -debit)-.02*n
    risk=number(package.get('max_risk'))
    if risk is None:risk=number((package.get('payoff') or {}).get('max_risk'))
    if risk is None or risk<=0:return blocked('No positive bounded maximum risk from the qualified package payoff')
    event=f"{now.astimezone(ET).date()}:{setup['setup_id']}"
    payload={'package':package,'entry_cash_per_share':entry,'entry_fees':.65*n,
             'quantity':1,'max_risk':risk+.02*n*100+.65*n*2,
             'entry_underlying':setup.get('current_price'),'last_mark':None,'mfe':None,'mae':None,
             'rules':RULES,'confirmation_sequence':setup.get('entry'),
             'invalidation':setup.get('invalidation'),'regime':setup.get('thesis'),
             'simulated_fill':True,'realized_pnl':None,'exception':None}
    ensure_tables()
    with engine.begin() as c:
        result=c.execute(text(f'''INSERT INTO {TABLE} (event_key,setup_id,symbol,entered_at,state,payload_json)
           VALUES (:event,:setup,:symbol,:now,'OPEN',:payload) ON CONFLICT(event_key) DO NOTHING'''),
           {'event':event,'setup':setup['setup_id'],'symbol':setup['symbol'],'now':now.replace(tzinfo=None),'payload':json.dumps(payload)})
    record_fill_attempt(setup,now,'FILLED' if result.rowcount>0 else 'ALREADY_FILLED','Modeled fresh natural BBO with configured adverse slippage and fees; no live execution')
    return result.rowcount>0

def liquidation_value(package,quotes,now):
    value=0.;stamps=[]
    from .intraday_watch import _option_time
    for leg in package['legs']:
        q=quotes.get(leg['symbol']) or {};bid=number(q.get('bid'));ask=number(q.get('ask'))
        bts,ats=_option_time(q.get('bid_date')),_option_time(q.get('ask_date'))
        if bid is None or ask is None or not 0<=bid<=ask or ask<=0 or not bts or not ats:return None
        if any(not 0<=(now-ts).total_seconds()<=90 for ts in (bts,ats)):return None
        value+=bid if leg['action']=='buy' else -ask
        stamps.extend([bts,ats])
    return {'cash_per_share':value-.02*len(package['legs']),'source_timestamp':min(stamps).isoformat()}

def mark_open_positions(now=None):
    now=now or datetime.now(UTC);ensure_tables()
    with engine.begin() as c:
        rows=c.execute(text(f"SELECT event_key,payload_json,entered_at FROM {TABLE} WHERE state='OPEN'")).fetchall()
    if not rows:return {'open':0,'marked':0}
    symbols=sorted({l['symbol'] for _,raw,_ in rows for l in json.loads(raw)['package']['legs']})
    try:
        raw=(tradier('/quotes',{'symbols':','.join(symbols)}).get('quotes') or {}).get('quote') or []
        if isinstance(raw,dict):raw=[raw]
        quotes={q['symbol']:q for q in raw};now=datetime.now(UTC)
    except Exception:return {'open':len(rows),'marked':0,'reason':'Fresh liquidation quotes unavailable'}
    marked=closed=0
    for event,raw,entered in rows:
        data=json.loads(raw);package=data['package'];mark=liquidation_value(package,quotes,now)
        if mark is None:
            data['exception']='Missing/stale exit BBO; position unresolved'
            state='OPEN';exit_at=None
        else:
            marked+=1;n=len(package['legs'])
            pnl=(data['entry_cash_per_share']+mark['cash_per_share'])*100-data['entry_fees']-.65*n
            data['last_mark']=dict(mark,pnl=round(pnl,2),retrieved_at=now.isoformat())
            data['mfe']=max(data['mfe'] if data['mfe'] is not None else pnl,pnl)
            data['mae']=min(data['mae'] if data['mae'] is not None else pnl,pnl)
            data['exception']=None
            premium=abs(number(package.get('natural_credit')) or number(package.get('natural_debit')) or 0)*100
            et=now.astimezone(ET)
            target=pnl>=premium*.5;stop=pnl<=-min(premium,data['max_risk'])
            entered_et=_parse_ts(entered).astimezone(ET)
            flatten=et.date()>entered_et.date() or et.time().replace(tzinfo=None)>=time(15,55)
            reason='premium_target' if target else 'premium_stop' if stop else 'session_flatten' if flatten else None
            state='CLOSED' if reason else 'OPEN';exit_at=now.replace(tzinfo=None) if reason else None
            if reason:closed+=1;data.update(realized_pnl=round(pnl,2),exit_reason=reason)
        with engine.begin() as c:
            c.execute(text(f'UPDATE {TABLE} SET state=:state,exited_at=:exit,payload_json=:payload WHERE event_key=:event AND state=\'OPEN\''),
                      {'state':state,'exit':exit_at,'payload':json.dumps(data),'event':event})
    return {'open':len(rows)-closed,'marked':marked,'closed':closed}

def scorecard():
    ensure_tables()
    with engine.begin() as c:
        rows=c.execute(text(f'SELECT event_key,setup_id,symbol,entered_at,exited_at,state,payload_json FROM {TABLE} ORDER BY entered_at')).fetchall()
        events=c.execute(text('SELECT event_key,state,observed_at,payload_json FROM sw_report_trigger_events ORDER BY observed_at')).fetchall()
        attempts={r[0]:{'updated_at':_parse_ts(r[1]).isoformat(),'outcome':r[2],'reason':r[3]} for r in c.execute(text('SELECT event_key,observed_at,outcome,reason FROM sw_report_fill_attempts')).fetchall()}
    trades=[]
    for event,setup,symbol,entered,exited,state,raw in rows:
        trades.append(dict(json.loads(raw),event_key=event,setup_id=setup,symbol=symbol,
           entered_at=_parse_ts(entered).isoformat(),exited_at=_parse_ts(exited).isoformat() if exited else None,state=state))
    closed=sorted([t for t in trades if t['state']=='CLOSED'],key=lambda t:t['exited_at'])
    equity=peak=drawdown=0.;history=[]
    for t in closed:
        equity+=t['realized_pnl'];peak=max(peak,equity);drawdown=min(drawdown,equity-peak)
        history.append({'timestamp':t['exited_at'],'equity':round(equity,2),'drawdown':round(equity-peak,2)})
    wins=[t['realized_pnl'] for t in closed if t['realized_pnl']>0];losses=[t['realized_pnl'] for t in closed if t['realized_pnl']<0]
    clusters=[];run=[]
    for t in closed:
        if t['realized_pnl']<0:run.append(t['event_key'])
        elif run:clusters.append(run);run=[]
    if run:clusters.append(run)
    trigger_events=[dict(json.loads(raw),event_key=key,state=state,observed_at=_parse_ts(observed).isoformat()) for key,state,observed,raw in events]
    reconciliation=[]
    trade_keys={t['event_key'] for t in trades}
    for e in trigger_events:
        if e['state']!='ENTRY_READY':continue
        key=e['event_key'].rsplit(':',1)[0]
        result=attempts.get(key) or {'outcome':'FILLED' if key in trade_keys else 'UNRESOLVED','reason':'Persistent paper fill exists' if key in trade_keys else 'No contemporaneous fill outcome was recorded; cannot reconstruct a historical fill'}
        reconciliation.append(dict(result,event_key=key,alert_time=e['observed_at']))
    return {'fill_reconciliation':reconciliation,'entry_ready_alerts':sum(e['state']=='ENTRY_READY' for e in trigger_events),'trigger_events':trigger_events,
      'fills':len(trades),'closed':len(closed),'wins_losses':{'wins':len(wins),'losses':len(losses)},
      'realized_pnl':round(equity,2),'cumulative_pnl':round(equity,2),'win_rate':len(wins)/len(closed) if closed else None,
      'average_win_loss':{'win':sum(wins)/len(wins) if wins else None,'loss':sum(losses)/len(losses) if losses else None},
      'drawdown':round(drawdown,2),'equity_history':history,'fill_rules':RULES,
      'slippage_costs':{'adverse_per_leg_per_side':.02,'fee_per_contract_per_leg_per_side':.65},
      'exceptions':[{'event_key':t['event_key'],'reason':t['exception']} for t in trades if t.get('exception')],
      'trade_details':trades,'loss_clusters':[r for r in clusters if len(r)>=2],
      'sample_status':('No ENTRY_READY alerts recorded; zero fills are expected' if not reconciliation else 'ENTRY_READY alerts exist but no valid fills; see fill reconciliation') if not trades else 'Forward paper observations; no historical fill reconstruction'}
