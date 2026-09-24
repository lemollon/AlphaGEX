"""Pre-registered entry stand-down rules, 2026-09-24:
  - CallDiag (IWM 10d/20d call diagonal): IWM_RV5 stand-down
    (ironforge-data/out/clusters/CLUSTER_calldiag_iwm.py's frozen rule).
  - SPIKE (squeeze spike-buy short hold): FOMC-week stand-down
    (ironforge-data/out/clusters/CLUSTER_squeeze_short.py's own fomc_week()).

Both rules are ENTRY-only (never touch exits/open positions) and fail
CLOSED: missing/insufficient data always stands down, never trades blind.
"""
from datetime import date

from backend.ember.legacy import call_diag, spike


# ---------------------------------------------------------------- CallDiag / IWM RV5
def test_iwm_rv5_matches_pct_change_sample_stdev():
    # Zero vol -> rv5 exactly 0.0.
    assert call_diag.iwm_rv5([100.0] * 6) == 0.0
    # Hand-computed: closes 100,101,100,101,100,101 -> returns +1%,-0.990099%,
    # +1%,-0.990099%,+1% ; sample stdev (ddof=1) * sqrt(252).
    closes = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
    rets = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, 6)]
    mean = sum(rets) / 5
    var = sum((r - mean) ** 2 for r in rets) / 4
    expected = var ** 0.5 * (252 ** 0.5)
    assert round(call_diag.iwm_rv5(closes), 10) == round(expected, 10)


def test_iwm_rv5_needs_exactly_six_trailing_closes():
    assert call_diag.iwm_rv5([100.0] * 5) is None       # 5 closes -> only 4 returns
    assert call_diag.iwm_rv5([]) is None
    assert call_diag.iwm_rv5(None or []) is None


def test_iwm_rv5_prior_close_only_ignores_leading_extra_data():
    """Only the LAST 6 elements matter -- extra closes ahead of the 6-window
    (which would represent data the caller should never have handed over,
    e.g. today's own close) must not change the computed rv5 at all."""
    closes = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
    padded = [55.0, 200.0, 3.0] + closes
    assert call_diag.iwm_rv5(padded) == call_diag.iwm_rv5(closes)


def test_iwm_standdown_threshold_boundary_is_inclusive():
    flat = [100.0] * 6  # rv5 == 0.0
    # spec: "<= 0.1781 -> skip" -- exactly-at-threshold stands down.
    standdown, reason = call_diag.iwm_standdown_check(flat, threshold=0.0)
    assert standdown is True
    assert reason == "STANDDOWN_IWM_RV5 0.0000"
    # just above the threshold does NOT stand down.
    up = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
    rv5 = call_diag.iwm_rv5(up)
    standdown_ok, reason_ok = call_diag.iwm_standdown_check(up, threshold=rv5 - 1e-6)
    assert standdown_ok is False
    assert "ok" in reason_ok
    standdown_eq, _ = call_diag.iwm_standdown_check(up, threshold=rv5)
    assert standdown_eq is True    # exactly at rv5 == threshold still stands down


def test_iwm_standdown_default_threshold_is_0_1781():
    assert call_diag.IWM_RV5_STANDDOWN_DEFAULT == 0.1781


def test_iwm_standdown_fails_closed_on_missing_or_insufficient_data():
    assert call_diag.iwm_standdown_check(None) == (True, "STANDDOWN_IWM_RV5 unknown (no closes)")
    assert call_diag.iwm_standdown_check([]) == (True, "STANDDOWN_IWM_RV5 unknown (no closes)")
    standdown, reason = call_diag.iwm_standdown_check([100.0] * 5)
    assert standdown is True
    assert "fewer than 6" in reason


def test_iwm_standdown_env_override(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DIAG_IWM_RV5_STANDDOWN=0.25\n", encoding="utf-8")
    cfg = call_diag.load_cfg(env_file)
    assert cfg.iwm_rv5_standdown == 0.25


def test_iwm_standdown_default_when_env_missing(tmp_path):
    cfg = call_diag.load_cfg(tmp_path / "does-not-exist.env")
    assert cfg.iwm_rv5_standdown == call_diag.IWM_RV5_STANDDOWN_DEFAULT


def test_fetch_iwm_prior_closes_fails_closed_without_token(monkeypatch):
    monkeypatch.delenv("TRADIER_TOKEN", raising=False)
    assert call_diag.fetch_iwm_prior_closes(date(2026, 9, 24)) is None


# ---------------------------------------------------------------- SPIKE / FOMC week
def test_fomc_week_matches_cluster_squeeze_short_window():
    # 2026-09-16 is a listed FOMC decision date (verified against
    # federalreserve.gov 2026-09-24) -- window is decision-2 .. decision+4,
    # i.e. entry_date in [2026-09-14, 2026-09-20] (Mon..Sun, since the
    # decision date is always a Wednesday).
    assert spike.fomc_week(date(2026, 9, 14)) is True     # Mon, decision - 2
    assert spike.fomc_week(date(2026, 9, 16)) is True     # decision day itself
    assert spike.fomc_week(date(2026, 9, 20)) is True     # Sun, decision + 4
    assert spike.fomc_week(date(2026, 9, 13)) is False    # one day too early
    assert spike.fomc_week(date(2026, 9, 21)) is False    # one day too late


def test_fomc_week_non_fomc_week_is_false():
    assert spike.fomc_week(date(2026, 9, 24)) is False    # today, not an FOMC week
    assert spike.fomc_standdown_check(date(2026, 9, 24)) == (False, "not an FOMC week")


def test_fomc_standdown_fires_inside_the_window():
    standdown, reason = spike.fomc_standdown_check(date(2026, 9, 16))
    assert standdown is True
    assert reason == "STANDDOWN_FOMC_WEEK"


def test_fomc_standdown_fails_closed_beyond_published_calendar():
    """The Fed had not published 2027 meeting dates as of the 2026-09-24
    verification -- any entry date past FOMC_COVERAGE_END must stand down
    rather than assume no FOMC week, i.e. missing calendar data never trades
    blind."""
    assert spike.fomc_week(date(2027, 1, 15)) is None
    standdown, reason = spike.fomc_standdown_check(date(2027, 1, 15))
    assert standdown is True
    assert reason.startswith("STANDDOWN_FOMC_WEEK unknown")


def test_fomc_dates_match_federal_reserve_2026_calendar():
    """Every 2026 decision date (second day of the 2-day meeting) verified
    live against federalreserve.gov/monetarypolicy/fomccalendars.htm on
    2026-09-24."""
    assert spike.FOMC_DATES == [
        date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
        date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    ]
