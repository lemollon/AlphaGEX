# Iron Forge — Product Knowledge (Project A)

Everything the avatar needs to talk about Iron Forge accurately. Source of truth:
`ironforge/CLAUDE.md` in the codebase. If a number here ever conflicts with the code,
the code wins — flag it to the founder.

---

## What Iron Forge is (one paragraph)

Iron Forge is a **standalone, autonomous SPY Iron Condor paper-trading system.** It runs
three bots that scan the market every minute, build Iron Condors on SPY using **real
Tradier market data**, and execute them on a **paper account** (simulated fills, no real
money — yet). It's a focused, transparent "can a disciplined bot actually grind Iron
Condors?" experiment, built on the same GEX philosophy as the parent AlphaGEX engine.
Each bot has its own live dashboard: equity curve, performance, open positions, trade
history, logs, and a PDT (pattern-day-trader) tracker.

**Theme:** fire / the forge. The bots are named for fire (FLAME, SPARK, INFERNO). The
metaphor — *forging discipline in the fire of the market* — is on-brand and reusable.

---

## The three bots (the heart of the content)

All three trade **SPY Iron Condors**. They differ mainly by **time-to-expiration (DTE)**
and aggressiveness. An Iron Condor wins when price stays inside a range; it has a
defined max profit (the credit collected) and a defined max loss (the wing width minus
credit). Theta (time decay) is the engine; a fast directional move is the enemy.

| Bot | DTE | Personality | Key parameters |
|---|---|---|---|
| **FLAME** | **2DTE** | The patient one. Longer duration = more premium and more time for the trade to work. | SD 1.2×, $5 wings, PT 30% of credit, SL 2×, **max 1 trade/day**, BP-sized |
| **SPARK** | **1DTE** | The quick one. Faster theta decay, quicker resolution. | SD 1.2×, $5 wings, PT 30% of credit, SL 2×, **max 1 trade/day**, half-Kelly sizing |
| **INFERNO** | **0DTE** | The aggressive one. FORTRESS-style — **unlimited trades/day**, multiple simultaneous positions. The high-gamma daredevil (respected, not glorified). | SD 1.0× (tighter), PT 50% of credit, SL 2×, **unlimited trades/day**, half-Kelly sizing |

**Shared parameters across the bots:**
- Ticker: **SPY**
- Starting capital: **$10,000 (paper)**
- Spread width: **$5**
- VIX skip: if VIX **> 32**, stand down (too dangerous)
- Entry window: **8:30 AM – 2:00 PM CT** (INFERNO until 2:30 PM CT)
- EOD safety close: **2:50 PM CT** — nothing held overnight
- Scan frequency: **every 1 minute**
- Position sizing: **per-trade Kelly criterion** (SPARK + INFERNO use clamped
  half-Kelly, 10%–85% of buying power; FLAME is buying-power-sized). No fixed contract
  ceiling — size scales with win probability × reward/risk.
- **PDT enforcement:** max 4 day trades per 5 rolling business days (matches FINRA Rule
  4210), tracked per bot with a 4-week rolling calendar in the UI.

> Content gold: three bots = three *characters* with different risk personalities. FLAME
> the patient grinder, SPARK the nimble striker, INFERNO the high-stakes specialist. You
> can run them as an ongoing cast.

---

## How a trade actually happens (the trading cycle)

Each minute, every bot:
1. **Manages open positions first** — checks profit target, stop loss, EOD, and stale/
   expired conditions before anything else.
2. Confirms it's active and inside the trading window.
3. Checks it isn't already at its position / daily-trade limit.
4. Runs the **PDT check** (won't break the day-trade rule).
5. Confirms enough buying power (> $200).
6. **Generates the signal** — pulls live SPY spot + VIX from Tradier, sets short strikes
   by standard-deviation distance, builds symmetric $5 wings, and prices the real
   bid/ask credit.
7. **Sizes the trade** (Kelly / BP math, ~85% BP usage cap).
8. Re-checks for races, then **executes the paper trade.**
9. **Saves an equity snapshot** every cycle (so the intraday chart is always live).

**Exit triggers:** profit target hit (cost-to-close ≤ a set % of entry credit), stop
loss (cost-to-close ≥ 2× credit), EOD safety (≥ 2:50 PM CT), stale/expired position, or
repeated data failures. Conservative fills: **sells at the bid, buys at the ask**
(worst-case paper assumptions — so the paper results are pessimistic, not flattering).

> Honesty angle worth posting: "The paper fills are intentionally *pessimistic* — sell
> the bid, buy the ask. If anything, real results could be better, not worse. I'd rather
> lie to myself in the safe direction."

---

## What's real vs. simulated (state this clearly, always)

- **Real:** market data (SPY quotes, option chains, VIX) via Tradier; the strike
  selection, sizing, and exit logic; the equity math.
- **Simulated:** the fills/execution. **No real money is at risk.** It's a paper
  account starting at $10,000.
- This honesty is a feature. Never present Iron Forge paper results as live returns.

---

## The dashboards (what followers can be shown / sent to)

Each bot (FLAME, SPARK, INFERNO) has a dashboard with:
- **Equity curve** (historical, cumulative P&L) and **intraday** equity (updates each
  cycle).
- **Performance:** win rate, total P&L, average win/loss, best/worst trade.
- **Open positions** with live mark-to-market.
- **Trade history** (closed trades).
- **Activity logs** (every open, close, skip, error, recovery).
- **PDT card + 4-week calendar** showing day-trade usage.
- A **compare** view (all three bots side by side) and an **accounts** view.

Screenshots of these (clearly labeled paper) are premium content: equity curves, a
clean win, an honest loss, the compare view.

---

## How Iron Forge relates to the bigger picture

- It lives inside the AlphaGEX monorepo but is **completely standalone** — its own
  Tradier client, its own database, no dependency on the big platform. That's a
  deliberate design choice (lightweight, portable). Good "engineering decisions" content.
- It shares the **GEX philosophy** and the Iron Condor DNA of AlphaGEX's flagship
  FORTRESS bot (INFERNO is explicitly "FORTRESS-style").
- Sibling product: **Spreadworks** (spread-builder + its own bots). Same parent engine,
  different job. Cross-reference via the website hub, don't turn the feed into an ad.

---

## Talking points & angles unique to Iron Forge

- **"Three bots, three temperaments"** — recurring cast: FLAME (patient), SPARK
  (nimble), INFERNO (aggressive 0DTE).
- **The 0DTE respect angle** — INFERNO shows how to trade the most dangerous day with
  guardrails (VIX skip, EOD close, tight SD, defined risk), not how to YOLO it.
- **Discipline made mechanical** — PDT limits, EOD flatten, profit targets, stop
  losses: the bot *can't* revenge-trade or hold-and-hope. Great "be more like your bot"
  content.
- **Pessimistic paper fills** — the integrity flex above.
- **The grind** — Iron Condors aren't sexy; they're a probability-and-discipline game.
  Lean into the un-sexiness as a credibility signal.
- **Forge metaphor** — heat, pressure, repetition forging something durable.

## Facts the avatar must NOT get wrong

- Iron Forge = **paper**, **SPY**, **Iron Condors**, **3 bots**.
- FLAME 2DTE, SPARK 1DTE, INFERNO 0DTE. Don't swap these.
- INFERNO is the only one with unlimited trades/day.
- $10k paper start, $5 wings, VIX>32 = skip, EOD close ~2:50pm CT, scans every 1 min.
- It does **not** place real orders and is **not** a signal service.
