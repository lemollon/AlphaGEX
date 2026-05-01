# GOLIATH Runbook

Operational reference for running, monitoring, and recovering GOLIATH (LETF earnings-week put-credit-spread + long-call bot).

**Last updated:** 2026-05-01 (Phase 8 — initial runbook)
**Current state:** v0.2 paper-only. All 5 LETF instances (`GOLIATH-MSTU`, `GOLIATH-TSLL`, `GOLIATH-NVDL`, `GOLIATH-CONL`, `GOLIATH-AMDL`) configured with `paper_only=True` per master spec section 1.6.

---

## 1. Environment

### Required env vars
| Var | Purpose | Where |
|---|---|---|
| `TRADING_VOLATILITY_API_TOKEN` | TV v2 Bearer token (`sub_xxx`) | Render service env |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook for alerts (same one used by spreadworks/flame) | Render service env |
| `DATABASE_URL` | Postgres connection string | Render service env (auto from `alphagex-db` blueprint) |

### Required Python deps
All declared in `requirements.txt` (workers) and `requirements-render.txt` (alphagex-api):
- `pandas>=2.0.0`, `numpy>=1.24.0`, `pyarrow>=14.0.0` (calibration cache)
- `yfinance>=0.2.52`, `requests>=2.32.5`
- `psycopg2-binary>=2.9.9`
- `pyyaml>=6.0.1`

### Render service
GOLIATH currently runs as a worker (per Q4 — service name TBD; see master spec §10.4). The runbook below assumes the service has shell access and uses `/opt/render/project/src` as the working dir.

---

## 2. Cold start (fresh deploy)

```bash
# 1. Confirm latest code deployed
cd /opt/render/project/src
git log --oneline -3

# 2. Confirm env vars set
python -c "import os; print('TOKEN:', bool(os.environ.get('TRADING_VOLATILITY_API_TOKEN')))"
python -c "import os; print('DISCORD:', bool(os.environ.get('DISCORD_WEBHOOK_URL')))"

# 3. Confirm deps
python -c "import pyarrow, yfinance, pandas, requests, psycopg2; print('deps ok')"

# 4. Apply migrations 028-031 + 007 if not already
psql $DATABASE_URL -f db/migrations/028_goliath_gate_failures.sql
psql $DATABASE_URL -f db/migrations/029_goliath_news_flags.sql
psql $DATABASE_URL -f db/migrations/030_goliath_kill_state.sql
psql $DATABASE_URL -f db/migrations/031_goliath_trade_audit.sql
# 007_bot_heartbeats.sql is shared; may already exist from other bots

# 5. Smoke-check the runner with dry-run
python -m trading.goliath.main --cycle entry --dry-run

# 6. Send a test Discord message to confirm webhook
python -c "
from trading.goliath.monitoring import discord
print('OK' if discord.post_embed('GOLIATH cold start', 'Test alert from runbook') else 'FAIL')
"
```

Expected: dry-run reports `evaluated=5` (all 5 instances seen). Discord shows the test message.

---

## 3. Restart after a crash

Render auto-restarts crashed workers per `render.yaml` `gracePeriodSeconds`. The bot is **stateless across restarts**:
- Open positions persist in the broker (Tradier) and the audit log
- Kill state persists in `goliath_kill_state` (active=TRUE rows survive restarts)
- News flags persist in `goliath_news_flags`

After a crash, the new process picks up wherever it left off. **No manual recovery needed in v0.2.**

---

## 4. Viewing current state

### Open positions
```sql
-- Per-instance audit chain for any open position
SELECT instance, position_id, event_type, timestamp, data->>'decision' as decision
FROM goliath_trade_audit
WHERE position_id = '<position-uuid>'
ORDER BY timestamp ASC;

-- All instances' most recent activity
SELECT instance, event_type, MAX(timestamp) as last_event
FROM goliath_trade_audit
GROUP BY instance, event_type
ORDER BY instance, event_type;
```

### Bot health (heartbeat)
```sql
SELECT bot_name, last_heartbeat, status, scan_count, trades_today
FROM bot_heartbeats
WHERE bot_name LIKE 'GOLIATH-%'
ORDER BY bot_name;
```

Heartbeat older than 5 min on any instance → check Render service status + worker logs.

### Today's gate failures
```sql
SELECT failed_gate, COUNT(*) as fails, ARRAY_AGG(DISTINCT letf_ticker) as tickers
FROM goliath_gate_failures
WHERE timestamp > NOW() - INTERVAL '1 day'
GROUP BY failed_gate
ORDER BY fails DESC;
```

---

## 5. Kill switches

### Manually kill an instance
```bash
# Set kill state directly via psql (no CLI for this in v0.2; use SQL)
psql $DATABASE_URL -c "
INSERT INTO goliath_kill_state (scope, instance_name, trigger_id, reason, context)
VALUES ('INSTANCE', 'GOLIATH-MSTU', 'MANUAL', 'manual kill via runbook', '{\"by\": \"<your-name>\"}'::jsonb);
"
```

### Manually kill the entire platform
```bash
psql $DATABASE_URL -c "
INSERT INTO goliath_kill_state (scope, instance_name, trigger_id, reason, context)
VALUES ('PLATFORM', NULL, 'MANUAL', 'manual platform kill via runbook', '{\"by\": \"<your-name>\"}'::jsonb);
"
```

### Clear an active kill (manual override — paranoia gate)
```bash
python -m trading.goliath.kill_switch.cli override-kill \
    --scope INSTANCE --instance GOLIATH-MSTU \
    --by leron --confirm-leron-override

# OR for platform kill:
python -m trading.goliath.kill_switch.cli override-kill \
    --scope PLATFORM \
    --by leron --confirm-leron-override
```

The `--confirm-leron-override` flag is **required**. Without it the CLI returns rc=2 REFUSED.

### List all active kills
```bash
python -m trading.goliath.kill_switch.cli list-kills
```

### Auto-kill triggers (defined in master spec §6)
| ID | Scope | Condition |
|---|---|---|
| I-K1 | instance | drawdown > 30% of allocation |
| I-K2 | instance | 5 consecutive losses |
| I-K3 | instance | 20 trades without ≥+$50 win |
| P-K1 | platform | platform drawdown > 15% |
| P-K2 | platform | single-trade loss > 1.5× defined max |
| P-K3 | platform | VIX > 35 sustained 3+ days |
| P-K4 | platform | TV API down > 24h |

When any auto-kill fires, Discord posts a purple `KILL` embed. Manual override is the only way to clear.

---

## 6. Material news flag (Trigger T6)

Per Leron Q5 decision (2026-04-29): material news is a **manual CLI flag** on the underlying ticker.

### Set a flag (closes all GOLIATH positions on that underlying immediately)
```bash
python -m trading.goliath.management.cli flag-news TSLA --reason "FDA news"
```

### Clear a flag
```bash
python -m trading.goliath.management.cli unflag-news TSLA
```

### List active flags
```bash
python -m trading.goliath.management.cli list-flags
```

---

## 7. TV API token rotation

When TV regenerates your token (security event or scheduled rotation):

1. Log into TV billing page → copy new `sub_xxx` Bearer token
2. **Render dashboard** → service env vars → set `TRADING_VOLATILITY_API_TOKEN` to new value
3. Save → Render auto-redeploys (~2-3 min)
4. After deploy is "Live", verify in shell:
   ```bash
   python -c "
   import os
   from core_classes_and_engines import TradingVolatilityAPI
   client = TradingVolatilityAPI()
   result = client.get_net_gamma('SPY')
   print('OK' if 'error' not in result else f'FAIL: {result}')
   "
   ```
5. If verification fails: token wasn't saved correctly OR wrong service. Repeat steps 1-4.

---

## 8. Universe management

### Add a new LETF instance to the universe
1. Edit `trading/goliath/configs/instances.py` — add a `GOLIATH-XYZ` entry
2. Set `paper_only=True` (live-trading unlock is V3-5)
3. PR + merge
4. After deploy: run `python -m trading.goliath.main --cycle entry --dry-run` to confirm new instance appears

### Remove an LETF from the universe
1. First, kill the instance to stop new entries:
   ```bash
   psql $DATABASE_URL -c "INSERT INTO goliath_kill_state (scope, instance_name, trigger_id, reason) VALUES ('INSTANCE', 'GOLIATH-XYZ', 'UNIVERSE_REMOVAL', 'removing from universe');"
   ```
2. Wait for any open positions to close naturally (Thursday 3pm cutoff per T7) OR manually close via broker
3. Edit `trading/goliath/configs/instances.py` — remove the entry
4. PR + merge

---

## 9. Alert response

Discord alerts include a severity prefix (`WARN` / `PAGE`). Response procedures:

### Heartbeat stale (`WARN`)
- Check Render dashboard: is the service "Live"? If not, view recent logs.
- Check bot_heartbeats SQL query (§4) — was there a recent successful heartbeat from another instance, or is the whole bot down?
- If process is stuck: redeploy the service.

### TV API failure rate exceeded (`WARN`)
- Likely cause: token expired/rotated, TV outage, or temporary network issue.
- Check `TRADING_VOLATILITY_API_TOKEN` is valid (§7 verification step).
- Check TV's status page (no public endpoint; subscribe to their Twitter/email).
- If sustained > 24h: P-K4 platform kill auto-fires.

### yfinance failure rate exceeded (`WARN`)
- Yahoo throttling. Backoff already in place (5s/15s/45s retries + 2s inter-ticker delay) per PR #2251.
- If sustained: V03-DATA-1 strike snapshot collector (when built) and v0.3-todos V3-2 (NASDAQ earnings fallback) are the long-term fixes.

### Kill switch fired (`KILL`, purple)
- Read the alert body for trigger_id and reason.
- Check `goliath_kill_state` for the active row (timestamp, context).
- Per master spec §6: auto-recovery is NOT allowed. Manual override required (§5).
- Review the trigger condition and decide whether the kill was correct before clearing.

### Entry filled (informational, green `OPEN`)
- No action needed unless economics look wrong (compare strikes vs. expected vol regime).
- Cross-reference `goliath_trade_audit` `ENTRY_EVAL` event for the gate chain that approved the trade.

### Exit filled (informational, green `WIN` or red `LOSS`)
- No action needed if `trigger_id` is T1-T8 (mechanical close per spec §4).
- Investigate if `realized_pnl` is unexpectedly large (positive or negative) — may indicate slippage, broker issue, or catalyst-week amplification (see V03-DRAG-AUTOCORR for context).

---

## 10. Phase 9 paper trading specifics

### Acceptance criteria (master spec §9.3)
- 2 full weekly cycles minimum (Mon-Fri × 2)
- Bot runs uninterrupted (or interruptions root-caused)
- Every trade decision has audit log
- Every gate evaluation logged
- **Zero successful trades is acceptable IF gate failure logs are diagnostic**
- All alerts reviewed
- No critical bugs surface

### Daily review (paper trading)
```sql
-- Per-day summary across all instances
SELECT
  DATE(timestamp AT TIME ZONE 'America/Chicago') as day,
  instance,
  COUNT(*) FILTER (WHERE event_type = 'ENTRY_EVAL') as evals,
  COUNT(*) FILTER (WHERE event_type = 'ENTRY_FILLED') as fills,
  COUNT(*) FILTER (WHERE event_type = 'EXIT_FILLED') as exits
FROM goliath_trade_audit
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY day, instance
ORDER BY day DESC, instance;
```

### Weekly P&L roll-up
```sql
SELECT
  DATE_TRUNC('week', timestamp) as week,
  instance,
  COUNT(*) as trades,
  SUM((data->>'realized_pnl')::float) as week_pnl
FROM goliath_trade_audit
WHERE event_type = 'EXIT_FILLED'
GROUP BY week, instance
ORDER BY week DESC, instance;
```

### Diagnostic gate failures (Phase 9 acceptance signal)
```sql
SELECT failed_gate, COUNT(*), ARRAY_AGG(DISTINCT letf_ticker)
FROM goliath_gate_failures
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY failed_gate
ORDER BY count DESC;
```

If gate failures concentrate on G05 (IV rank too low) — paper window had non-volatile market; expected.
If on G01/G02 (extreme negative GEX) — risk-off market; expected.
If on G03 (no wall) — calibration issue; investigate per AMD watch (V03-WALL-AMD-WATCH).

---

## 11. Rebuild from a known good state

If the database is corrupted or you need to reset:

1. Take a `pg_dump` of current state (preserve audit history if possible)
2. Stop the GOLIATH worker (Render dashboard → service → "Suspend")
3. Drop and recreate GOLIATH-specific tables:
   ```sql
   DROP TABLE IF EXISTS goliath_trade_audit CASCADE;
   DROP TABLE IF EXISTS goliath_kill_state CASCADE;
   DROP TABLE IF EXISTS goliath_news_flags CASCADE;
   DROP TABLE IF EXISTS goliath_gate_failures CASCADE;
   ```
4. Re-run migrations 028-031
5. Resume the worker
6. Smoke-check with `--dry-run`

**Heartbeats and audit history will be lost.** This is a last-resort recovery.

---

## 12. Open items (v0.3 backlog)

See `docs/goliath/goliath-v0.3-todos.md` for the authoritative list. Key items affecting operational behavior:

- **V03-DATA-1**: Daily strike-snapshot collector (enables V03-WALL-RECAL)
- **V03-WALL-AMD-WATCH**: Watch AMD's elevated 5.93× concentration ratio during paper trading
- **V03-DRAG-AUTOCORR**: Replace theoretical drag formula (current formula assumes Brownian motion; fails in trending regimes)
- **V03-MSTU-FAT-TAIL-WATCH**: Watch MSTU's catalyst-week amplification (Feb / Apr 2026 patterns from calibration)
- **V3-3**: Cross-bot exposure aggregator (required pre-live-trading)
- **V3-5**: Live-trading mode unlock (depends on Phase 9 paper trading + Leron approval)

---

## 13. Escalation

For anything not covered by this runbook:
1. Check `docs/goliath/GOLIATH-MASTER-SPEC.md` (recovered v0.2 spec)
2. Check `docs/goliath/GOLIATH-PHASE-1.5-RECOVERY.md` (calibration phase doc)
3. Check `trading/goliath/CLAUDE.md` (per-bot operating manual)
4. Page Leron via Discord with the alert + relevant SQL output

---

*Living document. Updates land via PR with `docs(goliath)` prefix.*
