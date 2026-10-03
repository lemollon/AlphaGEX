# Glossary — Terms the Avatar Must Use Correctly (Shared Knowledge)

If the avatar uses any of these terms, it uses them like a practitioner, not a
buzzword. Wrong usage = instant credibility loss with the target audience. Definitions
are written so they can be dropped into a post and lightly edited.

## GEX / gamma terms

- **Gamma** — How fast an option's delta changes as the underlying moves. High gamma =
  delta swings fast = hedging is twitchy.
- **GEX (Gamma Exposure)** — Aggregate measure of dealer gamma positioning across the
  options chain. Tells you whether dealer hedging will *dampen* (positive GEX) or
  *amplify* (negative GEX) price moves.
- **Positive GEX / long-gamma regime** — Dealers buy dips and sell rips. Mean
  reversion, pinning, tight ranges. Friendly to premium sellers.
- **Negative GEX / short-gamma regime** — Dealers sell dips and buy rips. Trending,
  accelerating moves, vol expansion. Friendly to directional plays; dangerous for
  naked premium selling.
- **Flip point** — Price level where net GEX flips sign. The dividing line between
  mean-reversion territory and momentum territory.
- **Call wall** — Largest call-gamma strike above price; acts as resistance/ceiling.
- **Put wall** — Largest put-gamma strike below price; acts as support/floor.
- **Magnet / pin strike** — High-gamma strike price tends to gravitate to and stall
  near, strongest into expiration.
- **Pinning** — Price getting "stuck" near a high-gamma strike because dealer hedging
  keeps pulling it back.

## Volatility terms

- **IV (Implied Volatility)** — The market's priced-in expectation of future movement.
  Higher IV = richer option premium.
- **IV Rank / IV Percentile** — Where current IV sits vs. its own past year. High IV
  Rank (>50) favors selling premium; low (<20) favors buying it.
- **VIX** — The market's 30-day implied-vol gauge for the S&P 500. Used here as a
  regime/sizing dial (see GEX doc table).
- **Expected move** — The ±range the options market is pricing for a period (roughly
  one standard deviation). Selling strikes outside it ≈ ~68% odds, all else equal.
- **IV crush** — The collapse in IV after a known event (earnings, FOMC), which
  benefits premium sellers who positioned before it.
- **Theta** — Time decay; how much an option loses per day from time passing. The
  premium seller's tailwind.
- **Gamma risk** — The danger that a fast move blows past your short strikes faster
  than theta can pay you. Worst on 0DTE.

## Strategy terms (these are what the bots trade)

- **Iron Condor (IC)** — Sell an out-of-the-money put spread *and* call spread
  simultaneously. Profits if price stays in a range. Iron Forge's core strategy; also
  Spreadworks' FLOW bot.
- **Iron Butterfly** — Like an Iron Condor but the short strikes are at-the-money
  (same strike). More premium, narrower profit zone. Spreadworks' BREEZE bot.
- **Double Calendar** — Sell near-dated options and buy longer-dated options at two
  strikes (a put strike and a call strike). Profits from time decay + a stable-to-
  rising-IV range. Spreadworks' TIDE bot.
- **Double Diagonal** — Like a double calendar but the long and short strikes differ;
  blends calendar (time) and vertical (directional) characteristics. Spreadworks'
  DRIFT bot.
- **Credit spread** — Net premium received at entry; you want the options to expire
  worthless. (The IC is two credit spreads.)
- **Debit spread** — Net premium paid at entry; directional, you want the underlying
  to move your way.
- **Wing / spread width** — Distance between the short and long strike of a spread
  (e.g., $5-wide). Defines max loss.
- **DTE (Days To Expiration)** — 0DTE = expires today, 1DTE = tomorrow, 2DTE, etc.
  Shorter DTE = more theta but more gamma risk.
- **Breakeven** — Underlying price(s) at which the position's P&L is zero at expiration.
- **Max profit / max loss** — The defined best- and worst-case outcomes of a
  defined-risk spread.

## Execution / account terms

- **Paper trading** — Simulated trading with real market data but no real money. Both
  products run paper accounts (currently). This is stated honestly, never hidden.
- **Tradier** — The brokerage/market-data API both products use for live quotes and
  option chains.
- **MTM (Mark-to-Market)** — Valuing an open position at the current market price.
- **PDT (Pattern Day Trader)** — FINRA rule (4210): an account under $25k is limited to
  ~4 day trades per 5 rolling business days. Iron Forge enforces this in its bots.
- **Profit target (PT)** — The % of max profit at which a bot closes a winner early
  (e.g., 30%).
- **Stop loss (SL)** — The loss threshold at which a bot exits (e.g., 2× the credit).
- **EOD close** — Forced flatten of positions before market close so nothing is held
  overnight (critical for 0DTE/1DTE).
- **Kelly criterion / Kelly sizing** — A position-sizing formula based on win
  probability and reward/risk. Iron Forge's SPARK/INFERNO use a clamped half-Kelly.
- **Buying power (BP)** — Capital available to open new positions; sizing is a % of it.

## Brand / system terms

- **AlphaGEX** — The parent engine that computes GEX + ML/AI signals. The brain behind
  both products.
- **Build in public** — The content philosophy: share the wins, losses, and lessons
  transparently, in real time, with no fake P&L.
- **Market maker / dealer** — The institutional liquidity provider whose forced
  hedging GEX maps. The recurring "character" in the content.

> Style note: spell out an acronym on first use in a post when writing for a broad
> audience (LinkedIn, YouTube). On X/Twitter and in Discord, the audience is fluent —
> bare acronyms are fine.
