"""MES-only cache research: no vendor or broker API, no MNQ configuration writes.

Predeclared three-hypothesis study. Reused 2023/24 development data; 2025 is
already-seen chronological validation, never described as a blind holdout.
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

import numpy as np
import pandas as pd

STUDY = 'valor-mes-rebuild-v4-20260923'
LOCK = 63260923
TICK, PV, FEE = .25, 5., 3.
START, END = 510, 900  # Equity cash session in America/Chicago.
SPECS = {'opening_acceptance_retest': 180, 'prior_extreme_reclaim': 120,
         'gap_fill_after_opening_failure': 90}
CACHE_HASHES = {
    2023: '2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580',
    2024: '6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040',
    2025: '629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16',
}


def prepare(frame):
    d = frame.copy()
    if 'timestamp' not in d:
        if 'ts_event' not in d:
            d = d.reset_index()
        d['timestamp'] = d['ts_event']
    cols = ['timestamp', 'instrument_id', 'open', 'high', 'low', 'close', 'volume']
    if d.empty or not set(cols).issubset(d):
        raise ValueError('Nonempty exact-contract minute OHLCV required')
    d = d[cols].copy()
    if getattr(d.timestamp.dtype, 'tz', None) is None:
        if any(pd.Timestamp(t).tzinfo is None for t in d.timestamp):
            raise ValueError('Timezone-aware source required')
    d['timestamp'] = pd.to_datetime(d.timestamp, utc=True, errors='raise')
    d = d.sort_values('timestamp').reset_index(drop=True)
    if d.timestamp.isna().any() or d.timestamp.duplicated().any() or d.instrument_id.isna().any():
        raise ValueError('Null or duplicate observation')
    if not (d.timestamp == d.timestamp.dt.floor('min')).all():
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
        raise ValueError('Off-grid MES price')
    dt = d.timestamp.diff().dt.total_seconds()
    change = d.instrument_id.ne(d.instrument_id.shift())
    d['segment'] = ((dt != 60) | change).cumsum()
    ct = d.timestamp.dt.tz_convert('America/Chicago')
    d['date'] = ct.dt.strftime('%Y-%m-%d')
    d['minute'] = ct.dt.hour*60 + ct.dt.minute
    d['rth'] = d.minute.ge(START) & d.minute.lt(END) & ct.dt.dayofweek.lt(5)
    d['key'] = d.date + ':' + d.instrument_id.astype(str)
    d['raw_index'] = np.arange(len(d))
    return d


def context(d):
    """Completed five-minute bars and prior full cash sessions, same contract."""
    x = d.assign(bucket=d.timestamp.dt.floor('5min'))
    b = x.groupby('bucket', sort=True).agg(
        open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), n=('close', 'size'), segments=('segment', 'nunique'),
        first=('timestamp', 'first'), last=('timestamp', 'last'),
        instrument_id=('instrument_id', 'first'), raw_index=('raw_index', 'last'),
        minute=('minute', 'first'), date=('date', 'first'), rth=('rth', 'all'))
    b = b[(b.n == 5) & (b.segments == 1) & (b['first'] == b.index) &
          (b['last'] == b.index+pd.Timedelta(minutes=4))].copy()
    b['bs'] = ((b.index.to_series().diff() != pd.Timedelta(minutes=5)) |
               b.instrument_id.ne(b.instrument_id.shift())).cumsum()
    prev = b.close.groupby(b.bs).shift()
    tr = pd.concat([b.high-b.low, (b.high-prev).abs(), (b.low-prev).abs()], axis=1).max(axis=1)
    b['atr'] = tr.groupby(b.bs, sort=False).transform(lambda s: s.rolling(14, min_periods=14).mean())
    v = d.volume.where(d.rth, 0.)
    vw = (((d.high+d.low+d.close)/3)*v).groupby(d.key).cumsum()/v.groupby(d.key).cumsum().replace(0, np.nan)
    b['vwap'] = vw.iloc[b.raw_index].to_numpy()
    seed = d.rth & d.minute.lt(START+30)
    count = seed.astype(int).groupby(d.key).cumsum()
    oh = d.high.where(seed).groupby(d.key).cummax().groupby(d.key).ffill()
    ol = d.low.where(seed).groupby(d.key).cummin().groupby(d.key).ffill()
    b['or_high'] = oh.where(count.eq(30)).iloc[b.raw_index].to_numpy()
    b['or_low'] = ol.where(count.eq(30)).iloc[b.raw_index].to_numpy()
    daily = d[d.rth].groupby('date', sort=True).agg(
        n=('close', 'size'), contracts=('instrument_id', 'nunique'),
        instrument_id=('instrument_id', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), open=('open', 'first'),
        first_min=('minute', 'min'), last_min=('minute', 'max'))
    daily['full'] = (daily.n == 390) & (daily.contracts == 1) & (daily.first_min == START) & (daily.last_min == END-1)
    same = daily.instrument_id.eq(daily.instrument_id.shift())
    p = daily.close.shift().where(same)
    daily['tr'] = pd.concat([daily.high-daily.low, (daily.high-p).abs(), (daily.low-p).abs()], axis=1).max(axis=1)
    daily['atr20'] = daily.tr.where(daily.full).rolling(20, min_periods=20).mean()
    previous = {}
    for n in range(1, len(daily)):
        day, prev_day = daily.index[n], daily.index[n-1]
        # Day n's completed statistics never become signal inputs for day n.
        if bool(daily.iloc[n-1]['full']) and (pd.Timestamp(day)-pd.Timestamp(prev_day)).days <= 4:
            previous[day] = dict(daily.iloc[n-1], date=prev_day)
    return b.reset_index(names='bar_start'), previous


def quantize(price, side):
    return (math.floor(price/TICK+1e-8) if side == 1 else math.ceil(price/TICK-1e-8))*TICK


def candidates(d):
    b, previous = context(d)
    found = {name: [] for name in SPECS}
    cost = FEE/PV + 4*TICK
    def add(name, row, side, stop, target):
        if not all(np.isfinite(z) for z in (stop, target, row.atr)):
            return
        ref = float(row.close)
        stop, target = quantize(float(stop), side), quantize(float(target), side)
        risk, reward = side*(ref-stop), side*(target-ref)
        if risk < 2*cost or risk > 3*row.atr or reward < 1.5*risk or reward < 5*cost:
            return
        found[name].append(dict(index=int(row.raw_index), side=int(side), reference=ref,
            stop=stop, target=target, risk=risk,
            signal_time=(row.bar_start+pd.Timedelta(minutes=5)).isoformat()))
    for _, group in b[b.rth].groupby(['date', 'instrument_id'], sort=False):
        rows = list(group.itertuples(index=False))
        if not rows or rows[0].minute != START:
            continue
        opening = rows[0]
        prior = previous.get(opening.date)
        if prior and prior['instrument_id'] != opening.instrument_id:
            prior = None
        accepted = {1: 0, -1: 0}
        armed = {1: False, -1: False}
        gap_used, last = False, None
        for row in rows:
            contiguous = last is not None and row.bar_start-last.bar_start == pd.Timedelta(minutes=5)
            if not contiguous:
                accepted = {1: 0, -1: 0}
                armed = {1: False, -1: False}
            a = float(row.atr)
            if not np.isfinite(a) or a <= 0 or not START+30 <= row.minute < END-120 or not np.isfinite(row.or_high):
                last = row
                continue
            for side in (1, -1):
                level = row.or_high if side == 1 else row.or_low
                aligned = side*(row.close-level) > 0 and side*(row.close-row.vwap) > 0
                touch = row.low <= level+.25*a if side == 1 else row.high >= level-.25*a
                reversal = row.close > row.open if side == 1 else row.close < row.open
                if armed[side] and contiguous and aligned and touch and reversal:
                    extreme = min(row.low, last.low) if side == 1 else max(row.high, last.high)
                    stop = extreme-side*.25*a
                    risk = side*(row.close-stop)
                    add('opening_acceptance_retest', row, side, stop, row.close+side*3*risk)
                    armed[side], accepted[side] = False, 0
                elif aligned:
                    accepted[side] += 1
                    if accepted[side] >= 2:
                        armed[side] = True
                else:
                    accepted[side] = 0
                    if side*(row.close-level) < -a:
                        armed[side] = False
            if prior is not None:
                ph, pl = prior['high'], prior['low']
                mid = (ph+pl)/2
                if row.high >= ph+.25*a and row.close < ph and row.close < row.open:
                    add('prior_extreme_reclaim', row, -1, row.high+.25*a, mid)
                if row.low <= pl-.25*a and row.close > pl and row.close > row.open:
                    add('prior_extreme_reclaim', row, 1, row.low-.25*a, mid)
                gap, da = opening.open-prior['close'], prior['atr20']
                if not gap_used and row.minute < START+90 and np.isfinite(da) and .2*da <= abs(gap) <= .8*da:
                    side = -1 if gap > 0 else 1
                    failed = (row.close < row.or_low and row.close < row.vwap) if side == -1 else (row.close > row.or_high and row.close > row.vwap)
                    unfilled = row.or_low > prior['close'] if side == -1 else row.or_high < prior['close']
                    if failed and unfilled:
                        stop = row.or_high+.25*a if side == -1 else row.or_low-.25*a
                        add('gap_fill_after_opening_failure', row, side, stop, prior['close'])
                        gap_used = True
            last = row
    return found


def fill(price, side, ticks):
    q = price/TICK+side*ticks
    return (math.ceil(q-1e-8) if side > 0 else math.floor(q+1e-8))*TICK


def replay(d, orders, horizon):
    ts = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op, hi, lo, cl = (d[c].to_numpy(float) for c in ('open', 'high', 'low', 'close'))
    seg, minute, dates = d.segment.to_numpy(), d.minute.to_numpy(), d.date.to_numpy()
    trades, censored, rejected = [], [], Counter()
    used, busy = set(), -1
    for order in orders:
        i = order['index']; e = i+1
        if i <= busy or dates[i] in used:
            continue
        if e >= len(d) or seg[e] != seg[i] or ts[e]-ts[i] != 60_000_000_000:
            rejected['missing_next_minute'] += 1
            used.add(dates[i])
            continue
        if not START <= minute[e] < END-30 or dates[e] != dates[i]:
            rejected['out_of_session'] += 1
            continue
        used.add(dates[i])
        side, stop, target = order['side'], order['stop'], order['target']
        if side not in (-1, 1):
            raise ValueError('Direction must be long or short')
        entry, deadline, closed, j = op[e], ts[e]+horizon*60_000_000_000, False, e
        while j < len(d) and seg[j] == seg[e]:
            reason, raw = None, None
            if j == e and (side*(entry-stop) <= 0 or side*(entry-target) >= 0):
                reason, raw = 'entry_gap_outside_bracket', entry
            elif side*(op[j]-stop) <= 0:
                reason, raw = 'gap_stop', op[j]
            elif (side == 1 and lo[j] <= stop) or (side == -1 and hi[j] >= stop):
                reason, raw = 'stop', stop
            elif (side == 1 and hi[j] >= target) or (side == -1 and lo[j] <= target):
                reason, raw = 'target', target
            elif ts[j]+60_000_000_000 >= deadline or minute[j] >= END-1:
                reason, raw = 'time_or_session', cl[j]
            if reason:
                trades.append(dict(order, entry=d.timestamp.iloc[e].isoformat(),
                    exit=(d.timestamp.iloc[j]+pd.Timedelta(minutes=1)).isoformat(),
                    instrument_id=int(d.instrument_id.iloc[e]), entry_raw=float(entry),
                    exit_raw=float(raw), reason=reason, date=dates[e]))
                closed, busy = True, j
                break
            j += 1
        if not closed:
            k = max(e, j-1)
            censored.append(dict(order, entry=d.timestamp.iloc[e].isoformat(),
                last_seen=d.timestamp.iloc[k].isoformat(), entry_raw=float(entry), last_raw=float(cl[k]),
                reason='missing_minute_contract_switch_or_end', date=dates[e]))
            busy = k
    return trades, censored, dict(rejected)


def summarize(trades, censored, rejected, name, ticks):
    ledger = []
    for t in trades:
        entry, exit_ = fill(t['entry_raw'], t['side'], ticks), fill(t['exit_raw'], -t['side'], ticks)
        ledger.append(dict(t, entry_fill=entry, exit_fill=exit_, net=round(t['side']*(exit_-entry)*PV-FEE, 6)))
    p = np.array([x['net'] for x in ledger], float); eq = np.r_[0., p.cumsum()]
    wins, losses, monthly = p[p > 0].sum(), -p[p < 0].sum(), {}
    for t in ledger:
        m = t['date'][:7]; monthly[m] = round(monthly.get(m, 0.)+t['net'], 6)
    return dict(spec=name, cost_ticks_each_side=ticks, round_trip_fee_assumed=FEE,
        trades=len(ledger), net_dollars=round(float(p.sum()), 6),
        avg_trade=round(float(p.mean()), 6) if len(p) else None,
        win_rate=round(float((p > 0).mean()*100), 3) if len(p) else None,
        gross_wins=round(float(wins), 6), gross_losses=round(float(losses), 6),
        profit_factor=round(float(wins/losses), 6) if losses else None,
        closed_trade_max_drawdown=round(float(np.max(np.maximum.accumulate(eq)-eq)), 6),
        censored_positions=len(censored), censored_fraction=len(censored)/max(1, len(ledger)+len(censored)),
        monthly=monthly, rejected=rejected, exit_reasons=dict(Counter(t['reason'] for t in ledger)),
        raw_price_pnl=round(sum(t['side']*(t['exit_raw']-t['entry_raw'])*PV for t in trades), 6),
        trade_ledger=ledger, censored_ledger=censored, gex_used=False, live_ready=False)


def evaluate(frame, selected=None):
    d = prepare(frame); signals = candidates(d); out = []
    for name, horizon in SPECS.items():
        if selected is not None and name != selected:
            continue
        trades, censored, rejected = replay(d, signals[name], horizon)
        for ticks in (2, 4):
            out.append(summarize(trades, censored, rejected, name, ticks))
    manifest = dict(study_id=STUDY, ticker='MES', bars=len(d), first_bar=d.timestamp.iloc[0].isoformat(),
        last_bar=d.timestamp.iloc[-1].isoformat(), specs=SPECS, point_value=PV, tick_size=TICK,
        gex_used=False, new_vendor_downloads=0, live_ready=False, mnq_changed=False,
        max_entries_per_strategy_per_session=1, price_source='cached exact-contract MES OHLCV',
        execution='completed five-minute signal; next minute open; stop first if ambiguous',
        vwap='minute typical-price/volume proxy, not trade VWAP',
        drawdown='closed-trade only; unresolved positions excluded from realized PnL',
        validation='reused 2023/24 development; 2025 previously seen, not blind OOS')
    return manifest, out


def select_candidate(dev):
    choices = []
    for name in SPECS:
        rows = [r for y in (2023, 2024) for r in dev.get(y, [])
                if r['spec'] == name and r['cost_ticks_each_side'] == 4]
        if len(rows) != 2:
            continue
        if all(r['trades'] >= 100 and r['net_dollars'] > 0 and r['profit_factor'] is not None and
               r['profit_factor'] >= 1.1 and r['censored_fraction'] <= .01 for r in rows):
            score = min(r['net_dollars']/max(1., r['closed_trade_max_drawdown']) for r in rows)
            choices.append((score, name))
    return sorted(choices, key=lambda x: (-x[0], x[1]))[0][1] if choices else None


def run():
    """Existing MES caches only; writes are restricted to new v4 research tables."""
    import psycopg2
    from psycopg2.extras import Json
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=15)
    conn.autocommit = True; cur = conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK,))
    if not cur.fetchone()[0]:
        conn.close(); return
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status, **detail):
        cur.execute('''INSERT INTO valor_mes_v4_state(study_id,status,detail) VALUES(%s,%s,%s)
            ON CONFLICT(study_id) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=now()''',
            (STUDY, status, Json(dict(detail, source_sha256=code_hash, mnq_changed=False, new_vendor_downloads=0))))
    def store(year, manifest, rows):
        manifest = dict(manifest, source_sha256=code_hash)
        summary = [{k: v for k, v in r.items() if k not in ('trade_ledger', 'censored_ledger')} for r in rows]
        cur.execute('''INSERT INTO valor_mes_v4_results(study_id,year,manifest,summary,evidence_gzip)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (STUDY, year, Json(manifest), Json(summary), gzip.compress(json.dumps(rows, allow_nan=False).encode(), mtime=0)))
        return summary
    def cached(year):
        cur.execute('SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s',
                    (f'GLBX.MDP3:ohlcv-1m:MES.v.0:{year}',))
        r = cur.fetchone()
        if not r:
            raise ValueError('Required MES cache absent; downloads prohibited')
        body = bytes(r[1]); h = hashlib.sha256(body).hexdigest()
        if h != r[0] or h != CACHE_HASHES[year]:
            raise ValueError('MES cache version mismatch')
        return pd.read_parquet(io.BytesIO(body)), h
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_mes_v4_state(study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
            CREATE TABLE IF NOT EXISTS valor_mes_v4_results(study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));''')
        cur.execute('SELECT status FROM valor_mes_v4_state WHERE study_id=%s', (STUDY,))
        if cur.fetchone() == ('completed',):
            return
        cur.execute("SELECT COUNT(*) FROM valor_mes_v4_results WHERE study_id=%s AND manifest->>'source_sha256' IS DISTINCT FROM %s", (STUDY, code_hash))
        if cur.fetchone()[0]:
            state('blocked_source_version'); return
        dev = {}
        for year in (2023, 2024):
            cur.execute('SELECT summary FROM valor_mes_v4_results WHERE study_id=%s AND year=%s', (STUDY, year))
            r = cur.fetchone()
            if r:
                dev[year] = r[0]; continue
            state('evaluating_development', ticker='MES', year=year)
            frame, cache_hash = cached(year); manifest, rows = evaluate(frame)
            manifest.update(cache_sha256=cache_hash, phase='development')
            dev[year] = store(year, manifest, rows); del frame, rows
        selected = select_candidate(dev)
        cur.execute('SELECT 1 FROM valor_mes_v4_results WHERE study_id=%s AND year=2025', (STUDY,))
        if not cur.fetchone():
            if selected:
                state('chronological_check', year=2025, selected=selected)
                frame, cache_hash = cached(2025); manifest, rows = evaluate(frame, selected)
                manifest.update(cache_sha256=cache_hash, phase='chronological_check', selection_frozen=selected)
                store(2025, manifest, rows)
            else:
                store(2025, dict(phase='not_tested', reason='no_development_candidate_passed'), [])
        state('completed', selected=selected, development_years=[2023, 2024],
            test_year_2025='chronological_check' if selected else 'not_tested', live_ready=False, gex_used=False)
    except Exception as exc:
        try:
            state('failed', error_type=type(exc).__name__)
        except Exception:
            pass
        logging.getLogger(__name__).error('MES cache-only v4 failed: %s', type(exc).__name__)
    finally:
        try:
            cur.execute('SELECT pg_advisory_unlock(%s)', (LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag = os.getenv('VALOR_MES_V4_AUTORUN', os.getenv('VALOR_EXIT_RESEARCH_AUTORUN',
                     os.getenv('VALOR_CONTRACT_RESEARCH_AUTORUN', 'false')))
    if flag.lower() not in {'1', 'true', 'yes', 'on'}:
        return False
    import threading
    threading.Thread(target=run, name='valor-mes-v4-cache-only', daemon=True).start()
    return True


if __name__ == '__main__':
    run()
