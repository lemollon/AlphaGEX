# VALOR MES v33 preregistration: causal MNQ-to-MES catch-up

## Decision and boundary

Test one genuinely new, research-only mechanism: whether MNQ leads a common
equity-index shock and MES subsequently catches up. MES v17-v32 used MES-only
OHLCV-derived signals; this study is the first synchronized cross-market test.

No production trader, broker, sizing, scheduler, Render service, or paper bot is
changed. No vendor request or paid download is allowed. The study reads the
existing Databento `GLBX.MDP3` one-minute caches for `MES.v.0` and `MNQ.v.0`.
Calendar year 2026 remains sealed.

## Causal data construction

- Use only 2023, 2024, and 2025 one-minute bars already stored in
  `valor_research_bar_cache`.
- Validate timestamps, finite OHLCV, tick geometry, duplicate rows, exact
  `instrument_id`, cash-session membership, holidays, and early closes with the
  existing v8 cash-session engine.
- Synchronize MES and MNQ by completed one-minute timestamp. A decision is valid
  only when both instruments have the exact timestamp and contiguous history.
- For each session, estimate the expected MES response to MNQ from the prior 60
  complete cash sessions only. Beta is the no-intercept OLS slope of MES cash
  open-to-close return in basis points on MNQ cash open-to-close return in basis
  points. Require 40 finite prior sessions and positive beta.
- For each lookback `L`, compute completed-bar returns
  `r_mes(t,L)` and `r_mnq(t,L)` in basis points. The leadership residual is
  `beta_prior_date * r_mnq(t,L) - r_mes(t,L)`.
- Standardize that residual with its standard deviation from the prior 20
  complete sessions for the same lookback. Current-day observations never enter
  beta or scale estimates. Require at least 500 prior residual observations and
  positive finite scale.
- Signal direction is the sign of the standardized residual: positive buys MES,
  negative shorts MES. This is a catch-up hypothesis, not a generic MES trend
  rule.

## Frozen discovery family

The only searched dimensions are:

- lookback `L` in `{5, 15, 30}` completed minutes;
- absolute residual threshold `Z` in `{1.5, 2.0}`;
- MES hold `H` in `{5, 15, 30, 60}` completed minutes.

That is 24 cells. Each cell holds at most one MES position. A signal at the exact
prior exit timestamp is allowed, but repeated entries while a position is open
are not. Entries must occur early enough for the fixed exit to complete by the
v8 pre-close flat time. Contract changes, missing minutes, unknown intervals, or
an unavailable next-minute entry remain skipped; no price is invented.

Entry is the next MES minute open after the completed decision bar. Exit is the
MES close exactly `H` minutes after entry. Entry and exit must use one exact MES
contract and a contiguous minute path. No stop, target, trailing rule, or
intrabar path assumption is introduced in v33.

## Costs and selection

MES point value is $5 and tick size is 0.25. Report raw gross plus a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse ticks on each side. These are planning
scenarios, not executable-BBO evidence.

Discovery uses 2023 only. A cell is eligible for selection only if its two-tick
case has:

- at least 80 closed trades;
- positive net dollars;
- profit factor at least 1.10;
- average net trade at least $8.

Rank eligible cells by two-tick net-profit-to-maximum-drawdown, then average net
trade, then the deterministic order `L`, `Z`, `H` shown above. Select exactly one
cell. If none qualify, the family fails and 2024/2025 stay unopened.

## Sequential confirmation firewall

Evaluate the selected cell once on 2024, unchanged. Open 2025 only if 2024 has:

- at least 60 closed trades;
- positive two-tick net dollars;
- two-tick profit factor at least 1.10;
- two-tick average net trade at least $8; and
- positive four-tick net dollars.

The final historical candidate passes only if 2025 independently meets the same
five requirements and the combined 2024-2025 day-cluster bootstrap 95% lower
confidence bound for mean two-tick daily P&L is above zero. Use a deterministic
10,000-resample bootstrap seed. Report each calendar year separately, all cost
views, monthly P&L, maximum drawdown, trade count, and a reviewable trade ledger.

No threshold or parameter may change after any result is read. A failed 2024
validation keeps 2025 sealed for a different future mechanism. A historical pass
is `HISTORICAL_CANDIDATE`, not profitable live evidence: promotion still requires
historical executable MES bid/ask calibration plus a source-filtered forward
paper ledger with observed fills and fees.
