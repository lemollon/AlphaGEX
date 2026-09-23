"""Isolated research entrypoint; no live strategy or broker-order imports."""
import json
import runpy
from types import SimpleNamespace
import flame_reset_baseline as core


def exact_json(value, **kwargs):
    kwargs.setdefault('default', str)
    return json.dumps(value, **kwargs)


core.json = SimpleNamespace(dumps=exact_json)

if __name__ == '__main__':
    runpy.run_module('flame_regime_continuation', run_name='__main__')
