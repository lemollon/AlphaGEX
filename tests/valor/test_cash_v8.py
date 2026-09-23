import copy
import gzip
import hashlib
import numpy as np
import pandas as pd
import pytest
from scripts import valor_cash_engine_v8 as c
from scripts import valor_cash_research_v8 as r


def tape(day='2024-02-01', minutes=390, slope=.25):
    ts = pd.date_range(day+' 08:30', periods=minutes, freq='min', tz='America/Chicago').tz_convert('UTC')
    op = 5000.+np.arange(minutes)*slope
    return pd.DataFrame(dict(timestamp=ts, instrument_id=42, open=op,
        high=np.maximum(op, op+slope)+.25, low=np.minimum(op, op+slope)-.25, close=op+slope, volume=100))


def order(i=29, side=1, **kw): return dict(index=i, side=side, **kw)


def replay(raw, orders, h=120, limit=None, trail=None):
    d = c.prepare(raw, .25)
    t, u, k, n = c.replay(d, orders, 5., .25, h, limit, 0, trail)
    return d, t, u, k, c.summarize(t, u, k, n, 5., .25, 2, int(d.timestamp.iloc[0].year))


@pytest.mark.parametrize('day', ['2023-07-04', '2023-11-23', '2024-01-01', '2025-01-09', '2025-04-18', '2026-07-03'])
def test_holidays(day):
    assert c.session(day) is None
    _, t, u, k, _ = replay(tape(day), [order()])
    assert not t and not u and k['outside_cash_entry_window'] == 1


@pytest.mark.parametrize('day', ['2023-07-03', '2023-11-24', '2024-12-24', '2025-11-28'])
def test_early_exit(day):
    _, t, u, _, _ = replay(tape(day, 210), [order()], 240)
    assert not u and len(t) == 1
    assert pd.Timestamp(t[0]['exit']).tz_convert('America/Chicago').strftime('%H:%M') == '11:55'


@pytest.mark.parametrize('day', ['2023-03-10', '2023-03-13', '2024-11-01', '2024-11-04'])
def test_dst(day):
    _, t, u, _, _ = replay(tape(day), [order()], 30)
    assert not u
    assert pd.Timestamp(t[0]['entry']).tz_convert('America/Chicago').strftime('%H:%M') == '09:00'
    assert pd.Timestamp(t[0]['exit']).tz_convert('America/Chicago').strftime('%H:%M') == '09:30'


def test_weekend(): assert c.session('2025-02-01') is None


def test_calendar_year_fails_closed():
    with pytest.raises(ValueError): c.session('2027-02-01')


def test_long_hold_clamped():
    _, t, u, _, s = replay(tape(), [order(269)], 240)
    assert len(t) == 1 and not u and s['net_dollars'] is not None
    assert pd.Timestamp(t[0]['exit']).tz_convert('America/Chicago').strftime('%H:%M') == '14:55'


def test_scheduled_open_ignores_future_extremes():
    raw = tape(); a = replay(raw, [order()], 30)[1]
    raw.loc[60, 'low'] = 1.; raw.loc[60, 'high'] = 9000.
    assert a == replay(raw, [order()], 30)[1]


def test_next_open():
    raw = tape(); t = replay(raw, [order()], 30)[1][0]
    assert t['entry_raw'] == raw.open.iloc[30] and t['exit_raw'] == raw.open.iloc[60]


def test_unresolved_withholds_full_totals():
    _, t, u, k, s = replay(tape().drop(index=40), [order(), order(69)])
    assert not t and len(u) == 1 and s['net_dollars'] is None and s['profit_factor'] is None
    assert k['date_blocked_after_unknown_exposure'] == 1


def test_missing_entry():
    _, t, u, _, s = replay(tape().drop(index=30), [order()], 30)
    assert not t and u[0]['reason'] == 'missing_entry_observation' and s['net_dollars'] is None


def test_roll_not_price_profit():
    raw = tape(); raw.loc[40:, 'instrument_id'] = 43; raw.loc[40:, ['open', 'high', 'low', 'close']] += 1000
    _, t, u, _, s = replay(raw, [order()])
    assert not t and len(u) == 1 and s['net_dollars'] is None


def test_no_entry_at_flat_deadline():
    _, t, u, k, _ = replay(tape(), [order(384)], 30)
    assert not t and not u and k['outside_cash_entry_window'] == 1


def test_stop_first():
    raw = tape(); raw.loc[31, ['high', 'low']] = [5100., 4900.]
    t = replay(raw, [order(reference=5007.5, risk=10., stop=4997.5, target=5027.5)])[1][0]
    assert t['reason'] == 'stop' and t['exit_raw'] == 4997.5


def test_limit_requires_trade_through():
    raw = tape(minutes=36, slope=0); raw.loc[31, 'high'] = 5005.
    o = [order(reference=5000., risk=5., stop=4995., target=5005.)]
    assert replay(raw, o, 5)[1][0]['reason'] == 'scheduled_open'
    raw.loc[31, 'high'] = 5005.25
    assert replay(raw, o, 5)[1][0]['reason'] == 'limit_trade_through'


def test_stop_gap():
    raw = tape(); raw.loc[31, ['open', 'high', 'low', 'close']] = [4980, 4981, 4979, 4980]
    t = replay(raw, [order(reference=5007.5, risk=10, stop=4997.5, target=5027.5)], 30)[1][0]
    assert t['reason'] == 'gap_stop' and t['exit_raw'] == 4980


def test_entry_gap_is_not_retroactive_skip():
    raw = tape(); raw.loc[30, ['open', 'high', 'low', 'close']] = [4980, 4981, 4979, 4980]
    _, t, u, _, s = replay(raw, [order(reference=5007.5, risk=10, stop=4997.5, target=5027.5)], 30)
    assert len(t) == 1 and not u and s['net_dollars'] == -8


def test_no_overlap():
    ts = replay(tape(), [order(i) for i in range(29, 100)], 30)[1]
    assert len(ts) > 1
    assert all(pd.Timestamp(b['entry']) >= pd.Timestamp(a['exit']) for a, b in zip(ts, ts[1:]))


def test_daily_limit(): assert len(replay(tape(), [order(i) for i in range(29, 200)], 30, 1)[1]) == 1


def test_fees_once_and_identical_cost_paths():
    _, t, u, k, a = replay(tape(), [order()], 30)
    b = c.summarize(t, u, k, 1, 5, .25, 4, 2024)
    assert b['net_dollars']-a['net_dollars'] == -5
    assert a['raw_price_pnl']-a['assumed_total_cost'] == a['net_dollars']


def test_directional_signs():
    assert replay(tape(), [order()], 30)[4]['net_dollars'] > 0
    assert replay(tape(), [order(side=-1)], 30)[4]['net_dollars'] < 0
    assert replay(tape(slope=-.25), [order(side=-1)], 30)[4]['net_dollars'] > 0


@pytest.mark.parametrize('defect', ['duplicate', 'naive', 'grid', 'high', 'negative'])
def test_bad_data_rejected(defect):
    raw = tape()
    if defect == 'duplicate': raw = pd.concat([raw, raw.iloc[[0]]])
    if defect == 'naive': raw['timestamp'] = raw.timestamp.dt.tz_localize(None)
    if defect == 'grid': raw.loc[0, 'open'] += .1
    if defect == 'high': raw.loc[0, 'high'] = 1
    if defect == 'negative': raw.loc[0, 'volume'] = -1
    with pytest.raises(ValueError): c.prepare(raw, .25)


def test_signed_zero(): assert c.canonical({'a': -0.}) == c.canonical({'a': 0.})


def test_identity_changes():
    a = dict(code='A', data='B', cost=8, calendar='C'); h = c.digest(a)
    for k in a:
        b = dict(a); b[k] = 'CHANGED'; assert c.digest(b) != h


def test_gex_never_same_day():
    d = c.prepare(tape(), .25); source = [('2024-01-31', -1), ('2024-02-01', 999)]
    assert len(r.lag_filter([order()], d, source, 1, 'negative_only')[0]) == 1
    assert not r.lag_filter([order()], d, source, 1, 'positive_only')[0]


def test_missing_gex_not_negative(): assert not r.lag_filter([order()], c.prepare(tape(), .25), [], 1, 'negative_only')[0]


def test_previous_early_close():
    d = c.prepare(pd.concat([tape('2024-11-29', 210), tape('2024-12-02')]), .25)
    assert r.prior_cash_days(d)['2024-12-02']['date'] == '2024-11-29'


def test_incomplete_prior_session():
    d = c.prepare(pd.concat([tape('2024-11-29', 209), tape('2024-12-02')]), .25)
    assert '2024-12-02' not in r.prior_cash_days(d)


def test_future_does_not_change_prior():
    raw = pd.concat([tape('2024-02-01'), tape('2024-02-02')], ignore_index=True)
    a = r.prior_cash_days(c.prepare(raw, .25))
    raw.loc[390:, ['open', 'high', 'low', 'close']] += 1000
    b = r.prior_cash_days(c.prepare(raw, .25))
    assert a['2024-02-02']['close'] == b['2024-02-02']['close']


def test_trail_only_next_bar():
    raw = tape(slope=0); raw.loc[31, ['high', 'low']] = [5021, 4995]
    t = replay(raw, [order(reference=5000., risk=10., stop=4990., trail=True)], 10, trail=np.full(390, 3.))[1][0]
    assert t['exit_index'] == 32 and t['reason'] == 'gap_stop'


def saved_result():
    row = replay(tape(), [order()], 30)[4]
    row.update(family='test', spec='rising', horizon=30)
    body = gzip.compress(c.canonical([row]), mtime=0)
    return [dict(fingerprint='valid'), r.summarize_rows([row]), hashlib.sha256(body).hexdigest(), body]


def test_completed_result_verified(): assert r.verified_saved(saved_result(), 'valid', 1, 'historical')


@pytest.mark.parametrize('defect', ['code', 'raw', 'cost', 'calendar', 'runtime', 'count', 'summary', 'bytes'])
def test_completed_cache_cannot_mask_changes(defect):
    data = saved_result(); fp = 'valid'; n = 1
    if defect in ('code', 'raw', 'cost', 'calendar', 'runtime'): fp = 'changed_'+defect
    if defect == 'count': n = 2
    if defect == 'summary': data[1][0]['net_dollars'] = 1234
    if defect == 'bytes': data[3] = b'corrupt'
    with pytest.raises(ValueError): r.verified_saved(data, fp, n, 'historical')


def test_duplicate_scenarios_rejected():
    row = replay(tape(), [order()], 30)[4]
    with pytest.raises(ValueError): r.validate_results([row, copy.deepcopy(row)], 2)


def test_unknown_cannot_become_valid_profit():
    row = replay(tape().drop(index=40), [order()], 30)[4]
    row['net_dollars'] = 0.
    with pytest.raises(ValueError): r.validate_results([row], 1)


def test_order_conservation():
    row = replay(tape(), [order(), order(384)], 30)[4]
    assert row['candidates'] == row['closed_trades']+row['unresolved']+sum(row['skipped'].values())
