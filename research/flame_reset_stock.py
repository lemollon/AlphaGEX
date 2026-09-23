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
        if v['low']>min(v['open'],v['close']) or v['high']<max(v['open'],v['close']):
            raise core.DataError('stock_invalid_ohlc:'+day+':'+str(m))
        if any(x!=x.to_integral_value() for x in v.values()) and len(precision_examples)<2:
            precision_examples.append({'minute':m,'original_prices':{k:r[k] for k in v}})
        out[m]=v
    if sorted(out)!=list(range(570,end)):raise core.DataError('missing_stock_prefix:'+day)
    if precision_examples:core.emit('stock_precision_preserved',day=day,examples=precision_examples)
    return out

core.stock_rows=stock_rows
# Exact source decimals are serialized as strings, never rounded to floats.
_original_dumps = json.dumps

def exact_json(value, **kwargs):
    kwargs.setdefault('default', str)
    return _original_dumps(value, **kwargs)

core.json = SimpleNamespace(dumps=exact_json)

if __name__=='__main__':
    if os.getenv('FLAME_FRESH_MODE')=='reset-regime-v1' and datetime.now(timezone.utc)<datetime.fromisoformat('2026-09-23T23:30:00+00:00'):
        core.emit('data_parser',stock_precision='original_decimal',option_precision='integer_0.0001',rounding=False)
        threading.Thread(target=core.execute,daemon=True).start()
    HTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),core.Handler).serve_forever()
