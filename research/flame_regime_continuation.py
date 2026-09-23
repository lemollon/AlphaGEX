"""Isolated continuation of the fixed-rule SPY reset. No trading API imports.

Only serialization noise within 1e-10 dollars of an option-price grid is
canonicalized. Genuine fifth-decimal stock observations remain unchanged.
All provider requests are new for this run. Old prices/results are never read.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
import pathlib
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import HTTPServer
import flame_reset_baseline as core

EXPECTED_BLOB = '3f677e307d81e5d9b70b51993a8bd4503a0d8f42'
TOLERANCE_DOLLARS = Decimal('0.0000000001')
FIX_COUNTS = {'stock_fields': 0, 'option_fields': 0}
SCORES = []
ORIGINAL_EMIT = core.emit
SOURCE_TOTAL = {'responses': 0, 'bytes': 0}
STOCK_DIAGNOSTICS = []


def checked_decimal(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise core.DataError('invalid_decimal') from exc
    if not value.is_finite():
        raise core.DataError('nonfinite_decimal')
    return value


def canonical_price(value, category):
    raw = checked_decimal(value)
    nearest = (raw * core.U).to_integral_value() / core.U
    if raw != nearest and abs(raw-nearest) <= TOLERANCE_DOLLARS:
        FIX_COUNTS[category] += 1
        if FIX_COUNTS[category] <= 2:
            ORIGINAL_EMIT('serialization_tail', category=category,
                          original=str(value), normalized=str(nearest),
                          maximum_tolerance_dollars=str(TOLERANCE_DOLLARS))
        return nearest
    return raw


def option_units(value):
    raw = canonical_price(value, 'option_fields') * core.U
    if raw != raw.to_integral_value():
        raise core.DataError('genuine_option_precision_exceeds_grid')
    return int(raw)


def stock_rows(rows, day):
    out = {}
    end = core.SPEC['decision_et_minute']
    for row in rows:
        minute = core.minute(row['timestamp'], day)
        if minute == end:
            continue
        if not 570 <= minute < end:
            raise core.DataError('stock_outside_prefix')
        if row.get('symbol', 'SPY') != 'SPY' or minute in out:
            raise core.DataError('stock_identity_or_duplicate')
        vals = {k: canonical_price(row[k], 'stock_fields') * core.U
                for k in ('open', 'high', 'low', 'close')}
        volume = checked_decimal(row['volume'])
        if min(vals.values()) <= 0 or volume < 0:
            raise core.DataError('invalid_stock_value')
        if vals['low'] > min(vals['open'], vals['close']) or vals['high'] < max(vals['open'], vals['close']):
            diagnostic = {'day': day, 'minute_et': minute,
                          'raw': {k: row[k] for k in vals},
                          'low_violation_dollars': str((vals['low']-min(vals['open'], vals['close']))/core.U),
                          'high_violation_dollars': str((max(vals['open'], vals['close'])-vals['high'])/core.U)}
            STOCK_DIAGNOSTICS.append(diagnostic)
            ORIGINAL_EMIT('stock_consistency_failure', **diagnostic)
            raise core.DataError('material_stock_ohlc_mismatch:'+day+':'+str(minute))
        out[minute] = vals
    if sorted(out) != list(range(570, end)):
        raise core.DataError('missing_stock_prefix:'+day)
    return out


def verify_source():
    raw = pathlib.Path(core.__file__).read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob != EXPECTED_BLOB:
        raise core.DataError('frozen_core_changed')
    if core.SPEC['symbol'] != 'SPY' or core.SPEC['right'] != 'put':
        raise core.DataError('wrong_product')
    ORIGINAL_EMIT('frozen_source', git_blob=blob,
                  config_sha256=hashlib.sha256(json.dumps(core.SPEC, sort_keys=True, separators=(',',':')).encode()).hexdigest(),
                  stock_timestamp='interval_start; use completed prefix only',
                  prior_market_data_inputs=0, prior_result_inputs=0)


def selftests():
    checks = 0
    def require(ok):
        nonlocal checks
        if not ok:
            raise AssertionError('continuation_selftest_failed_'+str(checks+1))
        checks += 1
    require(option_units('0.6900000000000001') == 6900)
    require(canonical_price('600.12345', 'stock_fields') == Decimal('600.12345'))
    require(option_units('0.60')-option_units('0.40') == 2000)
    require(option_units('0.70')-option_units('0.30') == 4000)
    require(2*(option_units('0.79')-option_units('0.60')+option_units('0.01')) == option_units('0.80')-option_units('0.39')-option_units('0.01'))
    try:
        option_units('0.69001')
        raise AssertionError('real_precision_was_rounded')
    except core.DataError:
        checks += 1
    k = 600*core.U
    data = {k: {}, k-core.U: {}}
    for m in range(720, 946):
        data[k][m] = (10000, 10100, 10, 10)
        data[k-core.U][m] = (6900, 7000, 10, 10)
    for m in (722, 723):
        data[k][m] = (8400, 8500, 10, 10)
        data[k-core.U][m] = (7000, 7100, 10, 10)
    trade = core.replay(data, k, 1, 0)
    core.agrees(trade, core.reference(data, k, 1, 0))
    require(trade['entry_minute_et'] == 721)
    require(trade['exit_minute_et'] == 723)
    require(trade['net_cents'] == 1240 and trade['reason'] == 'target')
    require(trade['risk_cents'] == 7260)
    del data[k][722]
    missing = core.replay(data, k, 1, 0)
    require(missing['status'] == 'unresolved')
    core.agrees(missing, core.reference(data, k, 1, 0))
    require(core.accepted('uptrend', 'uptrend') and not core.accepted('uptrend', 'downtrend'))
    require(core.accepted('uptrend_or_calm_range', 'calm_range') and not core.accepted('uptrend_or_calm_range', 'transition'))
    require(len(core.session_days()) == 39)
    day = '2025-01-02'
    empty = {day: {'regime': {'label': 'uptrend'}, 'trades': {}}}
    acc = core.account([day], empty, 1, 'natural', 'all', 'external', 0)
    require(acc['subscription'] == 50 and acc['customer_net'] == -50 and acc['ending_broker_equity'] == 2000)
    acc = core.account([day], empty, 1, 'natural', 'all', 'account', 200000)
    require(acc['ending_broker_equity'] == 1950 and acc['customer_net'] == -50 and acc['rejections']['account_floor'] == 1)
    FIX_COUNTS.update(stock_fields=0, option_fields=0)
    ORIGINAL_EMIT('selftests_passed', checks=checks,
                  meaning='mechanics checks, not a profitability claim')


def capture(event, **fields):
    if event == 'source':
        SOURCE_TOTAL['responses'] += 1
        SOURCE_TOTAL['bytes'] += fields['bytes']
    if event == 'summary':
        SCORES.append(fields)
        if fields['fee_location'] == 'external' and fields['floor'] == 0:
            ORIGINAL_EMIT('review_scorecard', **fields)
        elif fields['fee_location'] == 'external' and fields['profile'] == 'adverse3c':
            ORIGINAL_EMIT('floor_sensitivity', **fields)
        return
    if event == 'complete':
        ORIGINAL_EMIT('continuation_complete', **fields,
                      observed_responses=SOURCE_TOTAL['responses'],
                      observed_bytes=SOURCE_TOTAL['bytes'],
                      serialization_normalizations=FIX_COUNTS,
                      live_trading_changed=False)
        return
    ORIGINAL_EMIT(event, **fields)


def run():
    try:
        verify_source()
        core.units = option_units
        core.stock_rows = stock_rows
        selftests()
        core.emit = capture
        feed = core.Feed()
        params = {'symbol':'SPY','date':'2025-01-17','interval':'1m',
                  'start_time':'09:30:00','end_time':'12:00:00','venue':'utp_cta'}
        fp = feed.get('/v3/stock/history/ohlc', params)
        with fp.open() as f:
            rows = list(csv.DictReader(f))
        original = next(r for r in rows if core.minute(r['timestamp'], '2025-01-17') == 583)
        cleaned = stock_rows(rows, '2025-01-17')
        ORIGINAL_EMIT('preflight_row_verified', day='2025-01-17', minute_et=583,
                      original={k:original[k] for k in ('open','high','low','close')},
                      normalized={k:str(v/core.U) for k,v in cleaned[583].items()},
                      note='fresh diagnostic request; full study reacquires all dates')
        core.execute()
    except Exception as exc:
        core.STATE['stage'] = 'failed'
        ORIGINAL_EMIT('continuation_failed', kind=type(exc).__name__, reason=str(exc)[:250])


if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'reset-regime-v2':
        threading.Thread(target=run, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT','10000'))), core.Handler).serve_forever()
