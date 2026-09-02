"""/growth — the one-screen SPARK/FLAME backtest + today's frozen-model read.

The page's TODAY number is scored live from the frozen #60 weights shipped in
risk_advisor_growth.json. If that scorer drifted from the script that wrote
the file, the page would show a different "today" than the backtest it sits
on. The first test pins them together: the file's own features must score to
the file's own p.
"""
import json
from types import SimpleNamespace

import pytest

from backend import routes_risk as rr


@pytest.fixture(scope="module")
def growth_file():
    assert rr.GROWTH_JSON.exists(), "backend/data/risk_advisor_growth.json must ship"
    with open(rr.GROWTH_JSON, encoding="utf-8") as f:
        return json.load(f)


def test_the_frozen_scorer_reproduces_the_files_own_today_block(growth_file):
    today = growth_file["today"]
    out = rr._score_frozen(today["model"], today["features"])
    assert out is not None
    assert abs(out["p"] - today["p"]) < 1e-9
    assert out["state"] == today["state"]
    assert out["driver"] == today["driver"]
    # p_hist is stored to 4 dp, so the rank can move by a hair, no more.
    assert abs(out["percentile"] - today["percentile"]) < 0.005


def test_percentile_is_a_fraction_not_a_percent(growth_file):
    """The frontend multiplies by 100. Shipping 26 instead of 0.26 would print
    '2600th percentile'; shipping 0.26 and forgetting the multiply printed
    '0th' — the bug this guards on the backend side."""
    today = growth_file["today"]
    out = rr._score_frozen(today["model"], today["features"])
    assert 0.0 <= out["percentile"] <= 1.0


def test_a_missing_feature_scores_to_none_not_a_guess(growth_file):
    today = growth_file["today"]
    feats = dict(today["features"])
    feats.pop("vvix_l")
    assert rr._score_frozen(today["model"], feats) is None
    feats = dict(today["features"], rv5=None)
    assert rr._score_frozen(today["model"], feats) is None


def test_a_hot_tape_scores_stand_down(growth_file):
    """Sanity on sign: crank VIX, VVIX and realised vol far above their means
    and the frozen model must call STAND DOWN, not NORMAL."""
    today = growth_file["today"]
    hot = dict(today["features"], vix_l=45.0, vix3m_l=35.0, ts_spread_l=10.0,
               backwardation_l=1.0, vvix_l=150.0, rv5=0.04, rv21=0.03,
               semivar5=0.001, absret1=0.04)
    out = rr._score_frozen(today["model"], hot)
    assert out["state"] == "STAND DOWN"
    assert out["p"] > today["p"]


def test_downsample_keeps_both_ends_and_the_cap():
    pts = [[f"d{i}", float(i)] for i in range(950)]
    out = rr._downsample_curve(pts, max_n=400)
    assert len(out) <= 400
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert rr._downsample_curve(pts[:100], max_n=400) == pts[:100]


async def test_growth_falls_back_to_the_file_when_cboe_is_down(growth_file, monkeypatch):
    """No live VIX -> the page still gets a TODAY read, labelled as coming
    from the file, with the file's own p — never a 500, never a fabricated
    live number."""
    async def _no_cboe(_client, _sym):
        return {}
    monkeypatch.setattr(rr, "_cboe", _no_cboe)
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http=None)))

    out = await rr.growth(req)

    assert set(out["bots"]) == {"flame", "spark"}
    assert out["bots"]["flame"]["structure"] == "spot-1 / $2 wing"
    assert out["bots"]["spark"]["structure"] == "spot-2 / $5 wing"
    assert "sd60" in out["gates"] and "none" in out["gates"]
    for bot in out["bots"].values():
        assert set(bot["gates"]) >= {"none", "sd60"}
        assert bot["curves"]["none"][0][0] == bot["span"][0]
    lt = out["live_today"]
    assert lt["computed_from"] == "file"
    assert lt["p"] == growth_file["today"]["p"]
    assert lt["state"] == growth_file["today"]["state"]


async def test_growth_reports_unavailable_when_the_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "GROWTH_JSON", tmp_path / "nope.json")
    rr._growth_cache.clear()
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http=None)))
    out = await rr.growth(req)
    assert out["status"] == "unavailable"
    rr._growth_cache.clear()
