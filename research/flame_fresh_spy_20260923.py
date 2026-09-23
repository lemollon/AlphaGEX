"""Isolated SPY research. Fresh provider reads only. No broker orders or database access."""
from __future__ import annotations
import csv, hashlib, io, json, math, os, pathlib, threading, time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo
import requests
ET = ZoneInfo('America/New_York')
OUT = pathlib.Path('/tmp/flame_fresh_study')
OUT.mkdir(exist_ok=True)
STATE = {'stage': 'not_started'}
SPEC = {'version': 'fresh-v2-15minute-source-pilot', 'symbol': 'SPY',
        'last_allowed_date': '2026-09-22', 'underlying_interval_minutes': 15,
        'pilot': 'all complete sessions from fresh 14-day broker response; never an OOS claim',
        'families': ['breakout_retest', 'failed_breakdown', 'trend_reclaim'],
        'widths': [1, 2], 'slippages_per_side': [0.01, 0.03],
        'roundtrip_fee': 2.60, 'initial_equity': 2000, 'monthly_subscription': 50,
        'min_credit_width_fraction': .20, 'max_credit_width_fraction': .45,
        'target_capture': .50, 'stop_debit_multiple': 2.0,
        'short': 'floor(min(completed_bar_close-0.25, completed_bar_low-0.05))',
        'risk_fraction': .10, 'entry_clock': ['10:15','14:30'], 'close_clock': '15:40',
        'max_entries_per_day': 2, 'cooldown_minutes': 15,
        'old_data_or_results_inputs': [], 'broker_permissions': 'unverified; floor scenarios separate'}
MANIFEST = []

def emit(event, **fields):
    print('FRESH_SPY ' + json.dumps({'event':event, 'utc':datetime.now(timezone.utc).isoformat(), **fields}, default=str), flush=True)

class DataError(RuntimeError): pass

def stamp(raw):
    d = datetime.fromisoformat(str(raw).replace('Z','+00:00'))
    return d.replace(tzinfo=ET) if d.tzinfo is None else d.astimezone(ET)

class Feed:
    def __init__(self):
        self.http=requests.Session()
        self.http.headers.update({'Cache-Control':'no-cache','User-Agent':'FlameFreshResearch/1.0'})
        self.raw_quotes={}; self.calls=0; self.deadline=time.monotonic()+600
    def get(self,url,params):
        if self.calls>=120 or time.monotonic()>self.deadline: raise DataError('bounded_request_budget_exhausted')
        self.calls+=1
        r=self.http.get(url,params=params,timeout=(10,75))
        h=hashlib.sha256(r.content).hexdigest()
        rec={'request':self.calls,'url':url,'params':params,'status':r.status_code,'sha256':h,'bytes':len(r.content),'retrieved':datetime.now(timezone.utc).isoformat()}
        MANIFEST.append(rec);(OUT/f'{self.calls:03d}.raw').write_bytes(r.content)
        emit('retrieval',**rec)
        r.raise_for_status();return r
    def stocks(self):
        # Inspected API returns data_as_of=None only for its fresh upstream path.
        j=self.get('https://spreadworks-backend.onrender.com/api/spreadworks/candles', {'symbol':'SPY','interval':'15min'}).json()
        if j.get('data_as_of') is not None: raise DataError('cached_stock_response_rejected')
        if j.get('symbol','').upper()!='SPY': raise DataError('wrong_underlying')
        days={}
        for r in j.get('candles',[]):
            dt=stamp(r['time']);day=dt.date().isoformat()
            if day>SPEC['last_allowed_date'] or not '09:30'<=dt.strftime('%H:%M')<'16:00':continue
            vals={k:float(r[k]) for k in ['open','high','low','close','volume']}
            if not all(math.isfinite(x) for x in vals.values()):raise DataError('nonfinite_stock_bar')
            if vals['low']>min(vals['open'],vals['close']) or vals['high']<max(vals['open'],vals['close']):raise DataError('invalid_stock_ohlc')
            days.setdefault(day,[]).append({'t':dt,**vals})
        clean={}
        for day,rs in sorted(days.items()):
            rs.sort(key=lambda x:x['t'])
            ok=len(rs)==26 and rs[0]['t'].strftime('%H:%M')=='09:30' and all((b['t']-a['t'])==timedelta(minutes=15) for a,b in zip(rs,rs[1:]))
            emit('stock_session',day=day,bars=len(rs),complete=ok)
            if ok:clean[day]=rs
        if not clean:raise DataError('no_complete_independent_stock_sessions')
        return clean
    def quotes(self,day,k):
        key=(day,k)
        if key in self.raw_quotes:return self.raw_quotes[key] # same-run raw observations, never old files/results
        p={'symbol':'SPY','expiration':day,'date':day,'strike':str(k),'right':'put','interval':'1m','start_time':'10:15:00','end_time':'15:41:00'}
        rows=list(csv.DictReader(io.StringIO(self.get('http://thetadata-proxy:10000/v3/option/history/quote',p).text)))
        if not rows:raise DataError('empty_option_response')
        result={};bad=0
        for r in rows:
            if 'symbol' in r and r['symbol'].upper()!='SPY':raise DataError('wrong_option_symbol')
            if 'strike' in r and abs(float(r['strike'])-k)>1e-6:raise DataError('wrong_option_strike')
            if 'expiration' in r and str(r['expiration'])[:10].replace('-','')!=day.replace('-',''):raise DataError('wrong_option_expiration')
            raw=r.get('timestamp')
            if raw is None:raise DataError('missing_quote_timestamp')
            dt=stamp(raw)
            if dt.date().isoformat()!=day:raise DataError('wrong_quote_day')
            b,a=float(r['bid']),float(r['ask'])
            bs,az=float(r.get('bid_size',0)),float(r.get('ask_size',0))
            if not all(math.isfinite(x) for x in [b,a,bs,az]) or b<0 or a<=0 or a<b or bs<1 or az<1:
                bad+=1;continue
            if dt in result:raise DataError('duplicate_quote_timestamp')
            result[dt]=(b,a)
        emit('quote_coverage',day=day,strike=k,received=len(rows),usable=len(result),rejected=bad,quote_age='source-update-time not verified')
        self.raw_quotes[key]=result;return result

def signals(bars,family):
    oh=max(r['high'] for r in bars[:2]);ol=min(r['low'] for r in bars[:2]);prev_on=False
    answer=[]
    for i in range(3,len(bars)):
        b,p=bars[i],bars[i-1];available=b['t']+timedelta(minutes=15)
        if not '10:15'<=available.strftime('%H:%M')<='14:30':continue
        bull=b['close']>b['open']
        if family=='breakout_retest':on=p['close']>oh and b['low']<=oh+.03 and b['close']>oh and bull
        elif family=='failed_breakdown':on=b['low']<ol and b['close']>ol and bull
        else:
            mean=sum(x['close'] for x in bars[max(0,i-4):i])/min(4,i)
            on=p['close']<mean and b['close']>mean and b['close']>bars[0]['open'] and bull
        if on and not prev_on:answer.append({'time':available,'short':math.floor(min(b['close']-.25,b['low']-.05))})
        prev_on=bool(on)
    return answer

def replay_trade(feed,day,signal,width,slip):
    qs,ql=feed.quotes(day,signal['short']),feed.quotes(day,signal['short']-width)
    t=signal['time'];t1=t+timedelta(minutes=1)
    def price(at):
        if at not in qs or at not in ql:return None
        s,l=qs[at],ql[at]
        return s[0]-l[1],s[1]-l[0],(s[1]-s[0])+(l[1]-l[0])
    a=price(t);f=price(t1)
    if a is None:return {'status':'skip','reason':'missing_signal_quotes'}
    if not .20*width<=a[0]<=.45*width or a[2]>.10:return {'status':'skip','reason':'entry_price_or_spread'}
    if f is None:return {'status':'skip','reason':'no_delayed_fill_quotes'}
    credit=f[0]-slip
    if not .20*width<=credit<=.45*width:return {'status':'skip','reason':'unfilled_credit_limit'}
    base={'status':'trade','date':day,'entry':t1,'short':signal['short'],'width':width,'credit':round(credit,6),'risk':round((width-credit)*100+2.60,6)}
    end=stamp(day+'T15:39:00');m=t1;gap=False;worst=0.0
    while m<=end:
        p=price(m)
        if p is None:gap=True;m+=timedelta(minutes=1);continue
        debit=p[1]+slip;worst=min(worst,(credit-debit)*100-2.60)
        reason='stop' if debit>=2*credit else 'target' if debit<=.5*credit else 'eod' if m==end else None
        if reason:
            x=price(m+timedelta(minutes=1))
            if x is None or gap:return {**base,'status':'unresolved','reason':'missing_post_entry_quote_path'}
            close=x[1]+slip
            if close<0 or close>width+.20:return {**base,'status':'unresolved','reason':'extreme_synthetic_closing_market'}
            net=round((credit-close)*100-2.60,2)
            return {**base,'exit':m+timedelta(minutes=1),'debit':round(close,6),'net':net,'reason':reason,'worst_open':round(min(worst,net),2)}
        m+=timedelta(minutes=1)
    return {**base,'status':'unresolved','reason':'no_valid_preexpiry_exit'}

def account(feed,days,family,width,slip,floor):
    eq=2000.0;peak=eq;dd=0.0;trades=[];blocked=0;errors=0;skips=0;weeks=set();minimum=eq
    for day,bars in days.items():
        count=0;next_at=bars[0]['t'];daily_net=0
        for sig in signals(bars,family):
            if count>=2 or sig['time']<next_at or daily_net<=-100:continue
            if eq<floor:blocked+=1;continue
            rec=replay_trade(feed,day,sig,width,slip)
            if rec['status']=='skip':skips+=1;continue
            if rec['risk']>eq*.10:blocked+=1;continue
            if rec['status']=='unresolved':errors+=1;emit('unresolved',family=family,slip=slip,floor=floor,**rec);break
            count+=1;trades.append(rec);next_at=rec['exit']+timedelta(minutes=15)
            minimum=min(minimum,eq+rec['worst_open']);eq=round(eq+rec['net'],2);daily_net+=rec['net']
            peak=max(peak,eq);dd=max(dd,peak-eq);weeks.add(rec['entry'].isocalendar()[:2])
            emit('trade',family=family,slip=slip,floor=floor,equity=eq,**rec)
        if errors:break # Do not silently replace an unresolved open risk with a flat account.
    months=len({d[:7] for d in days});profit=round(eq-2000,2)
    return {'family':family,'width':width,'slippage':slip,'floor_sensitivity':floor,'days':len(days),'trades':len(trades),'blocked_signals':blocked,'skipped_signals':skips,'unresolved':errors,'trading_net':profit,'external_subscriptions':50*months,'customer_net':round(profit-50*months,2),'ending_broker_equity':eq,'worst_closed':min([t['net'] for t in trades],default=0),'closed_drawdown_dollars':round(dd,2),'lowest_observed_intraday_equity':round(minimum,2),'active_weeks':len(weeks),'verdict':'INVALID_MISSING_PATH' if errors else 'PILOT_ONLY_NOT_VALIDATED'}

def run():
    mode=os.getenv('FLAME_FRESH_MODE','probe')
    if mode=='disabled':STATE['stage']='disabled';return
    if datetime.now(timezone.utc)>datetime.fromisoformat('2026-09-23T20:00:00+00:00'):STATE['stage']='expired';return
    STATE['stage']='retrieving';feed=Feed();emit('specification',spec=SPEC,mode=mode)
    try:
        # Both tests run independently, so a stock failure does not conceal option entitlement.
        feed.quotes('2026-09-22',770)
        days=feed.stocks();emit('fresh_data_ready',days=list(days),old_backtest_inputs=0)
        if mode=='pilot':
            summaries=[]
            for family in SPEC['families']:
                for width in SPEC['widths']:
                    for slip in SPEC['slippages_per_side']:
                        for floor in [2000,0]:
                            summary=account(feed,days,family,width,slip,floor);summaries.append(summary);emit('summary',**summary)
            (OUT/'results.json').write_text(json.dumps(summaries,indent=2))
        STATE['stage']='completed';emit('completed',mode=mode,requests=feed.calls)
    except Exception as e:
        STATE['stage']='blocked';emit('failed',kind=type(e).__name__,reason=str(e)[:250])
    finally:
        (OUT/'manifest.json').write_text(json.dumps(MANIFEST,indent=2));(OUT/'spec.json').write_text(json.dumps(SPEC,indent=2))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(json.dumps({'research_only':True,**STATE}).encode())
    def log_message(self,*args):pass

if __name__=='__main__':
    threading.Thread(target=run,daemon=True).start()
    HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
