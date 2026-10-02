"""Recompute every affected price hypothesis through strict cash-session execution.

Separate recorded-signal management comparison changes only the session policy.
No broker requests or paid downloads. Reused history; no live approval.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from datetime import timedelta
import gzip
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import numpy as np
import pandas as pd
from scripts import valor_cash_engine_v8 as core

STUDY = 'valor-cash-v8-20260923'
LOCK = 63260923
YEARS = (2023, 2024, 2025)
PRODUCTS = {'MES': ('MES.v.0', 5., .25), 'MNQ': ('MNQ.v.0', 2., .25),
            'RTY': ('M2K.v.0', 5., .1), 'MGC': ('MGC.v.0', 10., .1),
            'NG': ('MNG.v.0', 1000., .001), 'CL': ('MCL.v.0', 100., .01)}
PINNED = {
    'v2': ('scripts.valor_contract_research_v2', '69d32ce2d6899a378a892b4e46c88b9484dcf30e2e9b838bf52514bf7cbfda1c'),
    'v3': ('scripts.valor_exit_specialists_v3', '50c8dd0c3ee949365b085638d6363bf1d128c7b6b501eda55184b3e7297d2002'),
    'v4': ('scripts.valor_mes_rebuild_v4', 'a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c'),
    'v6': ('scripts.valor_mes_session_v6', 'd3de6fbd29767a0c89c3816ffbbbcdb17f188952f9cecd75a2f8dea6892aceb0'),
}
ARCHIVE_HASH = '6905cc403754594824f313421ab644ae787c55d40f42fcd071465d5ece858ef9'
CONFIG = dict(years=YEARS, products=PRODUCTS, flatten_buffer_minutes=5, cost_ticks_each_side=[2, 4],
    fee_assumed=3., limit_trade_through_ticks=1, no_old_result_reads=True,
    incomplete_position_policy='retain unknown exposure; withhold full net and PF; block date',
    diagnostic_not_holdout=True, no_automatic_promotion=True,
    commodity_session_scope='NYSE-hours-only experiment; not native commodity RTH')
LEDGER_KEYS = {'ledger', 'unresolved_ledger'}


def modules():
    mods, hashes = {}, {}
    for key, (name, pinned) in PINNED.items():
        m = importlib.import_module(name)
        h = hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
        if h != pinned: raise ValueError('Pinned signal module changed: '+key)
        mods[key] = m; hashes[name] = h
    for m in (core, sys.modules[__name__]):
        hashes[m.__name__] = hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
    return mods, hashes


def prior_cash_days(d):
    """Only the complete PREVIOUS actual cash session can enter a current decision."""
    r = d[d.rth]
    daily = r.groupby('date', sort=True).agg(n=('close', 'size'), ids=('instrument_id', 'nunique'),
        instrument_id=('instrument_id', 'first'), high=('high', 'max'), low=('low', 'min'),
        close=('close', 'last'), open=('open', 'first'), first=('timestamp', 'first'), last=('timestamp', 'last'))
    full = []
    for day, row in daily.iterrows():
        s = core.session(day); count = int((s[1]-s[0]).total_seconds()/60)
        full.append(row.n == count and row.ids == 1 and row['first'] == pd.Timestamp(s[0]) and
                    row['last'] == pd.Timestamp(s[1])-pd.Timedelta(minutes=1))
    daily['full'] = full
    p = daily.close.shift().where(daily.instrument_id.eq(daily.instrument_id.shift()))
    tr = pd.concat([daily.high-daily.low, (daily.high-p).abs(), (daily.low-p).abs()], axis=1).max(axis=1)
    daily['atr20'] = tr.where(daily.full).rolling(20, min_periods=20).mean()
    out, past = {}, None
    for day, row in daily.iterrows():
        dt = pd.Timestamp(day).date()-timedelta(days=1)
        while dt.year in core.HOLIDAYS and core.session(dt) is None: dt -= timedelta(days=1)
        if past and past[0] == str(dt) and past[1]['full']: out[day] = dict(past[1], date=past[0])
        past = (day, row.to_dict())
    return out


def v4_orders(d, m):
    # Reuse completed-bar context, replace the old calendar-based prior-day mapping.
    b, _ = m.context(d); previous = prior_cash_days(d)
    found = {name: [] for name in m.SPECS}; cost = 1.6
    def add(name, row, side, stop, target):
        if not all(np.isfinite(v) for v in (stop, target, row.atr)): return
        stop, target = core.round_level(stop, side, .25), core.round_level(target, side, .25)
        risk, reward = side*(row.close-stop), side*(target-row.close)
        if risk < 2*cost or risk > 3*row.atr or reward < 1.5*risk or reward < 5*cost: return
        found[name].append(dict(index=int(row.raw_index), side=side, reference=float(row.close),
                                stop=stop, target=target, risk=risk))
    for _, group in b[b.rth].groupby(['date', 'instrument_id'], sort=False):
        rows = list(group.itertuples(index=False))
        if not rows or rows[0].minute != 510: continue
        opening = rows[0]; prior = previous.get(opening.date)
        if prior and prior['instrument_id'] != opening.instrument_id: prior = None
        accepted, armed, used, last = {1: 0, -1: 0}, {1: False, -1: False}, False, None
        for row in rows:
            contiguous = last is not None and row.bar_start-last.bar_start == pd.Timedelta(minutes=5)
            if not contiguous: accepted, armed = {1: 0, -1: 0}, {1: False, -1: False}
            a = float(row.atr)
            if not np.isfinite(a) or a <= 0 or not 540 <= row.minute < 780 or not np.isfinite(row.or_high): last = row; continue
            for side in (1, -1):
                level = row.or_high if side > 0 else row.or_low
                aligned = side*(row.close-level) > 0 and side*(row.close-row.vwap) > 0
                touch = row.low <= level+.25*a if side > 0 else row.high >= level-.25*a
                reversal = row.close > row.open if side > 0 else row.close < row.open
                if armed[side] and contiguous and aligned and touch and reversal:
                    extreme = min(row.low, last.low) if side > 0 else max(row.high, last.high)
                    stop = extreme-side*.25*a; risk = side*(row.close-stop)
                    add('opening_acceptance_retest', row, side, stop, row.close+side*3*risk)
                    armed[side], accepted[side] = False, 0
                elif aligned:
                    accepted[side] += 1
                    if accepted[side] >= 2: armed[side] = True
                else:
                    accepted[side] = 0
                    if side*(row.close-level) < -a: armed[side] = False
            if prior:
                ph, pl = prior['high'], prior['low']; mid = (ph+pl)/2
                if row.high >= ph+.25*a and row.close < ph and row.close < row.open:
                    add('prior_extreme_reclaim', row, -1, row.high+.25*a, mid)
                if row.low <= pl-.25*a and row.close > pl and row.close > row.open:
                    add('prior_extreme_reclaim', row, 1, row.low-.25*a, mid)
                gap, da = opening.open-prior['close'], prior['atr20']
                if not used and row.minute < 600 and np.isfinite(da) and .2*da <= abs(gap) <= .8*da:
                    side = -1 if gap > 0 else 1
                    failed = (row.close < row.or_low and row.close < row.vwap) if side < 0 else (row.close > row.or_high and row.close > row.vwap)
                    unfilled = row.or_low > prior['close'] if side < 0 else row.or_high < prior['close']
                    if failed and unfilled:
                        stop = row.or_high+.25*a if side < 0 else row.or_low-.25*a
                        add('gap_fill_after_opening_failure', row, side, stop, prior['close']); used = True
            last = row
    return found


def lag_filter(orders, d, source, lag, sign):
    from bisect import bisect_left
    if lag not in (1, 2) or sign not in ('all_matched', 'positive_only', 'negative_only'): raise ValueError('Unspecified GEX filter')
    dates = [x[0] for x in source]; out, counts = [], Counter()
    for o in orders:
        day = d.date.iloc[o['index']]; j = bisect_left(dates, day)-lag
        if j < 0 or (pd.Timestamp(day)-pd.Timestamp(dates[j])).days > (4 if lag == 1 else 7): counts['missing_or_stale'] += 1; continue
        value = source[j][1]
        if sign != 'all_matched' and ((sign == 'positive_only' and value <= 0) or (sign == 'negative_only' and value >= 0)):
            counts['sign_filtered'] += 1; continue
        out.append(o)
    return out, dict(counts)


def evaluate(frame, ticker, year, mods, gex):
    _, pv, tick = PRODUCTS[ticker]; d = core.prepare(frame, tick); f = mods['v2'].features(d, ticker)
    output = []
    def execute(family, name, orders, horizon, limit=None, cooldown=0, atr=None, **extra):
        trades, unknown, skips, n = core.replay(d, orders, pv, tick, horizon, limit, cooldown, atr)
        for ticks in (2, 4):
            r = core.summarize(trades, unknown, skips, n, pv, tick, ticks, year)
            r.update(family=family, spec=name, horizon=horizon, year=year, ticker=ticker, **extra); output.append(r)
    for rule in mods['v2'].RULES[ticker]:
        orders = []
        for i in np.flatnonzero(f[rule]):
            a = float(f['atr'][i])
            if not np.isfinite(a) or a <= 0: continue
            side = int(f[rule][i]); ref = float(d.close.iloc[i]); risk = math.ceil(max(4*a, 4*tick)/tick)*tick
            orders.append(dict(index=int(i), side=side, reference=ref, risk=risk, stop=ref-side*risk, target=ref+side*2*risk))
        for horizon in (60, 120): execute('v2_cash', rule, orders, horizon)
    ctx = mods['v3'].context(d, ticker)
    for spec in mods['v3'].SPECS[ticker]:
        orders = []; start, end = mods['v3'].PRODUCTS[ticker][3:]
        for i in np.flatnonzero(f[spec.source]):
            if not start+spec.start_delay <= int(d.minute.iloc[i])+1 < end-30: continue
            a, er = float(ctx['atr5'][i]), float(ctx['efficiency'][i])
            side, ref, cost = int(f[spec.source][i]), float(d.close.iloc[i]), 3/pv+4*tick
            if not np.isfinite(a) or a <= 0 or not np.isfinite(er): continue
            if (spec.efficiency == 'range' and er > .35) or (spec.efficiency == 'trend' and er < .30): continue
            if spec.exit_mode in ('vwap', 'opening_mid', 'range_mid'):
                target = float(ctx[spec.exit_mode][i]); extreme = ctx['low30'][i] if side > 0 else ctx['high30'][i]
                if not np.isfinite(target) or not np.isfinite(extreme): continue
                target = core.round_level(target, side, tick); stop = core.round_level(extreme-side*.25*a, side, tick)
                risk, reward = side*(ref-stop), side*(target-ref)
                if risk <= 0 or risk > 3*a or reward < 1.25*risk or reward < 5*cost: continue
            else:
                risk = math.ceil(max(1.5*a, 2*cost, 4*tick)/tick)*tick; stop = ref-side*risk
                target = ref+side*3*risk if spec.exit_mode == '3r' else None
            orders.append(dict(index=int(i), side=side, reference=ref, risk=risk, stop=stop, target=target,
                                trail=spec.exit_mode == 'trail', exit_minute=end-5))
        execute('v3_cash', spec.name, orders, spec.horizon, 2, 15, ctx['atr5'])
    g = d.close.groupby(d.segment, sort=False)
    hi = d.high.groupby(d.segment, sort=False).transform(lambda z: z.shift().rolling(30, min_periods=30).max())
    lo = d.low.groupby(d.segment, sort=False).transform(lambda z: z.shift().rolling(30, min_periods=30).min())
    e20 = g.transform(lambda z: z.ewm(span=20, min_periods=20, adjust=False).mean())
    e80 = g.transform(lambda z: z.ewm(span=80, min_periods=80, adjust=False).mean())
    rules = {'momentum_15m': np.sign(d.close-g.shift(15)), 'mean_reversion_15m': -np.sign(d.close-g.shift(15)),
        'momentum_30m': np.sign(d.close-g.shift(30)), 'breakout_30m': np.where(d.close > hi, 1, np.where(d.close < lo, -1, 0)),
        'ema_trend_20_80': np.sign(e20-e80)}
    ns = pd.DatetimeIndex(d.timestamp).as_unit('ns').asi8
    cash = (ns+core.MINUTE_NS >= d.cash_open_ns.to_numpy()) & (ns+core.MINUTE_NS < d.flat_ns.to_numpy()) & (d.cash_open_ns.to_numpy() > 0)
    for name, values in rules.items():
        values = np.asarray(values, float)
        orders = [dict(index=int(i), side=int(values[i])) for i in np.flatnonzero(cash & np.isfinite(values) & (values != 0))]
        for horizon in (30, 60, 120, 180, 240): execute('initial_cash', name, orders, horizon)
    if ticker == 'MES':
        found = v4_orders(d, mods['v4'])
        for name, horizon in mods['v4'].SPECS.items():
            execute('v4_cash', name, found[name], horizon, 1)
            for source, series in gex.items():
                for lag in (1, 2):
                    for sign in ('all_matched', 'positive_only', 'negative_only'):
                        selected, counts = lag_filter(found[name], d, series, lag, sign)
                        execute('v5_cash', name, selected, horizon, 1, gex_source=source, gex_lag=lag,
                            gex_filter=sign, filtered_orders=counts, gex_resolution='lagged daily proxy, not intraday')
        for name, (decision, exit_min) in mods['v6'].SPECS.items():
            orders, pre_skips = mods['v6'].orders(d, name)
            for view in ('signal', 'matched_long', 'matched_short'):
                converted = []
                for order in orders:
                    o = dict(order); side = o['side'] if view == 'signal' else (1 if view == 'matched_long' else -1)
                    o.update(side=side, stop=o['reference']-side*o['risk']); converted.append(o)
                execute('v6_cash', name, converted, exit_min-decision, 1, view=view, context_skips=pre_skips)
    expected = 162 if ticker == 'MES' else 66
    validate_results(output, expected)
    manifest = dict(rows=len(d), first=str(d.timestamp.iloc[0]), last=str(d.timestamp.iloc[-1]),
        calendar_sessions=len({day for day in d.date if core.session(day)}), expected_scenarios=expected,
        all_trades_cash_only=True, pre_close_buffer_minutes=5, input_has_real_contract_ids=True,
        quote_verification=False, live_ready=False, execution_definitions_changed=True, actual_bot_parity=False)
    return manifest, output


def record_key(r):
    return (r.get('family'), r.get('spec'), r.get('horizon'), r.get('view'), r.get('gex_source'),
            r.get('gex_lag'), r.get('gex_filter'), r.get('cost_ticks_each_side'))


def summarize_rows(rows): return [{k: v for k, v in r.items() if k not in LEDGER_KEYS} for r in rows]


def validate_results(rows, expected):
    if len(rows) != expected or len({record_key(r) for r in rows}) != expected: raise ValueError('Scenario coverage/identity mismatch')
    for r in rows:
        trades, unknown = r['ledger'], r['unresolved_ledger']
        if len(trades) != r['closed_trades'] or len(unknown) != r['unresolved']: raise ValueError('Ledger count mismatch')
        net = sum(t['net'] for t in trades)
        if abs(net-r['resolved_net_diagnostic']) > .001: raise ValueError('Ledger accounting mismatch')
        if abs(sum(r['monthly_resolved'].values())-net) > .001: raise ValueError('Monthly mismatch')
        if r['candidates'] != sum(r['skipped'].values())+len(trades)+len(unknown): raise ValueError('Unaccounted decisions')
        if abs(r['raw_price_pnl']-r['assumed_total_cost']-net) > .001: raise ValueError('Cost accounting mismatch')
        if unknown and (r['net_dollars'] is not None or r['profit_factor'] is not None): raise ValueError('Incomplete outcome presented as complete')
        for t in trades:
            e, x = pd.Timestamp(t['entry']), pd.Timestamp(t['exit']); s = core.session(t['date'])
            if not s or not s[0] <= e < s[2] or not e <= x <= s[2]: raise ValueError('Out-of-session trade')
    return True


def verified_saved(saved, fingerprint, expected, kind):
    """Completed status is NOT consulted before identity, input, coverage and ledger checks."""
    if saved is None: return False
    manifest, summary, h, body = saved; body = bytes(body)
    if manifest.get('fingerprint') != fingerprint or hashlib.sha256(body).hexdigest() != h: raise ValueError('Saved result identity mismatch')
    rows = json.loads(gzip.decompress(body))
    if len(rows) != expected or core.canonical(summarize_rows(rows)) != core.canonical(summary): raise ValueError('Incomplete/corrupt saved result')
    if kind == 'historical': validate_results(rows, expected)
    return True


def recorded_pair(conn):
    """Same recorded scans and current management/config in both session arms.

    Simulated intraminute paths. Not a recovered historical configuration, quote
    replay, or complete production-bot replication. Historical defaults unverified.
    """
    from scripts import replay_valor_execution as m
    cur = conn.cursor(); cur.execute('SELECT archive_bytes FROM valor_research_archives WHERE sha256=%s', (ARCHIVE_HASH,))
    row = cur.fetchone()
    if not row: raise ValueError('Preserved replay archive unavailable')
    body = bytes(row[0])
    if hashlib.sha256(body).hexdigest() != ARCHIVE_HASH: raise ValueError('Archive checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='valor_v8_') as temp:
        folder = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(body), mode='r:gz') as tar:
            members = [x for x in tar.getmembers() if x.isfile()]
            for required in ('MESZ6_1m.csv.gz', 'mes_scan_inputs.jsonl.gz'):
                matches = [x for x in members if Path(x.name).name == required]
                if len(matches) != 1: raise ValueError('Replay input not unique: '+required)
                (folder/required).write_bytes(tar.extractfile(matches[0]).read())
        start = m.timestamp('2026-09-15T00:00:00+00:00'); end = m.timestamp('2026-09-22T12:42:00+00:00')
        bars, signals, counts = m.load_inputs(folder, start, end)
        config = m.models.ValorConfig(); reports = []
        def allowed(at):
            s = core.session(at.astimezone(core.CT).date())
            return bool(s and s[0] <= at < s[2])
        for policy in ('all_session_recorded', 'cash_only'):
            for path in ('OHLC', 'OLHC'):
                for slip in (2, 4):
                    engine = m.make_engine(config, slip, 3., config.use_sar); original = engine.entry_block
                    if policy == 'cash_only':
                        def restricted(normal=True, original=original, engine=engine):
                            if not allowed(engine.clock.current): return 'cash_session_policy'
                            return original(normal=normal)
                        engine.entry_block = restricted
                    unknown, previous = [], None
                    for at, bar in bars.items():
                        if policy == 'cash_only' and previous and at-previous > m.MINUTE and engine.position:
                            unknown.append(dict(entry=str(engine.position.open_time), at=str(at), reason='gap_with_open_cash_position')); break
                        for second, price in m.simulated_prices(bar, path, 15):
                            engine.clock.current = at+timedelta(seconds=second); engine.price = price
                            if policy == 'cash_only' and engine.position and not allowed(engine.clock.current):
                                status = next(x for x in m.models.PositionStatus if x.value.lower() == 'closed')
                                engine._close_position(engine.position, price, status, 'CASH_SESSION_FLATTEN')
                            elif engine.position: engine._manage_position(engine.position, price, ticker='MES')
                            if second == 0:
                                for signal in signals.get(at, []):
                                    block = engine.entry_block()
                                    if block: engine.counts['entry_blocked_'+block] += 1
                                    else: engine.enter_recorded_signal(signal)
                            engine.mark_equity()
                        previous = at
                    if engine.position and not unknown: unknown.append(dict(entry=str(engine.position.open_time), reason='position_open_at_end'))
                    stats = m.statistics(engine.trades)
                    reports.append(dict(policy=policy, path=path, slippage_ticks_each_side=slip, fee_assumed=3., sar=config.use_sar,
                        **stats, counts=dict(engine.counts), unresolved=len(unknown), unresolved_ledger=unknown,
                        sampled_drawdown=engine.max_drawdown, ledger=engine.trades, source_hashes=engine.source_hashes,
                        coverage_complete=not unknown, full_strategy_net=stats['net_closed_pnl'] if not unknown else None,
                        live_ready=False, historical_config_verified=False, actual_bot_parity=False,
                        interpretation='paired management scenarios conditional on recorded signals; not verified fills'))
                    if policy == 'cash_only':
                        for t in engine.trades:
                            e, x = m.timestamp(t['entry_utc']), m.timestamp(t['exit_utc']); s = core.session(e.astimezone(core.CT).date())
                            if not s or not s[0] <= e < s[2] or x > s[2]: raise AssertionError('Recorded replay cash-window violation')
    manifest = dict(archive_sha256=ARCHIVE_HASH, start=str(start), end=str(end), bars=len(bars), signal_counts=counts,
        config_source='current ValorConfig defaults, not verified historical settings',
        true_historical_three_year_gex_replay=False, exact_contract_assignment='MESZ6 period assumption for scans',
        same_inputs_and_management_across_policy_arms=True, all_session_eod='existing replay carries through maintenance',
        production_parity_verified=False, live_ready=False)
    return manifest, reports


def selfcheck(mods):
    """Real-module integration on synthetic bars, before historical jobs start."""
    gex = {'SPX_ORATS_DAILY': [('2024-01-30', 1.), ('2024-01-31', -1.), ('2024-02-01', 1.)],
           'SPY_BASELINE_DAILY': [('2024-01-30', 1.), ('2024-01-31', -1.), ('2024-02-01', 1.)]}
    scenarios = 0
    for ticker, (_, pv, tick) in PRODUCTS.items():
        ts = pd.date_range('2024-02-01 06:00', periods=540, freq='min', tz='America/Chicago').tz_convert('UTC')
        op = 1000.+np.arange(len(ts))*tick
        frame = pd.DataFrame(dict(timestamp=ts, instrument_id=42, open=op, high=op+2*tick, low=op-tick, close=op+tick, volume=100))
        _, rows = evaluate(frame, ticker, 2024, mods, gex)
        validate_results(rows, 162 if ticker == 'MES' else 66)
        body = core.canonical(rows); json.loads(body); scenarios += len(rows)
    return scenarios


def run():
    import psycopg2
    from psycopg2.extras import Json
    if hasattr(os, 'nice'): os.nice(10)
    mods, hashes = modules()
    runtime = dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, pyarrow=importlib.metadata.version('pyarrow'))
    root = Path(__file__).resolve().parents[1]
    for path in ('scripts/replay_valor_execution.py', 'trading/valor/models.py', 'trading/valor/trader.py', 'trading/valor/signals.py'):
        hashes[path] = hashlib.sha256((root/path).read_bytes()).hexdigest()
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=15); conn.autocommit = True; cur = conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK,))
    if not cur.fetchone()[0]: conn.close(); return
    run_id = None
    def state(status, **detail):
        cur.execute('UPDATE valor_cash_v8_runs SET status=%s,detail=%s,updated_at=now() WHERE run_id=%s', (status, Json(detail), run_id))
        print('VALOR_CASH_V8 '+status+' '+json.dumps(detail), flush=True)
    def get_saved(key, fp, expected, kind):
        cur.execute('SELECT manifest,summary,evidence_sha256,evidence_gzip FROM valor_cash_v8_jobs WHERE job_key=%s', (key,))
        return verified_saved(cur.fetchone(), fp, expected, kind)
    def store(key, ticker, year, kind, manifest, rows, fp, expected):
        if len(rows) != expected: raise ValueError('Unexpected result count')
        summary = summarize_rows(rows); body = gzip.compress(core.canonical(rows), mtime=0)
        manifest.update(fingerprint=fp, expected_scenarios=expected, source_hashes=hashes, runtime=runtime,
                        calendar_sources=core.CALENDAR_SOURCES, config=CONFIG, old_result_tables_read=False)
        cur.execute('INSERT INTO valor_cash_v8_jobs(job_key,run_id,ticker,year,kind,manifest,summary,evidence_sha256,evidence_gzip) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
            (key, run_id, ticker, year, kind, Json(json.loads(core.canonical(manifest))), Json(json.loads(core.canonical(summary))), hashlib.sha256(body).hexdigest(), psycopg2.Binary(body)))
        if not get_saved(key, fp, expected, kind): raise AssertionError('Persisted job absent')
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_cash_v8_runs(run_id text PRIMARY KEY,status text NOT NULL,manifest jsonb,detail jsonb,updated_at timestamptz DEFAULT now());
          CREATE TABLE IF NOT EXISTS valor_cash_v8_jobs(job_key text PRIMARY KEY,run_id text NOT NULL,ticker text,year integer,kind text,manifest jsonb,summary jsonb,evidence_sha256 text,evidence_gzip bytea,created_at timestamptz DEFAULT now());''')
        cur.execute('SELECT pg_database_size(current_database())')
        if cur.fetchone()[0] > 12_000_000_000: raise ValueError('Research storage budget exceeded')
        cur.execute("SELECT cache_key,sha256,encode(sha256(parquet_zstd),'hex') FROM valor_research_bar_cache")
        inventory = {key: h for key, h, actual in cur.fetchall() if h == actual}
        required = [f'GLBX.MDP3:ohlcv-1m:{cfg[0]}:{year}' for cfg in PRODUCTS.values() for year in YEARS]
        if any(key not in inventory for key in required): raise ValueError('Required raw data absent or corrupt')
        cur.execute("SELECT trade_date,net_gamma FROM gex_structure_daily WHERE symbol='SPX' AND trade_date>='2022-01-01' AND trade_date<'2026-01-01' ORDER BY trade_date")
        spx = [(str(day), float(v)) for day, v in cur.fetchall()]
        cur.execute("SELECT trade_date,net_gex FROM sw_gamma_daily WHERE trade_date>='2022-01-01' AND trade_date<'2026-01-01' ORDER BY trade_date")
        gex = {'SPX_ORATS_DAILY': spx, 'SPY_BASELINE_DAILY': [(str(day), float(v)) for day, v in cur.fetchall()]}
        for rows in gex.values():
            if not rows or len({r[0] for r in rows}) != len(rows) or not all(math.isfinite(r[1]) for r in rows): raise ValueError('Invalid gamma source')
        identity = dict(CONFIG, source_hashes=hashes, inputs={k: inventory[k] for k in required}, gex_hash=core.digest(gex),
                        runtime=runtime, calendar_hash=core.digest([core.HOLIDAYS, core.EARLY]), archive_hash=ARCHIVE_HASH)
        run_id = STUDY+'-'+core.digest(identity)[:16]
        cur.execute('INSERT INTO valor_cash_v8_runs(run_id,status,manifest,detail) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (run_id, 'validating', Json(identity), Json({})))
        # No completed-status shortcut: source/input hashes and saved evidence checked every run.
        state('integration_checks'); synthetic_count = selfcheck(mods)
        state('integration_passed', synthetic_scenarios=synthetic_count)
        rec_key = run_id+':recorded'; rec_fp = core.digest(dict(identity=identity, kind='recorded'))
        cur.execute('SELECT kind FROM valor_cash_v8_jobs WHERE job_key=%s', (rec_key,)); old_rec = cur.fetchone()
        rec_blocked = old_rec is not None and old_rec[0] == 'recorded_pair_blocked'
        if not get_saved(rec_key, rec_fp, 0 if rec_blocked else 8, 'recorded'):
            state('recorded_signal_pair')
            try:
                manifest, rows = recorded_pair(conn)
                store(rec_key, 'MES', 2026, 'recorded_pair', manifest, rows, rec_fp, 8)
            except Exception as exc:
                rec_blocked = True
                manifest = dict(blocked_reason=type(exc).__name__+': '+str(exc)[:400], actual_bot_parity=False, live_ready=False)
                store(rec_key, 'MES', 2026, 'recorded_pair_blocked', manifest, [], rec_fp, 0)
        fresh = 0
        for ticker, cfg in PRODUCTS.items():
            for year in YEARS:
                key = f'GLBX.MDP3:ohlcv-1m:{cfg[0]}:{year}'
                fp = core.digest(dict(identity=identity, key=key)); job = run_id+':'+ticker+':'+str(year)
                expected = 162 if ticker == 'MES' else 66
                if get_saved(job, fp, expected, 'historical'): continue
                state('historical_replay', ticker=ticker, year=year, newly_computed_jobs=fresh)
                cur.execute('SELECT parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s', (key,)); body = bytes(cur.fetchone()[0])
                if hashlib.sha256(body).hexdigest() != inventory[key]: raise ValueError('Raw data changed during run')
                frame = pd.read_parquet(io.BytesIO(body)); manifest, rows = evaluate(frame, ticker, year, mods, gex)
                manifest.update(raw_sha256=inventory[key], gex_source_hash=core.digest(gex), gex_source_rows=gex if ticker == 'MES' else None)
                store(job, ticker, year, 'historical', manifest, rows, fp, expected); fresh += 1; del frame, body, rows
        cur.execute('SELECT count(*),sum(jsonb_array_length(summary)) FROM valor_cash_v8_jobs WHERE run_id=%s', (run_id,)); jobs, scenarios = cur.fetchone()
        if jobs != 19 or scenarios != (1476 if rec_blocked else 1484): raise AssertionError('Incomplete coverage')
        state('completed_with_recorded_track_blocked' if rec_blocked else 'completed', jobs=jobs, scenarios=scenarios,
            newly_computed_historical_jobs=fresh, recorded_track_blocked=rec_blocked, live_ready=False,
            production_settings_changed=False, new_vendor_downloads=0, quote_execution_verified=False,
            historical_config_parity_verified=False, incomplete_scenarios_withhold_full_net=True)
    except Exception as exc:
        if run_id: state('failed', error_type=type(exc).__name__, message=str(exc)[:400])
        raise
    finally:
        try: cur.execute('SELECT pg_advisory_unlock(%s)', (LOCK,))
        finally: conn.close()


def launch_if_enabled():
    names = ('VALOR_CASH_V8_AUTORUN', 'VALOR_RESEARCH_REPAIR_V7_AUTORUN', 'VALOR_MES_SESSION_V6_AUTORUN',
             'VALOR_MES_GEX_V5_AUTORUN', 'VALOR_MES_V4_AUTORUN', 'VALOR_EXIT_RESEARCH_AUTORUN', 'VALOR_CONTRACT_RESEARCH_AUTORUN')
    flag = next((os.environ[n] for n in names if n in os.environ), 'false')
    if flag.lower() not in ('true', '1', 'yes', 'on'): return False
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    subprocess.Popen([sys.executable, '-m', 'scripts.valor_cash_research_v8'], env=env, stdin=subprocess.DEVNULL, close_fds=True)
    return True


if __name__ == '__main__': run()
