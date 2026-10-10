import sys
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_mes_signal_quality as a


def fixture():
    start=a.START
    bars={start+timedelta(minutes=i): (100+i, 102+i, 99+i, 101+i) for i in range(100)}
    def signal(i):
        return dict(scan_time=(start+timedelta(minutes=i, seconds=10)).isoformat(), scan_id=str(i), signal_direction='LONG', signal_source='GEX_MOMENTUM')
    signals={start+timedelta(minutes=i+1): [signal(i)] for i in (0,1,30)}
    return bars,signals


def test_forward_returns_no_exit_bar_extrema_and_nonoverlap():
    bars,signals=fixture()
    rows,counts=a.observations(bars,signals)
    assert counts['nonoverlapping_windows_selected']==2
    assert counts['overlap_excluded']==1
    first=rows[0]
    assert first['forward_points']==1
    assert first['mfe_points']==2
    assert first['mae_points']==1
    assert a.summarize([first],3)['net_mean_2ticks']==-3


def test_missing_bar_rejects_whole_window():
    bars,signals=fixture()
    del bars[a.START+timedelta(minutes=10)]
    rows,counts=a.observations(bars,signals)
    assert counts['closure_or_end_excluded']==2
    assert counts['nonoverlapping_windows_selected']==1


def test_validation_cannot_select_candidate():
    rows=[dict(split='validation',source='GEX_MOMENTUM',session='rth',horizon=15,
               gross_dollars=100,trading_day='2026-09-21',mfe_points=20,mae_points=0)]*50
    _,candidate=a.analyze(rows,3)
    assert candidate is None


def test_purge_split_crossing_window():
    entry=a.SPLIT-timedelta(minutes=15)
    bars={entry+timedelta(minutes=i):(100,101,99,100) for i in range(31)}
    signals={entry:[dict(scan_time=(entry-timedelta(seconds=30)).isoformat(),scan_id='x',signal_direction='LONG',signal_source='GEX_MOMENTUM')]}
    rows,counts=a.observations(bars,signals)
    assert not rows and counts['split_boundary_excluded']==1
