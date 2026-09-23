"""Strict cash-session research kernel. No broker, DB or vendor calls.

OHLC execution scenarios, not verified quotes. Incomplete exposure prevents a
full-strategy net/PF claim. The policy is NYSE cash-hours-only, not commodity RTH.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import numpy as np
import pandas as pd

CT = ZoneInfo('America/Chicago')
MINUTE_NS = 60_000_000_000
HOLIDAYS = {
    2023: '01-02 01-16 02-20 04-07 05-29 06-19 07-04 09-04 11-23 12-25',
    2024: '01-01 01-15 02-19 03-29 05-27 06-19 07-04 09-02 11-28 12-25',
    2025: '01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25',
    2026: '01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25',
}
EARLY = {2023: '07-03 11-24', 2024: '07-03 11-29 12-24',
         2025: '07-03 11-28 12-24', 2026: '11-27 12-24'}
CALENDAR_SOURCES = [
    'https://ir.theice.com/press/news-details/2022/NYSE-Group-Announces-2023-2024-and-2025-Holiday-and-Early-Closings-Calendar/default.aspx',
    'https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx',
    'https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx',
]


def canonical(value):
    """Canonical JSON including PostgreSQL's normalization of signed zero."""
    def clean(x):
        if isinstance(x, dict): return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)): return [clean(v) for v in x]
        if isinstance(x, (np.integer,)): return int(x)
        if isinstance(x, (np.bool_,)): return bool(x)
        if isinstance(x, (float, np.floating)):
            x = float(x)
            if not math.isfinite(x): raise ValueError('Nonfinite evidence')
            return 0 if x == 0 else x
        return x
    return json.dumps(clean(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def session(day):
    """Published core session and five-minute flatten buffer, known ex ante."""
    if not isinstance(day, date): day = date.fromisoformat(str(day))
    if day.year not in HOLIDAYS: raise ValueError('Calendar year not audited')
    if day.weekday() >= 5 or day.strftime('%m-%d') in HOLIDAYS[day.year].split(): return None
    early = day.strftime('%m-%d') in EARLY[day.year].split()
    opening = datetime(day.year, day.month, day.day, 8, 30, tzinfo=CT)
    close = datetime(day.year, day.month, day.day, 12 if early else 15, 0, tzinfo=CT)
    return opening, close, close-timedelta(minutes=5)


def prepare(frame, tick):
    if not math.isfinite(tick) or tick <= 0: raise ValueError('Invalid tick')
    d = frame.copy()
    if 'timestamp' not in d:
        if 'ts_event' not in d: d = d.reset_index()
        d['timestamp'] = d['ts_event']
    cols = ['timestamp', 'instrument_id', 'open', 'high', 'low', 'close', 'volume']
    if d.empty or not set(cols).issubset(d): raise ValueError('Exact-contract OHLCV required')
    if getattr(d.timestamp.dtype, 'tz', None) is None:
        if any(pd.Timestamp(v).tzinfo is None for v in d.timestamp): raise ValueError('Naive timestamps')
    d = d[cols].copy(); d['timestamp'] = pd.to_datetime(d.timestamp, utc=True)
    d = d.sort_values('timestamp').reset_index(drop=True)
    if d.timestamp.duplicated().any() or d.timestamp.isna().any() or d.instrument_id.isna().any():
        raise ValueError('Duplicate or null observations')
    if not d.timestamp.eq(d.timestamp.dt.floor('min')).all(): raise ValueError('Minute start required')
    for col in cols[2:]: d[col] = pd.to_numeric(d[col], errors='raise')
    a = d[cols[2:]].to_numpy(float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any(): raise ValueError('Invalid OHLCV')
    if ((d.high < d[['open', 'close', 'low']].max(axis=1)) | (d.low > d[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Invalid bar geometry')
    if not np.allclose(a[:, :4]/tick, np.rint(a[:, :4]/tick), atol=1e-5, rtol=0): raise ValueError('Off-grid prices')
    local = d.timestamp.dt.tz_convert('America/Chicago')
    d['date'] = local.dt.strftime('%Y-%m-%d'); d['minute'] = local.dt.hour*60+local.dt.minute
    d['segment'] = ((d.timestamp.diff().dt.total_seconds() != 60) | d.instrument_id.ne(d.instrument_id.shift())).cumsum()
    clocks = {day: session(day) for day in d.date.unique()}
    for col, offset in [('cash_open_ns', 0), ('cash_close_ns', 1), ('flat_ns', 2)]:
        values = {day: int(pd.Timestamp(s[offset]).value) if s else -1 for day, s in clocks.items()}
        d[col] = d.date.map(values).astype('int64')
    ns = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    d['rth'] = (ns >= d.cash_open_ns) & (ns < d.cash_close_ns) & (d.cash_open_ns > 0)
    d['key'] = d.date+':'+d.instrument_id.astype(str); d['raw_index'] = np.arange(len(d))
    return d


def round_level(value, side, tick):
    return (math.floor(value/tick+1e-8) if side > 0 else math.ceil(value/tick-1e-8))*tick


def replay(d, orders, point_value, tick, horizon, daily_limit=None, cooldown=0, trail_atr=None):
    """Signal-time orders, next open, no overlap, and predetermined pre-close exit.

    Stop first on ambiguous bars. A limit target requires one-tick trade-through.
    Raw paths are the same across friction scenarios. Unknown exposure is retained
    and blocks further entries that date; no complete-account claim is then made.
    """
    if horizon <= 0 or cooldown < 0: raise ValueError('Invalid execution duration')
    ns = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    op, hi, lo, cl = (d[c].to_numpy(float) for c in ('open', 'high', 'low', 'close'))
    ids, days, flat = d.instrument_id.to_numpy(), d.date.to_numpy(), d.flat_ns.to_numpy()
    opening, closes = d.cash_open_ns.to_numpy(), d.cash_close_ns.to_numpy()
    attempts, skips = Counter(), Counter()
    done, unknown, blocked = [], [], set()
    busy = next_allowed = last_i = -1; candidate_count = 0
    for raw in orders:
        candidate_count += 1; o = dict(raw); i = int(o['index']); e = i+1
        if not 0 <= i < len(d) or i < last_i: raise ValueError('Unordered or out-of-range signal')
        last_i = i; day = days[i]; decision = ns[i]+MINUTE_NS
        if opening[i] < 0 or not opening[i] <= decision < flat[i]: skips['outside_cash_entry_window'] += 1; continue
        if day in blocked: skips['date_blocked_after_unknown_exposure'] += 1; continue
        if e <= busy or decision < next_allowed: skips['position_or_cooldown'] += 1; continue
        if daily_limit is not None and attempts[day] >= daily_limit: skips['daily_limit'] += 1; continue
        side = int(o['side']); ref = float(o.get('reference', cl[i]))
        risk, stop, target = o.get('risk'), o.get('stop'), o.get('target')
        if side not in (-1, 1) or not math.isfinite(ref): raise ValueError('Invalid signal')
        if risk is not None and (not math.isfinite(risk) or risk <= 0): skips['invalid_risk'] += 1; continue
        if stop is not None and (not math.isfinite(stop) or side*(ref-stop) <= 0): skips['invalid_stop'] += 1; continue
        if target is not None and (not math.isfinite(target) or side*(target-ref) <= 0): skips['invalid_target'] += 1; continue
        if o.get('trail') and (risk is None or stop is None or trail_atr is None): raise ValueError('Incomplete trail configuration')
        deadline = min(decision+int(horizon)*MINUTE_NS, flat[i])
        if o.get('exit_minute') is not None:
            at = pd.Timestamp(day, tz='America/Chicago')+pd.Timedelta(minutes=int(o['exit_minute']))
            deadline = min(deadline, int(at.value))
        if deadline <= decision: skips['no_holding_window'] += 1; continue
        attempts[day] += 1
        detail = dict(signal_index=i, signal_bar_start=d.timestamp.iloc[i].isoformat(),
            decision_time=pd.Timestamp(decision, tz='UTC').isoformat(), date=day, side=side,
            reference=ref, stop=stop, target=target, risk=risk,
            scheduled_exit=pd.Timestamp(deadline, tz='UTC').isoformat(), instrument_id=int(ids[i]))
        if e >= len(d) or ns[e] != decision or ids[e] != ids[i]:
            unknown.append(dict(detail, reason='missing_entry_observation', entry=None)); blocked.add(day); continue
        entry = float(op[e]); detail.update(entry=d.timestamp.iloc[e].isoformat(), entry_raw=entry)
        best = entry; j = e; closed = False
        while j < len(d):
            if ids[j] != ids[e] or days[j] != day or (j > e and ns[j]-ns[j-1] != MINUTE_NS): break
            reason = price = None
            if ns[j] >= deadline: reason, price = 'scheduled_open', float(op[j])
            elif j == e and ((stop is not None and side*(entry-stop) <= 0) or (target is not None and side*(entry-target) >= 0)):
                reason, price = 'entry_gap_outside_bracket', entry
            elif stop is not None and side*(op[j]-stop) <= 0: reason, price = 'gap_stop', float(op[j])
            elif stop is not None and ((side > 0 and lo[j] <= stop) or (side < 0 and hi[j] >= stop)):
                reason, price = 'stop', float(stop)
            elif target is not None and ((side > 0 and hi[j] >= target+tick) or (side < 0 and lo[j] <= target-tick)):
                reason, price = 'limit_trade_through', float(target)
            if reason:
                xt = ns[j]+(MINUTE_NS if reason in ('stop', 'limit_trade_through') else 0)
                if xt > flat[i] or xt >= closes[i]: raise AssertionError('Exit outside cash policy')
                done.append(dict(detail, exit_index=j, exit=pd.Timestamp(xt, tz='UTC').isoformat(),
                    exit_raw=price, reason=reason, raw_price_pnl=round(side*(price-entry)*point_value, 8)))
                busy = j; next_allowed = xt+cooldown*MINUTE_NS; closed = True; break
            if o.get('trail'):
                best = max(best, hi[j]) if side > 0 else min(best, lo[j])
                a = float(trail_atr[j])
                if side*(best-ref) >= 2*risk and math.isfinite(a) and a > 0:
                    proposed = round_level(best-side*2*a, side, tick)
                    stop = max(stop, proposed) if side > 0 else min(stop, proposed)
            j += 1
        if not closed:
            k = max(e, j-1)
            unknown.append(dict(detail, reason='missing_interval_or_contract_switch', last_seen=d.timestamp.iloc[k].isoformat(),
                last_raw=float(cl[k]), mark_price_pnl=round(side*(cl[k]-entry)*point_value, 8)))
            blocked.add(day); busy = k
    if candidate_count != sum(skips.values())+len(done)+len(unknown): raise AssertionError('Decision conservation')
    return done, unknown, dict(skips), candidate_count


def summarize(trades, unknown, skips, candidates, pv, tick, ticks, year):
    cost = 3.+2*ticks*tick*pv
    ledger = [dict(t, assumed_cost=cost, net=round(t['raw_price_pnl']-cost, 6)) for t in trades]
    p = np.array([t['net'] for t in ledger], float); eq = np.r_[0., p.cumsum()]
    wins, loss = float(p[p > 0].sum()), float(-p[p < 0].sum())
    monthly = {f'{year}-{m:02}': 0. for m in range(1, 13)}
    for t in ledger: monthly[t['date'][:7]] += t['net']
    complete = not unknown
    return dict(candidates=candidates, skipped=skips, closed_trades=len(p), unresolved=len(unknown),
        coverage_complete=complete, net_dollars=round(float(p.sum()), 6) if complete else None,
        resolved_net_diagnostic=round(float(p.sum()), 6), raw_price_pnl=round(sum(t['raw_price_pnl'] for t in trades), 6),
        assumed_total_cost=round(len(p)*cost, 6), cost_per_roundtrip=cost, cost_ticks_each_side=ticks, fee_assumed=3.,
        profit_factor=round(wins/loss, 6) if complete and loss else None,
        resolved_profit_factor_diagnostic=round(wins/loss, 6) if loss else None,
        average_resolved_trade=round(float(p.mean()), 6) if len(p) else None,
        closed_trade_drawdown=round(float((np.maximum.accumulate(eq)-eq).max()), 6),
        monthly_resolved=monthly, long_trades=sum(t['side'] > 0 for t in ledger), short_trades=sum(t['side'] < 0 for t in ledger),
        exit_reasons=dict(Counter(t['reason'] for t in trades)), ledger=ledger, unresolved_ledger=unknown,
        live_ready=False, execution='OHLC scenario; bid/ask/latency not verified', session='CASH_ONLY_FLAT_5_MIN_BEFORE_CLOSE')
