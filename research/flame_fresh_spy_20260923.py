"""Read-only SPY source audit. No strategy selection, cached inputs, or orders.

Replaces the research-only gateway reader, not any production trading module.
Every acquisition calls a historical endpoint on the private ThetaData bridge.
Provider-internal caching cannot be certified by this client. Raw payloads are
written for reproducibility but are never read as inputs by this audit.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import pathlib
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import requests

BASE = 'http://thetadata-proxy:10000'
OUT = pathlib.Path('/tmp/flame_direct_source_audit')
ET = ZoneInfo('America/New_York')
STATE = {'stage': 'disabled'}
SPEC = {
    'version': 'direct-source-audit-v1', 'symbol': 'SPY',
    'dates': ['2025-01-13', '2026-09-22'],
    'interval': '1m', 'prior_result_inputs': [], 'local_cache_reads': False,
    'max_requests': 12, 'purpose': 'source-repeatability-not-profitability',
    'provider_internal_cache': 'not_observable',
}


class DataError(RuntimeError):
    pass


def emit(event: str, **data):
    print('FLAME_SOURCE_AUDIT ' + json.dumps({
        'event': event, 'utc': datetime.now(timezone.utc).isoformat(), **data
    }, sort_keys=True), flush=True)


def number(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise DataError('invalid_numeric_value') from exc
    if not result.is_finite():
        raise DataError('nonfinite_numeric_value')
    return result


def timestamp(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError as exc:
        raise DataError('invalid_timestamp') from exc
    return dt.replace(tzinfo=ET) if dt.tzinfo is None else dt.astimezone(ET)


def normalize(text: str, kind: str, day: str, strike: int | None = None):
    """Strictly validate contract identity, clocks, values, and unique timestamps."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise DataError('empty_response')
    out = []
    seen = set()
    for row in rows:
        ts = timestamp(row.get('timestamp', ''))
        if ts.date().isoformat() != day:
            raise DataError('wrong_requested_date')
        if ts in seen:
            raise DataError('duplicate_timestamp')
        seen.add(ts)
        if row.get('symbol', 'SPY') != 'SPY':
            raise DataError('wrong_symbol')
        if kind == 'stock':
            ns = {k: number(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')}
            if min(ns[k] for k in ('open', 'high', 'low', 'close')) <= 0:
                raise DataError('nonpositive_stock_price')
            if ns['volume'] < 0 or ns['low'] > min(ns['open'], ns['close']) or ns['high'] < max(ns['open'], ns['close']):
                raise DataError('invalid_stock_bar')
        else:
            required = ('symbol', 'expiration', 'strike', 'right', 'bid', 'ask', 'bid_size', 'ask_size')
            if any(k not in row for k in required):
                raise DataError('missing_option_identity_or_size')
            if str(row['expiration'])[:10].replace('-', '') != day.replace('-', ''):
                raise DataError('wrong_expiration')
            if number(row['strike']) != strike or row['right'].lower() not in ('put', 'p'):
                raise DataError('wrong_option_contract')
            ns = {k: number(row[k]) for k in ('bid', 'ask', 'bid_size', 'ask_size')}
            if ns['bid'] < 0 or ns['ask'] <= 0 or ns['bid'] > ns['ask']:
                raise DataError('invalid_or_crossed_quote')
            if ns['bid_size'] < 0 or ns['ask_size'] < 0:
                raise DataError('negative_quote_size')
        out.append({'timestamp': ts.isoformat(), **{k: format(v.normalize(), 'f') for k, v in ns.items()}})
    return sorted(out, key=lambda row: row['timestamp'])


def require_minutes(rows, day: str, start: str, count: int):
    wanted = [timestamp(day + 'T' + start) + timedelta(minutes=i) for i in range(count)]
    actual = [timestamp(r['timestamp']) for r in rows]
    if actual != wanted:
        raise DataError('minute_coverage_mismatch')


class DirectFeed:
    def __init__(self):
        self.calls = 0
        self.deadline = time.monotonic() + 240
        self.manifest = []

    def fetch(self, path: str, params: dict, kind: str, strike: int | None = None):
        if path not in ('/v3/stock/history/ohlc', '/v3/option/history/quote'):
            raise DataError('nonhistorical_endpoint_rejected')
        if self.calls >= SPEC['max_requests'] or time.monotonic() > self.deadline:
            raise DataError('request_budget_exhausted')
        self.calls += 1
        # New request, no requests-cache, no saved-file reader, no app-cache fallback.
        response = requests.get(BASE + path, params=params, timeout=(8, 50), allow_redirects=False,
                                headers={'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache',
                                         'User-Agent': 'FlameSourceAudit/1.0'})
        rec = {'request': self.calls, 'path': path, 'params': params,
               'status': response.status_code, 'bytes': len(response.content),
               'raw_sha256': hashlib.sha256(response.content).hexdigest(),
               'response_cache_control': response.headers.get('Cache-Control'),
               'provider': response.headers.get('X-Market-Data-Provider'),
               'retrieved_utc': datetime.now(timezone.utc).isoformat()}
        self.manifest.append(rec)
        OUT.mkdir(exist_ok=True)
        (OUT / f'{self.calls:02d}.raw').write_bytes(response.content)
        emit('request', **rec)
        response.raise_for_status()
        if response.status_code != 200 or rec['provider'] != 'thetadata':
            raise DataError('unexpected_source_response')
        if kind == 'stock' and response.headers.get('X-Bar-Timestamp') != 'interval-start':
            raise DataError('unverified_bar_timestamp_semantics')
        rows = normalize(response.text, kind, params['date'], strike)
        canonical = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
        rec.update({'rows': len(rows), 'canonical_sha256': hashlib.sha256(canonical).hexdigest()})
        return rows, rec


def audit():
    """Repeat identical reads and an intervening different date; do not fit a rule."""
    feed = DirectFeed()
    baselines = {}
    agreements = []
    emit('specification', spec=SPEC)
    STATE['stage'] = 'running'
    try:
        for pass_number in (1, 2):
            for day in SPEC['dates']:
                p = {'symbol': 'SPY', 'date': day, 'interval': '1m',
                     'start_time': '09:30:00', 'end_time': '10:04:00', 'venue': 'utp_cta'}
                stock, record = feed.fetch('/v3/stock/history/ohlc', p, 'stock')
                require_minutes(stock, day, '09:30:00', 35)
                key = (day, 'stock')
                if pass_number == 1:
                    baselines[key] = record['canonical_sha256']
                else:
                    agreements.append({'day': day, 'kind': 'stock', 'rows': len(stock),
                                       'identical': baselines[key] == record['canonical_sha256']})
                # 10:00 minute bar completes at 10:01. Use only that close for contract identity.
                close = number(next(r['close'] for r in stock if timestamp(r['timestamp']).strftime('%H:%M') == '10:00'))
                short = int(close) - 1
                quotes = {}
                for strike in (short, short - 2):
                    p = {'symbol': 'SPY', 'date': day, 'expiration': day, 'strike': str(strike),
                         'right': 'put', 'interval': '1m', 'start_time': '10:01:00', 'end_time': '10:05:00'}
                    quotes[strike], record = feed.fetch('/v3/option/history/quote', p, 'quote', strike)
                    require_minutes(quotes[strike], day, '10:01:00', 5)
                    key = (day, str(strike))
                    if pass_number == 1:
                        baselines[key] = record['canonical_sha256']
                    else:
                        agreements.append({'day': day, 'kind': 'quote', 'strike': strike,
                                           'rows': len(quotes[strike]),
                                           'identical': baselines.get(key) == record['canonical_sha256']})
                # Fixed quote arithmetic is a reproducibility check, NOT an entry/exit strategy.
                entry = number(quotes[short][0]['bid']) - number(quotes[short-2][0]['ask'])
                exit_debit = number(quotes[short][-1]['ask']) - number(quotes[short-2][-1]['bid'])
                arithmetic = str((entry - exit_debit) * 100)
                key = (day, 'arithmetic')
                if pass_number == 1:
                    baselines[key] = arithmetic
                else:
                    agreements.append({'day': day, 'kind': 'quote_arithmetic', 'identical': baselines[key] == arithmetic})
        STATE['stage'] = 'complete'
        outcome = {'requests': feed.calls, 'comparisons': agreements,
                   'all_identical': all(x['identical'] for x in agreements),
                   'prior_saved_inputs': 0, 'stock_bars_per_read': 35,
                   'local_cache_reads': 0, 'backtest_results_reused': 0,
                   'claim': 'repeatability_check_only_not_validation_of_profitability',
                   'provider_internal_caching': 'not_observable',
                   'option_source_update_age': 'not_established_by_interval_timestamp'}
        (OUT / 'result.json').write_text(json.dumps(outcome, indent=2))
        emit('complete', **outcome)
    except Exception as exc:
        STATE['stage'] = 'failed'
        emit('failed', kind=type(exc).__name__, message=str(exc)[:180], requests=feed.calls)
    finally:
        OUT.mkdir(exist_ok=True)
        (OUT / 'manifest.json').write_text(json.dumps(feed.manifest, indent=2))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Do not expose licensed raw observations on a public endpoint.
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(json.dumps({'research_only': True, **STATE}).encode())

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'direct-audit':
        threading.Thread(target=audit, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT', '10000'))), Handler).serve_forever()
