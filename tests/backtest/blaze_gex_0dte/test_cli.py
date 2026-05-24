from backtest.blaze_gex_0dte.cli import parse_args, build_grid

def test_parse_args_defaults():
    ns = parse_args(["--start", "2023-01-03", "--end", "2026-05-22"])
    assert str(ns.start) == "2023-01-03"
    assert str(ns.end) == "2026-05-22"

def test_build_grid_cartesian():
    grid = build_grid(pts=[20, 30], sls=[30, 50])
    assert len(grid) == 4
    assert (20, 30) in [(c.profit_target_pct, c.stop_loss_pct) for c in grid]
