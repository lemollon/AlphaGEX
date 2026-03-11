# IronForge System Wireframe

Complete architecture documentation for the IronForge standalone SPY Iron Condor paper trading system.

---

## 1. Bot Profiles

Three bots share identical code — only `BotConfig` differs.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BOT COMPARISON MATRIX                             │
├──────────────────┬──────────────┬──────────────┬───────────────────────────┤
│                  │    FLAME     │    SPARK     │         INFERNO           │
│                  │    (2DTE)    │    (1DTE)    │         (0DTE)            │
├──────────────────┼──────────────┼──────────────┼───────────────────────────┤
│ DTE              │ 2            │ 1            │ 0                         │
│ Trades/Day       │ 1            │ 1            │ Unlimited (0 = no cap)    │
│ Max Contracts    │ 10           │ 10           │ 0 (sized by buying power) │
│ SD Multiplier    │ 1.2x         │ 1.2x         │ 1.0x (tighter strikes)    │
│ Profit Target    │ 30% sliding  │ 30% sliding  │ 50% sliding               │
│ Stop Loss        │ 100%         │ 100%         │ 200%                      │
│ Entry Window     │ 8:30–2:00 CT │ 8:30–2:00 CT │ 8:30–2:30 CT              │
│ PDT Enforcement  │ 4/5 rolling  │ 4/5 rolling  │ None (pdt_max=0)          │
│ Starting Capital │ $10,000      │ $10,000      │ $10,000                   │
│ VIX Skip         │ > 32         │ > 32         │ > 32                      │
│ Min Credit       │ $0.05        │ $0.05        │ $0.05                     │
│ Spread Width     │ $5           │ $5           │ $5                        │
│ BP Usage         │ 85%          │ 85%          │ 85%                       │
│ Min Win Prob     │ 42%          │ 42%          │ 42%                       │
└──────────────────┴──────────────┴──────────────┴───────────────────────────┘
```

### Sliding Profit Target Schedule

```
┌─────────────────────┬──────────────────┬──────────────────┐
│     Time (CT)       │  FLAME / SPARK   │     INFERNO      │
├─────────────────────┼──────────────────┼──────────────────┤
│ 8:30 – 10:29 AM    │     30%          │     50%          │
│ 10:30 AM – 12:59 PM│     20%          │     30%          │
│ 1:00 – 2:44 PM     │     15%          │     10%          │
│ 2:45 PM+            │   EOD close at any P&L              │
└─────────────────────┴─────────────────────────────────────┘
```

---

## 2. System Architecture

```
                    ┌──────────────────────────┐
                    │    Render Deployment      │
                    └──────────┬───────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Worker: FLAME  │ │  Worker: SPARK  │ │ Worker: INFERNO │
│  run_flame.py   │ │  run_spark.py   │ │ run_inferno.py  │
│  (2DTE, 1/day)  │ │  (1DTE, 1/day)  │ │ (0DTE, ∞/day)  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                    │
         └───────────┬───────┴────────────────────┘
                     │
                     ▼
          ┌──────────────────┐      ┌─────────────────────────┐
          │   Trader class   │─────▶│  Position Monitor        │
          │   (shared code)  │      │  run_position_monitor.py │
          └─────────┬────────┘      │  (15s loop, exits only)  │
                    │               └────────────┬────────────┘
         ┌──────────┼──────────┐                 │
         ▼          ▼          ▼                 │
  ┌───────────┐ ┌────────┐ ┌──────────┐         │
  │  Signal   │ │  Paper │ │   Rule   │         │
  │ Generator │ │Executor│ │ Advisor  │         │
  │signals.py │ │executor│ │advisor.py│         │
  └─────┬─────┘ └───┬────┘ └──────────┘         │
        │            │                            │
        ▼            ▼                            │
  ┌──────────────────────────┐                   │
  │   Tradier Client         │◀──────────────────┘
  │   tradier_client.py      │
  ├──────────────────────────┤
  │ • get_quote("SPY")       │──────▶ Market Data (Sandbox URL)
  │ • get_vix()              │
  │ • get_option_chain()     │
  │ • get_option_quote()     │
  │ • get_option_quotes_batch│──────▶ Batch MTM (Position Monitor)
  │ • place_ic_order()       │──────▶ Sandbox Order Execution
  │ • close_ic_order()       │──────▶ Sandbox Close Execution
  │ • get_order_fill_price() │◀────── Fill Price Readback
  └──────────────────────────┘
        │
        ▼
  ┌──────────────────────────┐      ┌──────────────────────────┐
  │  PostgreSQL (Render)     │◀─────│  Next.js Webapp          │
  │  ironforge-db            │      │  ironforge-dashboard     │
  │  285+ tables (shared)    │      │  /flame /spark /inferno  │
  └──────────────────────────┘      │  /compare                │
                                    └──────────────────────────┘
```

### Alternative: Combined Runner

```
┌──────────────────────────────────┐
│  run_all.py (single process)     │
│                                  │
│  Thread 1: FLAME  ─┐             │
│  Thread 2: SPARK  ─┼── Shared DB │
│  Thread 3: INFERNO ┘             │
│                                  │
│  (For Databricks cost savings)   │
└──────────────────────────────────┘
```

---

## 3. Tradier Integration

IronForge uses Tradier for **all market data AND sandbox execution**. No production orders — paper only.

### Account Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRADIER CONNECTIONS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PRIMARY CLIENT (market data)                                   │
│  ┌─────────────────────────────────────────────┐               │
│  │  API Key:    TRADIER_API_KEY                 │               │
│  │  Base URL:   sandbox.tradier.com/v1          │               │
│  │  Account:    TRADIER_ACCOUNT_ID              │               │
│  │  Used for:   Quotes, VIX, chains, MTM        │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  SANDBOX MIRROR ACCOUNTS (FLAME only)                           │
│  ┌─────────────────────────────────────────────┐               │
│  │  Account 1: "User"                           │               │
│  │    Key:   TRADIER_SANDBOX_KEY_USER            │               │
│  │    AccID: TRADIER_SANDBOX_ACCOUNT_ID_USER     │               │
│  ├─────────────────────────────────────────────┤               │
│  │  Account 2: "Matt"                           │               │
│  │    Key:   TRADIER_SANDBOX_KEY_MATT            │               │
│  │    AccID: TRADIER_SANDBOX_ACCOUNT_ID_MATT     │               │
│  ├─────────────────────────────────────────────┤               │
│  │  Account 3: "Logan"                          │               │
│  │    Key:   TRADIER_SANDBOX_KEY_LOGAN           │               │
│  │    AccID: TRADIER_SANDBOX_ACCOUNT_ID_LOGAN    │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  Each sandbox account gets the SAME IC trade mirrored to it.    │
│  Fill prices are read back and stored per-account.              │
│  "User" account fill is preferred for paper P&L.                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tradier API Call Flow

```
Signal Generation (every 5 min):
  1. GET /markets/quotes?symbols=SPY          → spot price
  2. GET /markets/quotes?symbols=VIX          → VIX level
  3. GET /markets/options/expirations?symbol=SPY → valid expirations
  4. GET /markets/options/chains?symbol=SPY&expiration=YYYY-MM-DD → strike validation
  5. GET /markets/quotes?symbols=SPY260311P00570000  (×4 legs) → bid/ask credits

Open Trade (mirror to sandbox):
  6. POST /accounts/{id}/orders (multileg, sell_to_open) → order_id  (×3 accounts)
  7. GET  /accounts/{id}/orders/{order_id}  → fill price readback  (×3 accounts)

Position Monitor MTM (every 15s):
  8. GET /markets/quotes?symbols=SYM1,SYM2,...  → batch quotes for ALL open legs

Close Trade (mirror to sandbox):
  9. POST /accounts/{id}/orders (multileg, buy_to_close) → order_id  (×3 accounts)
  10. GET  /accounts/{id}/orders/{order_id}  → fill price readback  (×3 accounts)
```

### Fill Logic

```
OPENING (conservative paper fills):
  Put credit  = put_short.BID - put_long.ASK
  Call credit = call_short.BID - call_long.ASK
  Total credit = put_credit + call_credit

  If Tradier sandbox fills at different price:
    → Use sandbox "User" account fill (preferred)
    → Fallback: any sandbox fill
    → Fallback: use bid/ask estimate

CLOSING (cost to close):
  Cost = put_short.ASK + call_short.ASK - put_long.BID - call_long.BID

  Same sandbox fill priority for close price.

P&L = (entry_credit - close_debit) × 100 × contracts
```

---

## 4. PDT System

Pattern Day Trader rule enforcement with database-backed toggle.

### PDT Rules

```
┌─────────────────────────────────────────────────────────────────┐
│                         PDT SYSTEM                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FINRA Rule 4210: ≤ 3 day trades per 5 rolling business days    │
│  IronForge config: pdt_max_day_trades = 4 (one extra buffer)    │
│                                                                 │
│  A "day trade" = open + close on the SAME calendar day          │
│  Tracked in: {bot}_pdt_log table                                │
│                                                                 │
│  PDT Check Flow:                                                │
│  ┌───────────┐                                                  │
│  │ is_pdt_   │──── FALSE ──▶ ALL LIMITS BYPASSED:              │
│  │ enabled() │              • max_trades_per_day: ignored       │
│  └─────┬─────┘              • rolling 5-day count: ignored      │
│        │                    • single-trade blocking: ignored     │
│      TRUE                                                       │
│        │                                                        │
│        ▼                                                        │
│  ┌─────────────────────────────────────┐                        │
│  │ 1. max_trades_per_day check         │                        │
│  │    trades_today >= max? → BLOCKED   │                        │
│  │                                     │                        │
│  │ 2. single-trade guard (max=1 only)  │                        │
│  │    position still open? → BLOCKED   │                        │
│  │                                     │                        │
│  │ 3. rolling 5-day PDT count          │                        │
│  │    day_trades >= 4? → BLOCKED       │                        │
│  └─────────────────────────────────────┘                        │
│                                                                 │
│  When PDT is OFF:                                               │
│  • run_cycle() skips ALL trade-count gates (lines 197-235)      │
│  • BUT: _compute_sleep_hint() still checks trade count          │
│    independently — so FLAME/SPARK still sleep after 1 trade     │
│    (this was the bug we just fixed)                             │
│                                                                 │
│  PDT Toggle:                                                    │
│  • Stored in DB: {bot}_config table, via is_pdt_enabled()       │
│  • Toggled via webapp: PUT /api/{bot}/pdt                       │
│  • INFERNO: pdt_max_day_trades = 0 (never enforced)            │
│                                                                 │
│  PDT Audit:                                                     │
│  • GET /api/{bot}/pdt/audit → rolling 5-day trade log           │
│  • Shows which trades count as day trades                       │
│  • Shows next PDT reset date                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### PDT Database Tracking

```
{bot}_pdt_log:
  ┌───────────────────────────────────────────────────────────┐
  │ trade_date │ position_id │ opened_at │ closed_at │ is_day │
  │ 2026-03-10 │ FLAME-...   │ 09:15 CT  │ 11:30 CT  │ TRUE   │
  │ 2026-03-10 │ FLAME-...   │ 09:15 CT  │ (open)    │ FALSE  │
  │ 2026-03-07 │ FLAME-...   │ 08:45 CT  │ 10:20 CT  │ TRUE   │
  └───────────────────────────────────────────────────────────┘

  Rolling 5-day query:
    SELECT COUNT(*) FROM {bot}_pdt_log
    WHERE is_day_trade = TRUE
    AND trade_date >= CURRENT_DATE - INTERVAL '5 days'
    AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5
```

---

## 5. Trade Scanner (Full Cycle)

The main `run_cycle()` in `trader.py` — runs every 60s during market hours.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     TRADE SCANNER: run_cycle()                           │
│                     trader.py:129-388                                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 1: MANAGE EXISTING POSITIONS    │  ◀── ALWAYS runs first        │
│  │ • Check profit target (sliding)      │                                │
│  │ • Check stop loss (100%/200%)        │                                │
│  │ • Check EOD cutoff (2:45 PM CT)      │                                │
│  │ • Close stale/expired positions      │                                │
│  │ • Handle MTM data failures           │                                │
│  │ • Mirror closes to sandbox           │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │                                                         │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 2: IS BOT ACTIVE?              │                                │
│  │ db.get_bot_active() → bool           │                                │
│  │ If FALSE → action="inactive"         │                                │
│  │ (still manages positions above)      │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ TRUE                                                    │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 3: TRADING WINDOW CHECK         │                                │
│  │ 8:30 AM – 2:45 PM CT                │                                │
│  │ (entry_start to eod cutoff)          │                                │
│  │ If outside → action="outside_window" │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ IN WINDOW                                               │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 4: CLOSE-ONLY MODE?            │                                │
│  │ If close_only=True → stop here       │                                │
│  │ (used for force-close scenarios)     │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ NOT close_only                                          │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 5: TRADE COUNT CHECK            │◀── PDT-gated                  │
│  │ trades_today >= max_trades_per_day?  │    (skipped if PDT off)       │
│  │ For max=1: is position still open?   │                                │
│  │ If blocked → action="max_trades"     │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ SLOTS AVAILABLE                                         │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 6: PDT ROLLING CHECK            │◀── PDT-gated                  │
│  │ day_trades in last 5 days >= 4?      │    (skipped if PDT off)       │
│  │ If blocked → action="pdt_blocked"    │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ PDT OK                                                  │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 7: BUYING POWER CHECK           │                                │
│  │ buying_power < $200?                 │                                │
│  │ If yes → action="insufficient_bp"    │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ BP OK                                                   │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 8: GENERATE SIGNAL              │  signals.py                    │
│  │ 1. Fetch SPY price + VIX             │                                │
│  │ 2. VIX > 32? → skip                  │                                │
│  │ 3. Calculate target expiration       │                                │
│  │ 4. SD-based strike selection         │                                │
│  │ 5. Enforce symmetric wings           │                                │
│  │ 6. Get real Tradier bid/ask credits  │                                │
│  │ 7. Run advisor (VIX/DOW/EM rules)   │                                │
│  │ 8. Advisor says SKIP + WP < 42%?    │                                │
│  │    → action="no_signal"              │                                │
│  │ If invalid → action="no_signal"      │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ VALID SIGNAL                                            │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 9: SIZE THE TRADE               │                                │
│  │ collateral = (width×100)-(credit×100)│                                │
│  │ max_contracts = (BP×85%) / collateral│                                │
│  │ Cap at config.max_contracts          │                                │
│  │ If 0 contracts → insufficient_bp     │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ SIZED                                                   │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 10: RACE GUARD                  │                                │
│  │ Re-check open positions + trade count│                                │
│  │ (prevents duplicates from timing)    │                                │
│  └──────────────┬───────────────────────┘                                │
│                 │ CLEAR                                                   │
│                 ▼                                                         │
│  ┌──────────────────────────────────────┐                                │
│  │ STEP 11: EXECUTE PAPER TRADE         │  executor.py                   │
│  │ 1. Create IronCondorPosition         │                                │
│  │ 2. Save to {bot}_positions           │                                │
│  │ 3. Deduct collateral from account    │                                │
│  │ 4. Log PDT entry                     │                                │
│  │ 5. Mirror to 3 sandbox accounts      │                                │
│  │ 6. Read back fill prices             │                                │
│  │ 7. Update position with actual fill  │                                │
│  │ 8. Log trade + save snapshot         │                                │
│  │ → action="traded"                    │                                │
│  └──────────────────────────────────────┘                                │
│                                                                          │
│  FINALLY (always runs):                                                  │
│  • Save equity snapshot (intraday chart)                                │
│  • Compute sleep_hint for adaptive loop                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Sleep Hint Logic

```
┌──────────────────────────────────────────────────────────────────┐
│                    ADAPTIVE SLEEP LOGIC                           │
│                    _compute_sleep_hint()                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Before market open?                                             │
│  └── Sleep until 5 min before entry_start (could be hours)      │
│                                                                  │
│  After EOD?                                                      │
│  └── Sleep until tomorrow 8:25 AM CT (could be 17+ hours)      │
│                                                                  │
│  Bot disabled?                                                   │
│  └── 300s (check every 5 min for re-enable)                     │
│                                                                  │
│  Max trades hit (regardless of PDT on/off)?                     │
│  ├── Open positions still exist? → 60s (monitoring)             │
│  └── All closed? → Sleep until tomorrow                          │
│                                                                  │
│  Everything else (scanning, monitoring, errors)?                │
│  └── 60s                                                         │
│                                                                  │
│  INFERNO (max_trades=0 / unlimited):                            │
│  └── Always 60s during market hours                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Fast Scanner (Position Monitor)

`run_position_monitor.py` — a lightweight, exit-only guardian running every **15 seconds**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    POSITION MONITOR (FAST SCANNER)                       │
│                    run_position_monitor.py                                │
│                    15-second loop, exits only                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  WHAT IT DOES:                                                           │
│  ✓ Close positions that hit profit target                               │
│  ✓ Close positions that hit stop loss                                   │
│  ✓ Close positions at EOD cutoff (2:45 PM CT)                          │
│  ✓ Close stale/overnight positions                                      │
│  ✓ Close expired positions                                              │
│  ✓ Mirror all closes to Tradier sandbox                                 │
│  ✓ Batch quote fetching (1 API call per bot, not per leg)              │
│                                                                          │
│  WHAT IT DOES NOT DO:                                                    │
│  ✗ No signal generation                                                 │
│  ✗ No new trade entry                                                   │
│  ✗ No option chain scanning                                             │
│  ✗ No PDT checks or buying power calculations                          │
│  ✗ No advisor evaluation                                                │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  FOR EACH BOT (FLAME, SPARK, INFERNO):                       │       │
│  │                                                               │       │
│  │  1. Query all open positions from DB                         │       │
│  │     └── If none → skip this bot                              │       │
│  │                                                               │       │
│  │  2. Build OCC symbols for ALL legs of ALL positions          │       │
│  │     SPY260311P00570000, SPY260311P00565000, ...              │       │
│  │                                                               │       │
│  │  3. SINGLE batch API call:                                   │       │
│  │     GET /markets/quotes?symbols=SYM1,SYM2,SYM3,...          │       │
│  │     (vs main scanner: 4 calls per position)                  │       │
│  │                                                               │       │
│  │  4. For each position:                                       │       │
│  │     ┌─────────────────────────────────┐                      │       │
│  │     │ Stale/expired from prior day?   │──YES──▶ Force close  │       │
│  │     └─────────────┬───────────────────┘                      │       │
│  │                   │ NO                                        │       │
│  │                   ▼                                           │       │
│  │     ┌─────────────────────────────────┐                      │       │
│  │     │ Calculate MTM from batch quotes │                      │       │
│  │     │ cost = short.ASK - long.BID     │                      │       │
│  │     └─────────────┬───────────────────┘                      │       │
│  │                   │                                           │       │
│  │                   ▼                                           │       │
│  │     ┌─────────────────────────────────┐                      │       │
│  │     │ Profit target hit?              │                      │       │
│  │     │ close_price <= credit × (1-PT%) │──YES──▶ Close (PT)   │       │
│  │     └─────────────┬───────────────────┘                      │       │
│  │                   │ NO                                        │       │
│  │                   ▼                                           │       │
│  │     ┌─────────────────────────────────┐                      │       │
│  │     │ Stop loss hit?                  │                      │       │
│  │     │ close_price >= credit × (1+SL%) │──YES──▶ Close (SL)   │       │
│  │     └─────────────┬───────────────────┘                      │       │
│  │                   │ NO                                        │       │
│  │                   ▼                                           │       │
│  │     ┌─────────────────────────────────┐                      │       │
│  │     │ Past EOD cutoff (2:45 PM CT)?   │──YES──▶ Close (EOD)  │       │
│  │     └─────────────┬───────────────────┘                      │       │
│  │                   │ NO                                        │       │
│  │                   ▼                                           │       │
│  │              [Keep monitoring]                                │       │
│  └──────────────────────────────────────────────────────────────┘       │
│                                                                          │
│  MODES:                                                                  │
│  • python run_position_monitor.py          → single pass, exit           │
│  • python run_position_monitor.py --loop   → 15s infinite loop          │
│                                                                          │
│  WHY THIS EXISTS:                                                        │
│  The main scanner runs every 60s. A position can blow through a          │
│  stop loss or hit profit target between scans. The position monitor      │
│  checks every 15s for 4× faster exit detection.                         │
│                                                                          │
│  PERFORMANCE ADVANTAGE:                                                  │
│  • Main scanner: 4 individual quote calls per position per cycle         │
│  • Position monitor: 1 batch call for ALL positions across ALL bots     │
│  • Result: fewer API calls, faster response, lower Tradier rate limits  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Scanner vs Position Monitor Comparison

```
┌────────────────────────┬──────────────────────┬────────────────────────┐
│                        │  TRADE SCANNER       │  POSITION MONITOR      │
│                        │  (run_cycle)         │  (run_position_monitor)│
├────────────────────────┼──────────────────────┼────────────────────────┤
│ Frequency              │ 60s (adaptive)       │ 15s (fixed)            │
│ Opens trades?          │ YES                  │ NO                     │
│ Closes trades?         │ YES                  │ YES                    │
│ Signal generation?     │ YES                  │ NO                     │
│ Market data quotes     │ 4 individual calls   │ 1 batch call           │
│ PDT checking?          │ YES                  │ NO                     │
│ Buying power check?    │ YES                  │ NO                     │
│ Advisor evaluation?    │ YES                  │ NO                     │
│ Equity snapshots?      │ YES (every cycle)    │ NO                     │
│ Covers all bots?       │ One bot per worker   │ ALL bots in one pass   │
│ Sandbox mirroring?     │ YES (open + close)   │ YES (close only)       │
│ Stale position cleanup?│ YES                  │ YES                    │
│ Run mode               │ Per-bot worker       │ Shared across bots     │
└────────────────────────┴──────────────────────┴────────────────────────┘
```

---

## 7. Database Schema

### Per-Bot Tables (prefix = flame_, spark_, inferno_)

```
┌─────────────────────────────────────────────────────────────────────┐
│  {bot}_positions                                                     │
│  ─────────────────                                                   │
│  All positions (open + closed + expired)                            │
│  Columns: position_id, ticker, expiration, put_short/long_strike,   │
│  call_short/long_strike, put/call_credit, contracts, spread_width,  │
│  total_credit, max_loss, max_profit, collateral_required,           │
│  underlying_at_entry, vix_at_entry, expected_move,                  │
│  call_wall, put_wall, gex_regime, flip_point, net_gex,             │
│  oracle_confidence, oracle_win_probability, oracle_advice,          │
│  oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,       │
│  wings_adjusted, original_put/call_width,                           │
│  sandbox_order_id, sandbox_close_order_id,                          │
│  status (open/closed/expired), open_time, close_time,               │
│  close_price, close_reason, realized_pnl, dte_mode                 │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_paper_account                                                 │
│  ─────────────────────                                               │
│  Paper account state (single row per dte_mode)                      │
│  Columns: starting_capital, current_balance, cumulative_pnl,        │
│  total_trades, collateral_in_use, buying_power,                     │
│  high_water_mark, max_drawdown, is_active, dte_mode                │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_signals                                                       │
│  ────────────────                                                    │
│  Every signal (executed or skipped)                                  │
│  Columns: signal_time, spot_price, vix, expected_move,              │
│  call_wall, put_wall, gex_regime, strikes (×4), total_credit,      │
│  confidence, was_executed, skip_reason, reasoning, wings_adjusted   │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_equity_snapshots                                              │
│  ────────────────────────                                            │
│  Periodic snapshots (every 60s cycle) for intraday chart            │
│  Columns: snapshot_time, balance, unrealized_pnl, realized_pnl,    │
│  open_positions, note, dte_mode                                     │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_pdt_log                                                       │
│  ──────────────                                                      │
│  PDT day trade tracking                                              │
│  Columns: trade_date, symbol, position_id, opened_at, closed_at,   │
│  is_day_trade, contracts, entry_credit, exit_cost, pnl,            │
│  close_reason, dte_mode                                             │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_daily_perf                                                    │
│  ─────────────────                                                   │
│  Daily performance summary (1 row per day)                          │
│  Columns: trade_date, trades_executed, positions_closed,            │
│  realized_pnl                                                       │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_logs                                                          │
│  ─────────                                                           │
│  Activity log (audit trail)                                          │
│  Columns: log_time, level (TRADE_OPEN/TRADE_CLOSE/SKIP/ERROR/      │
│  RECOVERY/CONFIG), message, details (JSON), dte_mode                │
├─────────────────────────────────────────────────────────────────────┤
│  {bot}_config                                                        │
│  ────────────                                                        │
│  Persisted config overrides (optional, overrides BotConfig defaults)│
│  Columns: dte_mode, sd_multiplier, spread_width, min_credit,       │
│  profit_target_pct, stop_loss_pct, vix_skip, max_contracts,        │
│  max_trades_per_day, buying_power_usage_pct, risk_per_trade_pct,   │
│  min_win_probability, entry_start, entry_end, eod_cutoff_et,       │
│  pdt_max_day_trades, starting_capital                               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  bot_heartbeats (shared across all bots)                             │
│  ────────────────                                                    │
│  Columns: bot_name (PK), last_heartbeat, status, scan_count,       │
│  details                                                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Signal Generation Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    SIGNAL GENERATION PIPELINE                             │
│                    signals.py: SignalGenerator.generate_signal()          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 1. FETCH MARKET DATA                        │                        │
│  │    SPY quote → spot_price                    │                        │
│  │    VIX quote → vix level                     │                        │
│  │    Expected move = VIX/√252 × spot           │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 2. VIX FILTER                                │                        │
│  │    VIX > 32? → INVALID (too volatile)        │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │ PASS                                           │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 3. TARGET EXPIRATION                         │                        │
│  │    FLAME: 2 trading days out (skip weekends) │                        │
│  │    SPARK: 1 trading day out                   │                        │
│  │    INFERNO: today (same day)                  │                        │
│  │    Validate against Tradier expiration list   │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 4. STRIKE SELECTION (SD-based)               │                        │
│  │                                               │                        │
│  │    put_short  = floor(spot - SD × EM)        │                        │
│  │    call_short = ceil(spot + SD × EM)         │                        │
│  │    put_long   = put_short - width ($5)       │                        │
│  │    call_long  = call_short + width ($5)      │                        │
│  │                                               │                        │
│  │    SD floor = 1.2 (never tighter)             │                        │
│  │    EM floor = 0.5% of spot                    │                        │
│  │                                               │                        │
│  │    Example: SPY=$590, VIX=18, EM=$6.70       │                        │
│  │    put_short  = 590 - 1.2×6.70 = 581.96→581 │                        │
│  │    call_short = 590 + 1.2×6.70 = 598.04→599 │                        │
│  │    put_long   = 576                           │                        │
│  │    call_long  = 604                           │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 5. SYMMETRIC WING ENFORCEMENT                │                        │
│  │    put_width = put_short - put_long           │                        │
│  │    call_width = call_long - call_short        │                        │
│  │    If unequal: widen the narrow side           │                        │
│  │    Validate against available strikes          │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 6. REAL CREDITS (Tradier bid/ask)            │                        │
│  │    Sell at bid, buy at ask (conservative)     │                        │
│  │                                               │                        │
│  │    put_credit  = put_short.BID - put_long.ASK│                        │
│  │    call_credit = call_short.BID-call_long.ASK│                        │
│  │    total = put_credit + call_credit           │                        │
│  │                                               │                        │
│  │    Fallback: mid-price if bid/ask negative    │                        │
│  │    Fallback: estimate if Tradier unavailable  │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │                                                │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 7. MINIMUM CREDIT CHECK                     │                        │
│  │    total_credit < $0.05? → INVALID           │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │ PASS                                           │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ 8. ADVISOR EVALUATION (rule-based)           │                        │
│  │                                               │                        │
│  │    Base win probability = 65%                 │                        │
│  │                                               │                        │
│  │    VIX scoring:                               │                        │
│  │      15-22  → +10% (ideal)                    │                        │
│  │      <15    → -5%  (thin premiums)            │                        │
│  │      22-28  → -5%  (elevated)                 │                        │
│  │      >28    → -15% (high risk)                │                        │
│  │                                               │                        │
│  │    Day of week:                               │                        │
│  │      Tue-Thu → +8%  (optimal)                 │                        │
│  │      Mon    → +3%                             │                        │
│  │      Fri    → -10% (expiration risk)          │                        │
│  │                                               │                        │
│  │    Expected move ratio:                       │                        │
│  │      <1%    → +8%  (tight range)              │                        │
│  │      1-2%   → +0%  (normal)                   │                        │
│  │      >2%    → -8%  (wide range)               │                        │
│  │                                               │                        │
│  │    DTE factor:                                │                        │
│  │      2DTE   → +3%  (more time decay)          │                        │
│  │      1DTE   → -2%  (tighter)                  │                        │
│  │      0DTE   → -5%  (aggressive)               │                        │
│  │                                               │                        │
│  │    Decision:                                  │                        │
│  │      WP≥60% + conf≥50% → TRADE_FULL          │                        │
│  │      WP≥42% + conf≥35% → TRADE_REDUCED       │                        │
│  │      Otherwise          → SKIP                │                        │
│  │                                               │                        │
│  │    If SKIP + WP < 42% → INVALID signal       │                        │
│  └──────────────────────┬──────────────────────┘                        │
│                         │ VALID                                          │
│                         ▼                                                │
│  ┌─────────────────────────────────────────────┐                        │
│  │ RETURN: IronCondorSignal (is_valid=True)     │                        │
│  │   • All strikes, credits, expiration          │                        │
│  │   • Oracle-compatible fields populated        │                        │
│  │   • Wings adjustment metadata                 │                        │
│  └──────────────────────────────────────────────┘                        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Webapp API Routes

All routes are dynamic: `/api/[bot]/...` where bot = `flame` | `spark` | `inferno`.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WEBAPP API ROUTES                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  BOT DATA ROUTES                                                    │
│  ─────────────────                                                  │
│  GET  /api/{bot}/status           Account balance, P&L, heartbeat  │
│  GET  /api/{bot}/positions        Open positions with strikes       │
│  GET  /api/{bot}/position-monitor Live MTM, proximity to PT/SL     │
│  GET  /api/{bot}/position-detail  Detailed single position view    │
│  GET  /api/{bot}/equity-curve     Historical equity from closed    │
│  GET  /api/{bot}/equity-curve/intraday  Today's 60s snapshots     │
│  GET  /api/{bot}/trades           Closed trade history              │
│  GET  /api/{bot}/performance      Win rate, avg win/loss stats     │
│  GET  /api/{bot}/daily-perf       Daily P&L breakdown              │
│  GET  /api/{bot}/logs             Activity log (audit trail)        │
│                                                                     │
│  BOT CONTROL ROUTES                                                 │
│  ──────────────────                                                 │
│  PUT  /api/{bot}/toggle           Enable/disable bot                │
│  POST /api/{bot}/force-trade      Force immediate signal + trade   │
│  POST /api/{bot}/force-close      Force close all open positions   │
│  GET/PUT /api/{bot}/config        Read/update bot config           │
│                                                                     │
│  PDT ROUTES                                                         │
│  ───────────                                                        │
│  GET  /api/{bot}/pdt              PDT status, rolling count        │
│  GET  /api/{bot}/pdt/audit        Detailed PDT trade log           │
│                                                                     │
│  ACCOUNT MANAGEMENT                                                 │
│  ──────────────────                                                 │
│  GET  /api/accounts/manage        List sandbox accounts             │
│  POST /api/accounts/manage        Add sandbox account               │
│  DEL  /api/accounts/manage/{id}   Remove sandbox account            │
│  POST /api/accounts/test          Test single account connectivity │
│  POST /api/accounts/test-all      Test all accounts                │
│  GET  /api/accounts/production    Production account info          │
│                                                                     │
│  SYSTEM                                                             │
│  ──────                                                             │
│  GET  /api/health                 Database + Tradier health check  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 10. Orphan Recovery & Startup

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    STARTUP / ORPHAN RECOVERY                             │
│                    trader.py: _recover_orphaned_positions()               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  On Trader.__init__():                                                  │
│                                                                          │
│  1. Load config from BotConfig defaults                                 │
│  2. Initialize database + paper account                                 │
│  3. Apply DB config overrides (if any saved in {bot}_config)           │
│  4. Initialize SignalGenerator + PaperExecutor                          │
│  5. Check for orphaned open positions:                                  │
│                                                                          │
│     ┌─────────────────────────────────────┐                             │
│     │  Query: SELECT * FROM positions      │                             │
│     │         WHERE status = 'open'        │                             │
│     └─────────────┬───────────────────────┘                             │
│                   │                                                      │
│          ┌────────┴────────┐                                            │
│          │  Found orphans? │                                            │
│          └────────┬────────┘                                            │
│                   │ YES                                                  │
│          ┌────────┴────────────┐                                        │
│          │  Market open now?   │                                        │
│          └────┬───────────┬────┘                                        │
│            YES│           │NO                                           │
│               ▼           ▼                                             │
│    [Resume monitoring] [Force-close at entry credit]                    │
│    Log: RECOVERY       Log: RECOVERY (force-closed)                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Deployment Topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        RENDER DEPLOYMENT                                 │
│                        (render.yaml)                                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-dashboard (Web Service)        │                           │
│  │  Runtime: Node.js                         │                           │
│  │  Command: npm start                       │                           │
│  │  Port: 3000                               │                           │
│  │  Serves: Next.js pages + API routes       │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-flame (Worker)                 │                           │
│  │  Runtime: Python 3.11                     │                           │
│  │  Command: python jobs/run_flame.py        │                           │
│  │  Loop: 60s adaptive sleep                 │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-spark (Worker)                 │                           │
│  │  Runtime: Python 3.11                     │                           │
│  │  Command: python jobs/run_spark.py        │                           │
│  │  Loop: 60s adaptive sleep                 │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-inferno (Worker)               │                           │
│  │  Runtime: Python 3.11                     │                           │
│  │  Command: python jobs/run_inferno.py      │                           │
│  │  Loop: 60s (always, unlimited trades)     │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-monitor (Worker) [optional]    │                           │
│  │  Runtime: Python 3.11                     │                           │
│  │  Command: python jobs/run_position_monitor│                           │
│  │           --loop                          │                           │
│  │  Loop: 15s fixed                          │                           │
│  │  Covers: ALL bots (FLAME+SPARK+INFERNO)  │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ┌──────────────────────────────────────────┐                           │
│  │  ironforge-db (Database)                  │                           │
│  │  PostgreSQL (Render free tier)            │                           │
│  │  Tables: 25 (8 per bot × 3 + heartbeats) │                           │
│  └──────────────────────────────────────────┘                           │
│                                                                          │
│  ENV VARS:                                                              │
│  ─────────                                                              │
│  DATABASE_URL                    (from Render DB)                       │
│  TRADIER_API_KEY                 (sandbox key for quotes)               │
│  TRADIER_ACCOUNT_ID              (primary sandbox account)              │
│  TRADIER_BASE_URL                (defaults to sandbox.tradier.com)      │
│  TRADIER_SANDBOX_KEY_USER        (mirror account 1)                     │
│  TRADIER_SANDBOX_KEY_MATT        (mirror account 2)                     │
│  TRADIER_SANDBOX_KEY_LOGAN       (mirror account 3)                     │
│  TRADIER_SANDBOX_ACCOUNT_ID_*    (matching account IDs)                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Data Flow Summary

```
EVERY 60 SECONDS (Trade Scanner):
  Tradier ──quote──▶ SignalGenerator ──signal──▶ Trader ──position──▶ DB
                                                    │
                                                    ├──▶ Executor ──▶ Paper Account (DB)
                                                    │        │
                                                    │        └──▶ 3× Sandbox (Tradier)
                                                    │                    │
                                                    │                    └──▶ Fill readback
                                                    │
                                                    ├──▶ PDT Log (DB)
                                                    ├──▶ Signal Log (DB)
                                                    ├──▶ Equity Snapshot (DB)
                                                    └──▶ Activity Log (DB)

EVERY 15 SECONDS (Position Monitor):
  Tradier ──batch quotes──▶ PositionMonitor ──close──▶ DB
                                    │
                                    └──▶ 3× Sandbox close (Tradier)

WEBAPP (on demand):
  Browser ──▶ Next.js API routes ──SQL──▶ PostgreSQL ──▶ JSON response
                                                              │
                                  position-monitor route ──Tradier──▶ Live MTM
```
