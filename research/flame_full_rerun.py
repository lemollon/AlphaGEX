"""Diagnostic launcher for the immutable, locally tested research source.

The pinned source is software, not saved market data. Its SHA-256 is verified.
Only the error message is expanded; strategy and pricing rules are unchanged.
No live trading modules are imported. The complete readable source is retained
in commit 02904232b558f4f0924fc1903fe5f5cb70ab3637.
"""
import hashlib
import os
import pathlib
import runpy
import requests

URL = 'https://raw.githubusercontent.com/lemollon/AlphaGEX/02904232b558f4f0924fc1903fe5f5cb70ab3637/research/flame_full_rerun.py'
EXPECTED = '2224957e25ffbeb7c18a7f131d96f6790ec29ff0c522d73a2bbe8670492cb4bd'

if __name__ == '__main__':
    response = requests.get(URL, timeout=(10, 30))
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != EXPECTED:
        raise RuntimeError('Pinned research source hash mismatch')
    source = response.content.decode('utf-8')
    before = "raise DataError('invalid stock OHLC')"
    after = "raise DataError('invalid stock OHLC: '+str(dict(day=day,minute=m,values=vals,raw=row)))"
    if source.count(before) != 1:
        raise RuntimeError('Diagnostic patch target mismatch')
    source = source.replace(before, after)
    destination = pathlib.Path('/tmp/flame_pinned_diagnostic.py')
    destination.write_text(source)
    runpy.run_path(str(destination), run_name='__main__')
