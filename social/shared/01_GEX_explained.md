# GEX / Gamma Exposure — The Core Idea (Shared Knowledge)

This is the single most important concept behind both products. The avatar must be
able to explain it at three depths — to a total beginner, to an options trader, and
to a quant — and never get the mechanics wrong. Getting GEX subtly wrong is the
fastest way to lose credibility with the audience that matters.

---

## Layer 1 — The plain-English version (for a beginner / non-trader)

Big banks and trading firms ("market makers") sell options to retail traders. When
they do, they don't want to gamble on which way the market goes — they want to stay
neutral. So they constantly buy and sell the underlying stock/index to cancel out
their risk. This is called **hedging**.

The punchline: **their hedging is forced, mechanical, and predictable.** It happens
at roughly the same price levels every day because that's where the options are.

So a lot of "random" market behavior isn't random at all — it's the footprint of
dealers hedging billions of dollars. **GEX (Gamma Exposure) is the map of where that
hedging pressure builds up.** If you know the map, you can position *with* the dealers
instead of getting run over by them.

> One-liner the avatar can reuse:
> *"The market makers aren't your enemy. They're the biggest, most predictable player
> at the table — once you can see what they're forced to do."*

---

## Layer 2 — The mechanics (for an options trader)

**Gamma** measures how fast an option's delta changes as the underlying moves.
**Gamma Exposure (GEX)** aggregates that across all the open options on a ticker to
estimate how dealers are positioned, and therefore how they'll be forced to hedge.

### The two regimes (memorize these — they drive everything)

| Regime | Dealer position | What dealers are forced to do | Market behavior | Best strategies |
|---|---|---|---|---|
| **Positive GEX** | Dealers are **long gamma** | They **buy dips, sell rips** (hedging dampens moves) | **Mean reversion** — price gets "pinned," ranges tighten | Premium selling: Iron Condors, butterflies, calendars |
| **Negative GEX** | Dealers are **short gamma** | They **sell dips, buy rips** (hedging amplifies moves) | **Trending / momentum** — moves accelerate, vol expands | Directional / debit, smaller premium-selling size |

The intuition: in **positive gamma**, dealer hedging is a shock absorber — it pushes
price back toward where the options are. In **negative gamma**, dealer hedging is an
accelerator — it pours gas on whatever direction price is already going. This is why
"calm, boring, pinned" days and "everything's falling apart" days *feel* so different.

### The key levels

- **GEX Flip Point** — the price level where net gamma flips from positive to
  negative. Above it, mean-reversion edge. Below it, momentum/trend edge. It's the
  single most important line on the map.
- **Call Wall** — the strike with the largest call gamma above price. Acts as
  **resistance / a ceiling magnet** — price often gets pulled up toward it and stalls.
- **Put Wall** — the strike with the largest put gamma below price. Acts as
  **support / a floor magnet**.
- **Magnets / Pin Strikes** — high-gamma strikes that price tends to gravitate to and
  "pin" near, especially into expiration (gamma is highest at expiry).

### Why expiration day (0DTE) is special

Gamma is largest right before expiration. On 0DTE (zero days to expiration), tiny price
moves cause huge delta changes, so dealer hedging is most intense — pinning is
strongest in positive gamma, and breakdowns are most violent in negative gamma. This
is exactly why both products focus on short-dated SPY strategies and treat 0DTE with
respect (and bigger guardrails).

---

## Layer 3 — How we actually use it (for a quant / power user)

GEX is computed from the full options chain (open interest × gamma per strike,
signed by dealer positioning assumptions) and is refreshed throughout the day. On top
of the raw levels, the parent engine (**AlphaGEX**) layers market-structure signals
that compare today vs. the prior session:

- **Flip point** rising / falling / stable → dealers repositioning
- **±1 standard-deviation bounds** shifting up / down → changing price expectations
- **Range width** widening / narrowing → vol expansion vs. contraction
- **Gamma walls** — which wall is closer (asymmetric risk)
- **Gamma regime** — mean-reversion vs. momentum (the IC-safety switch)
- **Wall-break risk** — how close price is to punching through a wall

Layered on top is **VIX regime** for position-sizing context:

| VIX | Regime | Posture |
|---|---|---|
| < 15 | LOW | Favor directional; premium is thin |
| 15–22 | NORMAL | Sweet spot for Iron Condors / premium selling |
| 22–28 | ELEVATED | Widen strikes, trim size |
| 28–35 | HIGH | Cut size ~50% |
| > 35 | EXTREME | Skip Iron Condors |

> **Honesty rule for the avatar:** GEX is an *edge and a map, not a crystal ball.* It
> tells you the terrain and the odds, not the outcome. It cannot predict black swans,
> gap risk, or surprise headlines. Never imply GEX "guarantees" anything. The honest
> framing — "stack probabilities, manage risk, survive to compound" — is more credible
> *and* more compliant than hype.

---

## The relationship between the brands and GEX

- **AlphaGEX** is the parent research engine — it computes the GEX map and the ML/AI
  signal layer. Think of it as the brain.
- **Iron Forge** is a focused product that runs **Iron Condor bots** on SPY, built on
  the same GEX philosophy.
- **Spreadworks** is **explicitly "powered by AlphaGEX GEX data"** — its analyzer and
  bots use GEX flip points and walls to suggest strikes.

So GEX is the common thread the avatar can always pull on, regardless of which product
it's posting about.

---

## Common misconceptions to correct (great content angles)

1. **"Support/resistance is just chart lines."** → Often it's a put/call wall; there's
   a mechanical reason it holds.
2. **"GEX predicts direction."** → No. It tells you the *regime* (trend vs. chop) and
   where the magnets are. Direction still needs a thesis.
3. **"0DTE is gambling."** → It's high-gamma; it's the most *structured* day if you
   respect the regime and size correctly. Disrespect it and yes, it's gambling.
4. **"More indicators = more edge."** → The whole origin story is the opposite:
   stripping away 47 indicators and watching dealer flow instead.
