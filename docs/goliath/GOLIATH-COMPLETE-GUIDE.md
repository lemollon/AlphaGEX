# GOLIATH — The Complete Guide

**Status:** v0.2 paper-trading on Render · Phase 1.5 calibration complete · 5 LETF instances live
**Last updated:** 2026-05-01
**Audience:** Anyone who needs to understand what GOLIATH is, why it exists, what it does, and how it was built — including someone who doesn't yet know what an LETF or an option is.

---

## Table of contents

1. [Plain-English summary](#1-plain-english-summary)
2. [Glossary — every term you need](#2-glossary--every-term-you-need)
3. [The strategy](#3-the-strategy)
4. [The universe — why these 5 LETFs](#4-the-universe--why-these-5-letfs)
5. [The 3-leg trade structure](#5-the-3-leg-trade-structure)
6. [Why this works (and why the standard Wheel doesn't on LETFs)](#6-why-this-works-and-why-the-standard-wheel-doesnt-on-letfs)
7. [The 10 pre-entry gates (G01–G10)](#7-the-10-pre-entry-gates-g01g10)
8. [Strike mapping — translating wall to LETF strikes](#8-strike-mapping--translating-wall-to-letf-strikes)
9. [The 8 exit triggers (T1–T8)](#9-the-8-exit-triggers-t1t8)
10. [Position sizing — two-level caps](#10-position-sizing--two-level-caps)
11. [The 7 kill switches](#11-the-7-kill-switches)
12. [Phase 1.5 calibration — what was measured](#12-phase-15-calibration--what-was-measured)
13. [Architecture and build phases](#13-architecture-and-build-phases)
14. [Operations and monitoring](#14-operations-and-monitoring)
15. [What's left — v0.3 and live unlock](#15-whats-left--v03-and-live-unlock)
16. [References — where to find things in the code](#16-references--where-to-find-things-in-the-code)

---

## 1. Plain-English summary

GOLIATH is a fully automated options-trading robot that places a very specific kind of bet on **leveraged single-stock ETFs** (the funds that move 2× the daily price of a single stock — MSTU follows MSTR, TSLL follows TSLA, etc.).

Once a week, on Monday morning, for each of five chosen LETFs, the bot does this:

1. Looks at where the **dealers** (the market-makers who write options) are most heavily hedged on the underlying stock — that's the "gamma wall" below current price, the price level the stock is most likely to bounce off.
2. Translates that bounce level into the equivalent price level on the LETF.
3. Builds a 3-leg options bet that says: *"the LETF will probably stay above this level by Friday, and if it instead rips upward I want unlimited upside."*
4. The bet is structured to cost almost nothing up-front (a few dollars), have a hard-defined maximum loss (we know exactly the worst case before opening), and have unlimited upside if the underlying rallies hard.

That's it. The bot is doing one weekly setup per LETF, with hard rules for opening, managing, and closing. It cannot:
- Roll a losing trade (rolling is how short-volatility strategies blow up)
- Hold past Thursday 3PM (must be flat by then)
- Add to existing positions
- Trade the LETF without reading the underlying's gamma data first

Everything is paper-trading right now. Real capital is not at risk. The bot writes simulated fills to a database; we watch the dashboard and study what would have happened with real money.

---

## 2. Glossary — every term you need

Read this section before the rest of the document. Skip a term and the strategy won't make sense.

### 2.1 Stocks vs. ETFs

- **Stock:** A share of ownership in a company (e.g., NVDA = a slice of Nvidia).
- **ETF (Exchange-Traded Fund):** A basket that holds stocks, bonds, or other assets and trades on the market like a single stock. SPY holds the S&P 500. QQQ holds the Nasdaq-100.

### 2.2 LETF (Leveraged ETF)

An ETF designed to deliver a multiple — usually 2× or 3× — of the **daily** percentage move of an underlying. It uses derivatives (swaps, futures) to amplify exposure.

- **Single-stock LETF:** An LETF whose underlying is one stock, not a basket.
  - **MSTU** = 2× MSTR (MicroStrategy)
  - **TSLL** = 2× TSLA (Tesla)
  - **NVDL** = 2× NVDA (Nvidia)
  - **CONL** = 2× COIN (Coinbase)
  - **AMDL** = 2× AMD

If MSTR closes up 3% today, MSTU is engineered to close up about 6% today.

### 2.3 The decay problem (volatility drag)

LETFs only deliver 2× **daily**, not 2× over a week, month, or year. Because of compounding mathematics, a volatile underlying causes the LETF to lose ground over time, even if the underlying is flat. This is "**volatility drag**" or "**vol decay**."

Concrete example:
- Day 1: MSTR up 10% → MSTU up 20%. Both at index 1.20.
- Day 2: MSTR down 10% (back to where it started, ≈ 1.08) → MSTU down 20% (lands at 0.96).
- After 2 days MSTR is roughly flat, but MSTU has lost 4%. Multiply this over weeks and the drag is severe.

The theoretical drag formula: `drag ≈ -0.5 × L × (L−1) × σ² × t`, where L = 2 (the leverage), σ = annualized volatility of the underlying, t = time in years.

Holding LETFs long-term is generally a losing trade because of this drag. **The strategy GOLIATH replaces (the "Wheel") fails on LETFs precisely because of decay.**

### 2.4 Options — the basics

An **option** is a contract giving the buyer the *right* (not obligation) to either buy or sell 100 shares of a stock at a specific price by a specific date.

- **Call option:** Right to **buy** 100 shares at the strike price.
- **Put option:** Right to **sell** 100 shares at the strike price.
- **Strike price:** The price specified in the contract.
- **Expiration:** The last date the option can be exercised. After it expires worthless or in-the-money.
- **Premium:** The price you pay to buy the option (or receive when you sell it).
- **Buyer (long):** Pays the premium, has the rights.
- **Seller (short, "writer"):** Receives the premium, has the obligations.

Options are quoted **per share**, but each contract covers 100 shares. So an option quoted at $0.50 actually costs $50 (0.50 × 100).

### 2.5 In-the-money (ITM) vs. out-of-the-money (OTM)

- **ITM call:** Strike *below* the current stock price (you'd benefit from buying at strike). Has intrinsic value.
- **OTM call:** Strike *above* current price. Has only "time value."
- **ITM put:** Strike *above* current price.
- **OTM put:** Strike *below* current price.

**At-the-money (ATM):** Strike close to current price.

### 2.6 Spread

A **spread** is buying one option and selling another in the same stock at different strikes (or different expirations). Spreads cap both your max loss and your max gain. They're "defined-risk."

- **Put credit spread (bull put spread):** Sell a higher-strike put, buy a lower-strike put. You collect a net credit (premium in). You profit if the stock stays *above* the higher strike. Maximum loss = (strike difference) × 100 − credit received.

GOLIATH uses put credit spreads for the bearish side of its bet.

### 2.7 The 0DTE / 1DTE / 7DTE notation

**DTE** = days-to-expiration. A 7DTE option expires 7 days from today. GOLIATH always uses 7DTE — open Monday, expire Friday of the same week.

### 2.8 Gamma exposure (GEX)

**Gamma** is one of the "Greeks" — sensitivities of an option's price to underlying changes. Specifically, gamma is how fast an option's *delta* (its sensitivity to the stock price) changes as the stock moves. High gamma = the option's behavior changes fast.

**Gamma exposure (GEX):** The sum of all dealer-held gamma at each strike, scaled by open interest and contract size. It tells you where dealers must hedge most aggressively.

Key concept: **dealers are usually short gamma**, meaning when the stock rises they have to buy more, and when the stock falls they have to sell more — this *amplifies* moves. But at certain strikes, dealers are **net long gamma**, and at those strikes they hedge in the opposite direction — they *dampen* moves. Those strikes act like magnets and walls.

- **Gamma wall (positive gamma concentration):** A strike where dealer long-gamma is so concentrated that dealers will defend the level — strong support (below price) or resistance (above price).
- **Flip point:** The price level where dealers transition from net-long-gamma to net-short-gamma. Crossing the flip dramatically changes the market's behavior.

GOLIATH's premise: **identify the gamma wall on the underlying, expect the LETF to respect a price level that maps to that wall**, and structure the trade so the put spread's short strike sits below that level.

### 2.9 IV (implied volatility) and IV Rank

- **Implied volatility:** The market's forecast of how much the stock will move, expressed as annualized standard deviation. Quoted as e.g. 80% or 0.80.
- **IV Rank:** Where today's IV sits in its own 52-week range, normalized 0–100. IV Rank = 60 means today's IV is at the 60th percentile of the past year — relatively elevated.

GOLIATH only opens trades when LETF IV Rank ≥ 60. Why? Because the long call leg is funded by the put spread's premium — and premium is bigger when IV is high.

### 2.10 Open Interest (OI)

Number of outstanding open contracts at a strike. Liquidity proxy. GOLIATH requires OI ≥ 200 on every leg — below that, bid-ask spreads widen and execution is unreliable.

### 2.11 Bid, ask, mid

- **Bid:** Highest price a buyer will pay.
- **Ask:** Lowest price a seller will accept.
- **Mid:** (bid + ask) / 2 — fair-ish price.
- **Bid-ask spread:** ask − bid. Wider spread = more slippage on every fill.

GOLIATH requires `(ask − bid) ≤ 20% of mid` on every leg.

### 2.12 Defined risk vs. undefined risk

- **Defined risk:** Maximum loss is known in advance and capped (spreads).
- **Undefined risk:** Theoretically unlimited loss (naked short calls/puts).

GOLIATH is 100% defined-risk. Every position has a calculable, hard-coded worst-case dollar loss before opening.

### 2.13 The wheel strategy (and why GOLIATH replaces it on LETFs)

The classic **wheel** is: sell cash-secured puts on a stock. If assigned, hold the shares and sell covered calls. If those calls are exercised, repeat. Generates premium income.

It works on slow-moving, dividend-paying blue chips. It **doesn't work on LETFs** because:
1. Volatility drag destroys principal between premium collections.
2. LETFs don't pay dividends.
3. LETF puts are wide-bid-ask and assignment is messy.

GOLIATH is the asymmetric replacement: short put **spread** instead of naked put (defined risk), long call instead of share ownership (no decay drag), 7-day cycle instead of monthly.

---

## 3. The strategy

### 3.1 What GOLIATH does in one paragraph

Once per week, on each of 5 LETFs, GOLIATH simultaneously sells a defined-risk put credit spread (collecting premium) and buys an out-of-the-money call (uncapped upside) on the LETF, paid for by the put-spread credit. The short-put strike is placed just above a price level computed from the **underlying stock's** gamma wall — meaning: dealers' hedging behavior protects the bot's break-even level. If the LETF stays above that level by Friday, the put spread expires worthless (full credit kept) and the call is either profitable or expires worthless. If the LETF drops, the put spread caps the loss. If the LETF rallies hard, the call delivers asymmetric upside.

### 3.2 What GOLIATH does NOT do

- Does not own LETF shares (no covered calls phase, no decay drag from holding the underlying)
- Does not run iron condors on LETFs (4-leg structures have too much slippage on thin LETF chains)
- Does not roll positions (closing when wrong is mandatory; rolling is how short-vol strategies die)
- Does not trade index LETFs like TQQQ/SOXL (different strategy class entirely)
- Does not connect to IronForge or any other live-trading system in v0.2 (paper-only)

### 3.3 Cadence

| Action | Time |
|---|---|
| **Enter** | Monday 10:30–11:30 AM ET |
| **DTE on entry** | 7 (Friday expiry, same week) |
| **Mandatory close** | Thursday 3:00 PM ET (no exceptions) |

Why Monday 10:30? The first hour of the week tends to be volatile (overnight news digestion, early flow). 10:30 lets that settle but still captures the full theta-decay window into Friday.

Why mandatory close Thursday? Because 0DTE-1DTE risk on the put spread is a different beast — gamma explodes near expiry, small underlying moves become large P&L moves. We exit before that regime begins.

### 3.4 The bet, intuitively

Imagine you think a stock will probably stay flat or up by Friday, but you're not 100% sure, and if it rips you want to participate.

- Selling a put credit spread = "I'll bet you a small amount that the stock stays above $X by Friday."
- Buying a call = "And if it rips, I keep the upside."

The trick: the short-put strike is placed where dealers' positioning makes a sudden drop unlikely (the gamma wall). And the call is funded by what we collected on the put spread. Net cost of the entire bet: usually ±$5 per contract.

---

## 4. The universe — why these 5 LETFs

**5 leveraged ETFs, all 2×, all single-stock:**

| LETF | Underlying | Reasoning |
|---|---|---|
| **MSTU** | MSTR | BTC catalyst stock; primary validation target. MSTR moves on bitcoin price news. |
| **TSLL** | TSLA | Largest single-stock LETF by AUM; deepest options chain. |
| **NVDL** | NVDA | AI mega-cap; high IV around earnings; biggest volume in semi space. |
| **CONL** | COIN | Crypto exchange exposure; lower volume than TSLL/NVDL (paper cap is $150 vs $200). |
| **AMDL** | AMD | AI/semi diversifier; second-tier semi exposure. |

**Why GEX comes from the underlying, not the LETF:** Dealer hedging happens in the larger options chain. NVDA has billions of dollars of open interest — NVDL has a fraction of that. The dealer activity that creates the gamma wall is on NVDA. NVDL is just the leveraged echo.

**Why no index LETFs (TQQQ, SOXL):** Index dynamics are fundamentally different from single-name. The strategy edge depends on stock-specific catalyst-driven moves, not broad market beta.

---

## 5. The 3-leg trade structure

Every GOLIATH trade is exactly this structure. No exceptions. Ever.

| Leg | Action | Instrument | Strike rule |
|---|---|---|---|
| 1 | **SELL** | Short put on the LETF | ~25–30 delta · 7 DTE — collects premium |
| 2 | **BUY** | Long put on the LETF | 1 strike below short put · 7 DTE — caps downside |
| 3 | **BUY** | Long call on the LETF | 15–25% OTM · 7 DTE — funded by spread credit, uncapped upside |

### 5.1 Concrete worked example

Say MSTU is trading at $10.00 on Monday morning. Underlying MSTR is at $200.

GOLIATH detects a gamma wall on MSTR at $191. Through strike mapping (Section 8), it computes that the equivalent MSTU "wall" sits around $9.00.

Strike selection:
- **Short put:** $9.00 (just at/above the mapped wall) → sell at mid $0.50 → +$50 credit per contract
- **Long put:** $8.50 (one strike below) → buy at mid $0.20 → −$20 cost per contract
- **Long call:** $12.00 (20% OTM) → buy at mid $0.30 → −$30 cost per contract

**Net cost on entry:** +0.50 − 0.20 − 0.30 = $0 per contract (literally free)

**Defined max loss:** ($9.00 − $8.50) × 100 − net credit received = $50 − $0 = **$50 per contract**

**Max upside:** Theoretically unlimited (long call has no upper cap)

For 2 contracts (the GOLIATH max), this is risking $100 to potentially make multiples of that.

### 5.2 What can go right vs. wrong by Friday

| Friday outcome | What happens |
|---|---|
| MSTU above $9.00, MSTU below $12.00 | Put spread expires worthless (keep full credit); call expires worthless. **Best efficient outcome — full credit kept, no further premium spent.** |
| MSTU above $12.00 (rally) | Put spread expires worthless; long call has intrinsic value. **Asymmetric upside — could be 3×, 5×, 10× the call cost.** |
| MSTU between $8.50 and $9.00 | Short put assigned (or closed for partial loss). Long call worthless. **Loss bounded.** |
| MSTU below $8.50 (drop through long put) | Both puts ITM, the long put protects further loss. Defined max loss. **Loss capped at $50/contract regardless of how low it goes.** |

The trade is asymmetric: bounded downside, unbounded upside, near-zero entry cost.

---

## 6. Why this works (and why the standard Wheel doesn't on LETFs)

### 6.1 The Wheel on a normal stock (e.g., GOOG)

1. Sell a cash-secured put. Collect premium.
2. If put assigned, you own 100 shares at strike. Cost basis = strike − premium.
3. Sell covered calls against the shares. Collect more premium.
4. If shares called away, repeat.

Works because: GOOG doesn't have decay. Holding shares + collecting premium yields positive expected value over time.

### 6.2 The Wheel on an LETF (e.g., MSTU)

1. Sell a cash-secured put. Collect premium.
2. If assigned, you own 100 shares of MSTU.
3. **MSTU loses 1–4% per week to volatility drag** (Section 2.3). Premium income from covered calls cannot keep up. You bleed principal faster than you collect.
4. Selling the shares to exit means realizing a big loss.

Negative expected value. The Wheel structurally cannot work on LETFs because of decay mechanics.

### 6.3 GOLIATH's substitution

Replace each Wheel ingredient with a decay-free equivalent:

| Wheel ingredient | GOLIATH replacement | Why |
|---|---|---|
| Cash-secured put | **Put credit spread** | Same directional bet, but defined risk and no assignment |
| Share ownership | **Long OTM call** | Same upside participation, but expires before drag accumulates |
| Premium income | **Net credit** from the put spread funds the call | No need to hold shares |
| Monthly cycle | **Weekly cycle (7 DTE)** | Decay doesn't have time to chew through capital |

The result: same conceptual trade ("I'm bullish/neutral, want to monetize that view") but defined-risk, no decay drag, asymmetric to the upside.

---

## 7. The 10 pre-entry gates (G01–G10)

Every Monday, before any trade can fire, the bot runs all 10 gates **in sequence**. The first gate that fails stops the chain — no trade. Every failed evaluation logs to the `goliath_gate_failures` Postgres table with diagnostic data, even when no trade results. Gate failures *are* the data.

| Gate | Check | Why |
|---|---|---|
| **G01** | SPY GEX not in extreme negative regime | Don't fight a broad market in dealer-driven sell-mode |
| **G02** | Underlying GEX not in extreme negative regime | Don't fight the specific stock either |
| **G03** | Underlying has identifiable positive gamma wall below spot | If no wall, there's no level to anchor the trade — skip |
| **G04** | Underlying earnings not within 7 days | Earnings = different vol regime; the strategy isn't designed for it |
| **G05** | LETF IV Rank ≥ 60 | Premium must be elevated to fund the long call |
| **G06** | All 3 LETF strikes have OI ≥ 200 | Liquidity check — under-OI strikes have bad fills |
| **G07** | Bid-ask spread on each leg ≤ 20% of mid | Slippage protection — wide spreads kill the trade economically |
| **G08** | Net cost on entry ≤ 30% of long call cost | Spread must subsidize the call meaningfully |
| **G09** | Underlying not in active downtrend (above 50-day MA) | Trend filter — don't catch a falling knife |
| **G10** | Total open GOLIATH positions ≤ 3 across all 5 instances | Platform-wide concentration cap |

### 7.1 Gate logging behaviors (built into the orchestrator)

- `gates_passed_before_failure` lists exactly which gates passed before the first fail
- `attempted_structure` is populated when applicable (gates G06+ have a structure to fail against)
- Cold-start IV-rank case logs `INSUFFICIENT_HISTORY` (not `FAIL`) and skips the trade
- Earnings yfinance failure → fail closed (no trade); never assume safe

### 7.2 Why this matters

Master spec section 9.3: **zero successful trades in a paper-trading window is acceptable** — *if* the gate failure logs are diagnostic. The whole point of logging failures with this much detail is so we can see *why* trades didn't fire and judge whether the gates were correct.

---

## 8. Strike mapping — translating wall to LETF strikes

This is the most technically tricky part of GOLIATH. Naive linear mapping (multiply underlying wall by 2) is wrong because:

1. **2× is daily, not terminal.** Over 7 DTE, the price relationship breaks down due to drag and path dependence.
2. **Volatility drag accumulates.** The math is non-linear.
3. **Strike step sizes don't match.** TSLA strikes are $2.50; TSLL strikes are $0.50. Rounding matters.
4. **"Wall" needs a quantitative definition.** It's not just "biggest gamma" — it's gamma concentration meaningfully larger than surrounding strikes.

### 8.1 Algorithm

**Step 1 — Find the wall.** From underlying gamma levels, identify the largest *positive* gamma below current spot where:

```
gamma_at_strike ≥ wall_concentration_threshold × median_gamma_within_±5%_of_spot
```

The default `wall_concentration_threshold = 2.0×`. If no qualifying wall exists, **fail Gate G03** and return None.

**Step 2 — Vol-adjusted price mapping.** Convert the underlying wall price to an equivalent LETF target price using the calibrated formula:

```
predicted_LETF_return = leverage × underlying_return + drag_term
drag_term = -0.5 × leverage × (leverage − 1) × σ² × t × drag_coefficient
LETF_target_price = LETF_spot × (1 + predicted_LETF_return)
```

Where:
- `leverage = 2.0` (all GOLIATH LETFs are 2×)
- `σ` = annualized volatility from realized-vol window (default 20d)
- `t` = 7 days / 365 in years
- `drag_coefficient` = Phase 1.5 calibrated parameter (currently 1.0 = pure theoretical formula)

**Step 3 — Tracking error band.** Account for variance in the LETF's daily-2× promise:

```
te_band = leverage × σ × √t × √(2/3) × tracking_error_fudge
```

This produces a `[band_low, band_high]` range around the target where realized LETF prices are statistically likely to land.

**Step 4 — Select strikes from the LETF chain.** Round to valid LETF strike intervals; pick the short put just above the band, long put one strike below short, long call 15–25% OTM.

### 8.2 The four Phase 1.5 calibrated parameters

These four parameters drive Step 2 and Step 3 math. They were validated empirically in Phase 1.5 against 90 days of real data.

| Parameter | Default | Purpose |
|---|---|---|
| `wall_concentration_threshold` | 2.0× | "Is this a wall?" classifier — how much taller than median |
| `tracking_error_fudge` | 0.1 | Width of the LETF target band |
| `drag_coefficient` | 1.0 | Multiplier on the theoretical drag formula |
| `realized_vol_window_days` | 20 | Lookback for σ in the formula (Phase 1.5 changed from 30→20) |

Section 12 covers what each calibration test found.

---

## 9. The 8 exit triggers (T1–T8)

Every 15 minutes during market hours, the bot's management cycle evaluates each open position against the 8 exit triggers. The first trigger that fires takes the documented action. **No discretion. No rolling. No "maybe one more day."**

| # | Trigger | Action |
|---|---|---|
| **T1** | Long call at 3× of cost | Close call leg only; hold put spread to expiry |
| **T2** | Long call at 5× of cost | Close entire position (lock in big call win) |
| **T3** | Put spread at 50% of max profit | Close put spread; hold call (let it run) |
| **T4** | Total loss > 80% of defined max | Close everything |
| **T5** | Short put strike breached AND ≤ 3 DTE | Close everything (gamma risk too high) |
| **T6** | Material news mid-trade (manual flag) | Close everything (CLI command on Render shell) |
| **T7** | Thursday 3:00 PM ET | Mandatory close — cannot be overridden |
| **T8** | Underlying GEX flip occurred mid-trade | Re-evaluate; close if regime now adverse |

### 9.1 The state machine

`OPEN → MANAGING → CLOSING → CLOSED`

- **OPEN:** Position just filled; no triggers fired yet
- **MANAGING:** A trigger is preparing to fire (avoids race conditions)
- **CLOSING:** Broker close order submitted; awaiting fill confirmation
- **CLOSED:** Fill confirmed; realized P&L recorded; audit trail finalized

Every trigger fire logs distinctly to `goliath_trade_audit` for post-hoc analysis. Filtering closed trades by `close_trigger_id` lets us answer "do T1 closes outperform T2 closes?" — operational research as it accumulates.

### 9.2 No rolling allowed in v0.2

This is a deliberate design decision from the master spec. **Rolling is how every short-vol strategy dies.** When a put credit spread goes against you and you "roll" — closing the losing position and opening a new one further out — you're paying away premium to delay realizing the loss. If you keep rolling, eventually one tail event vaporizes everything you collected.

GOLIATH does not roll. If a trade doesn't work, it closes. Period.

---

## 10. Position sizing — two-level caps

Account starting capital: **$5,000** (the research lab assumption).

| Cap | Value | Notes |
|---|---|---|
| Per-trade defined-risk cap | **1.5% = $75** | Maximum dollar loss any single trade can cause |
| Per-instance allocation (MSTU/TSLL/NVDL) | **$200 each** | Higher-IV LETFs |
| Per-instance allocation (CONL/AMDL) | **$150 each** | Lower-volume LETFs |
| Platform total cap | **$750 (15%)** | Sum across all 5 instances |
| Max concurrent positions | **3** | Across the entire platform |
| Hard cap per trade | **2 contracts** | Even if math allows more |

### 10.1 The sizing algorithm

```
contracts_to_trade = min(
    floor(per_trade_cap / defined_max_loss_per_contract),
    floor(instance_allocation_remaining / capital_per_contract),
    floor(platform_cap_remaining / capital_per_contract),
    2_hard_cap
)
```

If the result is 0 contracts (no allocation room), the trade is **skipped**, not "let's take 1 anyway."

---

## 11. The 7 kill switches

Hard automated risk controls. Once tripped, an instance (or the entire platform) stops trading until **Leron manually clears the kill via CLI**. There is no automatic recovery.

### 11.1 Per-instance kills (kills only that LETF instance)

| Trigger | Condition |
|---|---|
| **I-K1** | Instance drawdown > 30% of allocation |
| **I-K2** | 5 consecutive losses on the instance |
| **I-K3** | 20 trades without a single upside hit (≥ +$50) |

### 11.2 Platform-wide kills (kills all 5 instances)

| Trigger | Condition |
|---|---|
| **P-K1** | Platform drawdown > 15% of total GOLIATH allocation |
| **P-K2** | Single-trade loss > 1.5× the documented defined max |
| **P-K3** | VIX > 35 sustained 3+ days |
| **P-K4** | Trading Volatility API down > 24 hours |

### 11.3 Persistence and clearing

- Kill state lives in the `goliath_kill_state` Postgres table with `active = TRUE/FALSE`
- Kill survives process restart (re-read on boot)
- Manual override CLI requires explicit confirmation prompts ("paranoia gate") to prevent accidental clears
- Every kill event logs reason, snapshot data, and timestamp to `goliath_trade_audit`

---

## 12. Phase 1.5 calibration — what was measured

Phase 1.5 was the calibration phase. We pulled 90 days of real data (5/5 underlyings + 10/10 LETF/underlying prices) on 2026-04-30 and tested whether the 4 spec defaults from Section 8.2 actually fit reality.

Each test produced a tag:
- **CALIB-OK:** Default validated — keep it
- **CALIB-SANITY-OK:** Default reasonable but not strongly tested — keep it pending more data
- **CALIB-ADJUST:** Data prefers a different value — recommend changing
- **CALIB-BLOCK:** Calibration unsuccessful (formula misspecified or insufficient data) — defer to v0.3

### 12.1 Results

| Parameter | Default | Result | Tag | Action |
|---|---|---|---|---|
| `wall_concentration_threshold` | 2.0× | Median observed: 2.14×; range 1.77×–5.93×; no outliers >3× | **CALIB-SANITY-OK** | Keep at 2.0 |
| `tracking_error_fudge` | 0.1 | Universe median ratio 0.855 (in [0.75, 1.25]); MSTU outlier 1.56× | **CALIB-OK** | Keep at 0.1 |
| `drag_coefficient` | 1.0 | Universe mean ratio 0.77; AMDL extreme outlier 0.13× (drag formula misspecified during trends) | **CALIB-BLOCK** | Keep 1.0 conservatively; defer fix to v0.3 |
| `realized_vol_window_days` | 30 | 4 of 5 LETFs had lower residual SD with 20d than 30d | **CALIB-ADJUST** | **Changed 30 → 20** |

### 12.2 What CALIB-BLOCK means for the bot

The drag-coefficient calibration failed not because the bot is broken, but because the *formula itself* is misspecified during trending markets. The theoretical formula assumes Brownian motion (zero autocorrelation in returns), but real LETF behavior diverges in trending regimes. AMDL especially: it outperformed naive 2× in 8 of 17 weeks during AMD's April rally — meaning realized drag was a fraction of theoretical drag.

Conservative response: keep `drag_coefficient = 1.0` (use full theoretical drag). This *over-estimates* drag in trending markets, which makes strike mapping place the put spread short strike slightly more conservatively than necessary. We trade smaller wins in exchange for not under-estimating drag in choppy markets.

The autocorrelation-aware estimator is tracked in `docs/goliath/goliath-v0.3-todos.md` as **V03-DRAG-AUTOCORR**. AMDL's wall behavior is also under watch as **V03-WALL-AMD-WATCH**.

### 12.3 Why MSTU's 1.56× tracking-error outlier is fine

MSTU's observed-vs-predicted tracking error ratio was 1.56× — well above the universe median of 0.855. Investigation showed this was driven by 2 specific weeks: the February BTC dump and the April MSTR moonshot. Both were exactly the kind of single-stock catalyst events the strategy is designed to monetize. Not a bug — the strategy actively wants this signal. Keep MSTU at default.

---

## 13. Architecture and build phases

### 13.1 What runs where on Render

```
┌────────────────────────────────────────────────────────────────┐
│  RENDER (cloud platform)                                       │
│                                                                │
│  ┌──────────────────┐   ┌─────────────────┐   ┌─────────────┐ │
│  │ alphagex-api     │   │ alphagex-trader │   │ alphagex-db │ │
│  │ (FastAPI web)    │   │ (worker)        │   │ (Postgres)  │ │
│  │                  │   │                 │   │             │ │
│  │ Hosts /goliath/* │   │ Runs entry      │   │ goliath_*   │ │
│  │ dashboard API    │   │ + management    │   │ tables      │ │
│  │                  │   │ cycles          │   │             │ │
│  └──────────────────┘   └─────────────────┘   └─────────────┘ │
└────────────────────────────────────────────────────────────────┘
         │                          │                    │
         ▼                          ▼                    │
   ┌──────────┐             ┌────────────┐               │
   │ Vercel   │             │ Tradier +  │               │
   │ frontend │             │ TV API +   │               │
   │ /goliath │             │ yfinance   │───────────────┘
   └──────────┘             └────────────┘
```

- **alphagex-api:** Hosts the FastAPI HTTP routes for the dashboard. Read-only for GOLIATH.
- **alphagex-trader:** The worker process. Runs APScheduler-based cron: entry cycle Mon 10:30 ET, management cycle every 15 minutes during market hours.
- **alphagex-db:** Single Postgres database shared across all AlphaGEX bots. GOLIATH tables are prefixed `goliath_*`.
- **Vercel:** Hosts the Next.js frontend that calls the API.

### 13.2 Build phases

| Phase | Topic | Status | Artifact |
|---|---|---|---|
| 0 | Investigation & spec recovery | Done | `GOLIATH-MASTER-SPEC.md` |
| 1 | Trading Volatility API smoke test | Done | TV client validated |
| 1.5 | Parameter calibration (Steps 1–10) | **Done** | `goliath-calibration-results.md` |
| 2 | Strike mapping (4 modules + 13 tests) | Done | `trading/goliath/strike_mapping/` |
| 3 | 10 entry gates + orchestrator | Done | `trading/goliath/gates/` + migration 028 |
| 4 | 8 exit triggers + state machine + CLI | Done | `trading/goliath/management/` + migrations 029–030 |
| 5 | Sizing + 7 kill switches + persistence | Done | `trading/goliath/sizing/` + `kill_switch/` |
| 6 | Engine, instance, runner, audit log | Done | `trading/goliath/engine.py` + `main.py` + migration 031 |
| 7 | Monitoring (Discord, heartbeat, alerts) | Done | `trading/goliath/monitoring/` |
| α (PR-α) | Paper executor + scheduler + Tradier wiring | Done | `trading/goliath/broker/paper_executor.py` |
| β (PR-β) | UI dashboard (13 endpoints + 6 tabs) | **Done** | `backend/api/routes/goliath_routes.py` + `frontend/src/app/goliath/` |
| 9 | Paper trading 2+ weekly cycles | **In progress** | (data accumulating) |
| → v0.3 | Drag autocorr fix, AMDL watch, live unlock | TODO | `goliath-v0.3-todos.md` |

### 13.3 Key code locations

```
trading/goliath/
├── configs/                # Per-instance + global config
├── strike_mapping/         # Wall finder, LETF mapper, leg builder, engine
├── gates/                  # G01..G10 pre-entry gates + orchestrator
├── management/             # T1..T8 exit triggers + state machine + CLI
├── sizing/                 # Position sizing math
├── kill_switch/            # 7 kill triggers + persistence + CLI paranoia gate
├── audit/                  # Recorder + replayer for goliath_trade_audit
├── monitoring/             # Discord webhook, heartbeat, alert composers
├── data/                   # Tradier snapshot builder
├── broker/                 # Paper executor (simulates fills at Tradier mids)
├── calibration/            # Phase 1.5 calibration scripts
├── instance.py             # GoliathInstance — stateful per-LETF wrapper
├── engine.py               # GoliathEngine — stateless decision logic
├── main.py                 # Runner — entry + management cycles
├── equity_snapshots.py     # Periodic equity-curve writer
└── models.py               # GoliathConfig dataclass

scheduler/goliath_scheduler.py  # APScheduler hook into alphagex-trader

backend/api/routes/goliath_routes.py  # 13 dashboard endpoints

frontend/src/app/goliath/
├── page.tsx                # dynamic() loader
└── GoliathContent.tsx      # 6-tab dashboard

db/migrations/
├── 028_goliath_gate_failures.sql
├── 029_goliath_news_flags.sql
├── 030_goliath_kill_state.sql
├── 031_goliath_trade_audit.sql
├── 032_goliath_paper_positions.sql
└── 033_goliath_equity_snapshots.sql

scripts/
├── apply_goliath_migrations.py    # Idempotent migration runner
└── verify_goliath_deployment.py   # One-command deployment health check
```

---

## 14. Operations and monitoring

### 14.1 Dashboard URLs

- **Frontend:** `https://<your-vercel-domain>/goliath`
  - 6 tabs: Overview, Positions, Performance, Audit, Kills, Config
  - Instance selector at the top: PLATFORM (aggregate) or any of the 5 LETFs
- **API base:** `https://alphagex-api.onrender.com/api/goliath/*`
  - 13 read-only endpoints (status, positions, equity-curve, performance, audit, etc.)

### 14.2 Database tables

| Table | Purpose | Writer |
|---|---|---|
| `goliath_paper_positions` | Current + historical position state | broker.paper_executor |
| `goliath_trade_audit` | Append-only event log (every entry eval, fill, mgmt eval, exit) | audit.recorder |
| `goliath_gate_failures` | Why each rejected entry was rejected | gates.orchestrator |
| `goliath_kill_state` | Active + cleared kills | kill_switch.state |
| `goliath_news_flags` | Manual T6 news flags | management.cli |
| `goliath_equity_snapshots` | Periodic equity points (per management cycle) | equity_snapshots.py |

### 14.3 Verification

After deploy, run on any alphagex-* Render shell:

```bash
python scripts/verify_goliath_deployment.py
# or with live API check:
python scripts/verify_goliath_deployment.py --hit-api https://alphagex-api.onrender.com
```

Reports green/red on: DATABASE_URL connectivity, all 6 GOLIATH tables present, DISCORD_WEBHOOK_URL set, trading.goliath imports, scheduler hook callable, routes module loads, and (optionally) live `/api/goliath/status` returns 5 instances.

### 14.4 Monitoring channels

- **Discord webhook (`DISCORD_WEBHOOK_URL` env var):** Best-effort alerts on entry fill, kill activation, TV API failure spike. Set on `alphagex-trader` Render service.
- **Postgres heartbeat (`bot_heartbeats` table):** Every entry + management cycle UPSERTs a row; the dashboard `/status` endpoint reads it.
- **Audit log:** Every decision is in `goliath_trade_audit`, replayable via `trading.goliath.audit.replayer`.

### 14.5 Runbook

Full operational runbook: `docs/goliath/RUNBOOK.md` — 13 sections covering cold start, post-crash restart, manual kill activation, kill clear (paranoia-gated), TV API token rotation, news flag CLI, alert response, etc.

---

## 15. What's left — v0.3 and live unlock

### 15.1 v0.3 backlog

Tracked in `docs/goliath/goliath-v0.3-todos.md`:

- **V03-DRAG-AUTOCORR** — Replace theoretical drag formula with autocorrelation-aware estimator. The current formula systematically over-estimates drag in trending markets (AMDL was 0.13× expected during AMD rally).
- **V03-WALL-AMD-WATCH** — Monitor AMDL paper-trading; if wall-tracking remains broken across more weeks, may need per-instance wall threshold override.
- **V03-WALL-RECAL** — True distribution-based wall threshold validation (current sample only n=5).
- **V03-DATA-1** — Strike snapshot collector (additive; accumulates richer data for future recalibration).
- **V03-IV-RANK-COLD-START** — Better fallback than `INSUFFICIENT_HISTORY` skip when IV history is short.

### 15.2 What flips GOLIATH from v0.2 (paper) to v0.3 (live unlock candidacy)

Per master spec section 11–12:

1. **v0.3 backlog items resolved** (drag estimator + AMDL watch in particular)
2. **Phase 9 paper-trading data accumulated** — minimum 2 full weekly cycles with diagnostic gate-failure logs (zero successful trades acceptable if logs are diagnostic)
3. **Q3 sign-off** — explicit Leron approval to deploy real capital
4. **No critical bugs surface** during paper window

Until all 4 land, every instance has `paper_only = True` in its config, the broker executor refuses to fake live fills, and the dashboard shows the "PHASE 1.5 · PAPER" banner.

---

## 16. References — where to find things in the code

### 16.1 If you want to understand a specific behavior

| Question | Look here |
|---|---|
| "What does the bot do at 10:30 Monday?" | `scheduler/goliath_scheduler.py` → `add_goliath_jobs()` → `run_entry_cycle` |
| "How does it decide whether to enter?" | `trading/goliath/gates/orchestrator.py` |
| "Why didn't this entry fire?" | Postgres: `SELECT * FROM goliath_gate_failures ORDER BY timestamp DESC LIMIT 10;` |
| "How are strikes picked?" | `trading/goliath/strike_mapping/engine.py` |
| "Why did this position close?" | `goliath_paper_positions.close_trigger_id` (T1..T8 or MANUAL) |
| "What's the full lifecycle of a position?" | `SELECT * FROM goliath_trade_audit WHERE position_id = '...';` |
| "Is the bot alive?" | `bot_heartbeats` table or `/api/goliath/status` |

### 16.2 If you want to change a parameter

| Change | Edit |
|---|---|
| Per-instance allocation cap | `trading/goliath/configs/instances.py` |
| Wall threshold / drag / fudge / vol window | `trading/goliath/models.py` (the GoliathConfig defaults) |
| Cycle cadence (entry day/time, management interval) | `scheduler/goliath_scheduler.py` |
| Add a new LETF instance | `trading/goliath/configs/instances.py` + dashboard `_INSTANCES` list in `goliath_routes.py` |

### 16.3 Reference docs in the repo

- `docs/goliath/GOLIATH-MASTER-SPEC.md` — 433-line recovered v0.2 master spec with verbatim source-chat content
- `docs/goliath/GOLIATH-PHASE-1.5-RECOVERY.md` — Phase 1.5 specification + 10-step build order
- `docs/goliath/goliath-calibration-results.md` — Real-data calibration output with per-pair numbers
- `docs/goliath/goliath-v0.3-todos.md` — v0.3 backlog with categorized items
- `docs/goliath/RUNBOOK.md` — 13-section operational runbook
- `docs/goliath/GOLIATH-COMPLETE-GUIDE.md` — **this document**

---

## Appendix A — A worked example, end to end

Imagine it's Monday May 4, 2026, 10:30 AM ET. The bot wakes up.

**Cycle 1 — GOLIATH-MSTU**

1. `monitoring.heartbeat.record_heartbeat("GOLIATH-MSTU", "OK", {"cycle": "entry"})` → upserts a row.
2. Instance is not killed (`kill_switch.is_killed("GOLIATH-MSTU")` returns False).
3. `data.tradier_snapshot.build_market_snapshot(instance)` → fetches MSTU option chain from Tradier, MSTR GEX from TV API, MSTR/MSTU spot from yfinance.
4. `engine.evaluate_entry(instance, snapshot, platform_context, now)`:
   - Gate G01 — SPY GEX OK ✓
   - Gate G02 — MSTR GEX OK ✓
   - Gate G03 — Wall found at $191 (gamma 8.0 ≥ 2.0× median 1.0) ✓
   - Gate G04 — MSTR earnings 14 days away ✓
   - Gate G05 — MSTU IV Rank 72 ≥ 60 ✓
   - Gate G06 — Strike OI all ≥ 200 ✓
   - Gate G07 — Bid-ask all ≤ 20% mid ✓
   - Gate G08 — Net cost $0 ≤ 30% × $30 call cost ✓
   - Gate G09 — MSTR above 50DMA ✓
   - Gate G10 — Total platform open positions 1 ≤ 3 ✓
   - All 10 pass → returns `EngineEntryDecision(approved=True, contracts_to_trade=2, structure=...)`
5. `audit_recorder.record_entry_eval(...)` writes the full gate chain + structure to `goliath_trade_audit`.
6. `broker.paper_executor.paper_broker_executor(instance, decision)`:
   - Generates `position_id = "goliath-paper-abc123…"`
   - INSERTs row into `goliath_paper_positions` (state=OPEN, entry_short_put_mid=0.50, etc.)
   - Records `ENTRY_FILLED` audit event
   - Appends to `instance.open_positions`
   - Returns position_id
7. `monitoring.alerts.alert_entry_filled(...)` posts to Discord webhook (best-effort).

**Cycle 2 — Management at 10:45 AM** (15 min later)

1. Heartbeat upsert.
2. `engine.manage_open_positions(instance, now)`:
   - Position has been open 15 min; Long call P&L is +12% (not 3× yet → T1 not fired)
   - Put spread at 5% of max profit (not 50% → T3 not fired)
   - Total P&L within bounds → no triggers
   - Returns empty actions list
3. `equity_snapshots.write_snapshots(instances)` → INSERTs PLATFORM + GOLIATH-MSTU rows.

**Cycle 14 — Thursday 3:00 PM ET**

1. Position has been alive for 4 days. MSTU rallied to $11.50.
2. Long call cost $0.30 → now worth $1.80 → 6× of cost → T2 fires (5× threshold passed).
3. Action: close entire position.
4. Close fills at Tradier mids: short put closes at $0.05 (cost +$45 vs entry credit $50), long put $0.02 (cost +$2), long call $1.80 (gain $150).
5. Realized P&L: 50 − 5 − (−2 + 20) − (−180 + 30) = ~$157 per contract × 2 contracts = **+$314** for this position.
6. UPDATE `goliath_paper_positions` SET state='CLOSED', close_trigger_id='T2', realized_pnl=314.0.
7. Audit `EXIT_FILLED` event written.
8. Position cleared from `instance.open_positions`.

This whole flow is replayable from the audit log. Every decision was logged before, during, and after.

---

*End of document.*
