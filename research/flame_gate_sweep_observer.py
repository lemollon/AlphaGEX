import concurrent.futures,datetime,gzip,json,pathlib,subprocess,time,urllib.request
BASE='https://spark-flame-current-3y-20260928.onrender.com'
ROOT=pathlib.Path(__file__).resolve().parent;OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
TOKEN=pathlib.Path('/workspace/scratch/e7a31f7e798f/sf3y_research_access_token.secret')
def get(route):
 req=urllib.request.Request(BASE+route,headers={'Authorization':'Bearer '+TOKEN.read_text().strip()})
 with urllib.request.urlopen(req,timeout=60) as response:return response.read()
def day(date):
 for attempt in range(5):
  try:return get('/day?date='+date)
  except Exception:
   if attempt==4:raise
   time.sleep(2**attempt)
while True:
 try:
  s=json.loads(get('/status'));print(json.dumps({'observed':datetime.datetime.now(datetime.timezone.utc).isoformat(),**s}),flush=True)
  if s.get('scenarios')!=253:time.sleep(20);continue
  (OUT/'status.json').write_text(json.dumps(s))
  if s['stage']=='blocked':print('BLOCKED '+json.dumps(s),flush=True);time.sleep(45);continue
  if s['stage']=='completed_with_coverage_limits':
   r=json.loads(get('/report'));assert r['status']['completed']==751 and r['status']['baselineParity'];(OUT/'report.json').write_text(json.dumps(r))
   dates=json.loads(subprocess.check_output(['node','-e',"console.log(JSON.stringify(require('./AlphaGEX/research/spark_flame_current_3y_20260928.cjs').sessions()))"],cwd=ROOT.parent,text=True))
   (OUT/'sessions.json').write_text(json.dumps(dates));tmp=OUT/'days.jsonl.gz.tmp'
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool,gzip.open(tmp,'wb') as f:
    for raw in pool.map(day,dates):f.write(raw+b'\n')
   tmp.replace(OUT/'days.jsonl.gz')
   subprocess.run(['python3',str(ROOT/'audit_and_build.py')],check=True)
   print('VALIDATED_FINAL_EXPORTS',flush=True);break
 except Exception as e:print(json.dumps({'observerError':type(e).__name__,'message':str(e)[:200]}),flush=True)
 time.sleep(45)
