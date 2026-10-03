"""Bounded read-only collectors; provider timestamps and coverage are retained."""
from __future__ import annotations
import asyncio, csv, io, json, math, os, re, statistics, time as monotonic_time
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
from . import market_structure as ms
UTC=timezone.utc
ET=ZoneInfo('America/New_York')
HOLDINGS_URL='https://www.ssga.com/us/en/institutional/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx'
_holdings=None

def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def observation(value, source, source_time, now, reason=None, confidence='MEDIUM', delayed=False):
    ts=ms._parse_ts(source_time)
    age=(now-ts).total_seconds() if ts else None
    if value is None or ts is None or age is None or age<0:
        return unavailable(reason or 'No timestamped observation')
    return {'value':value,'status':'live' if age<=90 and not delayed else 'historical',
            'source':source,'source_timestamp':ts.isoformat(),'age_seconds':round(age,1),
            'confidence':confidence,'reason':reason}

def unavailable(reason): return {'status':'unavailable','reason':reason}

def spy_constituents(now):
    global _holdings
    if _holdings and (now-_holdings[0]).total_seconds()<21600: return _holdings[1]
    from openpyxl import load_workbook
    r=requests.get(HOLDINGS_URL,timeout=12);r.raise_for_status()
    w=load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
    rows=list(w.active.values);w.close()
    asof=next((str(r[1]) for r in rows if r[0]=='Holdings:'),'')
    m=re.search(r'(\d{2}-[A-Za-z]{3}-\d{4})',asof)
    if not m: raise ValueError('Missing holdings date')
    date=datetime.strptime(m.group(1),'%d-%b-%Y').date()
    if not 0<=(now.astimezone(ET).date()-date).days<=7: raise ValueError('Stale holdings')
    header=next(i for i,r in enumerate(rows) if r[0]=='Name' and r[1]=='Ticker')
    names=sorted({str(r[1]).replace('.','/') for r in rows[header+1:] if r[1] and re.fullmatch(r'[A-Z]{1,5}(?:\.[A-Z])?',str(r[1]))})
    if not 450<=len(names)<=550: raise ValueError('Incomplete universe')
    result={'symbols':names,'source':HOLDINGS_URL,'holdings_as_of':date.isoformat()}
    _holdings=(now,result);return result

def tradier(path, params):
    token=os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_API_KEY')
    if not token: raise RuntimeError('Tradier not configured')
    r=requests.get('https://api.tradier.com/v1/markets'+path,params=params,
       headers={'Authorization':'Bearer '+token,'Accept':'application/json'},timeout=8)
    r.raise_for_status();return r.json()

def batch_quotes(symbols):
    result=[]
    for i in range(0,len(symbols),100):
        raw=(tradier('/quotes',{'symbols':','.join(symbols[i:i+100])}).get('quotes') or {}).get('quote') or []
        result.extend([raw] if isinstance(raw,dict) else raw)
    return result

def summarize_breadth(quotes,universe,now,historical_session=None):
    advances=declines=unchanged=highs=lows=0
    up_volume=down_volume=0;stamps=[];seen=set();high_low_covered=0
    for q in quotes:
        symbol=q.get('symbol');ts=ms._quote_timestamp(q)
        last,prev=number(q.get('last')),number(q.get('prevclose'))
        if symbol not in universe or symbol in seen or not ts or not (0<=(now-ts).total_seconds()<=90 or (historical_session and ts.astimezone(ET).date()==historical_session)) or last is None or prev is None or last<=0 or prev<=0: continue
        seen.add(symbol);stamps.append(ts);volume=max(0,number(q.get('volume')) or 0)
        if last>prev: advances+=1;up_volume+=volume
        elif last<prev: declines+=1;down_volume+=volume
        else: unchanged+=1
        high,low=number(q.get('week_52_high')),number(q.get('week_52_low'))
        if high and low:
            high_low_covered+=1
            if number(q.get('high')) is not None and float(q['high'])>=high: highs+=1
            if number(q.get('low')) is not None and float(q['low'])<=low: lows+=1
    return {'advances':advances,'declines':declines,'unchanged':unchanged,
      'advance_decline_ratio':advances/declines if declines else None,
      'advancing_issue_volume':up_volume,'declining_issue_volume':down_volume,
      'up_down_volume_ratio':up_volume/down_volume if down_volume else None,
      'new_52w_highs':highs if high_low_covered else None,'new_52w_lows':lows if high_low_covered else None,
      'high_low_covered':high_low_covered,'covered':len(seen),'universe':len(universe),
      'coverage_pct':100*len(seen)/len(universe) if universe else 0,
      'source_timestamp':min(stamps).isoformat() if stamps else None,
      'volume_method':'Session volume of advancing/declining issues; not uptick/downtick trade volume'}

def minute_bars(symbol,now):
    et=now.astimezone(ET)
    raw=(tradier('/timesales',{'symbol':symbol,'interval':'1min','start':f'{et.date()} 09:30',
            'end':et.strftime('%Y-%m-%d %H:%M'),'session_filter':'open'}).get('series') or {}).get('data') or []
    if isinstance(raw,dict): raw=[raw]
    return sorted([r for r in raw if number(r.get('timestamp')) is not None and number(r.get('close')) is not None
      and datetime.fromtimestamp(float(r['timestamp']),UTC)<now.replace(second=0,microsecond=0)],key=lambda r:r['timestamp'])

def vwap_read(bars,now):
    valid=[b for b in bars if (number(b.get('volume')) or 0)>0 and (number(b.get('vwap')) or 0)>0]
    if not valid:return None
    total=sum(float(b['volume']) for b in valid);last=valid[-1]
    ts=datetime.fromtimestamp(float(last['timestamp']),UTC)+timedelta(minutes=1)
    if not 0<=(now-ts).total_seconds()<=90:return None
    vwap=sum(float(b['vwap'])*float(b['volume']) for b in valid)/total
    return {'above':float(last['close'])>vwap,'vwap':vwap,'close':float(last['close']),
            'source_timestamp':ts.isoformat(),'bars':len(valid)}

async def collect_breadth(now,vwap_symbols):
    try:
        universe=await asyncio.to_thread(spy_constituents,now)
        quotes=await asyncio.to_thread(batch_quotes,universe['symbols'])
        observed=datetime.now(UTC);et=observed.astimezone(ET);historical=None
        if et.weekday()>=5 or et.time().replace(tzinfo=None)>=time(16):
            from .economic_events import is_market_holiday
            historical=et.date() if et.weekday()<5 else et.date()-timedelta(days=1)
            while historical.weekday()>=5 or is_market_holiday(historical):historical-=timedelta(days=1)
        result=summarize_breadth(quotes,universe['symbols'],observed,historical_session=historical)
        result['quote_scope']='Last observed issue quotes for '+historical.isoformat()+'; timestamps are not synchronous closes' if historical else 'Fresh observed issue quotes'
        bar_clock=datetime.combine(historical,time(16),ET).astimezone(UTC) if historical else observed
        result.update(source='Tradier quotes; SSGA SPY constituents',holdings=universe)
        sem=asyncio.Semaphore(6)
        async def one(symbol):
            async with sem:
                try:return symbol,vwap_read(await asyncio.to_thread(minute_bars,symbol,bar_clock),bar_clock)
                except Exception:return symbol,None
        reads=dict(await asyncio.gather(*(one(s) for s in list(dict.fromkeys(vwap_symbols))[:24])))
        usable={s:r for s,r in reads.items() if r}
        result['vwap']={'above':sum(r['above'] for r in usable.values()),'covered':len(usable),'requested':len(reads),
           'percent_above':100*sum(r['above'] for r in usable.values())/len(usable) if usable else None,
           'scope':'SPY/QQQ and report candidate sample; not all constituents','rows':usable}
        return result
    except Exception as e:return {'reason':'Breadth collector failed: '+type(e).__name__,'source_timestamp':None}

def volume_profile(trades,bin_size,start,end):
    if not math.isfinite(bin_size) or bin_size<=0:raise ValueError('Invalid price bin')
    bins=defaultdict(float);timestamps=[];count=rejected=0
    for trade in trades:
        p,size=number(trade.get('price')),number(trade.get('size'));ts=ms._theta_ts(trade.get('timestamp'))
        if not ts or not start<=ts<=end or not p or p<=0 or not size or size<=0:rejected+=1;continue
        bins[int(math.floor((p+1e-9)/bin_size))]+=size;timestamps.append(ts);count+=1
    if not bins:return {'reason':'No valid timestamped trades','source_timestamp':None}
    if max(bins)-min(bins)>20000:return {'reason':'Outlier tape exceeds bounded profile grid','source_timestamp':None}
    grid={i:bins.get(i,0) for i in range(min(bins),max(bins)+1)}
    poc=max(grid,key=grid.get);lower=upper=poc;cumulative=grid[poc];total=sum(grid.values())
    while cumulative<total*.70 and (lower>min(grid) or upper<max(grid)):
        if grid.get(upper+1,-1)>grid.get(lower-1,-1):upper+=1;cumulative+=grid[upper]
        else:lower-=1;cumulative+=grid[lower]
    med=statistics.median(grid.values());centers=lambda ids:[round((i+.5)*bin_size,4) for i in ids]
    return {'poc':centers([poc])[0],'val':round(lower*bin_size,4),'vah':round((upper+1)*bin_size,4),
      'hvn':centers(sorted(grid,key=grid.get,reverse=True)[:5]),'lvn':centers([i for i,v in grid.items() if v<med*.5][:10]),
      'bins':[{'price':(i+.5)*bin_size,'volume':v} for i,v in grid.items()],
      'total_volume':total,'trade_count':count,'rejected_rows':rejected,'source_timestamp':max(timestamps).isoformat(),
      'window_start':start.isoformat(),'window_end':end.isoformat(),
      'method':f'Observed consolidated ThetaData prints; {bin_size:g} bins; contiguous 70% value area. Rolling 30-minute window, not full session. Provider trade conditions retained.'}

def collect_profile(symbol,now,previous=None):
    et=now.astimezone(ET)
    if et.weekday()>=5 or not time(9,30)<=et.time().replace(tzinfo=None)<time(16):
        return {'reason':'Regular equity session is closed','source_timestamp':None}
    previous=previous or {}
    previous_end=ms._parse_ts(previous.get('window_end'))
    same_session=previous_end is not None and previous_end.astimezone(ET).date()==et.date()
    start=previous_end if same_session else datetime.combine(et.date(),time(9,30),ET).astimezone(UTC)
    end=min(now.replace(microsecond=0),start+timedelta(minutes=30))
    if end<=start:return previous or {'reason':'No completed tape window yet','source_timestamp':None}
    try:
        rows=ms._theta_rows('/v3/stock/history/trade',{'symbol':symbol,'date':et.date().isoformat(),
          'start_time':start.astimezone(ET).strftime('%H:%M:%S'),'end_time':end.astimezone(ET).strftime('%H:%M:%S'),'venue':'utp_cta'},timeout=30)
        rows=[r for r in rows if (ts:=ms._theta_ts(r.get('timestamp'))) is not None and ts<end]
        result=volume_profile(rows,.10 if symbol=='SPY' else .25,start,end)
        if result.get('source_timestamp') and same_session and previous.get('bins'):
            result=merge_profiles(previous,result,.10 if symbol=='SPY' else .25)
        if result.get('source_timestamp'):
            result['method']='Cumulative observed consolidated RTH trades; fixed price bins; contiguous 70% value area; provider conditions retained; no bar-volume approximation'
            result['coverage_start']=result['window_start'];result['coverage_end']=end.isoformat()
            result['catchup_pending']=(now-end).total_seconds()>90
        return result
    except Exception as e:return {'reason':'Trade profile failed: '+type(e).__name__,'source_timestamp':None}

def merge_profiles(old,new,bin_size):
    bins=defaultdict(float)
    for row in old['bins']+new['bins']:bins[int(round(row['price']/bin_size-.5))]+=row['volume']
    if max(bins)-min(bins)>20000:raise ValueError('Profile grid exceeded bound')
    grid={i:bins.get(i,0) for i in range(min(bins),max(bins)+1)}
    poc=max(grid,key=grid.get);lo=hi=poc;total=sum(grid.values());covered=grid[poc]
    while covered<.7*total and (lo>min(grid) or hi<max(grid)):
        if grid.get(hi+1,-1)>grid.get(lo-1,-1):hi+=1;covered+=grid[hi]
        else:lo-=1;covered+=grid[lo]
    med=statistics.median(grid.values())
    return dict(new,poc=(poc+.5)*bin_size,val=lo*bin_size,vah=(hi+1)*bin_size,
      hvn=[(i+.5)*bin_size for i in sorted(grid,key=grid.get,reverse=True)[:5]],
      lvn=[(i+.5)*bin_size for i,v in grid.items() if v<med*.5][:10],
      bins=[{'price':(i+.5)*bin_size,'volume':v} for i,v in grid.items()],total_volume=total,
      trade_count=old['trade_count']+new['trade_count'],rejected_rows=old.get('rejected_rows',0)+new.get('rejected_rows',0),
      window_start=old['window_start'])

def collect_macro(now):
    import yfinance as yf
    symbols={'rates_13w':'^IRX','rates_5y':'^FVX','rates_10y':'^TNX','rates_30y':'^TYX','dollar':'DX-Y.NYB',
      'eurusd':'EURUSD=X','usdjpy':'JPY=X','gold':'GC=F','oil':'CL=F','move':'^MOVE','es':'ES=F','nq':'NQ=F'}
    data={}
    try:
        r=requests.get('https://fred.stlouisfed.org/graph/fredgraph.csv',params={'id':'DGS2,DGS5,DGS10,DGS30','cosd':(now-timedelta(days=14)).date().isoformat()},timeout=8)
        r.raise_for_status();rows=list(csv.DictReader(io.StringIO(r.text)))
        for name,key in [('rates_2y','DGS2'),('rates_5y','DGS5'),('rates_10y','DGS10'),('rates_30y','DGS30')]:
            row=next((r for r in reversed(rows) if number(r.get(key)) is not None),None)
            if row:
                date=row.get('DATE') or row.get('observation_date')
                ts=datetime.fromisoformat(date).replace(tzinfo=UTC)
                data[name]=observation({'symbol':key,'price':float(row[key]),'unit':'percent annual yield','observation_date':date},
                    'Federal Reserve FRED daily Treasury observation date; not an intraday exchange clock',ts,now,delayed=True)
    except Exception:pass
    for name,symbol in symbols.items():
        if name in data:continue
        try:
            frame=yf.Ticker(symbol).history(period='5d',interval='5m',timeout=5,raise_errors=True)
            if frame.empty:raise ValueError('Empty source')
            row=frame.iloc[-1];ts=frame.index[-1].to_pydatetime().astimezone(UTC)
            # Globex overnight starts 18:00 ET on the preceding day.
            et=ts.astimezone(ET);start=datetime.combine(et.date()-timedelta(days=1),time(18),ET)
            finish=datetime.combine(et.date(),time(9,30),ET)
            overnight=frame[(frame.index>=start)&(frame.index<finish)]
            data[name]=observation({'symbol':symbol,'price':number(row['Close']),
              'overnight_low':number(overnight['Low'].min()) if len(overnight) else None,
              'overnight_high':number(overnight['High'].max()) if len(overnight) else None},
              'Yahoo Finance delayed 5-minute bars; not an execution feed',ts,datetime.now(UTC),delayed=True)
        except Exception as e:data[name]=unavailable(f'{symbol} source failed: {type(e).__name__}')
    return data

def historical_stall_study(frames):
    outcomes=[]
    for symbol,date,bars in frames:
        bars=sorted(bars,key=lambda b:b['timestamp'])
        if len(bars)<40:continue
        opening=bars[:20];hi=max(float(b['high']) for b in opening);lo=min(float(b['low']) for b in opening)
        if any(float(opening[i]['timestamp'])-float(opening[i-1]['timestamp'])!=60 for i in range(1,20)):continue
        for i in range(20,len(bars)-10):
            close=float(bars[i]['close']);direction=1 if close>hi else -1 if close<lo else 0
            if not direction:continue
            future=bars[i+10]
            if any(float(bars[j]['timestamp'])-float(bars[j-1]['timestamp'])!=60 for j in range(20,i+11)):break
            ret=direction*(float(future['close'])/close-1)
            outcomes.append({'symbol':symbol,'date':date,'direction':direction,'forward_return':ret,'stalled':ret<=0,'event_timestamp':bars[i]['timestamp']});break
    n=len(outcomes);p=sum(r['stalled'] for r in outcomes)/n if n else None;interval=None
    if n:
        z=1.96;denom=1+z*z/n;center=(p+z*z/(2*n))/denom;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
        interval=[center-half,center+half]
    clusters=[];run=[]
    for row in sorted(outcomes,key=lambda r:(r['symbol'],r['date'])):
        if row['stalled']:
            if run and run[-1]['symbol']!=row['symbol']:clusters.append(run);run=[]
            run.append(row)
        elif run:clusters.append(run);run=[]
    if run:clusters.append(run)
    return {'frozen_method':'v1: first completed 1-minute close outside first 20 RTH bars; evaluate 10 minutes later; one event/symbol/day; no parameter search; price study, not option P&L',
      'sample_size':n,'stall_fraction':p,'wilson_95_interval':interval,'minimum_sample':30,
      'validated_statistics':n>=30,'outcomes':outcomes,'loss_clusters':[r for r in clusters if len(r)>=2],
      'reason':None if n>=30 else 'Underpowered: fewer than 30 events'}

def collect_study(now):
    from sqlalchemy import text
    from .db import engine
    if engine is None:return dict(historical_stall_study([]),reason='Database not configured')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS sw_report_study_bars (symbol TEXT NOT NULL, session_date TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(symbol,session_date))'))
    deadline=monotonic_time.monotonic()+90
    frames=[];failures=[];day=now.astimezone(ET).date()-timedelta(days=1);dates=[]
    from .economic_events import is_market_holiday
    while len(dates)<20:
        if day.weekday()<5 and not is_market_holiday(day):dates.append(day)
        day-=timedelta(days=1)
    for symbol in ('SPY','QQQ'):
        for day in dates:
            with engine.begin() as c:
                cached=c.execute(text('SELECT payload_json FROM sw_report_study_bars WHERE symbol=:symbol AND session_date=:date'),{'symbol':symbol,'date':day.isoformat()}).fetchone()
            if cached:
                frames.append((symbol,day.isoformat(),json.loads(cached[0])))
                continue
            if monotonic_time.monotonic()>deadline:
                failures.append({'reason':'90-second study work budget exhausted; captured sessions are checkpointed for next tick'})
                continue
            try:
                rows=ms._theta_rows('/v3/stock/history/ohlc',{'symbol':symbol,'date':day.isoformat(),'interval':'1m',
                 'start_time':'09:30:00','end_time':'16:00:00','venue':'utp_cta'},timeout=30)
                bars=[]
                for row in rows:
                    ts=ms._theta_ts(row.get('timestamp'))
                    if ts and all(number(row.get(k)) is not None for k in ('high','low','close')):bars.append(dict(row,timestamp=ts.timestamp()))
                if len(bars)>=40:
                    with engine.begin() as c:
                        c.execute(text('INSERT INTO sw_report_study_bars (symbol,session_date,payload_json) VALUES (:symbol,:date,:payload) ON CONFLICT(symbol,session_date) DO NOTHING'),{'symbol':symbol,'date':day.isoformat(),'payload':json.dumps(bars)})
                frames.append((symbol,day.isoformat(),bars))
            except requests.HTTPError as e:
                failures.append({'symbol':symbol,'date':day.isoformat(),'status':e.response.status_code})
                if e.response.status_code in (401,403,503):return dict(historical_stall_study(frames),failures=failures)
            except Exception as e:
                failures.append({'symbol':symbol,'date':day.isoformat(),'reason':type(e).__name__})
                if len(failures)>=3:return dict(historical_stall_study(frames),failures=failures)
    return dict(historical_stall_study(frames),failures=failures)

def stored_futures(now):
    """Existing broker microstructure observations; no futures execution calls."""
    from sqlalchemy import text
    from .db import engine
    result={}
    if engine is None:return result
    try:
        with engine.begin() as c:
            rows=c.execute(text('''SELECT DISTINCT ON (root_symbol) root_symbol,contract_symbol,
              source,last_quote_exchange_at,bid_close,ask_close,last_trade_at,trade_close
              FROM valor_mes_microstructure_minute_segments WHERE valid_quote_count>0
              ORDER BY root_symbol,bucket_start DESC''')).fetchall()
        for root,contract,source,qts,bid,ask,tts,last in rows:
            if not qts or number(bid) is None or number(ask) is None or not 0<float(bid)<=float(ask):continue
            ts=ms._parse_ts(qts)
            with engine.begin() as c:
                start=datetime.combine(ts.astimezone(ET).date()-timedelta(days=1),time(18),ET)
                end=datetime.combine(ts.astimezone(ET).date(),time(9,30),ET)
                range_row=c.execute(text('''SELECT MIN(trade_low),MAX(trade_high),SUM(trade_count)
                    FROM valor_mes_microstructure_minute_segments WHERE contract_symbol=:contract
                    AND bucket_start>=:start AND bucket_start<:end AND trade_count>0 AND quality_complete=true'''),
                    {'contract':contract,'start':start,'end':end}).fetchone()
            result[root]=observation({'root':root,'contract':contract,'bid':float(bid),'ask':float(ask),
               'midpoint':(float(bid)+float(ask))/2,'last_trade':number(last),'last_trade_timestamp':ms._parse_ts(tts).isoformat() if tts else None,
               'overnight_low':number(range_row[0]),'overnight_high':number(range_row[1]),'overnight_observed_trade_count':range_row[2],
               'range_scope':'Recorded quality-complete microstructure segments for this contract; gaps are not filled'},
               source+' persisted broker quote events',ts,now)
    except Exception as e:
        result['error']=unavailable('Stored futures collector failed: '+type(e).__name__)
    return result
