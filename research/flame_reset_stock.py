"""Accept original stock precision without changing option ticks or strategy rules.

Underlying stock prices are Decimal values at full supplied precision; only
option quotes and money require the four-decimal option grid. No imputation.
"""
import csv
import hashlib
import io
import json
import os
import threading
from types import SimpleNamespace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import HTTPServer
import flame_reset_baseline as core

def stock_rows(rows, day):
    out={}; end=core.SPEC['decision_et_minute']; precision_examples=[]
    for r in rows:
        m=core.minute(r['timestamp'],day)
        if m==end: continue
        if not 570<=m<end: raise core.DataError('stock_outside_prefix')
        if r.get('symbol','SPY')!='SPY' or m in out: raise core.DataError('stock_identity_or_duplicate')
        try:
            v={k:Decimal(str(r[k]))*core.U for k in ('open','high','low','close')}
            vol=Decimal(str(r['volume']))
        except (InvalidOperation,KeyError) as e:
            raise core.DataError('stock_numeric:'+day+':'+str(m)+':'+repr({k:r.get(k) for k in ('open','high','low','close','volume','count')})) from e
        if not all(x.is_finite() and x>0 for x in v.values()) or not vol.is_finite() or vol<0:
            raise core.DataError('stock_invalid_value:'+day+':'+str(m))
        # A provider float tail must not make high < open by 1e-13 dollars.
        epsilon=Decimal('0.000001')  # scaled units = 1e-10 dollars
        top=max(v['open'],v['close']);bottom=min(v['open'],v['close'])
        if v['low']-bottom>epsilon or top-v['high']>epsilon:
            raise core.DataError('stock_invalid_ohlc:'+day+':'+str(m)+':'+repr({k:r[k] for k in v}))
        if v['low']>bottom or v['high']<top:
            core.emit('ohlc_tail_reconciled',day=day,minute=m,original_prices={k:r[k] for k in v},max_tolerance_dollars='0.0000000001')
            v['low']=min(v['low'],bottom);v['high']=max(v['high'],top)
        if any(x!=x.to_integral_value() for x in v.values()) and len(precision_examples)<2:
            precision_examples.append({'minute':m,'original_prices':{k:r[k] for k in v}})
        out[m]=v
    if sorted(out)!=list(range(570,end)):raise core.DataError('missing_stock_prefix:'+day)
    if precision_examples:core.emit('stock_precision_preserved',day=day,examples=precision_examples)
    return out

core.stock_rows=stock_rows
# Provider floats can arrive as 0.6900000000000001. Only normalize a tail
# within 1e-10 dollars of the exact four-decimal grid; never round a real tick.
_precision_repairs = 0
_original_units = core.units

def wire_units(value):
    global _precision_repairs
    try:
        return _original_units(value)
    except core.DataError:
        try: raw = Decimal(str(value)) * core.U
        except InvalidOperation as exc: raise core.DataError('invalid_source_price') from exc
        nearest = raw.to_integral_value()
        if not raw.is_finite() or abs(raw-nearest) > Decimal('0.000001'):
            raise core.DataError('unsupported_source_precision')
        _precision_repairs += 1
        if _precision_repairs <= 8:
            core.emit('wire_tail_normalized', original=str(value), exact_units=int(nearest),
                      max_tolerance_dollars='0.0000000001')
        return int(nearest)

core.units = wire_units
_original_replay = core.replay

def identified_replay(data, strike, width, slippage):
    result = _original_replay(data, strike, width, slippage)
    result.setdefault('width', width)
    result.setdefault('short_units', strike)
    return result

core.replay = identified_replay
# Exact source decimals are serialized as strings, never rounded to floats.
_original_dumps = json.dumps

def exact_json(value, **kwargs):
    kwargs.setdefault('default', str)
    return _original_dumps(value, **kwargs)

core.json = SimpleNamespace(dumps=exact_json)

_original_feed = core.Feed

class PreflightFeed(_original_feed):
    def __init__(self):
        super().__init__()
        self.current_run_regimes = None

    def day(self, day):
        # Validate the whole underlying prefix dataset before any option replay.
        # These observations were retrieved in THIS run, not from a prior cache.
        if self.current_run_regimes is None:
            self.current_run_regimes = {}
            for session in core.session_days():
                p={'symbol':'SPY','date':session,'interval':'1m','start_time':'09:30:00','end_time':'12:00:00','venue':'utp_cta'}
                fp=self.get('/v3/stock/history/ohlc',p)
                with fp.open() as f:
                    stock=stock_rows(csv.DictReader(f),session)
                self.current_run_regimes[session]=core.regime(stock)
            core.emit('underlying_preflight_complete',sessions=len(self.current_run_regimes),bars=150*len(self.current_run_regimes))
        reg=self.current_run_regimes[day]
        p={'symbol':'SPY','date':day,'expiration':day,'right':'put','strike':'*','interval':'1m','start_time':'12:00:00','end_time':'15:45:00'}
        fp=self.get('/v3/option/history/quote',p)
        with fp.open() as f:
            data,coverage=core.parse_options(csv.DictReader(f),day,reg['spot_units'])
        return reg,data,coverage

core.Feed=PreflightFeed

if __name__=='__main__':
    if os.getenv('FLAME_FRESH_MODE')=='reset-regime-v1' and datetime.now(timezone.utc)<datetime.fromisoformat('2026-09-23T23:30:00+00:00'):
        core.emit('data_parser',stock_precision='original_decimal',option_precision='integer_0.0001',rounding=False)
        threading.Thread(target=core.execute,daemon=True).start()
    HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),core.Handler).serve_forever()
