"""Research-only SPY regression rerun. No broker or production database imports.

Monetary values are parsed from provider CSV strings. Decimal is the corrected
arm; float is an explicitly labelled defect-control, never a deployable candidate.
Each raw contract/date response is acquired once per study, shared only within
that study, and never loaded from a previous run or fallback file.
"""
from __future__ import annotations
import csv, hashlib, io, itertools, json, math, os, pathlib, threading, time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo
import requests

ET = ZoneInfo('America/New_York')
D = Decimal
BASE = 'http://thetadata-proxy:10000'
STATE = {'stage': 'disabled'}
SPEC = {
 'version': 'controlled-rerun-1', 'symbol': 'SPY', 'option_right': 'put', 'dte': 0,
 'families': ['breakout_retest','failed_breakdown','trend_reclaim'], 'widths': [1,2],
 'slippages': ['0.01','0.03','0.05'], 'arithmetic': ['legacy_float','decimal'],
 'fee_locations': ['external','account'], 'entry_floors': ['0','2000'],
 'stock_interval': '15m', 'quote_interval': '1m', 'stock_venue': 'utp_cta',
 'session_open': '09:30', 'session_close': '16:00', 'entry_start': '10:15',
 'entry_end': '14:30', 'liquidation_signal': '15:39', 'liquidation_fill': '15:40',
 'delay_minutes': 1, 'min_credit_width_fraction': '0.20',
 'max_credit_width_fraction': '0.45', 'max_signal_spread': '0.10',
 'target_capture': '0.50', 'stop_debit_multiple': '2.00',
 'initial_equity': '2000', 'risk_fraction': '0.10', 'roundtrip_fee': '2.60',
 'subscription': '50', 'max_entries': 2, 'cooldown_minutes': 15,
 'daily_realized_pause': '-100', 'old_outcome_inputs': [], 'price_fallback': False,
 'quote_update_age': 'not verified by interval timestamps',
 'execution_model': 'next-minute individual-leg bid/ask with explicit adverse allowance',
 'phases': [
  {'name':'september_regression','start':'2026-09-10','end':'2026-09-22',
   'holidays': [], 'expected_sessions':9, 'full_accounting_month':False},
  {'name':'january_retrospective','start':'2025-01-01','end':'2025-01-31',
   'holidays':['2025-01-01','2025-01-09','2025-01-20'],
   'expected_sessions':20,'full_accounting_month':True}],
 'max_provider_requests': 240, 'request_deadline_seconds': 660,
 'qualification': 'regression/retrospective, not untouched validation',
}
CONFIG_KEYS = tuple(SPEC)
OUT = pathlib.Path('/tmp/flame_controlled_rerun')

class DataError(RuntimeError): pass

def validate_spec(spec):
 if set(spec) != set(CONFIG_KEYS): raise ValueError('missing_or_unknown_configuration_field')
 if spec['symbol']!='SPY' or spec['option_right']!='put': raise ValueError('wrong_product')
 if spec['dte']!=0: raise ValueError('this_regression_requires_explicit_zero_dte')
 if spec['old_outcome_inputs'] or spec['price_fallback']: raise ValueError('old_inputs_forbidden')
 for k in ('initial_equity','risk_fraction','roundtrip_fee','subscription',
           'min_credit_width_fraction','max_credit_width_fraction','target_capture',
           'stop_debit_multiple','max_signal_spread','daily_realized_pause'):
  if not isinstance(spec[k],str) or not D(spec[k]).is_finite(): raise ValueError('decimal_string_required:'+k)
 if not D('0')<D(spec['min_credit_width_fraction'])<D(spec['max_credit_width_fraction'])<D('1'): raise ValueError('bad_credit_band')
 if not D('0')<D(spec['risk_fraction'])<=D('1'): raise ValueError('bad_risk')
 if not spec['session_open']<=spec['entry_start']<=spec['entry_end']<spec['liquidation_signal']<spec['liquidation_fill']<spec['session_close']: raise ValueError('bad_session')
 if spec['delay_minutes']!=1: raise ValueError('unexpected_latency')
 return hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def emit(event, **fields):
 print('FLAME_RERUN '+json.dumps({'event':event,'utc':datetime.now(timezone.utc).isoformat(),**fields},default=str,sort_keys=True),flush=True)

def stamp(s):
 t=datetime.fromisoformat(str(s).replace('Z','+00:00'))
 return t.replace(tzinfo=ET) if t.tzinfo is None else t.astimezone(ET)

def dec(s):
 try: x=D(str(s))
 except InvalidOperation as e: raise DataError('bad_numeric') from e
 if not x.is_finite(): raise DataError('nonfinite')
 return x

def money(x):
 if isinstance(x,D): return x.quantize(D('.01'),rounding=ROUND_HALF_UP)
 return round(x,2)

def number(x, mode): return D(str(x)) if mode=='decimal' else float(x)

def quote_prices(s,l,mode):
 n=lambda x:number(x,mode)
 return n(s['bid'])-n(l['ask']),n(s['ask'])-n(l['bid']),n(s['ask'])-n(s['bid'])+n(l['ask'])-n(l['bid'])

def credit_ok(c,width,mode,spec=SPEC):
 return number(spec['min_credit_width_fraction'],mode)*width<=c<=number(spec['max_credit_width_fraction'],mode)*width

def threshold(debit,credit,mode,spec=SPEC):
 if debit>=number(spec['stop_debit_multiple'],mode)*credit: return 'stop'
 if debit<=(number('1',mode)-number(spec['target_capture'],mode))*credit: return 'target'
 return None

class Feed:
 def __init__(self):
  self.calls=0; self.deadline=time.monotonic()+SPEC['request_deadline_seconds']
  self.manifest=[]; self.observations={}; self.same_run_dataset_hits=0
  self.run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
  self.out=OUT/self.run_id; self.out.mkdir(parents=True,exist_ok=False)
 def get(self,path,params):
  if path not in ('/v3/stock/history/ohlc','/v3/option/history/quote'): raise DataError('endpoint_forbidden')
  if self.calls>=SPEC['max_provider_requests'] or time.monotonic()>self.deadline: raise DataError('request_budget_exhausted')
  self.calls+=1
  r=requests.get(BASE+path,params=params,headers={'Cache-Control':'no-cache, no-store','Pragma':'no-cache'},timeout=(8,50),allow_redirects=False)
  record={'request':self.calls,'path':path,'params':params,'status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content),'source':r.headers.get('X-Market-Data-Provider'),'retrieved_utc':datetime.now(timezone.utc).isoformat()}
  self.manifest.append(record); (self.out/f'{self.calls:03d}.raw').write_bytes(r.content)
  emit('source',**record); r.raise_for_status()
  if r.status_code!=200 or record['source']!='thetadata': raise DataError('unverified_provider')
  return list(csv.DictReader(io.StringIO(r.text)))
 def stocks(self,phase):
  params={'symbol':'SPY','start_date':phase['start'],'end_date':phase['end'],'interval':'15m','start_time':'09:30:00','end_time':'16:00:00','venue':'utp_cta'}
  rows=self.get('/v3/stock/history/ohlc',params); out={}
  for r in rows:
   t=stamp(r['timestamp']);day=t.date().isoformat()
   if not phase['start']<=day<=phase['end']: raise DataError('stock_date_out_of_range')
   if t.strftime('%H:%M')=='16:00': continue # incomplete terminal bucket only
   if not '09:30'<=t.strftime('%H:%M')<'16:00': raise DataError('stock_outside_session')
   if r.get('symbol','SPY')!='SPY': raise DataError('wrong_symbol')
   nums={k:dec(r[k]) for k in ('open','high','low','close','volume')}
   if min(nums[k] for k in ('open','high','low','close'))<=0 or nums['volume']<0 or nums['low']>min(nums['open'],nums['close']) or nums['high']<max(nums['open'],nums['close']): raise DataError('invalid_ohlc')
   out.setdefault(day,[]).append({'t':t,**{k:float(v) for k,v in nums.items()}})
  expected=[];d=date.fromisoformat(phase['start']);end=date.fromisoformat(phase['end'])
  while d<=end:
   if d.weekday()<5 and d.isoformat() not in phase['holidays']: expected.append(d.isoformat())
   d+=timedelta(days=1)
  if len(expected)!=phase['expected_sessions'] or set(out)!=set(expected): raise DataError('session_calendar_mismatch')
  for day,bars in out.items():
   bars.sort(key=lambda x:x['t']);t=stamp(day+'T09:30:00')
   if [x['t'] for x in bars]!=[t+timedelta(minutes=15*i) for i in range(26)]: raise DataError('stock_gap_or_duplicate:'+day)
  emit('stock_coverage',phase=phase['name'],sessions=len(out),bars=sum(map(len,out.values())),first=min(out),last=max(out))
  return dict(sorted(out.items()))
 def quotes(self,day,strike):
  key=(day,strike)
  if key in self.observations:
   self.same_run_dataset_hits+=1
   return self.observations[key]
  params={'symbol':'SPY','date':day,'expiration':day,'strike':str(strike),'right':'put','interval':'1m','start_time':'10:15:00','end_time':'15:41:00'}
  rows=self.get('/v3/option/history/quote',params);out={};rejected=Counter()
  if not rows: raise DataError('empty_option_response')
  for r in rows:
   if not all(k in r for k in ('timestamp','symbol','strike','expiration','right','bid','ask','bid_size','ask_size')): raise DataError('missing_quote_schema')
   t=stamp(r['timestamp'])
   if t.date().isoformat()!=day or r['symbol']!='SPY' or dec(r['strike'])!=strike or r['right'].lower() not in ('p','put') or str(r['expiration'])[:10].replace('-','')!=day.replace('-',''): raise DataError('wrong_quote_identity')
   if t in out: raise DataError('duplicate_quote')
   vals={k:dec(r[k]) for k in ('bid','ask','bid_size','ask_size')}
   if vals['bid']<0 or vals['ask']<=0 or vals['ask']<vals['bid'] or vals['bid_size']<1 or vals['ask_size']<1:
    rejected['invalid_or_no_size']+=1;continue
   out[t]={k:r[k] for k in vals}
  self.observations[key]=out
  emit('quote_coverage',day=day,strike=strike,rows=len(rows),valid=len(out),rejected=dict(rejected))
  return out

def signals(bars,family):
 oh=max(r['high'] for r in bars[:2]);ol=min(r['low'] for r in bars[:2]);prev_on=False;answer=[]
 for i in range(3,len(bars)):
  b,p=bars[i],bars[i-1];available=b['t']+timedelta(minutes=15)
  if not SPEC['entry_start']<=available.strftime('%H:%M')<=SPEC['entry_end']: continue
  bull=b['close']>b['open']
  if family=='breakout_retest': on=p['close']>oh and b['low']<=oh+.03 and b['close']>oh and bull
  elif family=='failed_breakdown': on=b['low']<ol and b['close']>ol and bull
  elif family=='trend_reclaim':
   mean=sum(x['close'] for x in bars[max(0,i-4):i])/min(4,i)
   on=p['close']<mean and b['close']>mean and b['close']>bars[0]['open'] and bull
  else: raise ValueError('unknown_family')
  if on and not prev_on: answer.append({'time':available,'short':math.floor(min(b['close']-.25,b['low']-.05))})
  prev_on=bool(on)
 return answer

def replay_trade(feed,day,sig,width,slip,mode):
 n=lambda x:number(x,mode);slip=n(slip);fee=n(SPEC['roundtrip_fee'])
 qs,ql=feed.quotes(day,sig['short']),feed.quotes(day,sig['short']-width)
 t=sig['time'];t1=t+timedelta(minutes=1)
 def prices(at):
  if at not in qs or at not in ql:return None
  return quote_prices(qs[at],ql[at],mode)
 a,f=prices(t),prices(t1)
 if a is None:return {'status':'skip','reason':'signal_quote_missing'}
 if not credit_ok(a[0],width,mode) or a[2]>n(SPEC['max_signal_spread']):return {'status':'skip','reason':'signal_price_rejected'}
 if f is None:return {'status':'skip','reason':'fill_quote_missing'}
 credit=f[0]-slip
 if not credit_ok(credit,width,mode):return {'status':'skip','reason':'delayed_credit_rejected'}
 base={'status':'trade','date':day,'entry':t1,'short':sig['short'],'width':width,'credit':credit,'risk':(n(width)-credit)*100+fee}
 m=t1;end=stamp(day+'T'+SPEC['liquidation_signal']+':00');worst=n('0')
 while m<=end:
  p=prices(m)
  if p is None:return {**base,'status':'unresolved','reason':'interior_quote_gap'}
  debit=p[1]+slip;worst=min(worst,(credit-debit)*100-fee)
  reason=threshold(debit,credit,mode) or ('eod' if m==end else None)
  if reason:
   at=m+timedelta(minutes=1);x=prices(at)
   if x is None:return {**base,'status':'unresolved','reason':'exit_quote_gap'}
   close=x[1]+slip
   if close<0 or close>n(width)+n('.20'):return {**base,'status':'unresolved','reason':'extreme_synthetic_market'}
   pnl=money((credit-close)*100-fee)
   return {**base,'exit':at,'debit':close,'net':pnl,'reason':reason,'worst_open':money(min(worst,pnl))}
  m+=timedelta(minutes=1)
 return {**base,'status':'unresolved','reason':'missing_time_exit'}

def run_account(feed,days,family,width,slip,mode,floor,fee_location):
 n=lambda x:number(x,mode);eq=n(SPEC['initial_equity']);peak=eq;dd=n('0');low=eq
 trades=[];rejects=Counter();invalid=None;months={day[:7] for day in days}
 # Billing sensitivity charged at first observed session in each billed month.
 # September is partial and does not represent a completed-month return.
 billed=set();external=n('0');bills=n('0')
 for day,bars in days.items():
  if day[:7] not in billed:
   billed.add(day[:7]);bill=n(SPEC['subscription']);bills+=bill
   if fee_location=='account':eq-=bill
   else:external+=bill
   dd=max(dd,peak-(eq-external));low=min(low,eq)
  count=0;next_at=bars[0]['t'];daily=n('0')
  for sig in signals(bars,family):
   if count>=SPEC['max_entries']:rejects['daily_cap']+=1;continue
   if sig['time']<next_at:rejects['cooldown_or_open']+=1;continue
   if daily<=n(SPEC['daily_realized_pause']):rejects['daily_pause']+=1;continue
   if eq<n(floor):rejects['account_floor']+=1;continue
   rec=replay_trade(feed,day,sig,width,slip,mode)
   if rec['status']=='skip':rejects[rec['reason']]+=1;continue
   if rec['risk']>eq*n(SPEC['risk_fraction']):rejects['risk_cap']+=1;continue
   if rec['status']=='unresolved':invalid=rec;break
   low=min(low,eq+rec['worst_open']);dd=max(dd,peak-(eq+rec['worst_open']-external))
   eq=money(eq+rec['net']);daily+=rec['net'];peak=max(peak,eq-external);dd=max(dd,peak-(eq-external))
   count+=1;next_at=rec['exit']+timedelta(minutes=SPEC['cooldown_minutes']);trades.append(rec)
  if invalid:break
 profit=sum((r['net'] for r in trades),n('0'))
 result={'family':family,'width':width,'slip':str(slip),'arithmetic':mode,'floor':str(floor),'fee_location':fee_location,'sessions':len(days),'signals':sum(len(signals(b,family)) for b in days.values()),'trades':len(trades),'rejections':dict(rejects),'unresolved':bool(invalid),'net_trading':float(money(profit)),'billed_subscription':float(bills),'customer_net':float(money(profit-bills)),'broker_equity':float(eq),'observed_equity_drawdown':float(money(dd)),'lowest_broker_equity':float(money(low)),'complete':invalid is None,'verdict':'REGRESSION_ONLY_NOT_VALIDATED' if not invalid else 'INVALID_PATH'}
 if invalid:result['invalid_reason']=invalid['reason']
 return result,trades

def execute():
 validate_spec(SPEC);feed=Feed();STATE['stage']='running';all_results=[];comparisons=[]
 emit('frozen_configuration',config=SPEC,config_sha256=validate_spec(SPEC))
 try:
  for phase in SPEC['phases']:
   days=feed.stocks(phase);phase_rows={};phase_ledgers={}
   for family,width,slip,floor,location in itertools.product(SPEC['families'],SPEC['widths'],SPEC['slippages'],SPEC['entry_floors'],SPEC['fee_locations']):
    key=(family,width,slip,floor,location)
    for mode in SPEC['arithmetic']:
     result,trades=run_account(feed,days,family,width,slip,mode,floor,location)
     result['phase']=phase['name'];all_results.append(result);phase_rows[(key,mode)]=result;phase_ledgers[(key,mode)]=trades
     emit('result',**result)
     if mode=='decimal' and location=='external' and floor=='0' and slip=='0.03':
      for tr in trades:emit('ledger',phase=phase['name'],family=family,slip=slip,**tr)
    old,new=phase_rows[(key,'legacy_float')],phase_rows[(key,'decimal')]
    old_sig=[(r['entry'],r['short'],r.get('exit'),str(money(r['net']))) for r in phase_ledgers[(key,'legacy_float')]]
    new_sig=[(r['entry'],r['short'],r.get('exit'),str(money(r['net']))) for r in phase_ledgers[(key,'decimal')]]
    c={'phase':phase['name'],'family':family,'width':width,'slip':slip,'floor':floor,'fee_location':location,'old_trades':old['trades'],'new_trades':new['trades'],'old_net':old['customer_net'],'new_net':new['customer_net'],'delta_net':round(new['customer_net']-old['customer_net'],2),'changed':old['trades']!=new['trades'] or old['customer_net']!=new['customer_net'] or [x[:3] for x in old_sig]!=[x[:3] for x in new_sig],'both_complete':old['complete'] and new['complete']}
    comparisons.append(c)
    if c['changed']:emit('changed_comparison',**c)
   emit('phase_complete',phase=phase['name'],scenarios=len(phase_rows),comparisons=len(phase_rows)//2,changed=sum(c['changed'] for c in comparisons if c['phase']==phase['name']),provider_requests=feed.calls)
  STATE['stage']='complete';emit('complete',scenarios=len(all_results),paired_comparisons=len(comparisons),changed=sum(x['changed'] for x in comparisons),provider_requests=feed.calls,prior_data_reads=0,prior_result_reads=0)
 except Exception as e:
  STATE['stage']='failed';emit('failed',kind=type(e).__name__,reason=str(e)[:180],finished_scenarios=len(all_results),provider_requests=feed.calls)
 finally:
  for name,value in [('spec',SPEC),('manifest',feed.manifest),('results',all_results),('comparisons',comparisons)]:
   (feed.out/(name+'.json')).write_text(json.dumps(value,indent=2,default=str))

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(json.dumps({'research_only':True,**STATE}).encode())
 def log_message(self,*args):pass

if __name__=='__main__':
 if os.getenv('FLAME_FRESH_MODE')=='controlled-rerun' and datetime.now(timezone.utc)<datetime.fromisoformat('2026-09-23T22:00:00+00:00'):
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
