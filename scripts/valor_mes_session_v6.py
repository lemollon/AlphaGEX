"""MES session hypotheses: cache-only research, no brokers or vendor requests.

Three fixed hypotheses and matched-day long/short controls, one position per
specification per day. 2023/24 are reused development; 2025 is not blind OOS.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import io
import json
import logging
import math
import os
import subprocess
import sys

STUDY = 'valor-mes-session-v6-20260923'
LOCK = 63260923
PV, TICK, FEE = 5., .25, 3.
# Decision/entry and planned exit minutes in America/Chicago. Not a grid.
SPECS = {'morning_continuation': (540, 720),
         'afternoon_continuation': (780, 895),
         'closing_continuation': (870, 895)}
HASHES = {2023: '2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580',
          2024: '6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040',
          2025: '629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16'}


def prepare(frame):
    import numpy as np
    import pandas as pd
    d = frame.copy()
    if 'timestamp' not in d:
        if 'ts_event' not in d:
            d = d.reset_index()
        d['timestamp'] = d['ts_event']
    cols = ['timestamp', 'instrument_id', 'open', 'high', 'low', 'close', 'volume']
    if d.empty or not set(cols).issubset(d):
        raise ValueError('Exact-contract, nonempty MES minute bars required')
    d = d[cols].copy()
    if getattr(d.timestamp.dtype, 'tz', None) is None:
        if any(pd.Timestamp(t).tzinfo is None for t in d.timestamp):
            raise ValueError('Naive timestamps are not permitted')
    d['timestamp'] = pd.to_datetime(d.timestamp, utc=True, errors='raise')
    d = d.sort_values('timestamp').reset_index(drop=True)
    if d.timestamp.isna().any() or d.timestamp.duplicated().any() or d.instrument_id.isna().any():
        raise ValueError('Invalid timestamps or contracts')
    if not d.timestamp.eq(d.timestamp.dt.floor('min')).all():
        raise ValueError('Minute-start timestamps required')
    for c in cols[2:]:
        d[c] = pd.to_numeric(d[c], errors='raise')
    a = d[cols[2:]].to_numpy(float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any():
        raise ValueError('Invalid OHLCV')
    if ((d.high < d[['open', 'low', 'close']].max(axis=1)) |
            (d.low > d[['open', 'high', 'close']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC')
    if not np.allclose(a[:, :4]/TICK, np.rint(a[:, :4]/TICK), atol=1e-5, rtol=0):
        raise ValueError('Off-tick MES prices')
    local = d.timestamp.dt.tz_convert('America/Chicago')
    d['date'] = local.dt.strftime('%Y-%m-%d')
    d['minute'] = local.dt.hour*60+local.dt.minute
    d['rth'] = local.dt.dayofweek.lt(5) & d.minute.ge(510) & d.minute.lt(900)
    d['segment'] = ((d.timestamp.diff().dt.total_seconds() != 60) |
                    d.instrument_id.ne(d.instrument_id.shift())).cumsum()
    return d


def orders(d, spec):
    """Use only the prefix observable at the decision; never a full-day gate."""
    import numpy as np
    import pandas as pd
    decision, exit_min = SPECS[spec]
    out, skipped = [], Counter()
    for day, group in d[d.rth].groupby('date', sort=True):
        p = group[group.minute < decision]
        if len(p) != decision-510 or p.empty or p.minute.iloc[0] != 510 or p.minute.iloc[-1] != decision-1 or p.segment.nunique() != 1:
            skipped['incomplete_known_context'] += 1
            continue
        first = p.iloc[:30]
        width = float(first.high.max()-first.low.min())
        ref, opening = float(p.close.iloc[-1]), float(p.open.iloc[0])
        if width <= 0 or p.volume.sum() <= 0:
            skipped['flat_or_no_volume'] += 1
            continue
        vwap = float((p.volume*(p.high+p.low+p.close)/3).sum()/p.volume.sum())
        first_move = float(first.close.iloc[-1]-first.open.iloc[0])
        recent_move = float(p.close.iloc[-1]-p.open.iloc[-30])
        move = first_move if spec in ('morning_continuation', 'closing_continuation') else ref-opening
        side = int(np.sign(move))
        if side == 0 or side*(ref-vwap) <= 0:
            skipped['direction_not_confirmed'] += 1
            continue
        if spec == 'morning_continuation' and abs(move) < .25*width:
            skipped['opening_displacement_too_small'] += 1
            continue
        if spec != 'morning_continuation' and side*recent_move <= 0:
            skipped['last_30_minutes_disagree'] += 1
            continue
        risk = math.ceil(max(width, 4.)/TICK)*TICK
        out.append(dict(index=int(p.index[-1]), date=day, side=side,
            signal_time=(p.timestamp.iloc[-1]+pd.Timedelta(minutes=1)).isoformat(),
            reference=ref, risk=risk, exit_minute=exit_min))
    return out, dict(skipped)


def replay(d, schedule, view):
    """Single daily position; fixed opening-range risk; scheduled OPEN exit.

    Missing entry/exit bars or a contract switch are unresolved, never zero PnL.
    Signal/reference and stop distance are fixed before next open is observed.
    """
    import pandas as pd
    if view not in ('signal', 'matched_long', 'matched_short'):
        raise ValueError('Unknown control')
    ts = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op, hi, lo, cl = (d[c].to_numpy(float) for c in ('open', 'high', 'low', 'close'))
    seg, minute = d.segment.to_numpy(), d.minute.to_numpy()
    trades, unresolved, seen = [], [], set()
    for order in schedule:
        if order['date'] in seen:
            raise ValueError('More than one daily order')
        seen.add(order['date'])
        i, e = order['index'], order['index']+1
        side = order['side'] if view == 'signal' else (1 if view == 'matched_long' else -1)
        stop = order['reference']-side*order['risk']
        if e >= len(d) or seg[e] != seg[i] or ts[e]-ts[i] != 60_000_000_000:
            unresolved.append(dict(order, side=side, reason='missing_entry_bar', entry=None))
            continue
        entry = float(op[e]); marks = [entry]; done = False; j = e
        while j < len(d) and seg[j] == seg[e]:
            reason, raw = None, None
            if minute[j] >= order['exit_minute']:
                reason, raw = 'scheduled_open', op[j]
            elif side*(op[j]-stop) <= 0:
                reason, raw = 'gap_stop', op[j]
            elif (side == 1 and lo[j] <= stop) or (side == -1 and hi[j] >= stop):
                reason, raw = 'stop', stop
            if reason:
                marks.append(float(raw))
                # Stop time within the minute is unknown; use bar END as upper bound.
                exit_ts = d.timestamp.iloc[j] + pd.Timedelta(minutes=int(reason=='stop'))
                trades.append(dict(order, side=side, entry=d.timestamp.iloc[e].isoformat(),
                    exit=exit_ts.isoformat(), reason=reason, entry_raw=entry, exit_raw=float(raw),
                    instrument_id=int(d.instrument_id.iloc[e]), stop=stop, raw_marks=marks))
                done = True
                break
            marks.append(float(cl[j])); j += 1
        if not done:
            k = max(e, j-1)
            unresolved.append(dict(order, side=side, entry=d.timestamp.iloc[e].isoformat(),
                entry_raw=entry, last_raw=float(cl[k]), last_seen=d.timestamp.iloc[k].isoformat(),
                reason='missing_bar_roll_or_end'))
    return trades, unresolved


def fill(price, side, ticks):
    q = price/TICK+side*ticks
    return (math.ceil(q-1e-8) if side > 0 else math.floor(q+1e-8))*TICK


def summarize(trades, unresolved, year, ticks):
    import numpy as np
    ledger, marks, monthly = [], [0.], {f'{year}-{m:02d}': 0. for m in range(1,13)}
    cash = 0.
    for t in trades:
        entry, exit_ = fill(t['entry_raw'], t['side'], ticks), fill(t['exit_raw'], -t['side'], ticks)
        net = round(t['side']*(exit_-entry)*PV-FEE, 6)
        for price in t['raw_marks']:
            marks.append(cash+t['side']*(fill(price, -t['side'], ticks)-entry)*PV-FEE)
        cash += net
        monthly[t['date'][:7]] += net
        ledger.append(dict({k:v for k,v in t.items() if k!='raw_marks'}, entry_fill=entry, exit_fill=exit_, net=net))
    p = np.array([t['net'] for t in ledger], float); equity = np.r_[0., p.cumsum()]
    m = np.array(marks); wins, losses = p[p>0].sum(), -p[p<0].sum()
    return dict(trades=len(p), unresolved=len(unresolved),
        unresolved_fraction=len(unresolved)/max(1,len(p)+len(unresolved)),
        net_dollars=round(float(p.sum()),6), avg_trade=round(float(p.mean()),6) if len(p) else None,
        win_rate=round(float((p>0).mean()*100),4) if len(p) else None,
        profit_factor=round(float(wins/losses),6) if losses else None,
        gross_wins=round(float(wins),6), gross_losses=round(float(losses),6),
        closed_trade_max_drawdown=round(float((np.maximum.accumulate(equity)-equity).max()),6),
        resolved_minute_liquidation_mark_drawdown=round(float((np.maximum.accumulate(m)-m).max()),6),
        monthly=monthly, positive_months=sum(v>0 for v in monthly.values()),
        worst_trade=round(float(p.min()),6) if len(p) else None,
        best_five_removed_net=round(float(p.sum()-np.sort(p)[-5:].sum()),6) if len(p)>=5 else None,
        long_trades=sum(t['side']==1 for t in ledger), long_net=round(sum(t['net'] for t in ledger if t['side']==1),6),
        short_trades=sum(t['side']==-1 for t in ledger), short_net=round(sum(t['net'] for t in ledger if t['side']==-1),6),
        cost_ticks_each_side=ticks, round_trip_fee_assumed=FEE,
        exit_reasons=dict(Counter(t['reason'] for t in ledger)),
        ledger=ledger, unresolved_ledger=unresolved, gex_used=False, live_ready=False)


def evaluate(frame, year, selected=None):
    d = prepare(frame); rows = []
    for spec in SPECS:
        if selected is not None and spec != selected:
            continue
        schedule, skipped = orders(d, spec)
        for view in ('signal', 'matched_long', 'matched_short'):
            trades, unresolved = replay(d, schedule, view)
            for ticks in (2,4):
                r = summarize(trades, unresolved, year, ticks)
                r.update(spec=spec, view=view, year=year, decisions=len(schedule), skipped=skipped)
                rows.append(r)
    return dict(bars=len(d), first_bar=d.timestamp.iloc[0].isoformat(), last_bar=d.timestamp.iloc[-1].isoformat(),
        study=STUDY, year=year, specs=SPECS, point_value=PV, tick_size=TICK,
        one_trade_per_day_per_specification=True, gex_used=False, mnq_changed=False,
        live_ready=False, new_vendor_downloads=0, no_trade_control_net=0.,
        drawdown_scope='resolved trades only; minute-close liquidating marks are not full intrabar account drawdown',
        validation='reused 2023/24 development; 2025 already seen, not blind OOS'), rows


def decisions(dev):
    out = []
    for spec in SPECS:
        candidate = [r for y in (2023,2024) for r in dev.get(y,[]) if r['spec']==spec and r['view']=='signal' and r['cost_ticks_each_side']==4]
        numeric = len(candidate)==2 and {r['year'] for r in candidate}=={2023,2024} and all(
            r['trades']>=100 and r['net_dollars']>0 and r['profit_factor'] is not None and
            r['profit_factor']>=1.1 and r['unresolved_fraction']<=.01 for r in candidate)
        value_added = len(candidate)==2
        for r in candidate:
            controls = [c for c in dev.get(r['year'],[]) if c['spec']==spec and c['view']!='signal' and c['cost_ticks_each_side']==4]
            value_added = value_added and len(controls)==2 and all(r['net_dollars']>c['net_dollars'] for c in controls)
        out.append(dict(spec=spec, numeric_pass=bool(numeric), outperforms_both_matched_controls=bool(value_added),
                        selected=bool(numeric and value_added), live_ready=False))
    return out


def run():
    import pandas as pd
    import psycopg2
    from psycopg2.extras import Json
    if hasattr(os,'nice'):
        os.nice(10)
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=15)
    conn.autocommit = True; cur = conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK,))
    if not cur.fetchone()[0]:
        conn.close(); return
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status, **detail):
        cur.execute('''INSERT INTO valor_mes_session_v6_state(study_id,status,detail) VALUES(%s,%s,%s)
            ON CONFLICT(study_id) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=now()''',
            (STUDY,status,Json(dict(detail,source_sha256=source_hash,mnq_changed=False,new_vendor_downloads=0))))
    def cached(year):
        cur.execute('SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s',
                    (f'GLBX.MDP3:ohlcv-1m:MES.v.0:{year}',))
        row = cur.fetchone()
        if not row: raise ValueError('Cache absent; vendor downloads prohibited')
        body = bytes(row[1]); digest = hashlib.sha256(body).hexdigest()
        if digest != row[0] or digest != HASHES[year]: raise ValueError('Cache checksum mismatch')
        return pd.read_parquet(io.BytesIO(body))
    def store(year, manifest, rows):
        manifest.update(source_sha256=source_hash,cache_sha256=HASHES[year])
        summary = [{k:v for k,v in r.items() if k not in ('ledger','unresolved_ledger')} for r in rows]
        cur.execute('''INSERT INTO valor_mes_session_v6_results(study_id,year,manifest,summary,evidence_gzip)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (STUDY,year,Json(manifest),Json(summary),gzip.compress(json.dumps(rows,allow_nan=False).encode(),mtime=0)))
        return summary
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_mes_session_v6_state(study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
            CREATE TABLE IF NOT EXISTS valor_mes_session_v6_results(study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));''')
        cur.execute('SELECT status FROM valor_mes_session_v6_state WHERE study_id=%s',(STUDY,))
        if cur.fetchone()==('completed',): return
        cur.execute("SELECT COUNT(*) FROM valor_mes_session_v6_results WHERE study_id=%s AND manifest->>'source_sha256' IS DISTINCT FROM %s",(STUDY,source_hash))
        if cur.fetchone()[0]: state('blocked_code_version'); return
        dev={}
        for year in (2023,2024):
            cur.execute('SELECT summary FROM valor_mes_session_v6_results WHERE study_id=%s AND year=%s',(STUDY,year))
            row=cur.fetchone()
            if row: dev[year]=row[0]; continue
            state('evaluating_development',year=year)
            manifest,rows=evaluate(cached(year),year)
            manifest['phase']='development';dev[year]=store(year,manifest,rows)
        gate=decisions(dev); eligible=sorted(x['spec'] for x in gate if x['selected'])
        # Fixed lexicographic tie-break, never select by 2025 performance.
        selected=eligible[0] if eligible else None
        cur.execute('SELECT 1 FROM valor_mes_session_v6_results WHERE study_id=%s AND year=2025',(STUDY,))
        if not cur.fetchone():
            if selected:
                state('chronological_check',selected=selected)
                manifest,rows=evaluate(cached(2025),2025,selected)
                manifest.update(phase='chronological_check',selection_frozen=selected)
                store(2025,manifest,rows)
            else:
                store(2025,dict(phase='not_tested',reason='no_development_candidate_passed'),[])
        state('completed',decisions=gate,selected=selected,gex_used=False,live_ready=False,
              test_2025='chronological_check' if selected else 'not_tested')
    except Exception as exc:
        try: state('failed',error_type=type(exc).__name__)
        except Exception: pass
        logging.getLogger(__name__).error('MES session research failed: %s',type(exc).__name__)
    finally:
        try: cur.execute('SELECT pg_advisory_unlock(%s)',(LOCK,))
        finally: conn.close()


def launch_if_enabled():
    flags=('VALOR_MES_SESSION_V6_AUTORUN','VALOR_MES_GEX_V5_AUTORUN','VALOR_MES_V4_AUTORUN',
           'VALOR_EXIT_RESEARCH_AUTORUN','VALOR_CONTRACT_RESEARCH_AUTORUN')
    flag=next((os.environ[k] for k in flags if k in os.environ),'false')
    if flag.lower() not in {'1','true','yes','on'}: return False
    child_env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    subprocess.Popen([sys.executable,'-m','scripts.valor_mes_session_v6'],env=child_env,
                     stdin=subprocess.DEVNULL,close_fds=True)
    return True


if __name__=='__main__':
    run()
