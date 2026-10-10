from datetime import datetime,timedelta,timezone
import pytest
from freezegun import freeze_time
from backend import report_refresh as refresh, market_structure as ms, report_policy as policy
UTC=timezone.utc
NOW=datetime(2026,10,5,16,tzinfo=UTC)

@pytest.mark.asyncio
async def test_bounded_retry_records_actual_failure_and_stops():
    calls=[]
    def fail():calls.append(1);raise ConnectionError('provider failed')
    value,audit=await refresh.bounded_refresh('surface_SPY',fail,timeout=.1)
    assert value is None and len(calls)==2
    assert len(audit['attempts'])==2 and audit['outcome']=='last_known_or_unavailable'
    assert all(row['reason']=='ConnectionError' for row in audit['attempts'])

@pytest.mark.asyncio
@freeze_time(NOW)
async def test_failed_refresh_keeps_original_last_known_clock(monkeypatch):
    stamp=(NOW-timedelta(minutes=15)).isoformat()
    old={'confidence':'MEDIUM','source':'Tradier observed options','source_timestamp':stamp,'atm_iv':.2}
    core={'surface':{'SPY':dict(old),'QQQ':dict(old)},'gamma':{},'cross_asset':{},'volatility':{}}
    def failure(*a,**k):return {'reason':'provider unavailable'}
    for name in ('build_volatility_surface','build_gamma_snapshot','fetch_vol_indices','fetch_cross_asset','fetch_trade_quote_flow'):
        monkeypatch.setattr(ms,name,failure)
    result,audit=await refresh.refresh_core(core)
    assert result['surface']['SPY']['source_timestamp']==stamp
    assert result['surface']['SPY']['atm_iv']==.2
    assert len(audit)==8 and all(len(a['attempts'])==2 for a in audit)
    item=policy.normalize_item(dict(value=.2,status='live',source='Tradier',confidence='MEDIUM',source_timestamp=stamp),NOW)
    assert item['status']=='historical' and item['age_seconds']==900
    assert 'LAST KNOWN' in policy.display(item) and 'updated 2026-10-05' in policy.display(item)

@pytest.mark.asyncio
@freeze_time(NOW)
async def test_partial_surface_refresh_preserves_metric_clock(monkeypatch):
    stamp=(NOW-timedelta(hours=1)).isoformat()
    old={'confidence':'MEDIUM','source':'Tradier observed IV','source_timestamp':stamp,'atm_iv':.2,'realized_vol_60m':.1,'realized_vol_source_timestamp':stamp,'surface_read':{'available':True,'day_meaning':'prior observed comparison'}}
    core={'surface':{'SPY':old,'QQQ':old},'gamma':{},'cross_asset':{},'volatility':{}}
    def surface(*a,**k):return {'source':'Tradier BBO','confidence':'MEDIUM','source_timestamp':NOW.isoformat(),'atm_iv':.25,'realized_vol_60m':None,'surface_read':{'available':False}}
    monkeypatch.setattr(ms,'build_volatility_surface',surface)
    monkeypatch.setattr(ms,'persist_surface',lambda row:None)
    for name in ('build_gamma_snapshot','fetch_vol_indices','fetch_cross_asset','fetch_trade_quote_flow'):monkeypatch.setattr(ms,name,lambda *a,**k:{'reason':'no evidence'})
    result,_=await refresh.refresh_core(core)
    row=result['surface']['SPY']
    assert row['atm_iv']==.25 and row['realized_vol_60m']==.1
    assert row['field_timestamps']['realized_vol_60m']==stamp
    assert row['source_timestamp']==NOW.isoformat()
    from backend.full_options_report import merge_symbols
    assert merge_symbols({'SPY':row},['atm_iv'],NOW)['status']=='live'
    assert merge_symbols({'SPY':row},['realized_vol_60m'],NOW)['status']=='historical'

def test_session_horizons_are_close_to_close_and_not_calendar_days():
    assert set(policy.HOLDING_PERIODS)=={10,20}
    days=policy.business_dates(NOW.date(),21)
    assert (days[10]-days[0]).days>=14 and (days[20]-days[0]).days>=28


@pytest.mark.parametrize('loader',[ms._latest_surface,ms._latest_gamma,ms._latest_trade_quote_flow])
def test_persisted_utc_clocks_regain_timezone_without_becoming_fresh(monkeypatch,loader):
    # Writers explicitly store UTC in PostgreSQL timestamp-without-time-zone columns.
    stamp=(NOW-timedelta(hours=12)).replace(tzinfo=None)
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):
            columns=str(sql).split('SELECT ',1)[1].split('FROM ',1)[0].split(',')
            data={'captured_at':stamp,'source_timestamp':stamp,'realized_vol_source_timestamp':stamp,
                  'realized_vol_bar_timestamp':stamp,'source':'Tradier BBO','confidence':'MEDIUM',
                  'atm_iv':.2,'net_gex_b':1.,'n_rows':100,'n_trades':5}
            self.values=tuple(data.get(c.strip(),'{}' if c.strip().endswith('_json') else None) for c in columns)
            return self
        def fetchone(self):return self.values
    class Engine:
        def begin(self):return Connection()
    monkeypatch.setattr(ms,'engine',Engine())
    monkeypatch.setattr(ms,'ensure_tables',lambda:None)
    row=loader('SPY',verified_only=True)
    assert row['source_timestamp']==(NOW-timedelta(hours=12)).isoformat()
    assert refresh.verified(row)
    item=policy.observed(.2,'Tradier',row['source_timestamp'],NOW)
    assert item['status']=='historical' and item['age_seconds']==12*3600
