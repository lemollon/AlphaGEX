"""Pinned research source plus explicit numeric-serialization normalization.

Only tiny residuals within 1e-9 dollars of a four-decimal price are normalized.
Genuine finer prices are retained for stocks and rejected, not rounded, for the
four-decimal option representation. Raw provider bytes remain unchanged evidence.
"""
import hashlib
import pathlib
import runpy
import requests
URL = 'https://raw.githubusercontent.com/lemollon/AlphaGEX/02904232b558f4f0924fc1903fe5f5cb70ab3637/research/flame_full_rerun.py'
EXPECTED = '2224957e25ffbeb7c18a7f131d96f6790ec29ff0c522d73a2bbe8670492cb4bd'
CANONICAL = '''NORMALIZED_TAILS = Counter()
def canonical_price(value, field):
    x = Decimal(str(value))
    if not x.is_finite():
        raise DataError('nonfinite source price')
    q = x.quantize(Decimal('0.0001'))
    residue = abs(x-q)
    if Decimal('0') < residue <= Decimal('0.000000001'):
        NORMALIZED_TAILS[field] += 1
        return q
    return x

'''

def patched(source):
    patches = [
        ('def units(value):', CANONICAL+'def units(value):'),
        ('try: d = Decimal(str(value))', "try: d = canonical_price(value, 'option')"),
        ("vals={k:float(row[k]) for k in ['open','high','low','close','volume']}", "try:\n                    vals={k:(float(row[k]) if k=='volume' else float(canonical_price(row[k], 'stock_'+k))) for k in ['open','high','low','close','volume']}\n                except (InvalidOperation, ValueError, TypeError, KeyError) as exc:\n                    emit('invalid_stock_numeric', day=day, minute=m, kind=type(exc).__name__, raw={k:row.get(k) for k in ['open','high','low','close','volume']})\n                    continue"),
        ("raise DataError('invalid stock OHLC')", "raise DataError('invalid stock OHLC: '+str(dict(day=day,minute=m,values=vals,raw=row)))"),
        ("'rerun-v1-exact'", "'rerun-v2-exact-source-tail-normalization'"),
        ("    end=stamp(day+'T15:39:00') if False else None\n", ''),
        ("(ROOT/'manifest.json').write_text(json.dumps(feed.manifest,indent=2))", "(ROOT/'manifest.json').write_text(json.dumps(feed.manifest,indent=2))\n        emit('normalizations', fields=dict(NORMALIZED_TAILS), tolerance_dollars='0.000000001')")
    ]
    for before, after in patches:
        if source.count(before) != 1:
            raise RuntimeError('Pinned-source patch mismatch: '+before[:70])
        source = source.replace(before, after)
    return source

if __name__ == '__main__':
    r = requests.get(URL, timeout=(10,30))
    r.raise_for_status()
    if hashlib.sha256(r.content).hexdigest() != EXPECTED:
        raise RuntimeError('Pinned source SHA256 mismatch')
    target=pathlib.Path('/tmp/flame_pinned_rerun.py')
    target.write_text(patched(r.content.decode('utf-8')))
    runpy.run_path(str(target),run_name='__main__')
