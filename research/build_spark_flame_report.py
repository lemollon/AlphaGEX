import json,csv,io,zipfile,pathlib,datetime,sys,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from audit_spark_flame_exports import audit
OUT=pathlib.Path(os.environ.get('SF3Y_EXPORT_DIR', str(pathlib.Path.cwd()/'spark-flame-3y-results')))
def build():
 r=json.loads((OUT/'report.json').read_text());s=r['status'];finished=s['stage']=='completed_with_coverage_limits' and s['completed']==s['total']
 trades=json.loads((OUT/'trades.json').read_text());daily=json.loads((OUT/'daily.json').read_text())
 validation=audit(r,trades,daily)
 (OUT/'validation.json').write_text(json.dumps(validation,indent=2))
 finished=finished and validation['passed']
 title='Spark and Flame — three-year replay' if finished else 'Spark and Flame — incomplete replay'
 lines=['# '+title,'',f"Status: **{s['stage']}**; {s['completed']}/{s['total']} sessions processed.", '',f"Window: {r['spec']['start']} through {r['spec']['end']}. Frozen source: `{r['spec']['sourceCommit']}`.", '', 'Flame starts at $2,000; Spark starts at $5,000. No later deposits.', '', '**Gamma is reconstructed from point-in-time ThetaData inputs.** The same model is used across the study; this does not prove exact agreement with historical Tradier Greeks or broker executions.', '', 'Current customer sizing is the primary profile. Legacy ladders and internal sizing are separate comparisons; they are not stacked together.', '', '| Bot | Profile | Fill | Ending equity | Trading P&L | Return | Trades | FLINT trades | Closed drawdown | Complete path |', '|---|---|---|---:|---:|---:|---:|---:|---:|---|']
 for a in r['summary']:
  lines.append(f"| {a['bot']} | {a['profile']} | {a['fillCase']} | ${a['endingEquity']:,.2f} | ${a['pnl']:,.2f} | {a['returnPct']:.2f}% | {a['trades']} | {a['flintTrades']} | ${a['maxClosedDrawdown']:,.2f} | {'yes' if a['complete'] else 'NO'} |")
 lines+=['',f"Final reconciliation: **{'PASS' if validation['passed'] else 'NOT VALIDATED'}**.", '']
 lines+=['','Trading P&L includes the modeled $1.40 per-spread fee. The $50 monthly subscription is external; see netAfterExternalSubscription in the full report. Adverse fills deduct three cents on entry and buyback. A zero-bid long supplies zero proceeds at close.','', 'Incomplete account paths are diagnostic only: missing payoff data prevents valid compounded performance conclusions.', '', '## Coverage', '']
 for x in r['coverageLimits']:lines.append('- '+x)
 lines+=['- Stock minute OPEN approximates contemporaneous spot; historical broker fills are not verified.', '- Mark gaps limit observed intraday drawdown; see markGapMinutes per path.', f"- Reported gamma records including pre-window warmup: {r['gammaCoverageDays']} (the upsizing gate also requires sufficient prior records).", '', '## Files', '', '- report.json: frozen parameters, summary, monthly/leg/weekday aggregates, worst trades, coverage flags and source hashes.', '- trades.csv: individual simulated trades, quantities and exit reasons.', '- daily.csv: account equity, FLINT/host sizing, floor and intraday marks by session.', '- source_manifest.json: market-data request scopes, retrieval times and SHA-256 hashes.']
 (OUT/'Spark_Flame_Three_Year_Replay.md').write_text('\n'.join(lines)+'\n')
 trades=json.loads((OUT/'trades.json').read_text());tr=[]
 for a in trades:
  for t in a['trades']:tr.append({**{k:a[k] for k in ['bot','profile','fillCase']},**t})
 daily=json.loads((OUT/'daily.json').read_text());days=[]
 for d in daily:
  for a in d['accounts']:days.append({**a,'vixRatio':d['vix']['ratio']})
 for name,rows in [('trades.csv',tr),('daily.csv',days)]:
  if not rows:continue
  keys=list(dict.fromkeys(k for x in rows for k in x))
  with (OUT/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
   for x in rows:w.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in x.items()})
 (OUT/'source_manifest.json').write_text(json.dumps(r['sourceManifest'],indent=2))
 with zipfile.ZipFile(OUT/'Spark_Flame_Three_Year_Replay.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
  for n in ['Spark_Flame_Three_Year_Replay.md','report.json','trades.json','daily.json','status.json','trades.csv','daily.csv','source_manifest.json','validation.json']:
   if (OUT/n).exists():z.write(OUT/n,n)
 print(json.dumps({'built':str(OUT/'Spark_Flame_Three_Year_Replay.zip'),'finished':finished,'sessions':s['completed'],'completePaths':sum(a['complete'] for a in r['summary'])}))
if __name__=='__main__':build()
