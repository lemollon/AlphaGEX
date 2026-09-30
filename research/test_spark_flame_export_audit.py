import copy
import datetime
import unittest
from audit_spark_flame_exports import audit


def fixture():
    paths = [('flame', 'current_customer_package', 'natural'), ('spark', 'current_customer_package', 'natural')]
    spec = {'seeds': {'flame': 2000, 'spark': 5000}, 'profiles': ['current_customer_package'],
            'fillCases': {'natural': 0}, 'start': '2023-09-29', 'end': '2026-09-28', 'monthlyFeeExternalDollars': 50}
    dates = []
    date = datetime.date(2023, 9, 29)
    while len(dates) < 751:
        if date.weekday() < 5:
            dates.append(date.isoformat())
        date += datetime.timedelta(days=1)
    daily = [{'day': day, 'accounts': [{'bot': bot, 'profile': profile, 'fillCase': fill,
              'day': day, 'before': spec['seeds'][bot], 'after': spec['seeds'][bot],
              'pnl': 0, 'unresolved': [], 'markGaps': 0} for bot, profile, fill in paths]} for day in dates]
    summary = [{'bot': bot, 'profile': profile, 'fillCase': fill, 'startingEquity': spec['seeds'][bot],
                'endingEquity': spec['seeds'][bot], 'pnl': 0, 'complete': True, 'unresolved': [],
                'invalidFrom': None, 'trades': 0, 'flintTrades': 0, 'hostTrades': 0,
                'markGapMinutes': 0, 'netAfterExternalSubscription': -1800} for bot, profile, fill in paths]
    trades = [{'bot': bot, 'profile': profile, 'fillCase': fill, 'trades': []} for bot, profile, fill in paths]
    gamma = {day: {'priorDay': (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat(),
                   'used': 2, 'positiveOI': 2, 'unpricedOIContracts': 0} for day in dates}
    report = {'spec': spec, 'status': {'stage': 'completed_with_coverage_limits', 'completed': 751,
              'total': 751, 'dataErrors': []}, 'summary': summary, 'gammaReconstruction': gamma}
    return report, trades, daily


class AuditTests(unittest.TestCase):
    def test_consistent_synthetic_exports_pass(self):
        self.assertTrue(audit(*fixture())['passed'])

    def test_tampered_balance_is_detected(self):
        r, t, d = fixture()
        r['summary'][0]['endingEquity'] += 1
        result = audit(r, t, d)
        self.assertFalse(result['passed'])
        self.assertTrue(any('ending_equity_mismatch' in e for e in result['errors']))

    def test_omitted_day_and_gamma_cannot_pass_complete_flag(self):
        r, t, d = fixture()
        r['gammaReconstruction'].pop(d[0]['day'])
        d.pop()
        self.assertFalse(audit(r, t, d)['passed'])

    def test_unreported_trade_is_detected(self):
        r, t, d = fixture()
        t[0]['trades'].append({'day': d[0]['day'], 'leg': 'host_spy', 'symbol': 'SPY',
                             'entry': 845, 'exit': 960, 'n': 1, 'pnl': 10, 'reason': 'expiry'})
        self.assertFalse(audit(r, t, d)['passed'])

    def test_duplicated_session_is_detected(self):
        r, t, d = fixture()
        d[1] = copy.deepcopy(d[0])
        self.assertFalse(audit(r, t, d)['passed'])

    def test_unpriced_gamma_cannot_pass_complete_flag(self):
        r, t, d = fixture()
        r['gammaReconstruction'][d[0]['day']]['used'] = 1
        self.assertFalse(audit(r, t, d)['passed'])

    def test_wrong_subscription_charge_is_detected(self):
        r, t, d = fixture()
        r['summary'][0]['netAfterExternalSubscription'] = -50
        self.assertFalse(audit(r, t, d)['passed'])


if __name__ == '__main__':
    unittest.main()
