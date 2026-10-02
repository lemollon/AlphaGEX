# VALOR MES v42 preregistration: gap-opposed holdout validation

## Recommendation and fixed hypothesis

Validate exactly one preregistered v41 cluster lead; do not search another
family or another filter. The fixed setup is v41's 0.10-prior-ATR opening-range
breakout, separate retest, and separate resumption; 1.5R target; 120-minute
maximum hold; and a cash gap opposed to the eventual trade direction.

The rule came from v41's written single-condition cluster audit. Its 2023
diagnostic cohort had 41 trades, +$797 after the two-tick cost case, +$19.44
average, PF 2.307, +$592 under four-tick stress, and a mean-trade bootstrap 95%
lower bound of +$3.16. These are discovery statistics, not validation and not a
live profitability claim.

Research only. No broker, paper deployment, production rule, scheduler, or
real-money size change is authorized. Calendar year 2026 stays sealed.

## Unchanged signal and execution

- Reuse v41's exact-contract session, prior-ATR, 08:30-08:59 opening range,
  three-stage completed-five-minute signal, stop, target, gap handling,
  stop-first ambiguity, and one-tick target trade-through rules unchanged.
- Scan from the first completed post-opening-range block through the last entry
  that can complete a 120-minute hold before the exchange cash close.
- Keep only signals whose causal cash gap is opposed to trade direction. The gap
  is the 08:30 cash open minus the prior exact-contract cash close; flat or
  unavailable gaps are excluded.
- Apply the gap condition before position and cooldown logic. Enter at the next
  observed one-minute open. Allow at most two trades per date, one position at a
  time, and a 30-minute cooldown after exit.
- Report raw gross and a $3 round-trip fee with 0, 1, 2, and 4 adverse ticks per
  side. Two ticks selects; four ticks is stress. These remain trade-print OHLC
  planning scenarios, not executable bid/ask evidence.

## Validation firewall

Calendar 2023 may be read only as causal warmup for 2024 and for source-integrity
checks; no v42 parameter is selected from it. Evaluate 2024 first. The fixed rule
passes only with all of:

- at least 40 trades in at least six active months;
- positive two-tick net, PF at least 1.40, and average at least $12;
- two-tick net/MDD at least 0.75 and positive best-month-removed net;
- positive four-tick stress net;
- positive two-tick net in both January-June and July-December; and
- an active-session mean-trade bootstrap 95% lower bound above zero using 10,000
  deterministic resamples and seed `420042`.

Open 2025 only if 2024 passes every gate. Apply the identical unchanged annual
gate to 2025. Final historical promotion additionally requires a combined
2024-2025 usable-session day-cluster bootstrap 95% lower bound above zero,
including zero-trade usable sessions, and at least 40 trades/year on average.

Do not discover a second-generation subgroup from validation results. Report
win/loss streaks and five-active-session windows descriptively, but do not turn
them into filters or size rules.

## Output and safety

Persist immutable evidence only to `valor_mes_v42_results`, plus local JSON/CSV
output. Record source hashes, years read, years evaluated, every gate, and the
validation ledger. A pass is `HISTORICAL_CLUSTER_CANDIDATE`, not permission to
trade or increase size; it still requires untouched 2026, executable-fill
calibration, and forward shadow evidence.
