# tests/backtest/ember/test_policy.py
from backtest.ember.policy import ExitPolicy, default_grid, SPARK_BASELINE


def test_spark_baseline_matches_live_config():
    assert SPARK_BASELINE.profit_target_pct == 30
    assert SPARK_BASELINE.stop_loss_mult == 0.5
    assert SPARK_BASELINE.time_stop_minute is None


def test_default_grid_includes_baseline_and_is_nonempty():
    grid = default_grid()
    assert len(grid) > 10
    assert any(p.name == "spark_live" for p in grid)
    # names are unique
    names = [p.name for p in grid]
    assert len(names) == len(set(names))


def test_policy_is_hashable_frozen():
    p = ExitPolicy(name="x", profit_target_pct=40, stop_loss_mult=1.5, time_stop_minute=None)
    assert {p: 1}[p] == 1   # hashable
