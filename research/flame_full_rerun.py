"""Research-only regression suite. No broker, database, or saved-market-data reader.

All option prices are integer ten-thousandths of a dollar per share; for a
100-share option this is also cents per spread lot. Legacy float mode is an
explicit paired diagnostic, never the corrected engine. Fresh tapes are shared
only inside the current process. No historical result is an input.
"""
from __future__ import annotations
import csv, gzip, hashlib, io, json, math, os, pathlib, threading, time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, HTTPServer
from itertools import product
from zoneinfo import ZoneInfo
import requests

ET = ZoneInfo('America/New_York')
ROOT = pathlib.Path('/tmp/flame_corrected_rerun')
STATE = {'stage': 'disabled'}
U = 10000
FEE = 260
BASE = 'http://thetadata-proxy:10000'
WINDOWS = [('pilot', '2026-09-10', '2026-09-22'), ('discovery', '2026-03-09', '2026-05-22')]
PROFILE = [('natural', 0), ('stress3c', 300), ('stress5c', 500)]
# These are quote-model sensitivities, not calibrated expected customer fills.

class DataError(RuntimeError): pass

def emit(event, **fields):
    print('FLAME_RERUN ' + json.dumps(dict(event=event, utc=datetime.now(timezone.utc).isoformat(), **fields), default=str, separators=(',', ':')), flush=True)

def units(value):
    try: d = Decimal(str(value))
    except (InvalidOperation, ValueError) as e: raise DataError('invalid numeric field') from e
    if not d.is_finite(): raise DataError('nonfinite numeric field')
    n = d * U
    if n != n.to_integral_value(): raise DataError('option precision exceeds four decimals')
    return int(n)

def usd(n): return float(Decimal(n) / 100)

def minute(raw, day):
    dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    dt = dt.replace(tzinfo=ET) if dt.tzinfo is None else dt.astimezone(ET)
    if dt.date().isoformat() != day or dt.second or dt.microsecond: raise DataError('wrong minute or date')
    return dt.hour * 60 + dt.minute

def round_strike(spot):
    return int(Decimal(str(spot)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) * 100

@dataclass(frozen=True)
class Policy:
    name: str
    family: str
    width: int
    clock: int = 845             # Eastern minutes; default equals 13:05 Central
    otm: int = 1
    gate: int = 0                # percentage, zero means ungated
    pt: int = 50
    stop: int = 0
    flat: int = 955              # 15:55 Eastern / 14:55 Central
    hold: int = 0
    cap: int = 1
    cooldown: int = 10
    min_credit: int = 1000       # $0.10 per share, expressed exactly
    frac_min: int = 0
    frac_max: int = 0
    max_quote_spread: int = 0
    factor: int = 0
    min_dist: int = 1
    is_debit: bool = False
    pilot_only: bool = False


def registry():
    p=[]
    # Recovered 24 fixed/exit and 16 adaptive-distance definitions.
    cells=[('spark_current',665,2,5,90),('spark_selective',655,4,5,85),
           ('spark_active',655,4,5,95),('spark_ungated',655,4,5,0),
           ('flame_current',845,1,2,80),('flame_selective',845,1,3,75),
           ('flame_active',845,1,2,95),('flame_ungated',845,1,2,0)]
    for name,t,otm,w,g in cells:
        for pt,stop in [(0,0),(50,0),(50,2)]:
            p.append(Policy(f'{name}_pt{pt}_sl{stop}','fixed',w,t,otm,g,pt,stop))
    for bot,t,mind in [('spark',655,2),('flame',845,1)]:
        for fac,w,stop in product([75,100],[2,3],[0,3]):
            p.append(Policy(f'{bot}_adaptive_f{fac}_w{w}_sl{stop}','adaptive',w,t,pt=50,stop=stop,factor=fac,min_dist=mind))
    # Twelve standalone activity alternatives, retained as controls; call/debit
    # alternatives are not eligible for the requested SPY put-credit product.
    for fam,t,w in product(['trend_credit','trend_debit','range_credit'],[815,845],[2,3]):
        p.append(Policy(f'{fam}_t{t}_w{w}',fam,w,t,stop=2,is_debit=fam=='trend_debit'))
    for fam,w in product(['dual_credit','dual_debit'],[2,3]):
        p.append(Policy(f'{fam}_w{w}',fam,w,815,stop=2,is_debit=fam=='dual_debit'))
    for w,pt,cap in product([2,3],[15,25,50],[1,3]):
        p.append(Policy(f'multi_momentum_w{w}_pt{pt}_cap{cap}','multi_momentum',w,785,pt=pt,stop=2,hold=30,cap=cap,min_credit=2500))
    for pt,cap in product([25,50],[1,3]):
        p.append(Policy(f'multi_dual_pt{pt}_cap{cap}','multi_dual',3,815,pt=pt,cap=cap,stop=2))
    for fam,w,exit_kind in product(['quote_base','quote_compress','quote_reversal'],[1,2],['hold30','target50']):
        p.append(Policy(f'{fam}_w{w}_{exit_kind}',fam,w,660,pt=0 if exit_kind=='hold30' else 50,stop=0 if exit_kind=='hold30' else 2,hold=30 if exit_kind=='hold30' else 0,flat=950,min_credit=0,frac_min=20,frac_max=40,max_quote_spread=600))
    for t,w,g in product([785,845,905],[1,2],[80,90,0]):
        p.append(Policy(f'quote_clock_t{t}_w{w}_g{g}','quote_clock',w,t,gate=g,pt=0,flat=950,min_credit=0,frac_min=20,frac_max=40,max_quote_spread=600))
    p.append(Policy('quote_near_close','quote_clock',2,845,gate=80,pt=0,flat=957,min_credit=2000,max_quote_spread=600))
    for fam,w in product(['breakout_retest','failed_breakdown','trend_reclaim'],[1,2]):
        p.append(Policy(f'pilot_{fam}_w{w}',fam,w,615,pt=50,stop=2,flat=940,cap=2,cooldown=15,min_credit=0,frac_min=20,frac_max=45,max_quote_spread=1000,pilot_only=True))
    if len(p)!=109 or len({x.name for x in p})!=len(p): raise AssertionError('registry mismatch')
    return p

class Feed:
    def __init__(self):
        self.calls=0; self.manifest=[]; self.http=requests.Session()
        self.deadline=time.monotonic()+1200
        self.http.headers.update({'Cache-Control':'no-cache, no-store','Pragma':'no-cache','User-Agent':'FlameCorrectedRerun/1.0'})
    def get(self,url,params):
        if self.calls>=160 or time.monotonic()>self.deadline: raise DataError('request budget exhausted')
        self.calls+=1
        r=self.http.get(url,params=params,timeout=(10,120),allow_redirects=False)
        item=dict(request=self.calls,url=url,params=params,status=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),retrieved=datetime.now(timezone.utc).isoformat())
        self.manifest.append(item);ROOT.mkdir(parents=True,exist_ok=True)
        with gzip.open(ROOT/f'raw_{self.calls:03d}.gz','wb') as f:f.write(r.content)
        emit('retrieval',**item);r.raise_for_status()
        if r.status_code!=200:raise DataError('non-200 source')
        if url.startswith(BASE) and r.headers.get('X-Market-Data-Provider')!='thetadata':raise DataError('unverified provider')
        return r
    def stocks(self,start,end):
        all_days={};s=date.fromisoformat(start);e=date.fromisoformat(end)
        while s<=e:
            stop=min(e,s+timedelta(days=29))
            r=self.get(BASE+'/v3/stock/history/ohlc',dict(symbol='SPY',start_date=s.isoformat(),end_date=stop.isoformat(),interval='1m',start_time='09:30:00',end_time='16:00:00',venue='utp_cta'))
            if r.headers.get('X-Bar-Timestamp')!='interval-start':raise DataError('unknown bar semantics')
            for row in csv.DictReader(io.StringIO(r.text)):
                day=str(row['timestamp'])[:10];m=minute(row['timestamp'],day)
                if m==960:continue  # Only terminal bucket is outside requested complete interval.
                if not s.isoformat()<=day<=stop.isoformat() or not 570<=m<960:raise DataError('stock outside requested window')
                vals={k:float(row[k]) for k in ['open','high','low','close','volume']}
                if not all(math.isfinite(v) for v in vals.values()) or min(vals[k] for k in ['open','high','low','close'])<=0 or vals['volume']<0:raise DataError('invalid stock observation')
                if vals['low']>min(vals['open'],vals['close']) or vals['high']<max(vals['open'],vals['close']):raise DataError('invalid stock OHLC')
                d=all_days.setdefault(day,{})
                if m in d:raise DataError('duplicate stock minute')
                d[m]=vals
            s=stop+timedelta(days=1)
        expected=[];d=date.fromisoformat(start)
        while d<=e:
            if d.weekday()<5 and d.isoformat()!='2026-04-03':expected.append(d.isoformat())
            d+=timedelta(days=1)
        if sorted(all_days)!=expected:raise DataError('stock session coverage mismatch')
        for day,rs in all_days.items():
            if sorted(rs)!=list(range(570,960)):raise DataError('stock minute coverage mismatch '+day)
        return dict(sorted(all_days.items()))
    def vix(self):
        r=self.get('https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv',{})
        rows={}
        for x in csv.DictReader(io.StringIO(r.text)):
            day=datetime.strptime(x['DATE'],'%m/%d/%Y').date().isoformat()
            n=Decimal(x['CLOSE'])
            if day in rows or not n.is_finite() or n<=0:raise DataError('invalid VIX record')
            rows[day]=n
        return dict(sorted(rows.items()))
    def options(self,day):
        r=self.get(BASE+'/v3/option/history/quote',dict(symbol='SPY',date=day,expiration=day,strike='*',right='both',interval='1m',start_time='09:30:00',end_time='16:00:00'))
        data={};bad=0;total=0;times={}
        for x in csv.DictReader(io.StringIO(r.text)):
            total+=1
            if x.get('symbol')!='SPY' or x.get('expiration','')[:10].replace('-','')!=day.replace('-',''):raise DataError('wrong option identity')
            right={'put':'P','call':'C','p':'P','c':'C'}.get(x.get('right','').lower())
            if right is None:raise DataError('unknown option right')
            raw=x['timestamp']
            if raw not in times:times[raw]=minute(raw,day)
            m=times[raw]
            if not 570<=m<=960:raise DataError('non-RTH option')
            try:
                strike=Decimal(x['strike'])*100
                if strike!=strike.to_integral_value():raise DataError('unsupported strike precision')
                k=int(strike);b=units(x['bid']);a=units(x['ask']);bs=int(x['bid_size']);az=int(x['ask_size'])
            except (ValueError,InvalidOperation,KeyError,DataError):bad+=1;continue
            if b<0 or a<=0 or b>a or bs<0 or az<0:bad+=1;continue
            series=data.setdefault((right,k),{})
            if m in series:raise DataError('duplicate option key')
            series[m]=(b,a,bs,az)
        if not data:raise DataError('empty option tape')
        emit('coverage',day=day,option_rows=total,invalid_rows=bad,contracts=len(data),original_quote_update_age='unverified')
        return data,total,bad

class Tape:
    def __init__(self,day,stock,options,ratio):
        self.day=day;self.stock=stock;self.options=options;self.ratio=ratio
        self.candidates={};self.trades={}
    def spot(self,m):
        if m-1 not in self.stock:raise DataError('missing completed underlying bar')
        return self.stock[m-1]['close']
    def quote(self,side,k,m):return self.options.get((side,k),{}).get(m)
    def market(self,side,k,w,m,debit=False):
        direction=-1 if side=='P' else 1
        lk=k + direction*w*100*(-1 if debit else 1)
        s,l=self.quote(side,k,m),self.quote(side,lk,m)
        if s is None or l is None:return None
        if debit:return l[0]-s[1],l[1]-s[0],s[1]-s[0]+l[1]-l[0],l,s
        return s[0]-l[1],s[1]-l[0],s[1]-s[0]+l[1]-l[0],s,l
    def gated(self,gate):return gate==0 or(self.ratio is not None and self.ratio*100<=gate)
    def direction(self,m,range_mode=False):
        a=self.spot(m);b=self.spot(m-30);o=self.spot(575)
        r=a/b-1;day=a/o-1
        if range_mode:
            if abs(r)<.0005 or abs(day)>.0025:return 0
            return -1 if r>0 else 1
        if abs(r)<.001 or r*day<=0:return 0
        return 1 if r>0 else -1
    def pattern_signals(self,fam):
        bars=[]
        for t in range(570,960,15):
            rs=[self.stock[m] for m in range(t,t+15)]
            bars.append(dict(t=t,open=rs[0]['open'],close=rs[-1]['close'],high=max(r['high'] for r in rs),low=min(r['low'] for r in rs)))
        oh=max(x['high'] for x in bars[:2]);ol=min(x['low'] for x in bars[:2]);prev=False;out=[]
        for i in range(3,len(bars)):
            b,p=bars[i],bars[i-1];t=b['t']+15
            if not 615<=t<=870:continue
            bull=b['close']>b['open']
            if fam=='breakout_retest':on=p['close']>oh and b['low']<=oh+.03 and b['close']>oh and bull
            elif fam=='failed_breakdown':on=b['low']<ol and b['close']>ol and bull
            else:
                mean=sum(x['close'] for x in bars[max(0,i-4):i])/min(4,i)
                on=p['close']<mean and b['close']>mean and b['close']>bars[0]['open'] and bull
            if on and not prev:out.append((t,'P',math.floor(min(b['close']-.25,b['low']-.05))*100))
            prev=bool(on)
        return out
    def quote_selected(self,p,m):
        choices=[]
        for side,k in self.options:
            if side!='P':continue
            v=self.market(side,k,p.width,m)
            if v is None:continue
            c,d,spread,_,_=v
            if p.name=='quote_near_close':ok=2000<=c<=4000;distance=abs(c+d-6000)
            else:ok=20*p.width*U<=c*100<=40*p.width*U;distance=abs(5*(c+d)-3*p.width*U)
            if not ok or spread>600:continue
            if p.family in ['quote_compress','quote_reversal']:
                v5=self.market(side,k,p.width,m-5)
                if v5 is None or (c+d)*10>(v5[0]+v5[1])*9:continue
                if p.family=='quote_reversal':
                    v15=self.market(side,k,p.width,m-15)
                    if v15 is None or (v5[0]+v5[1])*10<(v15[0]+v15[1])*11:continue
            choices.append((distance,spread,k))
        return min(choices)[2] if choices else None
    def signals(self,p):
        if p.name in self.candidates:return self.candidates[p.name]
        result=[];effective=p
        if not self.gated(p.gate):self.candidates[p.name]=(p,[],'vix_gate');return self.candidates[p.name]
        fam=p.family
        if p.pilot_only:result=self.pattern_signals(fam)
        elif fam=='fixed':result=[(p.clock,'P',round_strike(self.spot(p.clock)-p.otm))]
        elif fam=='adaptive':
            atm=round_strike(self.spot(p.clock));c=self.quote('C',atm,p.clock);q=self.quote('P',atm,p.clock)
            if c is not None and q is not None:
                n=(c[0]+c[1]+q[0]+q[1])*p.factor
                dist=max(p.min_dist,(n+2*U*100-1)//(2*U*100))
                result=[(p.clock,'P',round_strike(self.spot(p.clock)-dist))]
        elif fam.startswith('quote_'):
            clocks=[p.clock] if fam=='quote_clock' else range(660,871)
            for t in clocks:
                k=self.quote_selected(p,t)
                if k is not None:result=[(t,'P',k)];break
        else:
            low=self.ratio is not None and self.ratio*100<=75
            if fam.startswith('dual_') or fam=='multi_dual':
                if self.ratio is None:self.candidates[p.name]=(p,[],'vix_unknown');return self.candidates[p.name]
                if low:
                    clocks=range(845,921,5) if fam=='multi_dual' else [845]
                    effective=replace(p,width=3,is_debit=False,stop=0)
                    result=[(t,'P',round_strike(self.spot(t)-1)) for t in clocks]
                else:
                    clocks=range(815,921,5) if fam=='multi_dual' else [815]
                    effective=replace(p,width=2 if fam=='multi_dual' else p.width,stop=2)
            elif fam=='multi_momentum':clocks=range(785,921,5)
            else:clocks=[p.clock]
            if not result:
                for t in clocks:
                    direction=self.direction(t,fam=='range_credit')
                    if not direction:continue
                    if effective.is_debit:
                        side='C' if direction>0 else 'P'
                        atm=round_strike(self.spot(t));k=atm+direction*effective.width*100
                    else:
                        side='P' if direction>0 else 'C';k=round_strike(self.spot(t)-direction)
                    result.append((t,side,k))
        self.candidates[p.name]=(effective,result,None)
        return self.candidates[p.name]


def simulate(tape,p,signal,slip,legacy=False):
    t,side,k=signal;key=(p,signal,slip,legacy)
    if key in tape.trades:return tape.trades[key]
    def calc(m):
        x=tape.market(side,k,p.width,m,debit=p.is_debit)
        if x is None:return None
        c,d,sp,s,l=x
        if legacy:
            # Deliberately preserve the former binary subtractions for the paired audit.
            s=[v/U for v in s[:2]]+list(s[2:]);l=[v/U for v in l[:2]]+list(l[2:])
            return s[0]-l[1],s[1]-l[0],(s[1]-s[0])+(l[1]-l[0]),s,l
        return x
    scale=1 if legacy else U;h=slip/U if legacy else slip
    def credit_ok(c):
        if p.name=='quote_near_close':return .2<=c<=.4 if legacy else 2000<=c<=4000
        if p.frac_min:
            if legacy:return p.frac_min/100*p.width<=c<=p.frac_max/100*p.width
            return p.frac_min*p.width*U<=c*100<=p.frac_max*p.width*U
        return c>=p.min_credit/U if legacy else c>=p.min_credit
    def record(x):tape.trades[key]=x;return x
    def reject(reason):return record(dict(status='rejected',reason=reason,signal=t))
    a,f=calc(t),calc(t+1)
    if a is None:return reject('missing_signal_quotes')
    if p.max_quote_spread and a[2]>(p.max_quote_spread/U if legacy else p.max_quote_spread):return reject('wide_signal_quotes')
    if f is None:return reject('missing_delayed_fill')
    if p.is_debit:
        debit=f[1]+h
        if debit<=0 or debit*100>65*p.width*scale:return reject('debit_limit')
        if f[3][3]<1 or(f[4][0]>0 and f[4][2]<1):return reject('entry_size')
        paid=debit
    else:
        if not credit_ok(a[0]):return reject('signal_credit_limit')
        paid=f[0]-h
        if not credit_ok(paid) or paid>=p.width*scale:return reject('delayed_credit_limit')
        if f[3][2]<1 or f[4][3]<1:return reject('entry_size')
    fill=t+1
    risk=paid if p.is_debit else p.width*scale-paid
    risk_u=round(risk*U) if legacy else risk
    credit_u=round(paid*U) if legacy else paid
    rec=dict(status='unresolved',day=tape.day,signal=t,entry=fill,side=side,short=k,width=p.width,debit_strategy=p.is_debit,entry_units=credit_u,payoff_risk_cents=risk_u+FEE,entry_sizes=([f[3][3],f[4][2]] if p.is_debit else [f[3][2],f[4][3]]))
    end=stamp(day+'T15:39:00') if False else None
    worst=0;last_trigger=min(p.flat-1,fill+p.hold-1) if p.hold else p.flat-1
    # All data-boundary rules explicit; no missing mark may become a free winner.
    for m in range(fill,last_trigger+1):
        x=calc(m)
        if x is None:return record({**rec,'reason':'missing_postentry_path','missing_minute':m})
        mark=x[0]-h if p.is_debit else x[1]+h
        if mark<0:return record({**rec,'reason':'negative_synthetic_exit'})
        pnl=(mark-paid) if p.is_debit else (paid-mark)
        pnl_cents=round(pnl*U)-FEE if legacy else pnl-FEE
        worst=min(worst,pnl_cents)
        if p.is_debit:
            reason='target' if mark*100>=paid*130 else 'stop' if mark*100<=paid*75 else None
        elif legacy:
            reason='stop' if p.stop and mark>=paid*p.stop else 'target' if p.pt and mark<=paid*(1-p.pt/100) else None
        else:
            reason='stop' if p.stop and mark>=paid*p.stop else 'target' if p.pt and mark*100<=paid*(100-p.pt) else None
        if not reason and m==last_trigger:reason='time_exit'
        if reason:
            y=calc(m+1)
            if y is None:return record({**rec,'reason':'missing_exit_fill'})
            if p.is_debit:
                if y[3][2]<1 or y[4][3]<1:return record({**rec,'reason':'exit_size'})
                close=y[0]-h;profit=close-paid
            else:
                if y[3][3]<1 or(y[4][0]>0 and y[4][2]<1):return record({**rec,'reason':'exit_size'})
                close=y[1]+h;profit=paid-close
            if close<0:return record({**rec,'reason':'negative_exit_fill'})
            net=round(profit*U)-FEE if legacy else profit-FEE
            closed=round(close*U) if legacy else close
            return record({**rec,'status':'trade','exit':m+1,'exit_units':closed,'net_cents':net,'reason':reason,'exit_capacity':(min(y[3][2],y[4][3]) if p.is_debit else min(y[3][3],y[4][2] if y[4][0]>0 else 1000000)),'worst_open_cents':min(worst,net),'synthetic_exit_above_width':closed>p.width*U})
    return record({**rec,'reason':'no_terminal_exit'})


class Account:
    def __init__(self,p,profile,slip,floor=0,internal=False,risk_pct=10,legacy=False,sizing='one'):
        self.p=p;self.profile=profile;self.slip=slip;self.floor=floor;self.internal=internal;self.risk_pct=risk_pct;self.legacy=legacy;self.sizing=sizing
        self.eq=200000;self.high=self.eq;self.external=0;self.fees=0;self.peak=self.eq;self.dd=0;self.low=self.eq
        self.trades=[];self.rejects=Counter();self.daily={};self.month=None;self.invalid=None;self.bills=[]
    def mark(self,value):
        value-=self.external;self.peak=max(self.peak,value);self.dd=max(self.dd,self.peak-value);self.low=min(self.low,value)
    def bill(self):
        if self.month is None:return
        self.fees+=5000
        if self.internal:self.eq-=5000
        else:self.external+=5000
        self.bills.append({'month':self.month,'fee':50});self.mark(self.eq)
    def day(self,tape):
        month=tape.day[:7]
        if month!=self.month:
            self.bill();self.month=month
        self.daily[tape.day]=0
        if self.invalid:return
        p,sigs,gate=tape.signals(self.p)
        if gate:self.rejects[gate]+=1;return
        n=0;next_t=0;losses=0;realized=0
        for sig in sigs:
            if n>=p.cap or sig[0]<next_t or losses>=2 or realized<=-10000:continue
            if self.eq<self.floor:self.rejects['account_floor']+=1;continue
            rec=simulate(tape,p,sig,self.slip,self.legacy)
            if rec['status']=='rejected':self.rejects[rec['reason']]+=1;continue
            desired=1
            if self.sizing=='two':desired=2
            elif self.sizing=='high_water':desired=max(0,self.high//150000)
            elif self.sizing in ['vix','credit','both']:
                v=tape.ratio is not None and tape.ratio*100<=70
                c=rec['entry_units']>=3000
                desired=2 if(v if self.sizing=='vix' else c if self.sizing=='credit' else v and c) else 1
            risk=rec['payoff_risk_cents']+self.slip
            qty=min(desired,self.eq*self.risk_pct//(100*risk),self.eq//risk)
            if qty<1:self.rejects['risk_or_capital']+=1;continue
            if rec['status']=='unresolved':self.invalid={**rec};return
            if rec['synthetic_exit_above_width']:self.rejects['above_width_natural_close']+=1
            # Multiple lots require enough displayed size on opening/closing legs.
            if qty>min(rec['entry_sizes']):qty=min(rec['entry_sizes'])
            if qty<1:self.rejects['sizing_liquidity']+=1;continue
            if qty>rec['exit_capacity']:
                self.invalid={**rec,'reason':'insufficient_multi_lot_exit_size'};return
            net=rec['net_cents']*qty
            self.mark(self.eq+rec['worst_open_cents']*qty)
            self.eq+=net;self.high=max(self.high,self.eq);self.mark(self.eq)
            self.trades.append({**rec,'contracts':qty,'net_cents':net})
            self.daily[tape.day]+=net;realized+=net;n+=1;losses+=net<0;next_t=rec['exit']+p.cooldown
    def result(self,window):
        self.bill();self.month=None
        total=sum(t['net_cents'] for t in self.trades)
        if self.eq!=200000+total-(self.fees if self.internal else 0):raise AssertionError('cash identity')
        weekly=defaultdict(lambda:[0,0]);streak=longest=0
        counts=Counter(t['day'] for t in self.trades)
        for day,net in self.daily.items():
            key=date.fromisoformat(day).isocalendar()[:2];weekly[str(key)][0]+=counts[day];weekly[str(key)][1]+=net
            streak=0 if counts[day] else streak+1;longest=max(streak,longest)
        return dict(window=window,policy=self.p.name,profile=self.profile,engine='legacy_float' if self.legacy else 'exact',floor=usd(self.floor),fee_location='account' if self.internal else 'external',risk_pct=self.risk_pct,sizing=self.sizing,days=len(self.daily),trades=len(self.trades),lots=sum(t['contracts'] for t in self.trades),trading_net=usd(total),subscription=usd(self.fees),customer_net=None if self.invalid else usd(total-self.fees),partial_resolved_customer_net=usd(total-self.fees),ending_equity=usd(self.eq),worst_trade=usd(min([t['net_cents'] for t in self.trades],default=0)),observed_equity_drawdown=usd(self.dd),minimum_economic_equity=usd(self.low),zero_weeks=sum(v[0]==0 for v in weekly.values()),longest_idle_sessions=longest,invalid=self.invalid,rejections=dict(self.rejects),fingerprint=hashlib.sha256(json.dumps(self.trades,sort_keys=True).encode()).hexdigest(),weekly=dict(weekly),control_not_put_only=any(t['side']!='P' or t['debit_strategy'] for t in self.trades),verdict='INVALID_INCOMPLETE_PATH' if self.invalid else 'RETROSPECTIVE_REBUILD_NOT_VALIDATED')


def self_tests():
    checks=0
    for a,b,expected in [('0.60','0.40',2000),('0.70','0.30',4000),('0.80','0.39',4100),('0.79','0.60',1900)]:
        assert units(a)-units(b)==expected;checks+=1
    credit=units('0.80')-units('0.39')-units('0.01');debit=units('0.79')-units('0.60')+units('0.01')
    assert debit*100<=credit*50;checks+=1
    assert not ((.79-.60+.01)<=.5*(.80-.39-.01));checks+=1
    for bad in ['nan','inf','-Infinity','', '0.00001']:
        try:units(bad)
        except DataError:checks+=1
        else:raise AssertionError('invalid number accepted')
    for p in registry():assert p.width>0 and p.flat<960;checks+=1
    for internal,floor in product([False,True],[0,200000]):
        a=Account(registry()[0],'test',0,floor,internal);a.month='2026-01';a.bill();a.month='2026-02'
        r=a.result('test');assert r['subscription']==100 and r['customer_net']==-100;checks+=1
    # Direct and integer arithmetic agree for every one-cent quote-grid pair.
    for a in range(0,101):
        for b in range(0,101):
            x=units(str(Decimal(a)/100))-units(str(Decimal(b)/100))
            assert x==(a-b)*100;checks+=1
    return checks


def main():
    mode=os.getenv('FLAME_FRESH_MODE','disabled')
    if mode!='corrected-rerun':STATE['stage']='disabled';return
    ROOT.mkdir(parents=True,exist_ok=True)
    reg=registry();spec=dict(version='rerun-v1-exact',policies=[asdict(p) for p in reg],windows=WINDOWS,fee_cents=FEE,profiles=PROFILE,initial_equity=2000,monthly_subscription=50,risk_limits_pct=[10,20],entry_floors=[0,2000],fee_locations=['external','account'],prior_market_inputs=[],prior_trade_inputs=[],underlying='independent completed SPY minute bars',session='regular daytime only',source_update_age='unverified',all_policies_retro_only=True,quote_model='next-minute natural individual-leg sides; no calibrated fill claim')
    (ROOT/'spec.json').write_text(json.dumps(spec,indent=2));emit('specification',sha256=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),policies=len(reg),windows=WINDOWS,checks=self_tests())
    feed=Feed();all_results=[];all_ledgers=[];STATE['stage']='running'
    try:
        # VIX is a freshly acquired public control variable, never a trade instrument.
        vix={}
        for window,start,end in WINDOWS:
            if window=='discovery':vix=feed.vix()
            stock=feed.stocks(start,end)
            active=[p for p in reg if p.pilot_only] if window=='pilot' else [p for p in reg if not p.pilot_only]
            accounts=[]
            for p in active:
                profiles=[('pilot1c',100),('pilot3c',300)] if window=='pilot' else PROFILE
                for (label,slip),floor,inside in product(profiles,[0,200000],[False,True]):
                    accounts.append(Account(p,label,slip,floor,inside,10))
                    if window=='discovery' and floor==0 and not inside:
                        accounts.append(Account(p,label,slip,0,False,100))
                    if window=='pilot':accounts.append(Account(p,label,slip,floor,inside,10,True))
            if window=='discovery':
                baseline=next(p for p in reg if p.name=='flame_current_pt0_sl0')
                for size,(label,slip),floor,inside,risk in product(['one','two','high_water','vix','credit','both'],PROFILE,[0,200000],[False,True],[10,20]):
                    accounts.append(Account(baseline,label,slip,floor,inside,risk,sizing=size))
            emit('batch_start',window=window,days=len(stock),accounts=len(accounts),policies=len(active))
            for day,rows in stock.items():
                vd=[d for d in vix if d<day]
                ratio=vix[vd[-1]]/max(vix[d] for d in vd[-21:-1]) if len(vd)>=21 else None
                options,total,bad=feed.options(day)
                tape=Tape(day,rows,options,ratio)
                for a in accounts:a.day(tape)
                emit('day_complete',window=window,day=day,accounts=len(accounts),unique_trade_replays=len(tape.trades),invalid_accounts=sum(a.invalid is not None for a in accounts),quote_rows=total,invalid_quote_rows=bad)
                del tape,options
            results=[a.result(window) for a in accounts]
            all_results.extend(results)
            with gzip.open(ROOT/f'{window}_ledgers.json.gz','wt') as f:json.dump([{'result':r,'trades':a.trades,'bills':a.bills} for a,r in zip(accounts,results)],f)
            (ROOT/'results.json').write_text(json.dumps(all_results,indent=2))
            # Print private logs only; never put licensed data on the public HTTP endpoint.
            for r in results:
                if r['fee_location']=='external' and r['floor']==0 and r['sizing']=='one':emit('result',**r)
            if window=='pilot':
                pairs={}
                for r in results:
                    key=(r['policy'],r['profile'],r['floor'],r['fee_location']);pairs.setdefault(key,{})[r['engine']]=r
                diffs=[dict(policy=k[0],profile=k[1],floor=k[2],fee_location=k[3],old_trades=v['legacy_float']['trades'],new_trades=v['exact']['trades'],old_net=v['legacy_float']['customer_net'],new_net=v['exact']['customer_net'],changed=v['exact']['fingerprint']!=v['legacy_float']['fingerprint']) for k,v in pairs.items()]
                (ROOT/'float_comparison.json').write_text(json.dumps(diffs,indent=2));emit('paired_comparison',cases=len(diffs),changed=sum(x['changed'] for x in diffs),comparisons=diffs)
            emit('batch_complete',window=window,accounts=len(results),invalid=sum(r['invalid'] is not None for r in results),completed_days=len(stock))
        STATE['stage']='completed';emit('completed',accounts=len(all_results),requests=feed.calls,policies=len(reg),no_live_changes=True)
    except Exception as e:
        STATE['stage']='failed';emit('failed',kind=type(e).__name__,reason=str(e)[:300],requests=feed.calls,completed_accounts=len(all_results))
    finally:
        (ROOT/'manifest.json').write_text(json.dumps(feed.manifest,indent=2))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(json.dumps({'research_only':True,**STATE}).encode())
    def log_message(self,*args):pass

if __name__=='__main__':
    if os.getenv('FLAME_SELFTEST')=='1':print(self_tests())
    else:
        threading.Thread(target=main,daemon=True).start()
        HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
