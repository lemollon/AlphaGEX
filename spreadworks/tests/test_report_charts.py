"""market_map chart legibility.

Leron, 2026-10-13: "expected move visuals is hard to read." Live screenshot showed the
gamma flip/call-wall/put-wall price labels stacked directly on top of each other whenever
the three levels sit close together (SPY especially) -- every label used the same fixed
(0,-20) offset regardless of spacing. These tests lock in the staggered-offset fix.
"""
from matplotlib.axes import Axes

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
