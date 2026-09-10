# Spreadworks — Product Knowledge (Project B)

Everything the avatar needs to talk about Spreadworks accurately. Sources of truth:
`spreadworks/README.md`, `spreadworks/backend/bots/registry.py`, and the brand book
referenced in `spreadworks/backend/brand.py`. If a number here conflicts with the code,
the code wins — flag it to the founder.

---

## What Spreadworks is (one paragraph)

Spreadworks is a **GEX-powered spread-trading toolkit** with three parts: (1) a
**spread analyzer** for building and visualizing Double Diagonals and Double Calendars
(and seeing their payoff, Greeks, and probability of profit); (2) a set of **four
autonomous paper-trading bots** that run defined-risk spread strategies on SPY; and (3)
a **Discord community engine** that ships a daily market brief, a `/spread` command, and
a steady stream of trading education. It is **explicitly "powered by AlphaGEX GEX
data"** — flip points and walls drive its strike suggestions. Where Iron Forge is a
*watch-the-bots* story, Spreadworks is a *tool + community* story.

**Theme:** water / weather / flow. Bots are named BREEZE, TIDE, DRIFT, FLOW. The
metaphor — *reading the market's currents, going with the flow instead of fighting it* —
maps perfectly onto the "trade with the dealers" thesis.

---

## Part 1 — The spread analyzer

A builder for two multi-leg, time-based options strategies:

- **Double Diagonal** — 4 strikes (long put, short put, short call, long call) across
  **2 expirations**. Blends calendar (time-decay) and vertical (directional) behavior.
- **Double Calendar** — 2 strikes (a put, a call) across **2 expirations** (a near-dated
  "front" and a longer-dated "back"). Profits from time decay within a stable range.

**Three input modes:**
1. **Live Chain** — pulls real expirations and strikes from Tradier.
2. **Manual** — type in strikes and dates directly.
3. **GEX Suggest** — *the differentiator.* Auto-fills strikes from AlphaGEX GEX levels
   (flip point, call/put walls, gamma regime). This is "build your spread around where
   the dealers are."

**What it shows:** payoff diagram, max profit / max loss, breakevens, the Greeks,
probability of profit, a leg-by-leg breakdown, live candles (1-min refresh), the GEX
levels (flip point, call/put walls, gamma regime), and price alerts (polled every 15s
with toast notifications).

> Content gold: the GEX-Suggest feature is a perfect "show, don't tell" demo of the
> whole GEX thesis — pick a symbol, and the tool places your spread's edges at the
> walls. Screen recordings of this are premium short-form content.

---

## Part 2 — The four bots

All four trade **SPY**, start at **$10,000 paper**, deploy **~50% of buying power** per
trade (uncapped contract count — size scales with risk), entry window **8:35 AM–2:00 PM
CT** (FLOW 8:30), **EOD close 2:45 PM CT**, and can optionally use GEX walls for strikes
and send Discord alerts. They differ by strategy:

| Bot | Strategy | DTE | What it is |
|---|---|---|---|
| **BREEZE** | **Iron Butterfly** | 0DTE | Short strikes at-the-money, defined-risk wings. Most premium, narrowest profit zone. The 0DTE specialist. |
| **TIDE** | **Double Calendar** | 1DTE front / 14DTE back | Sells the front, owns the back, at a put and a call strike. Time-decay + range. PT 50%. |
| **DRIFT** | **Double Diagonal** | 1DTE front / 14DTE back | Like TIDE but with offset strikes — a blend of calendar and directional. PT 50%. |
| **FLOW** | **Iron Condor** | 1DTE | Ported from Iron Forge's SPARK (SD 1.2×, $5 wings, PT 30%, SL 50% of max profit, VIX≤32). The familiar range-seller. |

> Content gold: the four bots = four different *ways to play a range*, each with a
> different risk/reward shape. That's an entire educational series — "four ways to fish
> the same water."

---

## Part 3 — The Discord community engine

Spreadworks ships a genuine community/education layer (this is the heart of the
Spreadworks audience strategy):

- **`/spread` command** — `/spread` returns a default SPY Double Diagonal suggestion;
  `/spread symbol:QQQ strategy:double_calendar` customizes it. Returns a clean embed
  with GEX levels, suggested strikes, and the rationale.
- **Daily market brief** with a deliberate rhythm:
  - **Market open:** an **encouraging Bible verse** (125+ in rotation — courage,
    trust, discipline themes).
  - **Throughout:** a rotating **trading tip** (155+ tips across 14 categories: entry
    timing, IV/IV-rank, strike selection, DTE management, GEX, risk, psychology, etc.).
  - **A daily engagement prompt** (21 in rotation) to spark conversation —
    "Iron Condor or Double Diagonal for this week's range — defend your pick."
  - **Economic-event intelligence** — per-event historical patterns (FOMC, CPI, NFP,
    etc.): typical pre-event lean, reversal risk, average move. Framed as *typical
    behavior, not predictions.*
  - **Market close:** a **reflective, gratitude/discipline message** (130+ in
    rotation) — "Did I follow my plan today?" energy.
- **Price alerts** with notifications.

> This content engine is basically a ready-made social-media content library. The
> verses, tips, engagement prompts, close messages, and event intel can be repurposed
> (with attribution to the brand voice) into X posts, carousels, and Discord-to-public
> cross-posts.

---

## Brand / design system (so visual content stays on-brand)

From the Spreadworks brand book (`brand.py` / the design system):
- **Colors:** electric blue `#3B82F6` (primary/neutral/info); green `#22C55E` (PUT side
  / long / profit / bullish); red `#EF4444` (CALL side / short / loss / bearish); GEX
  yellow `#EAB308` (flip point / medium-impact event); muted gray `#4B5563`.
- **Typography:** numbers are **monospaced**; metric **labels are UPPERCASE**,
  letter-spaced; clean middle-dot ` · ` separators.
- **No emoji in the working UI** (emojis live in the Discord brief embeds, not the app
  chrome). Keep product screenshots clean and serious.

> Note the deliberate color convention: **PUT = green, CALL = red.** That's the
> opposite of "green=up." It's tied to side/long/profit, not direction. Don't mislabel
> it in graphics.

---

## What's real vs. simulated (state clearly, always)

- **Real:** market data, option chains, GEX levels, the analyzer math, the Greeks/P(profit).
- **Simulated:** the bots' fills/execution — **paper accounts, no real money.**
- The analyzer is a *tool* (it computes; it doesn't place trades). The bots are paper.
  Never present bot paper results as live returns.

---

## How Spreadworks relates to the bigger picture

- **Powered by AlphaGEX GEX data** — the analyzer and GEX-Suggest pull flip points and
  walls from the parent engine. This is the cleanest place to *demonstrate* GEX.
- Sibling product: **Iron Forge** (autonomous Iron Condor bots). FLOW is literally
  ported from Iron Forge's SPARK. Cross-reference via the website hub.
- Deployed as three Render services: frontend (the app), backend (calc + GEX proxy +
  alerts), and the Discord bot.

---

## Talking points & angles unique to Spreadworks

- **"Build your spread around the dealers"** — the GEX-Suggest demo; show the tool
  placing strikes at walls.
- **"Four ways to play a range"** — BREEZE/TIDE/DRIFT/FLOW as a teaching series.
- **Calendars & diagonals demystified** — these are *under-taught* strategies; owning
  this education is a real positioning wedge vs. the saturated Iron-Condor content.
- **The community rhythm** — verse at open, tip midday, reflection at close; discipline
  and gratitude as a daily practice. Strong, differentiated, human.
- **Probability of profit & payoff visualization** — teach people to *see* a trade's
  shape before risking anything.

## Facts the avatar must NOT get wrong

- Spreadworks = analyzer **+** 4 paper bots **+** Discord community.
- Bots: **BREEZE** (Iron Butterfly 0DTE), **TIDE** (Double Calendar), **DRIFT** (Double
  Diagonal), **FLOW** (Iron Condor 1DTE). Don't confuse these with Iron Forge's
  FLAME/SPARK/INFERNO.
- Analyzer strategies are **Double Diagonal** and **Double Calendar** (Live Chain /
  Manual / **GEX Suggest** modes).
- Powered by AlphaGEX GEX data. Color rule: **PUT=green, CALL=red.**
- Bots are **paper**; the analyzer is a calculator, not an order router. Not a signal
  service.
