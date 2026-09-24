"""Isolated research launcher. No production imports or orders.

The history bridge serializes binary floats (for example 0.35000000000000003).
Normalize only deviations <= 1e-10 dollar to the 0.0001-dollar price grid.
Genuine off-grid prices, nonfinite numbers and absent prices still fail.
"""
import os
import threading
from collections import Counter
from decimal import Decimal as D, ROUND_HALF_UP
from http.server import HTTPServer
import flame_dual_extension_v1 as core

_original_get = core.Feed.get
_schema_logged = False
_normalized = Counter()


def grid_units(raw):
    x = D(str(raw)) * core.U
    if not x.is_finite():
        raise ValueError('nonfinite_option_price')
    nearest = x.to_integral_value(rounding=ROUND_HALF_UP)
    residual = abs(x - nearest)
    if residual > D('0.000001'):
        raise ValueError('genuine_off_grid_option_price')
    if residual:
        _normalized['values'] += 1
        if _normalized['values'] <= 3:
            core.emit('serialization_normalization', original=str(raw),
                      normalized=str(nearest / core.U), absolute_change_dollars=str(residual/core.U),
                      tolerance_dollars='1e-10')
    return int(nearest)


def verified_rows(self, path, params):
    global _schema_logged
    rows = _original_get(self, path, params)
    if path == '/v3/stock/history/ohlc':
        if not _schema_logged:
            core.emit('stock_schema', columns=sorted(rows[0]),
                      symbol_identity='verified single-symbol request when column omitted')
            _schema_logged = True
        for row in rows:
            if 'symbol' not in row:
                row['symbol'] = params['symbol']
    return rows

core.units = grid_units
core.Feed.get = verified_rows


def audited_execute():
    assert grid_units('0.35000000000000003') == 3500
    assert grid_units('0.7000000000000001') == 7000
    try:
        grid_units('0.35005')
    except ValueError:
        pass
    else:
        raise AssertionError('off-grid value accepted')
    core.execute()
    core.emit('reader_audit_complete', normalized_values=_normalized['values'],
              missing_prices_filled=0, genuine_off_grid_tolerance_dollars='1e-10')

if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'dual-extension-v1':
        core.emit('reader_adapter', version='stock-identity-and-grid-v2',
                  normalization_max_dollars='1e-10', missing_prices_filled=False)
        threading.Thread(target=audited_execute, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT', '10000'))), core.Handler).serve_forever()
