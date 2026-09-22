"""Isolated regression tests; no database or market-data credentials required."""
import ast
from dataclasses import dataclass
from pathlib import Path
import unittest
import pandas as pd


def load_evaluator():
    source = Path(__file__).with_name('backtest_ttp_tv_stock_strategy.py').read_text()
    tree = ast.parse(source)
    names = {'Program', 'evaluate_sequence', 'monte_carlo'}
    selected = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    scope = {'dataclass': dataclass, 'pd': pd}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(__file__), 'exec'), scope)
    return scope


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.scope = load_evaluator()
        self.program = self.scope['Program']('TEST_ONLY', 6, 20, 20, 1, 100, None)

    def evaluate(self, pnls, eligible=None):
        eligible = eligible if eligible is not None else pnls
        rows = [{'trading_date': '2026-01-05', 'entry_ts': i, 'pnl': p, 'valid_profit': v}
                for i, (p, v) in enumerate(zip(pnls, eligible))]
        return self.scope['evaluate_sequence'](pd.DataFrame(rows), 1000, self.program, 20)

    def test_gross_winners_do_not_pass(self):
        result = self.evaluate([-50, 40, 30])
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['valid_profit'], 20)

    def test_net_target_can_pass_diagnostic(self):
        self.assertEqual(self.evaluate([-20, 40, 40])['status'], 'PASS')

    def test_ineligible_winner_does_not_offset_eligible_losses(self):
        self.assertEqual(self.evaluate([-20, 50, 40], [-20, 0, 40])['status'], 'INCOMPLETE')

    def test_probability_withheld_even_with_large_sample(self):
        result = self.scope['monte_carlo'](pd.DataFrame({'trading_date': range(300)}), 1000,
                                         self.program, 3, 5000, 42)
        self.assertEqual(result['trials'], 0)
        self.assertEqual(result['status'], 'BLOCKED_MODEL_VALIDATION')


if __name__ == '__main__':
    unittest.main()
