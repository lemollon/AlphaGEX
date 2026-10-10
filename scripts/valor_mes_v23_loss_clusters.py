"""MES v23 loss-cluster forensic analyzer.

Reads completed v22 evidence and cached MES bars. No trading, no vendor calls.
For each v22 engine/year at 4 ticks/side:
- identify consecutive loss streaks >=2
- quantify dollars lost and share of total losses in clusters
- summarize pre-entry conditions for clustered losses vs noncluster trades
- persist compact JSON diagnostics for router design

2026 untouched. Research-only.
"""
from __future__ import annotations
from pathlib import Path
import gzip, hashlib, io, json, math, os, subprocess, sys

STUDY="valor-mes-v23-loss-clusters-20260924"
LOCK=663202609
V22="valor-mes-v22-event-driven-20260924"
YEARS=(2023,2024,2025)
HASHES={
  2023:"2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580",
  2024:"6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040",
  2025:"629f52ce5705e78ca3c8a29920dea6c3790af67af2a3423d889a947e35341c16",
}
ENGINES=("or_breakout_retest","failed_or_breakout","vwap_reclaim","compression_breakout")

def prep(frame):
    from scripts import valor_mes_rebuild_v4 as core
    d=core.prepare(frame)
    b,_=core.context(d)
    by_raw={int(r.raw_index):r for r in b.itertuples(index=False)}
    return d,by_raw

def feature(row, order):
    import numpy as np
    a=float(row.atr) if np.isfinite(row.atr) else None
    width=(float(row.or_high)-float(row.or_low)) if np.isfinite(row.or_high) and np.isfinite(row.or_low) else None
    ref=float(order["reference"]); side=int(order["side"])
    out=dict(
        minute=int(row.minute),
        side=side,
        atr=a,
        or_width=width,
        vwap_distance_atr=(side*(ref-float(row.vwap))/a if a and a>0 and np.isfinite(row.vwap) else None),
        or_location=(((ref-float(row.or_low))/width) if side>0 else
                     ((float(row.or_high)-ref)/width) if width and width>0 else None),
        distance_or_edge_atr=None,
    )
    if a and a>0 and width and width>0:
        edge=float(row.or_high) if side>0 else float(row.or_low)
        out["distance_or_edge_atr"]=side*(ref-edge)/a
    return out

def streaks(ledger):
    groups=[]; cur=[]
    for t in sorted(ledger,key=lambda x:x["entry"]):
        if float(t["net"])<0:
            cur.append(t)
        else:
            if len(cur)>=2: groups.append(cur)
            cur=[]
    if len(cur)>=2:groups.append(cur)
    return groups

def mean(items,key):
    xs=[x[key] for x in items if x.get(key) is not None and math.isfinite(float(x[key]))]
    return round(sum(map(float,xs))/len(xs),6) if xs else None

def summarize_engine(row, by_raw):
    ledger=row["trade_ledger"]
    clusters=streaks(ledger)
    clustered_ids={id(t) for g in clusters for t in g}
    # id() survives because group items are original dict references.
    feats=[]; cfeats=[]; ofeats=[]
    for t in ledger:
        idx=int(t["index"])
        br=by_raw.get(idx)
        if br is None: continue
        f=feature(br,t)
        f.update(net=float(t["net"]),date=t["date"],entry=t["entry"])
        feats.append(f)
        (cfeats if id(t) in clustered_ids else ofeats).append(f)
    losses=[t for t in ledger if float(t["net"])<0]
    cluster_losses=[t for g in clusters for t in g]
    total_loss=-sum(float(t["net"]) for t in losses)
    clustered_loss=-sum(float(t["net"]) for t in cluster_losses)
    def fs(xs):
        return dict(n=len(xs),
          avg_net=round(sum(x["net"] for x in xs)/len(xs),6) if xs else None,
          minute=mean(xs,"minute"),atr=mean(xs,"atr"),or_width=mean(xs,"or_width"),
          vwap_distance_atr=mean(xs,"vwap_distance_atr"),
          or_location=mean(xs,"or_location"),
          distance_or_edge_atr=mean(xs,"distance_or_edge_atr"))
    top=sorted(clusters,key=lambda g:sum(float(t["net"]) for t in g))[:5]
    return dict(
      trades=len(ledger),
      total_net=round(sum(float(t["net"]) for t in ledger),6),
      loss_trades=len(losses),
      cluster_count=len(clusters),
      clustered_loss_trades=len(cluster_losses),
      clustered_loss_dollars=round(clustered_loss,6),
      total_loss_dollars=round(total_loss,6),
      clustered_loss_share=round(clustered_loss/total_loss,6) if total_loss else 0,
      max_loss_streak=max([len(g) for g in clusters],default=0),
      clustered_features=fs(cfeats),
      noncluster_features=fs(ofeats),
      worst_clusters=[dict(
          n=len(g),
          start=g[0]["date"],
          end=g[-1]["date"],
          net=round(sum(float(t["net"]) for t in g),6),
          dates=[t["date"] for t in g]) for g in top],
    )

def run():
    import pandas as pd, psycopg2
    from psycopg2.extras import Json
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=15);conn.autocommit=True
    cur=conn.cursor();cur.execute("SELECT pg_try_advisory_lock(%s)",(LOCK,))
    if not cur.fetchone()[0]:conn.close();return
    sh=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS valor_mes_v23_loss_clusters(
          study_id text,year int,engine text,diagnostics jsonb NOT NULL,
          created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year,engine));
          CREATE TABLE IF NOT EXISTS valor_mes_v23_state(
          study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());""")
        cur.execute("""INSERT INTO valor_mes_v23_state(study_id,status,detail) VALUES(%s,'running',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='running',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(source_sha256=sh,research_only=True,production_changed=False))))
        for y in YEARS:
            cur.execute("SELECT evidence_gzip FROM valor_mes_v22_results WHERE study_id=%s AND year=%s",(V22,y))
            rr=cur.fetchone()
            if not rr: raise ValueError(f"missing v22 evidence {y}")
            rows=json.loads(gzip.decompress(bytes(rr[0])))
            selected={r["candidate"]:r for r in rows if int(r["cost_ticks_each_side"])==4}
            cur.execute("SELECT sha256,parquet_zstd FROM valor_research_bar_cache WHERE cache_key=%s",
                        (f"GLBX.MDP3:ohlcv-1m:MES.v.0:{y}",))
            c=cur.fetchone()
            if not c:raise ValueError("cache missing")
            body=bytes(c[1]);dig=hashlib.sha256(body).hexdigest()
            if dig!=c[0] or dig!=HASHES[y]:raise ValueError("cache mismatch")
            _,by_raw=prep(pd.read_parquet(io.BytesIO(body)))
            for eng in ENGINES:
                diag=summarize_engine(selected[eng],by_raw)
                cur.execute("""INSERT INTO valor_mes_v23_loss_clusters(study_id,year,engine,diagnostics)
                  VALUES(%s,%s,%s,%s) ON CONFLICT(study_id,year,engine)
                  DO UPDATE SET diagnostics=excluded.diagnostics,created_at=now()""",
                  (STUDY,y,eng,Json(diag)))
        cur.execute("""UPDATE valor_mes_v23_state SET status='completed',
          detail=%s,updated_at=now() WHERE study_id=%s""",
          (Json(dict(source_sha256=sh,research_only=True,production_changed=False,
                     years=list(YEARS),engines=list(ENGINES),untouched_next_year=2026)),STUDY))
    except Exception as e:
        cur.execute("""INSERT INTO valor_mes_v23_state(study_id,status,detail) VALUES(%s,'failed',%s)
          ON CONFLICT(study_id) DO UPDATE SET status='failed',detail=excluded.detail,updated_at=now()""",
          (STUDY,Json(dict(error_type=type(e).__name__,message=str(e)[:500],source_sha256=sh))))
        raise
    finally:
        try:cur.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
        finally:conn.close()

def launch_if_enabled():
    flag=os.getenv("VALOR_MES_V23_AUTORUN",os.getenv("VALOR_MES_CHOPGUARD_V10_AUTORUN","false"))
    if flag.lower() not in {"1","true","yes","on"}:return False
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    subprocess.Popen([sys.executable,"-m","scripts.valor_mes_v23_loss_clusters"],
                     env=env,stdin=subprocess.DEVNULL,close_fds=True)
    return True

if __name__=="__main__":run()
