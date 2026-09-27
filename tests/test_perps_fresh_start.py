"""scripts/perps_fresh_start.py: archive-not-delete, dry run changes nothing."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_spec = importlib.util.spec_from_file_location(
    "perps_fresh_start", Path(__file__).resolve().parent.parent / "scripts" / "perps_fresh_start.py"
)
fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fs)


def _conn(rows=3):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = lambda: ("x",) if "to_regclass" in cursor.execute.call_args[0][0] else (rows,)
    conn.cursor.return_value = cursor
    return conn, cursor


def _sql(cursor):
    return [c[0][0] for c in cursor.execute.call_args_list]


def test_dry_run_rolls_back_and_writes_nothing():
    conn, cursor = _conn()
    report = fs.fresh_start(conn, ["btc"], "20260927T011500", execute=False)
    assert not any(s.startswith(("CREATE", "DELETE")) for s in _sql(cursor))
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    assert report[0] == "agape_btc_perp_positions: 3 rows -> agape_btc_perp_positions_archive_20260927T011500"


def test_execute_archives_before_delete_in_one_commit():
    conn, cursor = _conn()
    fs.fresh_start(conn, ["eth"], "20260927T011500", execute=True)
    writes = [s for s in _sql(cursor) if s.startswith(("CREATE", "DELETE"))]
    assert writes == [
        "CREATE TABLE agape_eth_perp_positions_archive_20260927T011500 AS SELECT * FROM agape_eth_perp_positions",
        "DELETE FROM agape_eth_perp_positions",
        "CREATE TABLE agape_eth_perp_equity_snapshots_archive_20260927T011500 AS SELECT * FROM agape_eth_perp_equity_snapshots",
        "DELETE FROM agape_eth_perp_equity_snapshots",
    ]
    conn.commit.assert_called_once()


def test_failure_rolls_back_everything():
    conn, cursor = _conn()

    def boom(sql, *args):
        if sql.startswith("DELETE"):
            raise RuntimeError("db down")
    cursor.execute.side_effect = boom
    with pytest.raises(RuntimeError):
        fs.fresh_start(conn, ["btc"], "20260927T011500", execute=True)
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_rejects_unknown_bot_and_bad_tag():
    with pytest.raises(SystemExit):
        fs.main(["FOO"])
    with pytest.raises(SystemExit):
        fs.main(["--restore", "yesterday"])
