"""Isolated research launcher. No production imports or orders."""
import os
import threading
from http.server import HTTPServer
import flame_dual_extension_v1 as core

_original_get = core.Feed.get
_schema_logged = False

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

core.Feed.get = verified_rows

if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'dual-extension-v1':
        core.emit('reader_adapter', version='stock-identity-v1', price_values_modified=False)
        threading.Thread(target=core.execute, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT', '10000'))), core.Handler).serve_forever()
