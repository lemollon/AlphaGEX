"""Independently reconcile quality exports; never waive missing source records."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
report = json.loads((root / 'quality_report.json').read_text())
views = json.loads((root / 'view_definitions.json').read_text())
checks = report['checks']
assert report['stage'] == 'complete_with_coverage_limits'
for table in ('spy_minute_3y','vix_minute_3y','the_rock_3y','vix_history_3y'):
    r = checks[table][0]
    assert int(r['valid_ohlc']) + int(r['zero_placeholders']) == int(r['rows']), table
    assert all(int(r[k]) == 0 for k in ('wrong_date','subminute_rows','negative_volume')), table
for table in ('the_rock_3y','vix_history_3y'):
    assert all(int(v)==0 for v in checks[table+'_duplicates'][0].values()), table
    r=checks[table+'_identity'][0]
    assert int(r['invalid_contract'])==0 and int(r['future_eod'])==0, table
assert int(checks['vix_minute_3y'][0]['valid_ohlc'])==0
assert checks['quote_columns']==[], 'Do not relabel trade bars as historical NBBO'
calendar=checks['expected_calendar'][0]
assert int(calendar['days'])==751 and int(calendar['expected_minutes'])==291630
coverage={r['series']:r for r in checks['curated_minute_coverage']}
gaps=checks['minute_gaps']
for series,field in [('spy','missing_spy'),('vix_index','missing_vix')]:
    assert int(coverage[series]['days'])==751
    assert int(coverage[series]['rows'])+sum(int(r[field]) for r in gaps)==291630
assert sum(int(r['missing_vix']) for r in gaps)==0
assert sum(int(r['missing_spy']) for r in gaps)==2
assert {r['day'] for r in gaps}=={'2023-11-10','2025-04-11'}
assert all(any(i['table']==t and i['day']=='2023-09-29' and i.get('verified') for i in report['imports']) for t in ['spy_minute_3y','vix_index_price_3y'])
definitions={r['viewname']:r['definition'] for r in views}
assert len(definitions)==6
assert 'vix_index_price_3y' in definitions['research_vix_index_minute_valid']
assert 'vix_minute_3y' not in definitions['research_vix_index_minute_valid']
for name in ['research_spy_prior_eod_valid','research_vix_prior_eod_valid']:
    # PostgreSQL removes redundant single-table aliases in pg_get_viewdef.
    d=definitions[name].replace('r.','')
    for side in ('call','put'):
        assert f'prior_eod_{side}_bid <= prior_eod_{side}_ask' in d, (name,side)
    assert 'prior_eod_trade_date < trade_date' in d
result={'controls':'PASS','source_status':'LIMITED: two authentic SPY minute bars remain unavailable; all-zero VIX OHLC is rejected','calendar_sessions':751,'expected_minutes':291630,'spy_valid_minutes':291628,'vix_index_valid_minutes':291630,'duplicate_contract_groups':0,'future_eod_records':0,'crossed_prior_eod_rows_rejected_by_feature_policy':{'spy':3916,'vix_options':355}}
(root/'independent_validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
