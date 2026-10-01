"""Read-only completion observer for the isolated Spark/Flame research run.
It never calls broker, order, or live-strategy endpoints.
"""
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT=pathlib.Path('/workspace/scratch/e7a31f7e798f')
TOKEN=pathlib.Path('/tmp/sf3y_access_token')
if not TOKEN.exists(): TOKEN=ROOT/'sf3y_research_access_token.secret'
BASE='https://spark-flame-current-3y-20260928.onrender.com'
OUT=ROOT/'spark-flame-minute-protection-results'
OUT.mkdir(exist_ok=True)
ENGINE_HASH='24f57aa0de28e9052b896878e1b9b32e6163dd8e2a126f1f3ed2dc8973ca0ceb'

def get(path):
    req=urllib.request.Request(BASE+path,headers={'Authorization':'Bearer '+TOKEN.read_text().strip()})
    with urllib.request.urlopen(req,timeout=60) as response:
        return response.read()

while True:
    try:
        raw=get('/status'); status=json.loads(raw); (OUT/'status.json').write_bytes(raw)
        print(json.dumps({k:status.get(k) for k in ('stage','completed','total','currentDay','error')}),flush=True)
        if status.get('engineHash')!=ENGINE_HASH:
            raise RuntimeError('waiting for corrected numerical engine; obsolete results rejected')
        if status.get('stage')=='completed_with_coverage_limits' and status.get('completed')==751:
            pathlib.Path('/tmp/spark-flame-minute-protection-report.json').write_bytes(get('/report'))
            subprocess.run(['python','/workspace/scratch/e7a31f7e798f/flame-event-risk-audit.py',str(TOKEN)],check=True)
            subprocess.run(['python',str(ROOT/'alphagex-test-run/research/build_spark_flame_minute_report.py'),str(OUT)],check=True)
            break
        if status.get('stage')=='blocked': raise RuntimeError(status.get('error','research blocked'))
    except Exception as exc:
        print(json.dumps({'observer_error':str(exc)}),flush=True)
    time.sleep(45)
