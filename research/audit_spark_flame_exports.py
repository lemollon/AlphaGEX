"""Reconcile terminal replay exports without trusting the summary's complete flag.

Standard library only. No network, database, or broker access.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def key(row):
    return row['bot'], row['profile'], row['fillCase']


def audit(report, trades, daily):
    errors = []
    spec, status = report['spec'], report['status']
    expected = {(bot, profile, fill) for bot in spec['seeds']
                for profile in spec['profiles'] for fill in spec['fillCases']}
    summaries = {key(a): a for a in report['summary']}
    trade_paths = {key(a): a['trades'] for a in trades}
    def check(condition, message):
        if not condition:
            errors.append(message)
    check(status['stage'] == 'completed_with_coverage_limits', 'run_not_terminal_complete')
    check(status['completed'] == status['total'] == 751, 'requested_751_sessions_not_completed')
    check(not status.get('dataErrors'), 'data_errors_present')
    check(len(summaries) == len(report['summary']) and set(summaries) == expected, 'summary_path_set_mismatch')
    check(len(trade_paths) == len(trades) and set(trade_paths) == expected, 'trade_path_set_mismatch')
    dates = [d['day'] for d in daily]
    check(len(dates) == 751 and dates == sorted(set(dates)), 'daily_sessions_missing_duplicated_or_out_of_order')
    check(all(spec['start'] <= day <= spec['end'] for day in dates), 'daily_date_outside_requested_window')
    gamma = report.get('gammaReconstruction', {})
    for day in dates:
        g = gamma.get(day)
        check(bool(g), f'gamma_missing:{day}')
        if g:
            check(g['used'] == g['positiveOI'] and g.get('unpricedOIContracts', 0) == 0, f'gamma_oi_coverage:{day}')
            check(g['priorDay'] < day, f'gamma_lookahead:{day}')
    days_by_path = defaultdict(list)
    for d in daily:
        rows = d['accounts']
        check(len(rows) == len(expected) and {key(a) for a in rows} == expected, f'daily_path_set_mismatch:{d["day"]}')
        for a in rows:
            check(a['day'] == d['day'], f'daily_account_date_mismatch:{d["day"]}')
            days_by_path[key(a)].append(a)
    for path in sorted(expected):
        label = '/'.join(path)
        if path not in summaries or path not in trade_paths:
            continue
        s, ts = summaries[path], trade_paths[path]
        check(s['complete'] and not s['unresolved'] and s.get('invalidFrom') is None, f'incomplete_path:{label}')
        check(cents(s['startingEquity']) == cents(spec['seeds'][path[0]]), f'seed_mismatch:{label}')
        by_day = defaultdict(int)
        entries = defaultdict(set)
        for t in ts:
            check(t['day'] in dates, f'trade_without_session:{label}:{t["day"]}')
            check(isinstance(t['n'], int) and not isinstance(t['n'], bool) and t['n'] > 0, f'invalid_quantity:{label}')
            check(t['symbol'] in ('SPY', 'XSP'), f'unexpected_symbol:{label}')
            check(t['entry'] <= t['exit'], f'exit_before_entry:{label}')
            if t['symbol'] == 'XSP':
                check(t['reason'] == 'cash_settlement', f'xsp_non_cash_exit:{label}')
            by_day[t['day']] += cents(t['pnl'])
            entries[(t['day'], 'flint' if t['leg'] == 'flint' else 'host')].add(t['entry'])
        check(all(len(v) <= 1 for v in entries.values()), f'multiple_entries_per_leg_day:{label}')
        trade_pnl = sum(by_day.values())
        check(trade_pnl == cents(s['pnl']), f'trade_summary_pnl_mismatch:{label}')
        check(cents(s['startingEquity']) + trade_pnl == cents(s['endingEquity']), f'ending_equity_mismatch:{label}')
        check(len(ts) == s['trades'], f'trade_count_mismatch:{label}')
        check(sum(t['leg'] == 'flint' for t in ts) == s['flintTrades'], f'flint_count_mismatch:{label}')
        check(sum(t['leg'].startswith('host') for t in ts) == s['hostTrades'], f'host_count_mismatch:{label}')
        ds = days_by_path[path]
        prior = cents(s['startingEquity'])
        for d in ds:
            check(cents(d['before']) == prior, f'equity_chain_mismatch:{label}:{d["day"]}')
            check(cents(d['pnl']) == by_day[d['day']], f'daily_trade_pnl_mismatch:{label}:{d["day"]}')
            check(cents(d['after']) == cents(d['before']) + cents(d['pnl']), f'daily_equity_mismatch:{label}:{d["day"]}')
            check(not d['unresolved'], f'daily_unresolved:{label}:{d["day"]}')
            prior = cents(d['after'])
        check(len(ds) == 751 and prior == cents(s['endingEquity']), f'daily_ending_equity_mismatch:{label}')
        check(sum(d['markGaps'] for d in ds) == s['markGapMinutes'], f'mark_gap_count_mismatch:{label}')
        check(cents(s['netAfterExternalSubscription']) == trade_pnl - 36 * cents(spec['monthlyFeeExternalDollars']), f'external_subscription_mismatch:{label}')
    return {'passed': not errors, 'errors': errors, 'checkedPaths': len(expected),
            'checkedSessions': len(dates), 'checkedTrades': sum(len(ts) for ts in trade_paths.values()),
            'scope': 'Export coverage and ledger reconciliation; not independent proof of broker fills or gamma-model accuracy.'}
