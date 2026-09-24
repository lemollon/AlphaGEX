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
PINK = 0xFF4FA3
SMOKE_ON_START = os.getenv("TTP_DISCORD_SMOKE_ON_START", "").strip().lower() in {"1","true","yes","on"}

seen = set()
app = FastAPI(title="TTP Discord Relay")
task = None

async def post_signal(client, s):
    key = f"{s.get('symbol')}:{s.get('bar_time')}"
    if key in seen:
        return
    seen.add(key)
    shares = int(s.get("shares") or 0)
    symbol = str(s.get("symbol") or "").upper()
    entry = float(s.get("entry") or 0)
    stop = float(s.get("stop") or 0)
    t1 = float(s.get("target1") or 0)
    t2 = float(s.get("target2") or 0)
    risk = float(s.get("risk_dollars") or 0)
    value = float(s.get("position_value") or 0)
    rank = s.get("tv_rank")
    score = s.get("tv_score")
    bias = s.get("tv_bias") or "bullish"
    embed = {
        "title": f"🌸 TTP FLEX TRADE ALERT — {symbol}",
        "description": "Signal-only. Place manually in Trader Evolution using a bracket/OCO order.",
        "color": PINK,
        "fields": [
            {"name": "ENTRY LIMIT", "value": f"BUY {shares} {symbol} @ ${entry:.2f} LIMIT", "inline": False},
            {"name": "ATTACHED OCO EXIT", "value": f"🛑 STOP SELL {shares} @ ${stop:.2f}\n🎯 TAKE PROFIT SELL {shares} @ ${t2:.2f}", "inline": False},
            {"name": "RISK", "value": f"Approx risk: ${risk:.2f}\nPosition value: ${value:,.2f}", "inline": True},
            {"name": "TV CONTEXT", "value": f"Rank: {rank if rank is not None else 'n/a'}\nScore: {score if score is not None else 'n/a'}\nBias: {bias}", "inline": True},
            {"name": "REFERENCE", "value": f"+1R: ${t1:.2f}\n+2R: ${t2:.2f}", "inline": True},
        ],
        "footer": {"text": "Trade The Pool FLEX25 • AlphaGEX signal engine"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r = await client.post(WEBHOOK, json={"username": "TTP FLEX Bot", "embeds": [embed]}, timeout=15)
    r.raise_for_status()

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
        while True:
            try:
                r = await client.get(SOURCE, timeout=15)
                r.raise_for_status()
                payload = r.json()
                for s in reversed(payload.get("signals") or []):
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
