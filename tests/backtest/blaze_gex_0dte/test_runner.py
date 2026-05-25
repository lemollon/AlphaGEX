import datetime as dt
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.reconstruct import build_snapshots
from backtest.blaze_gex_0dte.runner import replay_daychain
from trading.helios.models import JoshuaConfig

def test_replay_daychain_runs_without_error_and_returns_list():
    rows = []
    for m in range(0, 6):
        rows += [
            (m, 499.0, "C", 1.6, 1.7), (m, 499.0, "P", 0.5, 0.6),
            (m, 500.0, "C", 1.0, 1.1), (m, 500.0, "P", 1.0, 1.1),
            (m, 501.0, "C", 0.5, 0.6), (m, 501.0, "P", 1.6, 1.7),
        ]
    oi = {(499.0,"C"):100,(499.0,"P"):100,(500.0,"C"):9000,
          (500.0,"P"):9000,(501.0,"C"):100,(501.0,"P"):100}
    day = bars_to_daychain(dt.date(2024,3,15), rows, oi)
    out = replay_daychain(day, JoshuaConfig())
    assert isinstance(out, list)
