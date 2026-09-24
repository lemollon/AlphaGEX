"""Read-only, fixed-rule SPY regime comparison. No production trading imports.

Prices use integer 0.0001-dollar units. For a 100-share option, differences in
these units equal P&L cents per contract. Every quote is re-acquired this run;
raw responses are evidence outputs and never inputs from earlier research.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, pathlib, threading, time, uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from zoneinfo import ZoneInfo

D = Decimal
U = 10000
ET = ZoneInfo('America/New_York')
BASE = 'http://thetadata-proxy:10000'
STATE = {'stage': 'disabled'}
SPEC = {
 'id': 'flame-reset-regime-20260923-v1', 'symbol': 'SPY', 'right': 'put',
 'start': '2025-01-01', 'end': '2025-02-28',
 'closures': ['2025-01-01','2025-01-09','2025-01-20','2025-02-17'],
 'expected_sessions': 39, 'decision_et_minute': 720, 'fill_delay_minutes': 1,
 'flat_et_minute': 945, 'widths_dollars': [1,2], 'fee_cents_roundtrip': 260,
 'credit_min_pct_width': 25, 'credit_max_pct_width': 40, 'credit_target_pct_width': 30,
 'max_combined_quote_width_units': 1000, 'short_strike_search_dollars_below': 20,
 'profit_capture_pct': 50, 'stop_debit_multiple': 2,
 'profiles_units': {'natural':0,'adverse3c':300,'adverse5c':500},
 'initial_equity_cents': 200000, 'monthly_bill_cents': 5000,
 'position_risk_pct':10, 'contracts':1, 'entries_per_day':1,
 'fee_locations':['external','account'], 'admission_floors_cents':[0,200000],
 'masks':['all','uptrend','calm_range','uptrend_or_calm_range'],
 'regime': {'bar_minutes':5,'sma_periods':20,'slope_lookback_bars':3,
            'efficiency_bars':12,'trend_efficiency_pct':30,'range_efficiency_pct':20,
            'calm_recent_bars':6,'calm_prior_bars':12},
 'max_requests':100, 'max_bytes_per_response':35000000,'deadline_seconds':1050,
 'scope':'retrospective fixed-rule comparison, not certified unseen validation',
 'no_saved_price_inputs':True,'no_previous_trade_inputs':True,
 'execution':'next-minute natural leg quotes; no midpoint fills; no expiry substitution',
 'eligibility':'floor sensitivities; actual customer brokerage permission unverified',
}

class DataError(RuntimeError): pass

def emit(event, **kw):
 print('FLAME_RESET '+json.dumps({'event':event,'utc':datetime.now(timezone.utc).isoformat(),**kw},sort_keys=True,default=str,separators=(',',':')),flush=True)

def units(s):
 try: v=D(str(s))*U
 except InvalidOperation as e: raise DataError('invalid_price') from e
 if not v.is_finite() or v!=v.to_integral_value(): raise DataError('unsupported_price_precision')
 return int(v)

def money(cents): return float(D(cents)/100)

def minute(raw,day):
 try: dt=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
 except ValueError as e: raise DataError('bad_timestamp') from e
 dt=dt.replace(tzinfo=ET) if dt.tzinfo is None else dt.astimezone(ET)
 if dt.date().isoformat()!=day or dt.second or dt.microsecond: raise DataError('wrong_quote_time')
 return dt.hour*60+dt.minute

def session_days():
 days=[]; d=date.fromisoformat(SPEC['start']); last=date.fromisoformat(SPEC['end'])
 while d<=last:
  if d.weekday()<5 and d.isoformat() not in SPEC['closures']:days.append(d.isoformat())
  d+=timedelta(days=1)
 if len(days)!=SPEC['expected_sessions']:raise DataError('calendar_mismatch')
 return days

def stock_rows(rows,day):
 out={};end=SPEC['decision_et_minute']
 for r in rows:
  m=minute(r['timestamp'],day)
  if m==end:continue  # The bar at the ending timestamp is not yet complete.
  if not 570<=m<end:raise DataError('stock_outside_prefix')
  if r.get('symbol','SPY')!='SPY' or m in out:raise DataError('stock_identity_or_duplicate')
  try:v={k:units(r[k]) for k in ['open','high','low','close']};vol=D(r['volume'])
  except Exception as e:raise DataError('stock_numeric:'+day+':'+str(m)+':'+repr({k:r.get(k) for k in ['open','close','volume','count']})) from e
  if min(v.values())<=0 or not vol.is_finite() or vol<0 or v['low']>min(v['open'],v['close']) or v['high']<max(v['open'],v['close']):raise DataError('bad_stock_bar')
  out[m]=v
 if sorted(out)!=list(range(570,end)):raise DataError('missing_stock_prefix:'+day)
 return out

def regime(stock):
 """Only completed prefix bars; classification does not use later option P&L."""
 b=[]
 for m in range(570,SPEC['decision_et_minute'],5):
  g=[stock[j] for j in range(m,m+5)]
  b.append({'open':g[0]['open'],'close':g[-1]['close'],'high':max(x['high'] for x in g),'low':min(x['low'] for x in g)})
 c=[x['close'] for x in b];now=sum(c[-20:]);past=sum(c[-23:-3]);diff=c[-1]-c[-13]
 travel=sum(abs(y-x) for x,y in zip(c[-13:-1],c[-12:]));eff=D(abs(diff))/travel if travel else D(0)
 tr=[max(b[i]['high']-b[i]['low'],abs(b[i]['high']-c[i-1]),abs(b[i]['low']-c[i-1])) for i in range(1,len(b))]
 calm=2*sum(tr[-6:])<=sum(tr[-18:-6])
 if c[-1]*20>now and now>past and diff>0 and eff>=D('.30'):label='uptrend'
 elif c[-1]*20<now and now<past and diff<0 and eff>=D('.30'):label='downtrend'
 elif eff<=D('.20') and calm:label='calm_range'
 else:label='transition'
 return {'label':label,'spot_units':c[-1],'efficiency':str(eff.quantize(D('.000001'))),'calm':calm,'sma20_units_sum':now,'sma20_lag_units_sum':past}

def parse_options(rows,day,spot):
 data={};seen=set();counts=Counter()
 lower=spot-SPEC['short_strike_search_dollars_below']*U;upper=spot
 for r in rows:
  counts['received']+=1
  if r.get('symbol')!='SPY' or r.get('right','').lower() not in ('p','put') or r.get('expiration','')[:10].replace('-','')!=day.replace('-',''):raise DataError('wrong_option_identity')
  k=units(r['strike'])
  if not lower<=k<=upper:continue
  m=minute(r['timestamp'],day)
  if not SPEC['decision_et_minute']<=m<=SPEC['flat_et_minute']:raise DataError('option_outside_window')
  if (k,m) in seen:raise DataError('duplicate_option_observation')
  seen.add((k,m));counts['near_rows']+=1
  try:
   bid,ask=units(r['bid']),units(r['ask']);bs,az=D(r['bid_size']),D(r['ask_size'])
   if not bs.is_finite() or not az.is_finite() or bid<0 or ask<=0 or bid>ask or bs<1 or az<1:raise DataError('invalid_quote')
  except (DataError,InvalidOperation,KeyError):counts['unusable_near_rows']+=1;continue
  data.setdefault(k,{})[m]=(bid,ask,int(bs),int(az))
 return data,dict(counts)

def market(data,k,w,m):
 s=data.get(k,{}).get(m);l=data.get(k-w*U,{}).get(m)
 if s is None or l is None:return None
 return (s[0]-l[1],s[1]-l[0],s[1]-s[0]+l[1]-l[0],s,l)

def choose(data,spot,w):
 choices=[]
 for k in data:
  if k>=spot:continue
  p=market(data,k,w,SPEC['decision_et_minute'])
  if p is None:continue
  credit,debit,spread=p[:3]
  if w*U*SPEC['credit_min_pct_width']<=100*credit<=w*U*SPEC['credit_max_pct_width'] and spread<=SPEC['max_combined_quote_width_units']:
   choices.append((abs(100*credit-w*U*SPEC['credit_target_pct_width']),spread,k))
 return min(choices)[2] if choices else None

def replay(data,k,w,slip):
 """Exact quote-model trade. k selected at signal; never reselect after fill."""
 t=SPEC['decision_et_minute']+1;end=SPEC['flat_et_minute'];p=market(data,k,w,t)
 if p is None:return {'status':'skip','reason':'no_entry_quote'}
 credit=p[0]-slip
 if not w*U*SPEC['credit_min_pct_width']<=100*credit<=w*U*SPEC['credit_max_pct_width']:
  return {'status':'skip','reason':'entry_credit_changed'}
 if p[2]>SPEC['max_combined_quote_width_units']:return {'status':'skip','reason':'entry_spread_widened'}
 fee=SPEC['fee_cents_roundtrip'];risk=w*U-credit+fee;base={'short_units':k,'width':w,'credit_units':credit,'risk_cents':risk,'entry_minute_et':t,'entry_leg_units':[p[3][0],p[4][1]],'slip_units':slip}
 worst=0;best=0;within_dd=0
 for m in range(t,end):
  q=market(data,k,w,m)
  if q is None:return {**base,'status':'unresolved','reason':'missing_open_position_quote','at_minute':m}
  debit=q[1]+slip
  if debit<0:return {**base,'status':'unresolved','reason':'negative_synthetic_debit'}
  mark=credit-debit-fee;worst=min(worst,mark);best=max(best,mark);within_dd=max(within_dd,best-mark)
  # Decision from an observed executable-side estimate, not a hypothetical fill.
  reason='stop' if debit>=SPEC['stop_debit_multiple']*credit else 'target' if debit*100<=(100-SPEC['profit_capture_pct'])*credit else 'time' if m==end-1 else None
  if reason:
   x=market(data,k,w,m+1)
   if x is None:return {**base,'status':'unresolved','reason':'missing_exit_quote'}
   close=x[1]+slip
   if close<0:return {**base,'status':'unresolved','reason':'negative_close_debit'}
   pnl=credit-close-fee
   return {**base,'status':'trade','reason':reason,'exit_minute_et':m+1,'debit_units':close,'exit_leg_units':[x[3][1],x[4][0]],'net_cents':pnl,'worst_open_cents':min(worst,pnl),'best_open_cents':max(best,pnl),'within_trade_drawdown_cents':max(within_dd,best-pnl),'close_above_width':close>w*U}
 raise AssertionError('missing_clock_exit')

def reference(data,k,w,slip):
 """Independent Decimal price/path calculation, not a call to replay or market."""
 t=SPEC['decision_et_minute']+1;end=SPEC['flat_et_minute'];fee=D(SPEC['fee_cents_roundtrip'])/100;ad=D(slip)/U
 def legs(m):
  a=data.get(k,{}).get(m);b=data.get(k-w*U,{}).get(m)
  if a is None or b is None:return None
  return tuple(D(x)/U for x in [a[0],a[1],b[0],b[1]])
 e=legs(t)
 if e is None:return ('skip','no_entry_quote')
 credit=e[0]-e[3]-ad
 if not D(w)*D('.25')<=credit<=D(w)*D('.40'):return ('skip','entry_credit_changed')
 if e[1]-e[0]+e[3]-e[2]>D('.10'):return ('skip','entry_spread_widened')
 worst=D(0)
 for m in range(t,end):
  z=legs(m)
  if z is None:return ('unresolved','missing_open_position_quote')
  debit=z[1]-z[2]+ad
  if debit<0:return ('unresolved','negative_synthetic_debit')
  worst=min(worst,(credit-debit)*100-fee)
  label='stop' if debit>=2*credit else 'target' if debit<=credit/2 else 'time' if m==end-1 else None
  if label:
   f=legs(m+1)
   if f is None:return ('unresolved','missing_exit_quote')
   close=f[1]-f[2]+ad
   if close<0:return ('unresolved','negative_close_debit')
   pnl=(credit-close)*100-fee
   return ('trade',label,m+1,int(pnl*100),int(min(worst,pnl)*100))
 raise AssertionError('oracle_missing_exit')

def agrees(rec,oracle):
 got=(rec['status'],rec['reason'])
 if rec['status']=='trade':got+=(rec['exit_minute_et'],rec['net_cents'],rec['worst_open_cents'])
 if got!=oracle:raise AssertionError(('independent_calculation_disagreement',got,oracle))

def accepted(mask,reg):
 return mask=='all' or mask==reg or(mask=='uptrend_or_calm_range' and reg in ('uptrend','calm_range'))

def account(days,results,w,profile,mask,fee_location,floor):
 eq=SPEC['initial_equity_cents'];peak=eq;dd=0;external=0;bills=0;profit=0;n=0;lowest=eq;reject=Counter();months={};weekdays=Counter();worst=0;streak=0;max_streak=0;valid=True
 for day in days:
  month=day[:7]
  if month not in months:
   months[month]={'trades':0,'net_cents':-SPEC['monthly_bill_cents']};bills+=SPEC['monthly_bill_cents']
   if fee_location=='account':eq-=SPEC['monthly_bill_cents']
   else:external+=SPEC['monthly_bill_cents']
   dd=max(dd,peak-(eq-external));lowest=min(lowest,eq)
  r=results[day];tr=r['trades'].get((w,profile));take=False
  if r.get('error'):
   valid=False;reject['data_error']+=1
  elif not accepted(mask,r['regime']['label']):reject['regime']+=1
  elif eq<floor:reject['account_floor']+=1
  elif tr is None:reject['no_candidate']+=1
  elif tr['status']=='skip':reject[tr['reason']]+=1
  elif tr['risk_cents']*100>eq*SPEC['position_risk_pct']:reject['risk_budget']+=1
  elif tr['status']=='unresolved':
   valid=False;reject['unresolved_position']+=1;break
  else:
   take=True;n+=1;net=tr['net_cents'];profit+=net;worst=min(worst,net);lowest=min(lowest,eq+tr['worst_open_cents']);dd=max(dd,peak-(eq+tr['worst_open_cents']-external),tr['within_trade_drawdown_cents']);peak=max(peak,eq+tr['best_open_cents']-external);eq+=net;peak=max(peak,eq-external);dd=max(dd,peak-(eq-external));months[month]['trades']+=1;months[month]['net_cents']+=net;weekdays[date.fromisoformat(day).isocalendar()[:2]]+=1
  streak=0 if take else streak+1;max_streak=max(max_streak,streak)
 allweeks={date.fromisoformat(d).isocalendar()[:2] for d in days}
 return {'width':w,'profile':profile,'mask':mask,'fee_location':fee_location,'floor':floor/100,'complete':valid,'sessions':len(days),'trades':n,'trading_net':money(profit),'subscription':money(bills),'customer_net':money(profit-bills),'ending_broker_equity':money(eq),'worst_trade':money(worst),'sampled_economic_drawdown':money(dd),'lowest_broker_equity':money(lowest),'zero_trade_weeks':len(allweeks-set(weekdays)),'longest_no_trade_sessions':max_streak,'monthly':months,'rejections':dict(reject),'qualification':'RETROSPECTIVE_ONLY' if valid else 'INCOMPLETE_NOT_RANKABLE'}

class Feed:
 def __init__(self):
  self.n=0;self.start=time.monotonic();self.manifest=[];self.root=pathlib.Path('/tmp/flame_reset')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]);self.root.mkdir(parents=True,exist_ok=False)
 def get(self,path,p):
  if path not in ('/v3/stock/history/ohlc','/v3/option/history/quote'):raise DataError('endpoint')
  for attempt in range(3):
   if self.n>=SPEC['max_requests'] or time.monotonic()-self.start>SPEC['deadline_seconds']:raise DataError('research_budget_exhausted')
   self.n+=1;fp=self.root/f'{self.n:03d}.csv';count=0;h=hashlib.sha256();err=None
   try:
    with requests.get(BASE+path,params=p,headers={'Cache-Control':'no-cache, no-store','Pragma':'no-cache'},timeout=(8,20),stream=True,allow_redirects=False) as r:
     r.raise_for_status()
     if r.status_code!=200 or r.headers.get('X-Market-Data-Provider')!='thetadata':raise DataError('wrong_provider')
     if path.endswith('/ohlc') and r.headers.get('X-Bar-Timestamp')!='interval-start':raise DataError('unknown_bar_semantics')
     with fp.open('wb') as f:
      for chunk in r.iter_content(65536):
       count+=len(chunk)
       if count>SPEC['max_bytes_per_response']:raise DataError('response_size_budget')
       h.update(chunk);f.write(chunk)
    rec={'request':self.n,'path':path,'params':p,'bytes':count,'sha256':h.hexdigest()};self.manifest.append(rec);emit('source',**rec)
    return fp
   except (requests.ConnectionError,requests.Timeout) as e:err=type(e).__name__
   except requests.HTTPError as e:
    if e.response is None or e.response.status_code not in (502,503,504):raise
    err='HTTP_'+str(e.response.status_code)
   if attempt==2:raise DataError('transport_failed:'+str(err))
   emit('retry',request=self.n,kind=err);time.sleep(2*(attempt+1))
 def day(self,day):
  p={'symbol':'SPY','date':day,'interval':'1m','start_time':'09:30:00','end_time':'12:00:00','venue':'utp_cta'}
  fp=self.get('/v3/stock/history/ohlc',p)
  with fp.open() as f:stock=stock_rows(csv.DictReader(f),day)
  reg=regime(stock)
  p={'symbol':'SPY','date':day,'expiration':day,'right':'put','strike':'*','interval':'1m','start_time':'12:00:00','end_time':'15:45:00'}
  fp=self.get('/v3/option/history/quote',p)
  with fp.open() as f:data,coverage=parse_options(csv.DictReader(f),day,reg['spot_units'])
  return reg,data,coverage

def execute():
 STATE['stage']='running';feed=Feed();days=session_days();results={};checked=0
 config_hash=hashlib.sha256(json.dumps(SPEC,sort_keys=True,separators=(',',':')).encode()).hexdigest();emit('spec',configuration=SPEC,sha256=config_hash)
 try:
  for day in days:
   reg,data,coverage=feed.day(day);trades={};ledger=[]
   for w in SPEC['widths_dollars']:
    k=choose(data,reg['spot_units'],w)
    for profile,slip in SPEC['profiles_units'].items():
     if k is None:continue
     rec=replay(data,k,w,slip);agrees(rec,reference(data,k,w,slip));checked+=1;trades[(w,profile)]=rec;ledger.append(dict(profile=profile,**rec))
   results[day]={'regime':reg,'trades':trades};emit('day',day=day,regime=reg,coverage=coverage,trades=ledger)
   (feed.root/'progress.json').write_text(json.dumps({'complete_days':list(results),'oracle_comparisons':checked}))
  totals=[]
  for w in SPEC['widths_dollars']:
   for profile in SPEC['profiles_units']:
    for mask in SPEC['masks']:
     for location in SPEC['fee_locations']:
      for floor in SPEC['admission_floors_cents']:
       rec=account(days,results,w,profile,mask,location,floor);totals.append(rec)
  (feed.root/'summaries.json').write_text(json.dumps(totals,indent=2));STATE['stage']='complete'
  for r in totals:
   if r['fee_location']=='external':emit('summary',**r)
  emit('complete',days=len(results),oracle_comparisons=checked,scenarios=len(totals),prior_inputs=0,provider_requests=feed.n,regimes=dict(Counter(r['regime']['label'] for r in results.values())),raw_exported=False)
 except Exception as e:
  STATE['stage']='failed';emit('failed',kind=type(e).__name__,reason=str(e)[:300],completed_days=len(results),provider_requests=feed.n)
 finally:
  (feed.root/'spec.json').write_text(json.dumps(SPEC,indent=2));(feed.root/'manifest.json').write_text(json.dumps(feed.manifest,indent=2));(feed.root/'daily.json').write_text(json.dumps({d:{'regime':r['regime'],'trades':[{**v,'profile':p} for (w,p),v in r['trades'].items()]} for d,r in results.items()},indent=2))

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(json.dumps({'research_only':True,**STATE}).encode())
 def log_message(self,*a):pass

if __name__=='__main__':
 if os.getenv('FLAME_FRESH_MODE')=='reset-regime-v1' and datetime.now(timezone.utc)<datetime.fromisoformat('2026-09-23T23:30:00+00:00'):
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
