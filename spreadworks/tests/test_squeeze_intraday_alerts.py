from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine
from backend.squeeze_intraday_alerts import post_reading

CT = ZoneInfo('America/Chicago')


def test_crossing_dedup_recovery_and_hourly_context():
    engine = create_engine('sqlite://')
    messages = []
    def send(embed):
        messages.append(embed)
        return True
    def tick(minute, value):
        return post_reading(engine, datetime(2026, 10, 1, 9, minute, tzinfo=CT), value, 760, .38, send)
    assert tick(0, -5.38)
    assert '$4.75B above' in messages[-1]['description']
    assert not tick(1, -5.4)
    assert tick(2, -10.14)
    assert 'BELOW' in messages[-1]['title']
    assert not tick(3, -12)
    assert not tick(4, -10.13)  # strict "under", re-arms at equality
    assert tick(5, -10.15)
    assert len(messages) == 3
    assert post_reading(engine, datetime(2026, 10, 1, 10, 0, tzinfo=CT), -11, 760, .1, send)
    assert 'current reading' in messages[-1]['title']


def test_veto_threshold_crosses_independently_and_shows_both_legs():
    """🚨 2026-10-04: a second threshold (VETO_THRESHOLD_B, mirrors
    gamma_regime.DEEP_SHORT_B) was added alongside the original
    WARN_THRESHOLD_B -- Leron's call was "do both with context", meaning
    every alert shows both legs' distance/zone, not just whichever one
    fired. Crossing warn then veto in the same session must fire two
    distinct alerts, each still describing both thresholds."""
    engine = create_engine('sqlite://')
    messages = []
    def send(embed):
        messages.append(embed)
        return True
    def tick(minute, value):
        return post_reading(engine, datetime(2026, 10, 1, 9, minute, tzinfo=CT), value, 760, .05, send)

    assert tick(0, -5.0)   # above both -- hourly first-reading alert
    assert 'clear of both thresholds' in messages[-1]['description']

    assert tick(1, -11.0)  # crosses warn only
    assert 'BELOW WARNING' in messages[-1]['title']
    assert 'WARNING — approaching the veto zone' in messages[-1]['description']
    assert '$10.13' in messages[-1]['description'] and '$12.5' in messages[-1]['description']

    assert tick(2, -13.0)  # now crosses veto too -- veto title takes priority
    assert 'BELOW VETO' in messages[-1]['title']
    assert 'NO_SELL live' in messages[-1]['title']
    assert 'VETO ACTIVE' in messages[-1]['description']
    # still shows the warning leg's own distance, not just the veto leg
    assert 'Warning (' in messages[-1]['description']

    assert not tick(3, -13.5)  # still below both, same hour -- no re-alert
    assert len(messages) == 3


def test_failed_delivery_retries_and_state_survives_restart():
    engine = create_engine('sqlite://')
    now = datetime(2026, 10, 1, 9, 0, tzinfo=CT)
    assert not post_reading(engine, now, -11, None, None, lambda _: False)
    assert post_reading(engine, now, -11, None, None, lambda _: True)
    assert not post_reading(engine, now, -11, None, None, lambda _: True)


def test_invalid_or_closed_readings_do_not_alert():
    engine = create_engine('sqlite://')
    def fail(_):
        raise AssertionError('invalid reading posted')
    for value in (None, float('nan'), float('inf')):
        assert not post_reading(engine, datetime(2026, 10, 1, 9, 0, tzinfo=CT), value, None, None, fail)
    assert not post_reading(engine, datetime(2026, 10, 1, 16, 0, tzinfo=CT), -12, None, None, fail)


def test_partial_expiration_is_identified_for_alert_gate():
    # Execute the production reducer with two synthetic expiration responses.
    import ast
    import logging
    from pathlib import Path
    from datetime import date, timedelta
    from typing import Any
    source = (Path(__file__).resolve().parents[1] / 'backend/bots/gamma_regime.py').read_text()
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('compute_net_gex', 'fetch_net_gex')]
    ns = {'Any': Any, 'date': date, 'timedelta': timedelta, 'MAX_DTE': 45,
          'logger': logging.getLogger('test'), '_base': lambda: 'fake',
          '_hdrs': lambda: {}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<gamma>', 'exec'), ns)
    class Response:
        status_code = 200
        def json(self):
            return {'options': {'option': [{'greeks': {'gamma': .01},
                                           'open_interest': 100, 'option_type': 'call'}]}}
    class Client:
        _client = None
        def _spot(self, _): return 760
        def _all_expirations(self, _): return ['2026-10-02', '2026-10-09']
        def get(self, *args, **kwargs):
            response = Response()
            if kwargs['params']['expiration'] == '2026-10-09':
                response.status_code = 429
            return response
    client = Client(); client._client = client
    out = ns['fetch_net_gex'](client, today=date(2026, 10, 1))
    assert out['chain_complete'] is False
    assert out['failed_expirations'] == ['2026-10-09']
    assert out['net_gex'] is not None
