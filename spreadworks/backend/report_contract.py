"""Pure completeness checks; missing observations never become live evidence."""
REQUIRED_BLOCKS = (
    "risk_on_defensive", "premium_selling", "surface", "smile",
    "expected_move", "gamma", "flow", "forward_strikes", "sector_credit",
    "breadth", "profile", "macro", "event_calendar", "entry_watches",
    "contract_packages", "paper_scorecard", "morning_comparison",
)


def completeness(blocks, rendered):
    """Separate rendering completeness from data completeness explicitly."""
    rendered = set(rendered)
    omitted = [name for name in REQUIRED_BLOCKS if name not in rendered]
    missing = [name for name in REQUIRED_BLOCKS
               if not blocks.get(name, {}).get("available")]
    return {"publishable": not omitted, "all_data_live": not missing,
            "omitted_blocks": omitted, "unavailable_blocks": missing}


if __name__ == "__main__":
    import unittest

    class ContractTests(unittest.TestCase):
        def test_omission_fails(self):
            self.assertFalse(completeness({}, [])['publishable'])

        def test_disclosures_are_not_live(self):
            check = completeness({}, REQUIRED_BLOCKS)
            self.assertTrue(check['publishable'])
            self.assertFalse(check['all_data_live'])

        def test_every_producer_required(self):
            blocks = {key: {"available": True} for key in REQUIRED_BLOCKS}
            self.assertTrue(completeness(blocks, REQUIRED_BLOCKS)['all_data_live'])
            blocks['flow']['available'] = False
            self.assertEqual(completeness(blocks, REQUIRED_BLOCKS)['unavailable_blocks'], ['flow'])

    unittest.main()
