"""JSONB round-trip regression: zero-sign changes are not P&L changes."""
import json
import unittest
from scripts.valor_research_repair_v7 import canonical

class JsonbTests(unittest.TestCase):
    def test_signed_zero_matches_postgres(self):
        self.assertEqual(canonical({'gross_losses': -0.0}), canonical({'gross_losses': 0.0}))
    def test_nested_zero(self):
        self.assertEqual(canonical([{'m': {'x': -0.0}}]), canonical([{'m': {'x': 0.0}}]))
    def test_nonzero_amount_change_rejected(self):
        self.assertNotEqual(canonical({'net': 17.0}), canonical({'net': 17.000001}))
    def test_missing_field_rejected(self):
        self.assertNotEqual(canonical({'net': 17.0}), canonical({'net': 17.0, 'other': 0.0}))
    def test_nonfinite_rejected(self):
        for x in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError): canonical({'net': x})
    def test_roundtrip_scientific(self):
        self.assertEqual(canonical({'x': 1e-7}), canonical(json.loads('{"x":0.0000001}')))
    def test_bools_not_numbers(self):
        self.assertNotEqual(canonical({'x': False}), canonical({'x': 0.0}))

if __name__ == '__main__': unittest.main()
