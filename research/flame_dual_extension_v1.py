"""Isolated fixed-rule Flame extension. Never imports brokers or production DBs.

Fresh source observations only. Portfolio decisions use no future P&L. Primary
legacy governor uses realized equity; marked-equity sensitivity is separate.
EBB retains the earlier theoretical expiry-payoff convention (last 5m close),
NOT a representation of physical exercise/assignment or broker liquidation.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, os, pathlib, random, threading, time, uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo
import requests

U = 10000
ET = ZoneInfo('America/New_York')
BASE = 'http://thetadata-proxy:10000'
VIX_URL = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'
SPEC = {
    'id': 'flame-dual-extension-v1-20260924',
    'start': '2025-06-02', 'end': '2026-08-31', 'expected_sessions': 314,
    'closures': ['2025-06-19','2025-07-04','2025-09-01','2025-11-27','2025-12-25',
                 '2026-01-01','2026-01-19','2026-02-16','2026-04-03','2026-05-25',
                 '2026-06-19','2026-07-03'],
    'early_closes': ['2025-07-03','2025-11-28','2025-12-24'],
    'early_close_policy': 'no_entries_either_engine; billed_month_retained',
    'symbol': 'SPY', 'right': 'put', 'dte': 0, 'contracts': 1,
    'research': {'decision_et':720,'entry_et':721,'exit_et':945,'efficiency_min':'0.30',
                 'efficiency_bars':12,'width':2,'credit_min_pct':25,'credit_max_pct':40,
                 'credit_target_pct':30,'quote_width_max_units':1000,
                 'strike_search_dollars':20,'target_capture_pct':50,'stop_debit_multiple':2},
    'ebb': {'decision_et':845,'entry_et':846,'exit_et':960,'offset':'1','width':2,
            'vix_decay_ceiling':'0.80','vix_prior_window':20,'minimum_credit_units':1000,
            'stop':None,'target':None,'exit':'last_full_5m_bar_close_intrinsic_proxy'},
    'initial_equity_cents':200000,'fee_cents_roundtrip':260,'monthly_fee_cents':5000,
    'portfolio_risk_pct':10,'primary_fee_location':'external','floor_cents':0,
    'profiles':{'natural':0,'adverse3c':300},
    'execution':'fixed_contracts_at_signal; next_minute_natural_leg_quotes; no_perfect_target_fills',
    'quote_age':'interval_snapshot_age_not_verified',
    'clustering':'descriptive_only; fixed_bins; no_admission_rules_selected_from_extension',
    'validation':'temporal_extension; not pristine holdout for historically selected EBB',
    'max_requests':2400,'max_bytes_per_response':35000000,'deadline_seconds':2700,
    'workers':2,'prior_price_inputs':0,'prior_trade_inputs':0,
}
STATE = {'stage':'disabled','completed_sessions':0}

def emit(event, **kw):
    print('FLAME_EXT '+json.dumps({'event':event,'utc':datetime.now(timezone.utc).isoformat(),**kw},
          default=str,sort_keys=True,separators=(',',':')),flush=True)

def cents(x):
    return int(D(x).quantize(D('1'),rounding=ROUND_HALF_UP))

def dollars(x):
    return round(float(D(x)/100),2)

def units(raw):
    x = D(str(raw))*U
    if not x.is_finite() or x != x.to_integral_value():
        raise ValueError('invalid_option_price_precision')
    return int(x)

def minute(raw, day):
    t = datetime.fromisoformat(str(raw).replace('Z','+00:00'))
    t = t.replace(tzinfo=ET) if t.tzinfo is None else t.astimezone(ET)
    if t.date().isoformat()!=day or t.second or t.microsecond:
        raise ValueError('wrong_timestamp')
    return t.hour*60+t.minute

def clock(m):
    return '%02d:%02d:00' % divmod(m,60)

def calendar_days():
    d=date.fromisoformat(SPEC['start']); end=date.fromisoformat(SPEC['end']); out=[]
    while d<=end:
        if d.weekday()<5 and d.isoformat() not in SPEC['closures']: out.append(d.isoformat())
        d+=timedelta(days=1)
    assert len(out)==SPEC['expected_sessions']
    return out

class Feed:
    def __init__(self):
        self.root=pathlib.Path('/tmp')/('flame-ext-'+uuid.uuid4().hex)
        self.root.mkdir(exist_ok=False)
        self.lock=threading.Lock(); self.n=0; self.manifest=[]
        self.deadline=time.monotonic()+SPEC['deadline_seconds']
    def get(self,path,params):
        if path not in ('/v3/stock/history/ohlc','/v3/option/history/quote'):
            raise ValueError('endpoint_forbidden')
        for attempt in range(3):
            with self.lock:
                if self.n>=SPEC['max_requests'] or time.monotonic()>self.deadline:
                    raise RuntimeError('request_budget_exhausted')
                self.n+=1; number=self.n
            try:
                r=requests.get(BASE+path,params=params,headers={'Cache-Control':'no-cache, no-store',
                      'Pragma':'no-cache'},timeout=(8,60),allow_redirects=False)
                r.raise_for_status()
                if r.status_code!=200 or r.headers.get('X-Market-Data-Provider')!='thetadata':
                    raise ValueError('provider_not_verified')
                if path.endswith('/ohlc') and r.headers.get('X-Bar-Timestamp')!='interval-start':
                    raise ValueError('bar_timestamp_not_verified')
                if len(r.content)>SPEC['max_bytes_per_response']: raise ValueError('size_limit')
                raw=r.content; (self.root/('%04d.raw'%number)).write_bytes(raw)
                rec={'number':number,'path':path,'params':params,'bytes':len(raw),
                     'sha256':hashlib.sha256(raw).hexdigest()}
                with self.lock: self.manifest.append(rec)
                emit('source',**rec)
                rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                if not rows: raise ValueError('empty_provider_response')
                return rows
            except (requests.ConnectionError,requests.Timeout):
                if attempt==2: raise
            except requests.HTTPError as e:
                if attempt==2 or e.response is None or e.response.status_code not in (429,502,503,504): raise
            emit('retry',request=number,attempt=attempt+1)
            time.sleep(2*(attempt+1))
        raise AssertionError('unreachable')

def vix_history(feed):
    r=requests.get(VIX_URL,headers={'Cache-Control':'no-cache, no-store'},timeout=30)
    r.raise_for_status(); raw=r.content; (feed.root/'vix.raw').write_bytes(raw)
    out={}
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        day=datetime.strptime(row['DATE'],'%m/%d/%Y').date().isoformat()
        x=D(row['CLOSE'])
        if not x.is_finite() or x<=0 or day in out: raise ValueError('invalid_vix_history')
        out[day]=x
    sha=hashlib.sha256(raw).hexdigest()
    emit('vix_source',sha256=sha,rows=len(out),source=VIX_URL)
    return sorted(out.items()),sha

def stock_day(feed,day):
    rows=feed.get('/v3/stock/history/ohlc',{'symbol':'SPY','date':day,'interval':'5m',
          'start_time':'09:30:00','end_time':'16:00:00','venue':'utp_cta'})
    out={}
    for row in rows:
        m=minute(row['timestamp'],day)
        if m==960: continue
        if row.get('symbol')!='SPY' or m in out or m not in range(570,960,5):
            raise ValueError('stock_identity_or_grid')
        v={k:D(str(row[k])) for k in ('open','high','low','close','volume')}
        if not all(v[k].is_finite() and v[k]>0 for k in ('open','high','low','close')) or not v['volume'].is_finite() or v['volume']<0:
            raise ValueError('invalid_stock_value')
        eps=D('1e-10')
        if v['low']-min(v['open'],v['close'])>eps or max(v['open'],v['close'])-v['high']>eps:
            raise ValueError('invalid_ohlc')
        out[m]=v
    if sorted(out)!=list(range(570,960,5)): raise ValueError('missing_stock_grid')
    return out

def features(stock,decision):
    b=[stock[m] for m in range(570,decision,5)]; c=[v['close'] for v in b]
    move=c[-1]-c[-13]; travel=sum(abs(y-x) for x,y in zip(c[-13:-1],c[-12:]))
    eff=abs(move)/travel if travel else D(0)
    sma=sum(c[-20:])/20; lag=sum(c[-23:-3])/20
    tr=[max(b[i]['high']-b[i]['low'],abs(b[i]['high']-c[i-1]),abs(b[i]['low']-c[i-1])) for i in range(1,len(b))]
    calm=2*sum(tr[-6:])<=sum(tr[-18:-6])
    label='transition'
    if c[-1]>sma>lag and move>0 and eff>=D('.3'): label='uptrend'
    elif c[-1]<sma<lag and move<0 and eff>=D('.3'): label='downtrend'
    elif eff<=D('.2') and calm: label='calm_range'
    return {'efficiency':str(eff),'direction':'up' if move>0 else 'down' if move<0 else 'flat',
            'regime':label,'calm':calm,'spot':str(c[-1]),
            'return_from_open_pct':str(100*(c[-1]/b[0]['open']-1)),
            'last_hour_range_pct':str(100*(max(x['high'] for x in b[-12:])-min(x['low'] for x in b[-12:]))/c[-1])}

def vix_gate(history,day):
    prior=[x for x in history if x[0]<day]
    if len(prior)<21: raise ValueError('vix_history_short')
    p=prior[-1][1]; mx=max(x[1] for x in prior[-21:-1]); ratio=p/mx
    return {'ok':ratio<=D('.80'),'prior':str(p),'window_max':str(mx),'ratio':str(ratio),
            'prior_date':prior[-1][0]}

class DayQuotes:
    def __init__(self,feed,day): self.feed=feed; self.day=day; self.same_run={}; self.invalid=Counter()
    def get(self,strike,start,end):
        key=(strike,start,end)
        if key in self.same_run:return self.same_run[key]
        rows=self.feed.get('/v3/option/history/quote',{'symbol':'SPY','date':self.day,
            'expiration':self.day,'right':'put','strike':str(strike),'interval':'1m',
            'start_time':clock(start),'end_time':clock(end)})
        out={};seen=set()
        for row in rows:
            if row.get('symbol')!='SPY' or row.get('right','').lower() not in ('p','put') or row.get('expiration','')[:10].replace('-','')!=self.day.replace('-',''):
                raise ValueError('wrong_option_identity')
            m=minute(row['timestamp'],self.day)
            if not start<=m<=end:raise ValueError('option_outside_request')
            k=units(row['strike'])
            if strike!='*' and k!=units(strike):raise ValueError('wrong_strike')
            if (k,m) in seen:raise ValueError('duplicate_quote')
            seen.add((k,m))
            try:
                bid,ask=units(row['bid']),units(row['ask']); bs=D(row['bid_size']);az=D(row['ask_size'])
                if not bs.is_finite() or not az.is_finite() or bid<0 or ask<=0 or ask<bid or bs<1 or az<1:
                    raise ValueError('invalid_or_no_size')
            except (ValueError,ArithmeticError):
                self.invalid['unusable_rows']+=1;continue
            out.setdefault(k,{})[m]=(bid,ask,int(bs),int(az))
        self.same_run[key]=out
        return out
    def legs(self,k,start,end):
        sh=self.get(D(k)/U,start,end).get(k,{})
        lo=self.get(D(k-2*U)/U,start,end).get(k-2*U,{})
        return {m:(sh[m][0]-lo[m][1],sh[m][1]-lo[m][0],
                    sh[m][1]-sh[m][0]+lo[m][1]-lo[m][0]) for m in sh.keys() & lo.keys()}

def choose_research(q,spot):
    candidates=[]
    for k,minutes in q.items():
        if not (spot-20)*U<=k<spot*U:continue
        a=minutes.get(720);b=q.get(k-2*U,{}).get(720)
        if a is None or b is None:continue
        credit=a[0]-b[1];wide=a[1]-a[0]+b[1]-b[0]
        if 5000<=credit<=8000 and wide<=1000:
            candidates.append((abs(credit-6000),wide,k))
    return min(candidates)[2] if candidates else None

def research_path(quotes,k,slip):
    if 721 not in quotes:return {'status':'skip','reason':'entry_quote_missing'}
    credit=quotes[721][0]-slip
    if not 5000<=credit<=8000:return {'status':'skip','reason':'entry_credit_changed'}
    if quotes[721][2]>1000:return {'status':'skip','reason':'entry_spread_widened'}
    fee=SPEC['fee_cents_roundtrip']; marks={};reason=None
    for m in range(721,945):
        if m not in quotes: return {'status':'unresolved','reason':'open_quote_gap','minute':m}
        debit=quotes[m][1]+slip
        if debit<0:return {'status':'unresolved','reason':'negative_debit'}
        marks[m]=credit-debit-fee
        reason='stop' if debit>=2*credit else 'target' if 2*debit<=credit else 'time' if m==944 else None
        if reason:
            end=m+1
            if end not in quotes:return {'status':'unresolved','reason':'exit_quote_gap'}
            close=quotes[end][1]+slip
            if close<0:return {'status':'unresolved','reason':'negative_exit'}
            net=credit-close-fee;marks[end]=net
            oracle=cents(((D(credit)/U-D(close)/U)*100-D(fee)/100)*100)
            assert net==oracle
            return {'status':'trade','engine':'research','short_units':k,'width':2,
                    'entry':721,'exit':end,'credit_units':credit,'net_cents':net,
                    'risk_cents':20000-credit+fee,'reason':reason,'marks':marks,
                    'best_open_cents':max([0]+list(marks.values())),
                    'worst_open_cents':min([0]+list(marks.values()))}
    raise AssertionError('research_no_exit')

def ebb_path(quotes,k,spot_close,slip):
    if 846 not in quotes:return {'status':'skip','reason':'entry_quote_missing'}
    credit=quotes[846][0]-slip;fee=SPEC['fee_cents_roundtrip']
    if not 1000<=credit<20000:return {'status':'skip','reason':'ebb_credit_out_of_range'}
    intrinsic=max(D(0),min(D(20000),D(k)-spot_close*U))
    net=cents(D(credit)-intrinsic-fee)
    oracle=cents(((D(credit)/U-max(D(0),min(D(2),D(k)/U-spot_close)))*100-D(fee)/100)*100)
    assert net==oracle
    marks={m:credit-quotes[m][1]-fee for m in range(846,960) if m in quotes and quotes[m][1]>=0}
    gaps=[m for m in range(846,960) if m not in marks]
    marks[960]=net
    return {'status':'trade','engine':'ebb','short_units':k,'width':2,'entry':846,'exit':960,
            'credit_units':credit,'risk_cents':20000-credit+fee,'net_cents':net,
            'reason':'expiry_proxy','marks':marks,'mark_gaps':gaps,
            'close_proxy':str(spot_close),'full_payoff_loss':intrinsic>=20000,
            'between_strikes_at_close':0<intrinsic<20000,
            'best_open_cents':max([0]+list(marks.values())),
            'worst_open_cents':min([0]+list(marks.values()))}

def run_day(feed,history,day):
    if day in SPEC['early_closes']:return {'day':day,'early_close':True,'profiles':{}}
    stock=stock_day(feed,day);dq=DayQuotes(feed,day);vg=vix_gate(history,day)
    rf=features(stock,720);ef=features(stock,845);rquotes=None;equotes=None;k=None;ek=None
    if D(rf['efficiency'])>=D('.30'):
        k=choose_research(dq.get('*',720,720),D(rf['spot']))
        if k is not None:rquotes=dq.legs(k,721,945)
    if vg['ok']:
        ek=int((D(ef['spot'])-1).quantize(D(1),rounding=ROUND_HALF_UP)*U)
        equotes=dq.legs(ek,846,959)
    prof={}
    for name,slip in SPEC['profiles'].items():
        r=research_path(rquotes,k,slip) if rquotes is not None else {'status':'skip','reason':'efficiency' if D(rf['efficiency'])<D('.30') else 'no_research_candidate'}
        e=ebb_path(equotes,ek,stock[955]['close'],slip) if equotes is not None else {'status':'skip','reason':'vix_gate'}
        prof[name]={'research':r,'ebb':e}
    return {'day':day,'profiles':prof,'research_features':rf,'ebb_features':ef,'vix':vg,'quote_quality':dict(dq.invalid)}

def summarize_account(days,results,engines,cap=10,marked=False,fee_location='external',profile='natural',floor=0):
    eq=SPEC['initial_equity_cents'];peak=eq;dd=0;netpeak=eq;netdd=0;profit=0;bills=0
    lastmonth=None;accept=[];blocked=[];monthrows={};min_eq=eq;marks_complete=True;valid=True
    for day in days:
        month=day[:7]
        if month!=lastmonth:
            bills+=5000
            if fee_location=='account':eq-=5000
            lastmonth=month
            monthrows[month]={'trades':0,'trading_cents':0,'customer_cents':-5000}
        row=results.get(day)
        if row is None or row.get('error'):valid=False;continue
        if row.get('early_close'):continue
        ts=[row['profiles'][profile][key] for key in engines];active=[]
        if any(t.get('status')=='unresolved' for t in ts):valid=False
        good=[t for t in ts if t.get('status')=='trade']
        for m in range(720,961):
            for tr in list(active):
                if tr['exit']==m:
                    eq+=tr['net_cents'];profit+=tr['net_cents'];active.remove(tr)
                    monthrows[month]['trading_cents']+=tr['net_cents'];monthrows[month]['customer_cents']+=tr['net_cents']
            for tr in good:
                if tr['entry']!=m:continue
                mark_known=all(m in x['marks'] for x in active)
                unrl=sum(x['marks'].get(m,0) for x in active)
                budget_eq=eq+unrl if marked else eq
                risk=sum(x['risk_cents'] for x in active)+tr['risk_cents']
                reason='unknown_open_mark' if marked and not mark_known else 'equity_floor' if budget_eq<floor else 'open_risk_cap' if cap is not None and 100*risk>cap*budget_eq else None
                if reason:
                    blocked.append({'day':day,'engine':tr['engine'],'reason':reason,
                                    'net_cents':tr['net_cents'],'research_open':any(x['engine']=='research' for x in active)})
                    continue
                active.append(tr);accept.append({'day':day,**{k:v for k,v in tr.items() if k!='marks'}})
                monthrows[month]['trades']+=1
            if all(m in x['marks'] for x in active):
                value=eq+sum(x['marks'][m] for x in active)
                economic=value-bills if fee_location=='external' else value
                peak=max(peak,value);dd=max(dd,peak-value)
                netpeak=max(netpeak,economic);netdd=max(netdd,netpeak-economic);min_eq=min(min_eq,value)
            else: marks_complete=False
        assert not active
    wins=sum(x['net_cents']>0 for x in accept);losses=sum(x['net_cents']<0 for x in accept)
    engine_counts=Counter(x['engine'] for x in accept)
    weeks=defaultdict(int)
    for d in days:weeks[date.fromisoformat(d).isocalendar()[:2]]+=0
    for t in accept:weeks[date.fromisoformat(t['day']).isocalendar()[:2]]+=1
    return {'engines':list(engines),'cap':cap,'marked_budget':marked,'profile':profile,'fee_location':fee_location,
            'floor':floor,'sessions':len(days),'complete':valid,'mark_coverage_complete':marks_complete,
            'trades':len(accept),'wins':wins,'losses':losses,'engine_counts':dict(engine_counts),
            'trading_net':dollars(profit),'subscription':dollars(bills),'customer_net':dollars(profit-bills),
            'ending_broker_equity':dollars(eq),'minimum_marked_equity':dollars(min_eq),
            'mtm_drawdown_observed':dollars(dd),'customer_mtm_drawdown_observed':dollars(netdd),
            'blocked_count':len(blocked),'blocked_pnl':dollars(sum(t['net_cents'] for t in blocked)),
            'blocked_reasons':dict(Counter(x['reason'] for x in blocked)),
            'average_trades_per_week':round(len(accept)/len(weeks),2),'empty_weeks':sum(v==0 for v in weeks.values()),
            'months':{k:{'trades':v['trades'],'trading_net':dollars(v['trading_cents']),
                          'customer_net':dollars(v['customer_cents'])} for k,v in monthrows.items()},
            'blocked':blocked}

def score(items):
    n=len(items); w=[t for t in items if t['net_cents']>0];l=[t for t in items if t['net_cents']<0]
    return {'n':n,'wins':len(w),'losses':len(l),'loss_rate':round(len(l)/n,4) if n else None,
            'net':dollars(sum(t['net_cents'] for t in items)),
            'gross_losses':dollars(-sum(t['net_cents'] for t in l)),
            'average_win':dollars(sum(t['net_cents'] for t in w)/len(w)) if w else None,
            'average_loss':dollars(sum(t['net_cents'] for t in l)/len(l)) if l else None}

def band(x,edges):
    x=D(str(x))
    for limit in edges:
        if x<D(str(limit)):return '<'+str(limit)
    return '>='+str(edges[-1])

def clusters(days,results,engine):
    items=[]
    for day in days:
        row=results.get(day,{})
        if row.get('error') or row.get('early_close') or not row:continue
        tr=row['profiles']['natural'][engine]
        if tr.get('status')!='trade':continue
        f=row[engine+'_features'];r=row['profiles']['natural']['research']
        priorstate='none'
        if engine=='ebb' and r.get('status')=='trade':
            priorstate='research_open' if r['exit']>846 else 'research_closed_win' if r['net_cents']>0 else 'research_closed_loss'
        items.append({'day':day,**{k:v for k,v in tr.items() if k!='marks'},'month':day[:7],
            'weekday':date.fromisoformat(day).strftime('%a'),'direction':f['direction'],'regime':f['regime'],
            'eff_bin':band(f['efficiency'],[.2,.3,.5,.7]),
            'vix_level_bin':band(row['vix']['prior'],[15,20,30]),
            'vix_decay_bin':band(row['vix']['ratio'],[.5,.65,.8,1]),
            'range_bin':band(f['last_hour_range_pct'],[.25,.5,1]),'research_state':priorstate})
    out={'engine':engine,'total':score(items)}
    for col in ('month','weekday','direction','regime','eff_bin','vix_level_bin','vix_decay_bin','range_bin','research_state'):
        groups=defaultdict(list)
        for t in items:groups[t[col]].append(t)
        out[col]={k:score(v) for k,v in sorted(groups.items())}
    losses=[t for t in items if t['net_cents']<0];seq=[int(t['net_cents']<0) for t in items]
    def ll(s):return sum(a==b==1 for a,b in zip(s,s[1:]))
    def streak(s):
        best=current=0
        for x in s:current=current+1 if x else 0;best=max(best,current)
        return best
    observed=ll(seq);rng=random.Random(24092026);hits=0
    for _ in range(2000):
        shuffled=seq[:];rng.shuffle(shuffled);hits+=ll(shuffled)>=observed
    afterloss=[items[i] for i in range(1,len(items)) if seq[i-1]]
    afterwin=[items[i] for i in range(1,len(items)) if not seq[i-1]]
    out['sequence']={'after_loss':score(afterloss),'after_win':score(afterwin),
                     'longest_loss_streak':streak(seq),'adjacent_loss_pairs':observed,
                     'permutation_p_extra_loss_pairs':round((hits+1)/2001,4),
                     'interpretation':'exploratory one-sided permutation; not proof of a stable predictive edge'}
    out['worst_trades']=[{k:t[k] for k in ('day','net_cents','reason','credit_units','direction','regime','eff_bin','vix_level_bin','vix_decay_bin','research_state')} for t in sorted(losses,key=lambda x:x['net_cents'])[:10]]
    out['full_payoff_losses']=sum(t.get('full_payoff_loss',False) for t in items)
    out['assignment_sensitive_closes']=sum(t.get('between_strikes_at_close',False) for t in items)
    out['top5_loss_share']=round(sum(-t['net_cents'] for t in sorted(losses,key=lambda x:x['net_cents'])[:5])/sum(-t['net_cents'] for t in losses),4) if losses else None
    out['winners_then_losers']=sum(t['best_open_cents']>=1000 for t in losses)
    return out

def self_test():
    assert units('.60')-units('.40')==2000
    assert cents(D('-5959.999999999'))==-5960
    assert len(calendar_days())==314
    q={m:(6000,10000,200) for m in range(721,946)}
    q[725]=(6000,3000,200);q[726]=(6000,3200,200)
    tr=research_path(q,5800000,0)
    assert (tr['exit'],tr['net_cents'],tr['reason'])==(726,2540,'target')
    for close,net in [(D('580'),5740),(D('579.16'),-2660),(D('577'),-14260)]:
        e=ebb_path({m:(6000,6100,100) for m in range(846,960)},5800000,close,0)
        assert e['net_cents']==net
    day='2025-06-02'
    r={'status':'trade','engine':'research','entry':721,'exit':900,'risk_cents':14000,'net_cents':-6000,'marks':{m:-6000 for m in range(721,901)}}
    e={'status':'trade','engine':'ebb','entry':846,'exit':960,'risk_cents':16000,'net_cents':5000,'marks':{m:0 for m in range(846,960)}};e['marks'][960]=5000
    data={day:{'profiles':{'natural':{'research':r,'ebb':e}}}}
    s=summarize_account([day],data,('research','ebb'),10)
    assert s['trades']==1 and s['blocked_count']==1 and s['trading_net']==-60
    s=summarize_account([day],data,('research','ebb'),None)
    assert s['trading_net']==-10 and s['mtm_drawdown_observed']>=60
    r['exit']=800;r['marks']={m:0 for m in range(721,801)};r['net_cents']=3000
    s=summarize_account([day],data,('research','ebb'),10)
    assert s['trades']==2 and s['trading_net']==80
    r['exit']=900;r['marks']={m:0 for m in range(721,901)}
    r['net_cents']=99999
    a=summarize_account([day],data,('research','ebb'),10)['blocked_count']
    r['net_cents']=-99999
    b=summarize_account([day],data,('research','ebb'),10)['blocked_count']
    assert a==b==1
    return {'passed':True,'cases':'exact money, thresholds, payoff, calendar, overlap, event order, no future-PnL admission'}

def execute():
    STATE['stage']='running';feed=Feed();days=calendar_days();results={};failures=[]
    spec_hash=hashlib.sha256(json.dumps(SPEC,sort_keys=True).encode()).hexdigest()
    try:
        emit('self_test',**self_test());history,vix_sha=vix_history(feed)
        emit('frozen_spec',spec=SPEC,sha256=spec_hash,output_dir=str(feed.root))
        def task(day):
            try:return run_day(feed,history,day)
            except Exception as exc:return {'day':day,'error':type(exc).__name__+':'+str(exc)[:180]}
        with ThreadPoolExecutor(max_workers=SPEC['workers']) as pool:
            for row in pool.map(task,days):
                day=row['day'];results[day]=row;STATE['completed_sessions']=len(results)
                if row.get('error'):failures.append({'day':day,'error':row['error']});emit('data_error',**failures[-1])
                compact={k:v for k,v in row.items() if k!='profiles'}
                compact['profiles']={p:{e:{k:v for k,v in t.items() if k!='marks'} for e,t in es.items()} for p,es in row.get('profiles',{}).items()}
                emit('day',**compact)
                if len(results)%25==0:emit('progress',completed=len(results),last=day,requests=feed.n,errors=len(failures))
        summaries=[]
        cases=[(('research',),10,False,'external',0),(('ebb',),10,False,'external',0),
               (('research','ebb'),10,False,'external',0),(('research','ebb'),10,True,'external',0),
               (('research','ebb'),None,False,'external',0),(('research','ebb'),10,True,'account',0),
               (('research','ebb'),10,True,'external',200000)]
        for profile in SPEC['profiles']:
            for es,cap,marked,location,floor in cases:
                s=summarize_account(days,results,es,cap,marked,location,profile,floor);summaries.append(s)
                emit('account',**s)
        analyses=[clusters(days,results,e) for e in ('research','ebb')]
        for a in analyses:
            emit('cluster',**a)
        report={'spec':SPEC,'spec_sha256':spec_hash,'vix_sha256':vix_sha,'summaries':summaries,'clusters':analyses,'errors':failures,'requests':feed.n}
        (feed.root/'report.json').write_text(json.dumps(report,default=str,indent=2))
        STATE['stage']='complete' if not failures and all(s['complete'] for s in summaries) else 'incomplete'
        emit('complete',stage=STATE['stage'],sessions=len(results),provider_requests=feed.n,errors=failures,
             prior_price_inputs=0,prior_trade_inputs=0,spec_sha256=spec_hash)
    except Exception as exc:
        STATE['stage']='failed';emit('failed',kind=type(exc).__name__,reason=str(exc)[:300],sessions=len(results))
    finally:
        (feed.root/'manifest.json').write_text(json.dumps(feed.manifest,indent=2))
        (feed.root/'daily.json').write_text(json.dumps(results,default=str))
        (feed.root/'spec.json').write_text(json.dumps(SPEC,indent=2))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'research_only':True,**STATE}).encode())
    def log_message(self,*args):pass

if __name__=='__main__':
    if os.getenv('FLAME_FRESH_MODE')=='dual-extension-v1':
        threading.Thread(target=execute,daemon=True).start()
    HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
