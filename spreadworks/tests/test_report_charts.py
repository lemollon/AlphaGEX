"""market_map chart legibility.

Leron, 2026-10-13: "expected move visuals is hard to read." Live screenshot showed the
gamma flip/call-wall/put-wall price labels stacked directly on top of each other whenever
the three levels sit close together (SPY especially) -- every label used the same fixed
(0,-20) offset regardless of spacing. These tests lock in the staggered-offset fix.

Phone-first rebuild (UX review 2026-10-16, items #25-#36): native width ~800px instead of 1440,
values on bars, per-symbol Market Map panels, price levels marked, headline titles, human footers.
"""
import re
import struct

import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from backend.report_charts import chart_png


def _evidence(spy_walls):
    return {
        "generated_at": "2026-10-13T19:00:00+00:00",
        "surface": {
            "SPY": {"expected_move_low": 771.49, "expected_move_high": 784.05, "spot": 777.77,
                    "source_timestamp": "2026-10-13T18:58:47+00:00"},
        },
        "profiles": {"SPY": {"val": 775.0, "vah": 779.0, "poc": 777.0,
                              "source_timestamp": "2026-10-13T18:59:59+00:00"}},
        "gamma": {"SPY": spy_walls},
    }


def test_market_map_renders_without_error_when_gamma_walls_are_tightly_clustered():
    close_walls = {"gamma_flip": 777.70, "call_wall": 780.00, "put_wall": 777.00}
    png, plotted = chart_png("market_map", _evidence(close_walls))
    assert plotted
    assert png.startswith(b"\x89PNG")


def test_market_map_gives_each_close_gamma_wall_label_a_distinct_vertical_offset(monkeypatch):
    close_walls = {"gamma_flip": 777.70, "call_wall": 780.00, "put_wall": 777.00}
    offsets = []
    real_annotate = Axes.annotate

    def spy_annotate(self, text, xy, xytext=None, **kwargs):
        if any(label in text for label in ("flip", "call wall", "put wall")):
            offsets.append(xytext)
        return real_annotate(self, text, xy, xytext=xytext, **kwargs)

    monkeypatch.setattr(Axes, "annotate", spy_annotate)
    chart_png("market_map", _evidence(close_walls))
    assert len(offsets) == 3
    assert len(set(offsets)) == 3  # three distinct offsets -- the whole point of the fix


KINDS = ["smile_term", "term_structure", "surface", "flow", "gamma_expiry", "sector_credit", "market_map",
         "baseline_comparison", "paper_equity_drawdown", "event_risk", "volume_profile"]


def png_size(png):
    return struct.unpack(">II", png[16:24])


def _surface_points(spot, expiry):
    pts = []
    for dte in (0, 5, 20):
        for k in range(-6, 7):
            strike = round(spot + k * 2)
            pts.append({"strike": strike, "iv": 0.14 + 0.004 * abs(k) + 0.01 * dte / 20, "dte": dte,
                        "expiration": expiry if dte == 20 else "2026-10-23", "right": "put" if strike <= spot else "call"})
    return pts


def full_evidence():
    ts = "2026-10-16T19:59:01+00:00"
    surface = {}
    for sym, spot, em in (("SPY", 770.0, 6.0), ("QQQ", 620.0, 5.0)):
        surface[sym] = {"symbol": sym, "spot": spot, "expected_move_low": spot - em, "expected_move_high": spot + em,
                        "source_timestamp": ts, "surface_points": _surface_points(spot, "2026-11-06"),
                        "smile": {"expiration": "2026-11-06"},
                        "iv_0dte": .18, "iv_1_5dte": .16, "iv_6_20dte": .15, "iv_21_365dte": .17}
    bucket = {"calls_bought": {"premium": 1_200_000}, "calls_sold": {"premium": 800_000},
              "puts_bought": {"premium": 500_000}, "puts_sold": {"premium": 300_000},
              "unclassified": {"premium": 9_000_000}}
    return {
        "generated_at": "2026-10-16T20:00:00+00:00",
        "surface": surface,
        "profiles": {s: {"val": surface[s]["spot"] - 2, "vah": surface[s]["spot"] + 2, "poc": surface[s]["spot"],
                          "source_timestamp": ts,
                          "bins": [{"price": surface[s]["spot"] + i, "volume": 1000 * (10 - abs(i))} for i in range(-8, 9)]}
                     for s in ("SPY", "QQQ")},
        "gamma": {s: {"gamma_flip": surface[s]["spot"] - 1, "call_wall": surface[s]["spot"] + 4,
                      "put_wall": surface[s]["spot"] - 5, "source_timestamp": ts,
                      "buckets": {"0dte": {"net_gex_b": -1.25}, "1_5dte": {"net_gex_b": 0.8}, "6_20dte": {"net_gex_b": 0.3}}}
                  for s in ("SPY", "QQQ")},
        "flow": {s: {"source_timestamp": ts, "evidence": {"buckets": {"0dte": bucket}}} for s in ("SPY", "QQQ")},
        "cross_asset": {"assets": {"XLK": {"price": 101.0, "prev_close": 100.0, "source_timestamp": ts},
                                    "HYG": {"price": 79.0, "prev_close": 80.0, "source_timestamp": ts}}},
        "comparison": {"SPY": {"price_change_pct": -1.0}, "QQQ": {"price_change_pct": -2.5},
                       "VIX": {"price_change_pct": 25.0}},
        "prior_comparison": {"SPY": {"price_change_pct": -0.4}, "VIX": {"price_change_pct": 6.0}},
        "paper": {"equity_history": [{"equity": 10.0, "drawdown": 0.0}, {"equity": 25.5, "drawdown": 0.0},
                                      {"equity": 12.0, "drawdown": -13.5}]},
        "events": [{"name": "FOMC minutes", "datetime": "2026-10-21T18:00", "impact": "HIGH", "verified": True}],
    }


def _capture(monkeypatch, kind, evidence):
    """Render a chart and return (all drawn strings, axes, figure legends)."""
    seen = {}
    real_savefig = Figure.savefig

    def spy_savefig(self, *a, **k):
        self.canvas.draw()
        seen["text"] = "\n".join(t.get_text() for t in self.findobj(lambda o: hasattr(o, "get_text")))
        seen["axes"] = list(self.axes)
        seen["legends"] = list(self.legends)
        seen["ax_legends"] = [ax.get_legend() for ax in self.axes if ax.get_legend()]
        return real_savefig(self, *a, **k)

    monkeypatch.setattr(Figure, "savefig", spy_savefig)
    chart_png(kind, evidence)
    return seen


@pytest.mark.parametrize("kind", KINDS)
def test_every_chart_is_phone_width_and_plots_with_full_evidence(kind):
    png, plotted = chart_png(kind, full_evidence())
    width, height = png_size(png)
    assert plotted
    assert 760 <= width <= 820  # was 1440; phones display ~320px so text must be drawn near display size
    assert height > width * .5


@pytest.mark.parametrize("kind", KINDS)
def test_every_chart_degrades_to_the_empty_state_without_raising(kind):
    png, plotted = chart_png(kind, {})
    assert not plotted and png.startswith(b"\x89PNG")
    assert 760 <= png_size(png)[0] <= 820


def test_market_map_gives_each_symbol_its_own_panel_and_x_range(monkeypatch):
    axes = _capture(monkeypatch, "market_map", full_evidence())["axes"]
    assert len(axes) == 2
    (a_lo, a_hi), (b_lo, b_hi) = axes[0].get_xlim(), axes[1].get_xlim()
    assert a_lo > b_hi or b_lo > a_hi  # SPY ~770 and QQQ ~620 no longer share one squeezed range


def test_market_map_legend_is_outside_the_plot_area(monkeypatch):
    seen = _capture(monkeypatch, "market_map", full_evidence())
    assert len(seen["legends"]) == 1 and not seen["ax_legends"]  # figure-level legend, none inside an axes


def test_gamma_chart_has_values_sign_legend_net_gex_label_and_unrotated_ticks(monkeypatch):
    seen = _capture(monkeypatch, "gamma_expiry", full_evidence())
    assert "-1.25" in seen["text"] and "+0.80" in seen["text"]
    assert "net GEX ($B)" in seen["text"] and "billions" not in seen["text"]
    assert "Negative net gamma" in seen["text"] and "Positive net gamma" in seen["text"]
    assert all(t.get_rotation() == 0 for t in seen["axes"][0].get_xticklabels())


@pytest.mark.parametrize("kind", ["gamma_expiry", "flow", "volume_profile", "surface", "smile_term"])
def test_charts_mark_spot_and_walls_from_evidence(monkeypatch, kind):
    text = _capture(monkeypatch, kind, full_evidence())["text"]
    for label in ("flip 769.00", "call wall 774.00", "put wall 765.00"):
        assert label in text, (kind, label)


def test_flow_uses_plain_money_and_does_not_chart_unclassified(monkeypatch):
    text = _capture(monkeypatch, "flow", full_evidence())["text"]
    assert "$1.2M" in text and "1e6" not in text
    assert "SPY unclassified" not in text
    assert "Unclassified flow ($18.0M) not shown" in text


def test_sector_credit_bars_carry_values(monkeypatch):
    text = _capture(monkeypatch, "sector_credit", full_evidence())["text"]
    assert "+1.00%" in text and "-1.25%" in text


def test_baseline_gives_vix_its_own_axis_so_equity_moves_are_readable(monkeypatch):
    axes = _capture(monkeypatch, "baseline_comparison", full_evidence())["axes"]
    assert len(axes) == 2
    assert max(abs(v) for v in axes[0].get_ylim()) < 10  # VIX +25% no longer sets the equity scale
    assert max(abs(v) for v in axes[1].get_ylim()) > 25


def test_surface_is_2d_with_iv_axis_clamped_to_data(monkeypatch):
    ev = full_evidence()
    ax = _capture(monkeypatch, "surface", ev)["axes"][0]
    assert not hasattr(ax, "get_zlim")
    ivs = [p["iv"] * 100 for p in ev["surface"]["SPY"]["surface_points"]]
    lo, hi = ax.get_ylim()
    assert min(ivs) - 2 <= lo <= min(ivs) and max(ivs) <= hi <= max(ivs) + 2


def test_footer_and_smile_labels_are_human_not_machine_tags(monkeypatch):
    text = _capture(monkeypatch, "smile_term", full_evidence())["text"]
    assert "LIVE NOW" not in text and "LAST KNOWN" not in text
    assert "SPY puts" in text and "SPY live" in text
    assert re.search(r"\d{2}:\d{2}:\d{2} CT", text) is None


def test_absent_fields_are_omitted_never_replaced_with_placeholders(monkeypatch):
    ev = full_evidence()
    ev["gamma"]["SPY"].pop("call_wall")
    ev["gamma"].pop("QQQ")
    text = _capture(monkeypatch, "gamma_expiry", ev)["text"]
    assert "call wall" not in text and "QQQ" not in text
    ev2 = full_evidence()
    ev2["surface"]["SPY"].pop("spot")
    text2 = _capture(monkeypatch, "market_map", ev2)["text"]
    assert "SPY  spot" not in text2 and "QQQ  spot 620.00" in text2
