# VALOR contract-specific research results — 2026-09-23

## Data used

- Archived VALOR scan tape: 27 trading days, 2026-08-23 through 2026-09-22.
- Approximate per-contract round-trip costs used in point terms:
  - MES 1.10
  - MNQ 2.00
  - MGC 0.50
  - NG 0.032
  - RTY 0.80
  - CL 0.05
- Entries were de-overlapped by allowing one entry per tested holding-horizon bucket.
- First/second-half split used 2026-09-08 as the boundary.
- Results are research evidence only; they are not a live-trading certification.

## Key structural findings

1. Fixed proxy-to-futures GEX level scaling produces persistent one-sided directional bias.
2. Zero-gamma flip is often many ATRs from futures price and is not a suitable universal mean-reversion target.
3. Current no-loss trailing uses raw entry as breakeven rather than fee/slippage-adjusted breakeven.
4. Strategy edge is strongly instrument-, session-, and gamma-regime-dependent.

## Contract results

### MNQ — strongest candidate

Best robust segment: RTH + POSITIVE gamma using existing VALOR direction.

Non-overlapping results after modeled costs:

- 60 min:
  - first half: +$1,059.75, 46 trades, 52.2% WR, PF 1.52
  - second half: +$1,605.50, 27 trades, 63.0% WR, PF 3.86
- 120 min:
  - first half: +$1,366.00, 29 trades, 58.6% WR, PF 1.90
  - second half: +$1,879.25, 13 trades, 61.5% WR, PF 5.96
- 180 min:
  - first half: +$624.25, 19 trades, 57.9% WR, PF 1.55
  - second half: +$1,294.50, 11 trades, 63.6% WR, PF 3.90
- 240 min:
  - first half: +$1,611.00, 17 trades, 58.8% WR, PF 3.25
  - second half: +$1,651.00, 9 trades, 55.6% WR, PF 4.78

RTH NEGATIVE gamma was unstable and strongly negative in the second half. Overnight NEGATIVE gamma also failed the second half.

Research recommendation: trade MNQ only in positive gamma initially; use 120-minute research horizon as the balanced starting point; disable SAR and use fee-aware trailing/exit logic.

### MES — current universal logic not ready

RTH POSITIVE gamma was negative in both halves at every 60/120/180/240-minute horizon.

RTH NEGATIVE gamma was promising in the recent half, but the earlier-half sample was too small for confidence. 240-minute de-overlapped sample:
- first half: only 2 trades, +$84
- second half: 8 trades, +$383.50, 62.5% WR, PF 3.29

Overnight regimes changed sign between halves and were not stable.

Research recommendation: do not promote a new MES live rule yet. Disable the current positive-gamma flip fade in research and continue with wall/rejection and futures-native trend candidates. Do not simply reverse every MES signal.

### MGC — profitable live control, but regime-dependent

Current fresh-paper sample is profitable, so MGC remains the control instrument.

Archived de-overlapped tests show:
- RTH POSITIVE gamma: consistently negative across both halves.
- RTH NEGATIVE gamma: positive at 60/120 minutes in the first half, near-flat to weak in the second.
- Overnight POSITIVE gamma: strong recent performance, but first-half 120-minute result was negative.

Research recommendation: keep MGC as the control while adding a hard RTH-positive-gamma block in the research variant. Do not broadly rewrite its signal engine yet.

### RTY / M2K — no robust edge after costs

Across session/regime/horizon combinations, the existing signal was generally negative after modeled costs in both halves. Occasional positive cells did not persist.

Research recommendation: stop using GEX direction as the primary RTY entry. Retain IWM GEX only as context and test futures-native trend/reversion triggers.

### NG / MNG — current GEX mapping invalid for entries

UNG fixed scaling is structurally mismatched to MNG. The current observed setup is effectively one-direction LONG.

Archived positive-gamma tests remained negative after costs in both halves and all tested horizons.

Research recommendation: disable GEX-directed entries for NG. Build a natural-gas-specific volatility/breakout system; use UNG GEX only as a regime/context variable.

### CL / MCL — quarantine remains justified

CL showed regime sign changes between halves:
- several first-half RTH-positive results were strong but reversed negative in the second half;
- overnight-negative improved in the second half after losing in the first.

Research recommendation: keep CL quarantined. Build crude-specific logic around futures price/volatility/session/event structure before reconsidering activation.

## Exit-engine finding

The current "no-loss" stop is set to raw entry price. Under the paper execution model, approximate true net breakeven offsets are:

- MES: +1.10 points
- MNQ: +2.00 points
- MGC: +0.50 points
- NG: +0.032 points
- RTY: +0.80 points
- CL: +0.05 points

A fee-aware breakeven helper is included in `trading/valor/research_profiles.py`. It is research-only and is not wired into production.

## Proposed research deployment order

1. MNQ: positive gamma only; start with RTH; 120-minute management baseline; SAR off; fee-aware trailing.
2. MGC: preserve current logic as control, but block RTH positive gamma in the research variant.
3. MES: no production promotion yet; continue replacement entry research.
4. RTY: GEX context only.
5. NG: GEX context only; futures-native volatility/breakout entry.
6. CL: remain quarantined.
