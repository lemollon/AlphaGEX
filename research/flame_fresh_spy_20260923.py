"""Isolated research launcher. No production imports or orders."""
import os
import threading
from collections import Counter
from decimal import Decimal as D
from http.server import HTTPServer
import flame_dual_extension_v1 as core

_original_get = core.Feed.get
_schema_logged = False
_quote_logged = set()

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
    if path == '/v3/option/history/quote' and len(_quote_logged) < 5:
        counts = Counter()
        samples = []
        for row in rows:
            reason = None
            try:
                bid, ask = core.units(row['bid']), core.units(row['ask'])
                bs, az = D(row['bid_size']), D(row['ask_size'])
                if bid < 0 or ask <= 0 or ask < bid:
                    reason = 'bad_price_or_crossed'
                elif not bs.is_finite() or not az.is_finite() or bs < 1 or az < 1:
                    reason = 'quote_size'
            except Exception as exc:
                reason = type(exc).__name__ + ':' + str(exc)
            if reason:
                counts[reason] += 1
                if len(samples) < 2:
                    samples.append({k:row.get(k) for k in ('timestamp','strike','bid','ask','bid_size','ask_size')})
        key = (params['date'], params.get('strike'))
        if counts and key not in _quote_logged:
            _quote_logged.add(key)
            core.emit('quote_audit', date=params['date'], strike=params.get('strike'),
                      rejected_reasons=dict(counts), examples=samples)
    return rows

core.Feed.get = verified_rows

if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'dual-extension-v1':
        core.emit('reader_adapter', version='stock-identity-v1-quote-audit', price_values_modified=False)
        threading.Thread(target=core.execute, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT', '10000'))), core.Handler).serve_forever()
