# Vol suppression + call demand — the gap the VVIX corpus never covered

**Status:** research only. Nothing here is wired into `vol_regime_advisor.py`.
**Date:** 2026-08-07 · **Sample:** 2006-03-06 → 2026-08-06, 5,170 trading days
(median VIX–SPY beta −6.51).

## Why this exists

Every signal in `backtest/vvix_vix_analysis/` is an **expansion/stress** lens
(`backwardation`, `ts_flattening`, `exhaustion`, `divergence`; `double_floor` is a
static level floor, not a dynamic). The corpus has **no** signal for the opposite
regime — vol being *crushed* — and **no call-side input of any kind**.

That gap had a live cost: on 2026-07-29 the only thing that fired was
`ts_flattening`, whose advice was "buy puts / cut short premium," one day before
SPY ran **+5.7% in four sessions**. (Direction bug fixed separately in PR #2764.)

## The two signals

Both are **index-only** (CBOE + Yahoo), so they need no warehouse and no ORATS —
deliberately, so they can be computed in the same place the existing five are.

| signal | definition |
|---|---|
| **SUPPRESSION** | `resid = dlnVIX - beta_t * spy_ret`, `beta_t` from a **trailing** 252d window (never today's). `resid_z <= -2.0` **and** front-end led (`dlnVIX9D < dlnVIX3M`). Vol falls far more than the spot move explains. |
| **CALL DEMAND** | `spy_ret > 0` **and** `dlnVIX > 0` — spot-up *and* vol-up on the same day. Dealers paying up for upside convexity. Needs no options data. |

## Result 1 — SUPPRESSION is bullish for DIRECTION, hostile to SHORT PREMIUM

67 days / **63 episodes** (1.3% of sample).

| outcome | on | base | diff | t_block |
|---|---|---|---|---|
| SPY fwd 10d | +1.73% | +0.47% | **+1.26%** | **+3.38** |
| SPY fwd 20d | +2.56% | +0.94% | +1.62% | +2.46 |
| VIX fwd 5d | −4.58% | +1.22% | −5.80% | −2.07 |
| **realized vol fwd 5d** | **21.13** | **14.97** | **+6.16** | **+2.67** |
| next-day \|SPY\| ≥ 1.5% | 28.4% | 13.1% | — | **2.16× lift** |

The softer cut (`resid_z <= -1.5`, no front-end condition) fires 219 days / 197
episodes and points the same way but weaker: fwd10 +0.76% (t +2.27), fwd20 +0.93%
(t +1.96), realized vol fwd **25.48 vs 14.97** (t +3.17), next-day tail **2.57×**.

**Survives crisis removal.** Dropping 2008–09 and 2020 entirely: fwd10 +1.61% vs
+0.53% base, **t_block +2.98** (n=65). Present in 2010–2019 (+0.68%) and
2022–2026 (+2.22%).

The two halves point opposite ways and that is the whole point: **price drifts up,
but the tape gets more violent.** A suppression day is a reason to be long
direction and a reason to be *smaller* in short premium — not the same trade.

## Result 2 — CALL DEMAND widens the variance risk premium

530 days / **448 episodes** (10.3%).

| outcome | on | base | t_block |
|---|---|---|---|
| **realized vol fwd 5d** | **11.88** | 14.97 | **−6.19** |
| VIX fwd 5d | +4.06% | +1.22% | +3.81 |
| next-day \|SPY\| ≥ 1.5% | 7.2% | 13.1% | **0.55× lift** |
| SPY fwd 5d | +0.08% | +0.24% | −1.75 (ns) |

**Implied vol goes UP while realized vol goes DOWN** — the variance risk premium
widens. For a premium seller that is a green light, and it is the opposite of the
intuitive read ("vol is rising, stand down").

**Honest caveat — about two-thirds of the raw realized-vol effect is a level/
composition effect.** Within VIX-percentile buckets the gap shrinks from −3.10 to
roughly −1.0 (low −1.20, mid −0.83, high −1.17). The clean like-for-like
comparison still holds: among *up days only*, vol-up days run **11.88** forward RV
vs **13.95** for the normal vol-down variety.

**No directional edge.** fwd SPY is mildly negative and insignificant. This is a
sizing/vol signal, not a direction bet — the same discipline the `ts_flattening`
fix imposed.

**"Extreme" is the wrong cut.** The hard variant (SPY +>0.5% & VIX +>2%, n=41)
is insignificant on every outcome. The edge is in the soft condition.

## What 2026-07-30 actually was

Stated correctly (an earlier read of this event mis-stated the SPY move):

| date | SPY | dlnVIX actual | beta-explained | unexplained | resid_z |
|---|---|---|---|---|---|
| 07-29 | −1.54% | +12.6% | +12.1% | +0.5% | −0.00 |
| **07-30** | **+1.68%** | **−19.0%** | **−13.2%** | **−5.8%** | **−1.43** |
| 08-04 | +1.80% | +4.0% | −14.1% | **+18.1%** | **+3.89** |

So 07-30 was a **moderate** suppression day (5th percentile residual), not an
extreme decoupling — most of the vol crush was justified by a strong up day. It
did **not** clear the HARD threshold.

**08-04 is the real standout**: with a −7.8 beta, a +1.80% SPY day "should" have
taken VIX down 14.1%; VIX rose 4.0% instead — **+18.1% unexplained, resid_z
+3.89**. That is the textbook call-buying print, and it is the single cleanest
instance of Result 2 in the recent tape.

## Limitations — read before trading any of this

1. **Suppression n is small**: 63–67 episodes over 20 years.
2. **The suppression payoff is a 10–20 day drift.** No current bot trades that
   horizon — SPARK is 1DTE. It is a *sizing/《regime》* input, not a SPARK signal.
3. **Neither signal uses actual options data.** Call skew, call volume and call
   GEX remain untested — that needs the warehouse (`hf_trades` call/put staging,
   `hf_13_skew.py`'s `call_skew`) or ORATS.
4. Multiple outcomes were examined per signal; no multiple-testing correction has
   been applied. Treat single results near t≈2 with suspicion.

## Reproduce

```bash
python backtest/vol_suppression/analyze.py      # main study
python backtest/vol_suppression/robustness.py   # era + confound checks
```
Data: CBOE daily CSVs (keyless) + `backtest/vvix_vix_analysis/data/SPY_raw.json`.

## Next

- [ ] Options-side test (call skew / call volume / call GEX) — **blocked**: the
      DuckDB warehouse is write-locked by a running ingest, prices+flow end
      2026-07-24, and all GEX ends 2026-06-17 (no `ORATS_TOKEN`).
- [ ] Ingest 07-25 → present so the 07-30 window is in-sample at all.
- [ ] Decide whether CALL DEMAND becomes a real advisor signal — it is the
      strongest result here (448 episodes, t −6.19) and it speaks directly to
      SPARK/FLAME sizing.
