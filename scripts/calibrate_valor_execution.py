#!/usr/bin/env python3
"""Read-only broker calibration probe; never places orders or changes trading config.

Run inside Render where OAuth credentials exist. Stores one bounded evidence
bundle in Postgres so a deploy cannot destroy it. No account numbers are saved.
"""
import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

UTC = timezone.utc
PRODUCT = re.compile(r'^/(MES|MNQ|M2K|MCL|MNG|MGC)[FGHJKMNQUVXZ]\d{1,2}$')
FEES = ('commission', 'clearing_fees', 'regulatory_fees',
        'proprietary_index_option_fees', 'other_charge')
FIELDS = ('id', 'symbol', 'transaction_type', 'action', 'quantity', 'price',
          'executed_at', 'value', 'net_value', 'is_estimated_fee', 'reverses_id') + FEES


def fee_report(rows):
    """SDK signs debits negative. Reconcile components to gross-minus-net.

    Exclude estimated, reversed, incomplete and nontrade rows; do not turn
    missing history into a zero-cost assumption. Opening/closing rates separate.
    """
    groups = defaultdict(lambda: {'rows': 0, 'quantity': Decimal(0), 'cost': Decimal(0)})
    rejected = Counter()
    reversed_ids = {str(r['reverses_id']) for r in rows if r.get('reverses_id') is not None}
    seen = set()
    for r in rows:
        if str(r.get('id')) in seen:
            rejected['duplicate'] += 1
            continue
        seen.add(str(r.get('id')))
        match = PRODUCT.fullmatch(r.get('symbol') or '')
        if not match or r.get('transaction_type') != 'Trade':
            rejected['outside_supported_futures_trades'] += 1
            continue
        if r.get('reverses_id') is not None or str(r['id']) in reversed_ids:
            rejected['reversal_requires_review'] += 1
            continue
        if r.get('is_estimated_fee') is not False:
            rejected['estimated_or_unknown_fee_status'] += 1
            continue
        try:
            qty = Decimal(str(r['quantity']))
            values = [Decimal(str(r[k])) for k in FEES if r.get(k) is not None]
            if not values or not qty.is_finite() or qty <= 0 or qty != qty.to_integral_value():
                raise ValueError()
            cost = -sum(values, Decimal(0))
            net_cost = Decimal(str(r['value'])) - Decimal(str(r['net_value']))
            if not cost.is_finite() or not net_cost.is_finite() or abs(cost-net_cost) > Decimal('0.000001'):
                rejected['fees_do_not_reconcile'] += 1
                continue
            action = r.get('action') or ''
            phase = 'open' if action.endswith(' to Open') else 'close' if action.endswith(' to Close') else 'unspecified'
            g = groups[(match[1], phase)]
            g['rows'] += 1
            g['quantity'] += qty
            g['cost'] += cost
        except (KeyError, TypeError, ValueError, ArithmeticError):
            rejected['incomplete_fee_record'] += 1
    rates = []
    for (product, phase), g in sorted(groups.items()):
        rates.append(dict(product=product, phase=phase, rows=g['rows'], contracts=float(g['quantity']),
                          net_fee_cost=float(g['cost']), fee_per_contract=float(g['cost']/g['quantity'])))
    return {'observed_fee_rates': rates, 'excluded': dict(rejected),
            'automatically_applied': False,
            'note': 'Observed historical rates only; later adjustments and current fee schedules need review.'}


def percentile(values, fraction):
    return sorted(values)[min(len(values)-1, math.ceil(len(values)*fraction)-1)] if values else None


def shadow_report(events, tick=0.25):
    """Independent top-of-book sensitivity trials; no queue/depth prediction.

    Use only the first changed quote AT OR AFTER assumed arrival. Consume that
    displayed size once per hypothetical order; unfilled remainder stays unfilled.
    Future quote movement is an outcome, never an input to order selection.
    """
    times = [e['elapsed_ms'] for e in events]
    anchors = []
    next_ms = 2000
    for i, event in enumerate(events):
        if event['elapsed_ms'] >= next_ms:
            anchors.append(i)
            next_ms = event['elapsed_ms'] + 2000
    results = []
    for latency in (100, 250, 500, 1000):
        for quantity in (1, 5):
            for fraction in (1.0, 0.5):
                for side in ('bid', 'ask'):
                    counts = Counter()
                    moves, delays = [], []
                    for i in anchors:
                        j = bisect_left(times, times[i]+latency, lo=i+1)
                        if j == len(events) or times[j]-(times[i]+latency) > 2000:
                            counts['missing_arrival_observation'] += 1
                            continue
                        event = events[j]
                        filled = min(quantity, math.floor(event[side+'_size']*fraction))
                        counts['trials'] += 1
                        counts['modeled_filled_contracts'] += filled
                        counts['modeled_unfilled_contracts'] += quantity-filled
                        counts['full' if filled == quantity else 'partial' if filled else 'unfilled'] += 1
                        if filled:
                            moves.append(round((event[side]-events[i][side])*(1 if side=='ask' else -1)/tick,6))
                        delays.append(times[j]-times[i])
                    results.append(dict(assumed_latency_ms=latency,requested_quantity=quantity,
                        displayed_liquidity_fraction=fraction,side='buy' if side=='ask' else 'sell',
                        counts=dict(counts),median_adverse_move_ticks=percentile(moves,0.5),
                        p95_adverse_move_ticks=percentile(moves,0.95),
                        median_observation_delay_ms=percentile(delays,0.5)))
    return results


async def collect_history(session, days):
    from tastytrade import Account
    from tastytrade.order import InstrumentType
    configured = os.getenv('TASTYTRADE_ACCOUNT_ID')
    if configured:
        account = await asyncio.wait_for(Account.get(session, configured), 20)
    else:
        accounts = await asyncio.wait_for(Account.get(session), 20)
        eligible = [a for a in accounts if a.is_futures_approved and not a.is_closed and not a.is_test_drive]
        if len(eligible) != 1:
            return [], 'Set TASTYTRADE_ACCOUNT_ID: no unique eligible futures account.'
        account = eligible[0]
    if account.is_test_drive:
        return [], 'Test-drive history is not real broker execution evidence.'
    rows = []
    for page in range(100):
        batch = await asyncio.wait_for(account.get_history(session,
            start_date=(datetime.now(UTC)-timedelta(days=days)).date(),
            instrument_type=InstrumentType.FUTURE, per_page=250,page_offset=page), 30)
        for tx in batch:
            raw = tx.model_dump(mode='json')
            rows.append({k:raw.get(k) for k in FIELDS})
        if len(batch) < 250:
            return rows, 'complete_requested_window'
    return rows, 'truncated_at_25000_rows; do not treat as complete'


async def collect_quotes(session, seconds):
    from tastytrade import DXLinkStreamer
    from tastytrade.dxfeed import Quote
    from tastytrade.instruments import Future
    now = datetime.now(UTC)
    futures = await asyncio.wait_for(Future.get(session, product_codes=['MES']), 20)
    eligible = [f for f in futures if f.product_code=='MES' and f.active_month and
                f.is_tradeable and not f.is_closing_only and f.stops_trading_at>now and f.streamer_symbol]
    if len(eligible)!=1:
        raise ValueError('No unique broker active MES contract')
    future=eligible[0]
    events=[]
    rejected=Counter()
    previous=None
    async with DXLinkStreamer(session) as stream:
        await stream.subscribe(Quote,[future.streamer_symbol])
        start=time.monotonic()
        while time.monotonic()-start < seconds:
            try:
                q=await asyncio.wait_for(stream.get_event(Quote),min(5,seconds-(time.monotonic()-start)))
            except asyncio.TimeoutError:
                continue
            if q.event_symbol!=future.streamer_symbol:
                rejected['wrong_symbol']+=1
                continue
            values=tuple(float(v) for v in (q.bid_price,q.ask_price,q.bid_size,q.ask_size))
            if not all(math.isfinite(v) for v in values) or min(values[:2])<=0 or min(values[2:])<0 or values[0]>values[1]:
                rejected['invalid_book']+=1
                continue
            if previous is None or previous==values:
                previous=values
                rejected['snapshot_or_unchanged']+=1
                continue
            previous=values
            events.append(dict(elapsed_ms=round((time.monotonic()-start)*1000,3),
                observed_at=datetime.now(UTC).isoformat(),bid=values[0],ask=values[1],
                bid_size=values[2],ask_size=values[3],broker_bid_time=q.bid_time,broker_ask_time=q.ask_time))
            if len(events)>=50000:
                rejected['event_limit_reached']+=1
                break
    return future.symbol,events,dict(rejected)


def persist(bundle):
    import psycopg2
    encoded=json.dumps(bundle,sort_keys=True,allow_nan=False).encode()
    compressed=gzip.compress(encoded)
    digest=hashlib.sha256(compressed).hexdigest()
    if len(compressed)>10_000_000:
        raise ValueError('Evidence bundle exceeds 10MB')
    with psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=15) as conn:
        with conn.cursor() as c:
            c.execute("SET LOCAL statement_timeout='30s'")
            c.execute('''CREATE TABLE IF NOT EXISTS valor_execution_calibration (
                run_id TEXT PRIMARY KEY,created_at TIMESTAMPTZ DEFAULT NOW(),
                summary JSONB NOT NULL,evidence_gzip BYTEA NOT NULL,sha256 TEXT NOT NULL)''')
            c.execute('INSERT INTO valor_execution_calibration(run_id,summary,evidence_gzip,sha256) VALUES (%s,%s::jsonb,%s,%s)',
                (bundle['run_id'],json.dumps(bundle['summary']),psycopg2.Binary(compressed),digest))
            c.execute('SELECT evidence_gzip FROM valor_execution_calibration WHERE run_id=%s',(bundle['run_id'],))
            if hashlib.sha256(bytes(c.fetchone()[0])).hexdigest()!=digest:
                raise ValueError('Archive verification failed')
    return digest


async def main(args):
    from tastytrade import Session
    logging.disable(logging.CRITICAL)
    session=Session(os.environ['TASTYTRADE_CLIENT_SECRET'],os.environ['TASTYTRADE_REFRESH_TOKEN'])
    print('Reading existing futures transactions; no orders will be submitted.',flush=True)
    try:
        history,history_status=await asyncio.wait_for(collect_history(session,args.days),120)
    except Exception as exc:
        history,history_status=[], 'history_unavailable:'+type(exc).__name__
    print('History:',history_status,'| rows:',len(history),flush=True)
    print('Observing MES quote changes for',args.seconds,'seconds...',flush=True)
    symbol,events,rejected=await collect_quotes(session,args.seconds)
    summary={'contract':symbol,'history_status':history_status,'history_rows':len(history),
             'fee_analysis':fee_report(history),'quote_events':len(events),'rejected':rejected,
             'latency_liquidity_scenarios':shadow_report(events),
             'broker_slippage_calibrated':False,'trading_settings_changed':False,
             'limitations':['Shadow scenarios are hypothetical, not broker fills.',
                 'No historical arrival quotes: broker slippage/latency cannot yet be measured.',
                 'Reception times do not prove exchange freshness or absence of vendor delay.',
                 'One short sample is exploratory; repeat across sessions before choosing assumptions.',
                 'Only top-of-book size; no queue priority, replenishment or deeper book modeled.',
                 'Unfilled remainder is never booked as a completed trade.']}
    bundle={'run_id':str(uuid.uuid4()),'summary':summary,'transactions':history,'quote_events':events}
    digest=persist(bundle)
    print('FEES:',json.dumps(summary['fee_analysis'],sort_keys=True),flush=True)
    print('QUOTE EVENTS:',len(events),'| SCENARIOS:',len(summary['latency_liquidity_scenarios']))
    print('CALIBRATION SAVED:',bundle['run_id'],'SHA256:',digest)
    print('No orders submitted. Paper balances and settings unchanged.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=60,choices=range(15,301))
    parser.add_argument('--days',type=int,default=30,choices=range(1,91))
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception as exc:
        print('CALIBRATION STOPPED:',type(exc).__name__,'Details suppressed to protect credentials.')
        raise SystemExit(1)
