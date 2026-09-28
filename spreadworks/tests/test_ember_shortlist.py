"""Unit tests for the intraday curve-refresh shortlist rule (see
spreadworks/backend/ember/legacy/shortlist.py for the full design note)."""
from __future__ import annotations

from backend.ember.legacy.shortlist import build_shortlist


def test_shortlist_is_todays_ledgered_tickers():
    rows = [
        {"ticker": "AAA", "scan_date": "2026-09-28"},
        {"ticker": "BBB", "scan_date": "2026-09-28"},
        {"ticker": "CCC", "scan_date": "2026-09-27"},  # yesterday -- excluded
        {"ticker": "AAA", "scan_date": "2026-09-28"},  # duplicate -- set dedupes
    ]
    ranked = ["AAA", "BBB", "CCC", "DDD"]
    assert build_shortlist(rows, "2026-09-28", ranked, max_size=15) == {"AAA", "BBB"}


def test_empty_ledger_falls_back_to_opportunity_score_order():
    ranked = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert build_shortlist([], "2026-09-28", ranked, max_size=3) == {"AAA", "BBB", "CCC"}


def test_ledger_rows_for_a_different_date_are_treated_as_empty():
    rows = [{"ticker": "AAA", "scan_date": "2026-09-27"}]
    ranked = ["ZZZ", "YYY"]
    assert build_shortlist(rows, "2026-09-28", ranked, max_size=2) == {"ZZZ", "YYY"}


def test_shortlist_is_capped_and_prefers_higher_ranked_tickers():
    rows = [{"ticker": t, "scan_date": "2026-09-28"} for t in
            ["AAA", "BBB", "CCC", "DDD", "EEE"]]
    ranked = ["EEE", "DDD", "CCC", "BBB", "AAA"]  # opportunity_score-desc
    shortlist = build_shortlist(rows, "2026-09-28", ranked, max_size=2)
    assert shortlist == {"EEE", "DDD"}


def test_ledgered_ticker_no_longer_in_todays_candidates_is_kept_not_dropped():
    rows = [{"ticker": "GONE", "scan_date": "2026-09-28"},
            {"ticker": "AAA", "scan_date": "2026-09-28"}]
    ranked = ["AAA", "BBB"]  # "GONE" fell off every source list this tick
    assert build_shortlist(rows, "2026-09-28", ranked, max_size=15) == {"GONE", "AAA"}


def test_malformed_rows_never_raise():
    rows = [{"ticker": "AAA", "scan_date": "2026-09-28"}, "not a dict", {}, None]
    ranked = ["AAA", "BBB"]
    assert build_shortlist(rows, "2026-09-28", ranked, max_size=15) == {"AAA"}
