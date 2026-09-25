"""Discord relay for the TTP FLEX signal-only bot.

Polls the existing TTP bot /signals endpoint and posts each new signal
to a Discord webhook as a pink card. It never places or routes orders.
"""
import asyncio
import os
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI

SOURCE = os.getenv("TTP_SIGNAL_SOURCE", "https://ttp-flex-bot-v1.onrender.com/signals").strip()
WEBHOOK = os.getenv("TTP_DISCORD_WEBHOOK_URL", "").strip()
POLL = max(15, int(os.getenv("TTP_DISCORD_POLL_SECONDS", "30")))
MAX_SIGNAL_AGE_SECONDS = max(60, int(os.getenv("TTP_DISCORD_MAX_SIGNAL_AGE_SECONDS", "300")))
PINK = 0xFF4FA3
SMOKE_ON_START = os.getenv("TTP_DISCORD_SMOKE_ON_START", "").strip().lower() in {"1","true","yes","on"}
SAMPLE_ALERTS_ON_START = os.getenv("TTP_DISCORD_SAMPLE_ALERTS_ON_START", "").strip().lower() in {"1","true","yes","on"}

seen = set()
app = FastAPI(title="TTP Discord Relay")
task = None

def signal_key(s):
    return f"{s.get('symbol')}:{s.get('engine')}:{s.get('bar_time')}"

async def post_signal(client, s):
    key = signal_key(s)
    if key in seen:
        return
    try:
        bar_time = datetime.fromisoformat(str(s["bar_time"]))
        if bar_time.tzinfo is None:
            return
        age = (datetime.now(timezone.utc) - bar_time.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= MAX_SIGNAL_AGE_SECONDS:
            return
    except (KeyError, TypeError, ValueError):
        return
    shares = int(s.get("shares") or 0)
    symbol = str(s.get("symbol") or "").upper()
    entry = float(s.get("entry") or 0)
    stop = float(s.get("stop") or 0)
    t1 = float(s.get("target1") or 0)
    t2 = float(s.get("target2") or 0)
    risk = float(s.get("risk_dollars") or 0)
    value = float(s.get("position_value") or 0)
    engine = str(s.get("engine") or "SETUP")
    quality = s.get("quality")
    protection = s.get("profit_protection") or {}
    hard_target = float(protection.get("hard_target") or t2)
    force_flat = protection.get("force_flat_by_et") or "15:45"
    embed = {
        "title": f"🌸 TTP FLEX TRADE ALERT — {symbol}",
        "description": "Day-trade only. Place manually in Trader Evolution using a bracket/OCO order.",
        "color": PINK,
        "fields": [
            {"name": "SETUP", "value": f"{engine} • Quality {quality if quality is not None else 'n/a'}/10", "inline": False},
            {"name": "BUY", "value": f"{shares} shares @ ${entry:.2f} LIMIT", "inline": False},
            {"name": "SET THIS OCO EXIT", "value": f"🛑 STOP LOSS: ${stop:.2f}\n🎯 TAKE PROFIT: ${hard_target:.2f}", "inline": False},
            {"name": "PROTECT THE WINNER", "value": f"At +1R (${t1:.2f}), move the stop to at least breakeven. Do not let a winner turn into a loser.", "inline": False},
            {"name": "RISK", "value": f"About ${risk:.2f}\nPosition size: ${value:,.2f}", "inline": True},
            {"name": "DAY-TRADE RULE", "value": f"Close any remaining position by {force_flat} ET.", "inline": True},
        ],
        "footer": {"text": "Trade The Pool FLEX25 • AlphaGEX profit-protection alerts"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r = await client.post(WEBHOOK, json={"username": "TTP FLEX Bot", "embeds": [embed]}, timeout=15)
    r.raise_for_status()
    seen.add(key)

async def send_sample_alerts(client):
    now = datetime.now(timezone.utc).isoformat()
    samples = [
        {"symbol":"AMD","engine":"VWAP_RECLAIM","quality":8.4,"shares":44,"entry":162.40,"stop":161.75,"target1":163.05,"target2":163.38,"risk_dollars":28.60,"position_value":7145.60,"bar_time":now,
         "profit_protection":{"hard_target":163.38,"force_flat_by_et":"15:45"}},
        {"symbol":"NVDA","engine":"HOD_BREAKOUT","quality":8.7,"shares":35,"entry":224.90,"stop":224.10,"target1":225.70,"target2":226.10,"risk_dollars":28.00,"position_value":7871.50,"bar_time":now,
         "profit_protection":{"hard_target":226.10,"force_flat_by_et":"15:45"}},
        {"symbol":"RIVN","engine":"MOMENTUM_RVOL","quality":8.1,"shares":300,"entry":15.60,"stop":15.52,"target1":15.68,"target2":15.72,"risk_dollars":24.00,"position_value":4680.00,"bar_time":now,
         "profit_protection":{"hard_target":15.72,"force_flat_by_et":"15:45"}},
    ]
    for s in samples:
        await post_signal(client, s)

async def send_smoke_test(client):
    embed = {
        "title": "🌸 TTP FLEX SMOKE TEST — PASS",
        "description": "Discord alert path is live. No trade was placed.",
        "color": PINK,
        "fields": [
            {"name": "CHECK", "value": "Render → Discord webhook", "inline": True},
            {"name": "STATUS", "value": "LIVE", "inline": True},
            {"name": "NOTE", "value": "Real alerts will include BUY / STOP / TAKE PROFIT.", "inline": False},
        ],
        "footer": {"text": "Trade The Pool FLEX25 • smoke test only"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r = await client.post(WEBHOOK, json={"username": "TTP FLEX Bot", "embeds": [embed]}, timeout=15)
    r.raise_for_status()

async def loop():
    if not WEBHOOK:
        raise RuntimeError("TTP_DISCORD_WEBHOOK_URL is required")
    async with httpx.AsyncClient() as client:
        if SMOKE_ON_START:
            await send_smoke_test(client)
        if SAMPLE_ALERTS_ON_START:
            await send_sample_alerts(client)
        # A Render restart must not repost the scanner's recent signal history.
        # Wait for a successful snapshot before sending anything from this process.
        while True:
            try:
                r = await client.get(SOURCE, timeout=15)
                r.raise_for_status()
                seen.update(signal_key(s) for s in (r.json().get("signals") or []) if isinstance(s, dict))
                break
            except Exception as exc:
                print(f"[ttp-discord] bootstrap {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(POLL)
        while True:
            try:
                r = await client.get(SOURCE, timeout=15)
                r.raise_for_status()
                payload = r.json()
                sigs = payload.get("signals") or []
                latest = sigs[0] if sigs and isinstance(sigs[0], dict) else None
                print(f"[ttp-discord] poll count={len(sigs)} latest={latest}", flush=True)
                for s in reversed(sigs):
                    if isinstance(s, dict):
                        await post_signal(client, s)
            except Exception as exc:
                print(f"[ttp-discord] {type(exc).__name__}: {exc}", flush=True)
            await asyncio.sleep(POLL)

@app.on_event("startup")
async def startup():
    global task
    task = asyncio.create_task(loop())

@app.on_event("shutdown")
async def shutdown():
    global task
    if task:
        task.cancel()
        task = None

@app.get("/health")
async def health():
    return {"status": "ok", "source": SOURCE, "webhook_configured": bool(WEBHOOK), "seen": len(seen)}
