# Spark and Flame — current state as of September 28, 2026

This is the current strategy reference for IronForge inside `lemollon/AlphaGEX`.
Source baseline: commit `3637fd18396b9ab532ee0d9bd42281338353a8a2` (September 28,
PR #3102). Reviewed September 29. Older documents describe historical systems;
their 1DTE/2DTE iron-condor, Kelly-sizing, Databricks, and paper-only claims must
not be used as current Spark/Flame operating instructions.

## Repository, runtime, and account boundaries

- `ironforge/webapp/` is the Next.js application, API, and in-process one-minute
  scanner. `ironforge-customer` is a Render service built from that directory in
  AlphaGEX; it is not a separate repository.
- Customer and operator surfaces are selected by `IRONFORGE_MODE` in
  [surface.ts](webapp/src/lib/surface.ts). Bot-console APIs such as
  `/api/spark/config` belong to the operator surface and can return 404 on a
  customer-only deployment. Do not interpret that as a missing strategy.
- Internal paper/Tradier accounts use `DATABASE_URL` and `lib/db.ts`.
  Activated app customers have separate records in `CUSTOMERS_DATABASE_URL` and
  broker orders through `lib/customer-executor/executor.ts` and SnapTrade.
- Internal Spark Tradier live placement is hard-disabled by
  `canPlaceLiveOrders('spark')`; read access is retained. Flame live placement
  requires `IRONFORGE_FLAME_LIVE=true` and configured Flame credentials.
  Activated app-customer SnapTrade mirroring is a separate gated path; do not
  generalize the internal Spark block to all customer accounts.
- Internal production, internal sandbox, the separate staging sandbox service,
  and an app customer's brokerage account are distinct scopes. A master-ledger
  trade is not proof that every customer received or filled an order.
- `ironforge/trading/`, `ironforge/jobs/`, and `ironforge/databricks/` describe
  retired/reference execution paths; they do not define these current strategies.

## Main strategy: EBB put credit spreads

All clock values below are America/Chicago (Central). These are source defaults,
not a claim that every database override or deployment switch was inspected.

| Parameter | Spark | Flame |
|---|---|---|
| Underlying, before optional XSP swap | SPY | SPY |
| Expiration and ledger tag | Same-day / `0DTE` | Same-day / `0DTE` |
| Entry window | 10:05–10:20 AM CT | 1:05–1:10 PM CT |
| Short put strike | `Math.round(spot - 2)` | `Math.round(spot - 1)` |
| Long put strike | Short minus $5 | Short minus $2 |
| Code minimum net credit | $0.10/share ($10/contract) | $0.10/share ($10/contract) |
| VIX-decay ratio ceiling | 0.90 | 0.80 |
| Main trades/day default | 1 | 1 |
| Early profit target default | Disabled (`pt_pct=1.0`) | Disabled (`pt_pct=1.0`) |
| Conventional stop | Not consulted on settle-at-expiry path | Not consulted on settle-at-expiry path |
| Stand-down default | 0 days | 0 days |
| Internal paper seed | $5,000 | $2,000 |

Source: [scanner.ts](webapp/src/lib/scanner.ts), `BOTS`, `DEFAULT_CONFIG`,
`botStructure`, `tryOpenFlamePutSpread`, and
[bot-capital.ts](webapp/src/lib/bot-capital.ts). Paper seeds are not universal
broker eligibility minima or customer account balances. Strike placement is
fixed-dollar rounding, not delta selection or an SD multiplier.

The VIX ratio is the **prior session's VIX close divided by the maximum VIX
close over the 20 sessions before that prior session**. It requires 21 stored
sessions before the entry date; today's close is never an entry input. Missing
or invalid history blocks the main entry. `ensureVixHistory` can backfill genuine
history gaps from Tradier without overwriting existing `sw_vix_daily` rows.

The entry end, minimum credit, profit-target setting, and trade-count setting
can have database overrides. The credit is clamped to at least $0.10 in the
scanner. Read the applicable `0DTE` scope and executable source, not retired
`1DTE`/`2DTE` rows or display-only fields. Event blackout, market calendar,
account availability, buying power, and order gates still apply.

## Exits, assignment protection, and settlement

EBB defaults hold toward expiry. The generic 2:45 PM cutoff does not force an
EBB exit, and changing `stop_loss_pct` does not activate a stop on this path.
This does **not** mean every position is left unguarded through the bell.

The SPY assignment guard checks at-risk short strikes during the final three
minutes before the actual market close: normally 2:57–3:00 PM CT, or
11:57 AM–noon CT on an early-close day. It attempts a buyback when SPY is at or
within `IRONFORGE_ASSIGNMENT_GUARD_BUFFER` of the short strike. The source
fallback is $0.50; an environment override may differ and was not independently
read in this documentation pass. Missing quotes or unfilled closes remain
exposure and must not be described as successful protection.

Internal settlement accounting uses the official close. Actual broker fills,
assignment, costs, and cash movements must be reconciled separately; a paper
intrinsic-value settlement is not a broker execution guarantee.

## Customer sizing and optional protection package

Enrollment's default `max_deployment_pct` is **20**. Customer base contracts are
`floor(min(live buying power, authorized deployment) / per-contract collateral)`;
authorized deployment is the saved percentage of the live balance read.
Per-contract collateral is `(width - credit) × 100`. Customer values can differ
from the launch default. A failed or unusable live balance read skips a new
customer open; it never falls back to the balance captured at connection time.
Close handling does not require a new buying-power read.

| Feature | September 28 implementation | Activation condition |
|---|---|---|
| Customer executor | Mirrors eligible master opens/closes, with durable idempotency and customer/account gates | `CUSTOMER_EXECUTOR_ENABLED=true` for new opens |
| Deposit/profit floor | Sticky trigger N=3; K=0.10; variant G; $50/contract margin | `CUSTOMER_DEPOSIT_FLOOR=on` |
| B1 fast start | Add one contract before the floor triggers, if base count >0 and VIX ratio ≤0.70; no minimum-deposit gate | Floor on and `CUSTOMER_FAST_START=on` |
| Post-trigger calm upsize | Add one contract only with sufficient net cushion and original deposit ≥$4,000, ratio ≤0.70 | Floor triggered and `CUSTOMER_CALM_UPSIZE=on` |
| Customer FLINT | Profits-only call sleeve, net of actual/planned host risk | `CUSTOMER_FLINT=on`, master FLINT entry, and customer open gates |
| Internal ONE_STRATEGY | Uses the same pure customer package functions with 20% base sizing for production/sandbox accounts | `ONE_STRATEGY=on`; default off |

Each customer feature switch is separately default-off in source. App customers
do not depend on `ONE_STRATEGY`, but their own switches above still apply. Do not
turn the executor header's “unconditional package” wording into a claim that all
four customer features are enabled.

The floor triggers when profit above the fixed deposit covers three times the
normal deposit-based position's maximum loss. Once triggered, its reference
level is `deposit + 0.10 × prior peak profit`. Variant G permits a first contract
when the deposit-based cushion covers its maximum loss plus $50; additional
contracts must fit the stricter ratcheted-floor budget. Therefore the 10% floor
is a sizing rule, **not** an unconditional guarantee that 10% of profits can
never be lost. A failed floor evaluation logs the problem and retains ordinary
sizing; the separate live-balance gate still fails closed.

Internal ONE_STRATEGY persists its own deposit/trigger/peak state. Its peak
ratchet advances when the host leg sizes, with a documented timing limitation
on FLINT-only days. Legacy internal ladders and fast-start flags remain fallback
paths when ONE_STRATEGY is off; they are not the shared-package sizing rule.

Source: [agent-rules.ts](webapp/src/lib/enrollment/agent-rules.ts),
[contracts.ts](webapp/src/lib/customer-executor/contracts.ts),
[executor.ts](webapp/src/lib/customer-executor/executor.ts),
[one-strategy.ts](webapp/src/lib/one-strategy.ts).

## FLINT, weekday skipping, and XSP

- FLINT is a separate same-day **call credit spread**, not the call half of the
  main EBB put spread. Default short call is `ceil(SPY + 1)`, long call short+2,
  minimum credit $0.10/share, base size one contract. It uses the host entry
  window; market/credit/cushion/account gates apply. Unlike EBB, the VIX-decay
  ratio does not veto FLINT entry.
- `FLINT_MODE=off|paper|live` defaults off. Spark's sleeve additionally depends
  on `SPARK_FLINT=on`. Customer mirroring additionally needs `CUSTOMER_FLINT=on`.
  FLINT may add a contract under its optional gamma-upsize feature after 20
  logged sessions and a top-third gamma reading; sufficient cushion is still
  required. Its source guard-buffer default is $0.25, separately configurable.
- The customer FLINT cushion subtracts host committed risk before requiring
  FLINT maximum loss plus $50. It accounts for open host positions and a
  same-day planned host position, because FLINT can run first. This is a gate,
  not a guaranteed realized outcome or evidence of live fills.
- `FLAME_SKIP_WEEKDAYS` accepts a weekday list; empty means no skipping.
  `FLAME_SKIP_SCOPE=customers|all` defaults `customers`. In this helper,
  “customers” means non-owner internal accounts and the paper book; do not infer
  that the environment name alone proves every SnapTrade customer is skipped.
  A Wed/Thu configuration is supported, not an independently verified setting.
- `XSP_SWAP=on` optionally moves the first `min(host contracts,2)` to XSP 0DTE
  put spreads when XSP credit ≥ SPY credit−$0.05/share and quoted depth suffices.
  It preserves total host contracts and falls back to SPY if routing/filling
  fails. XSP legs use cash settlement from SPX close/10 and are exempt from the
  SPY assignment guard. The switch defaults off.

Source: [flint.ts](webapp/src/lib/flint.ts),
[flame-skip.ts](webapp/src/lib/flame-skip.ts),
[xsp-swap.ts](webapp/src/lib/xsp-swap.ts),
[bot-feature-coverage.ts](webapp/src/lib/bot-feature-coverage.ts).

## Verification boundary

Render's customer service was observed running the September 28 baseline.
September 29 logs showed internal ONE_STRATEGY execution and FLINT cushion
skips; these corroborate those internal paths, not every app customer's state.
The customer database's empty external allowlist prevented individual saved
configuration verification. No credentials, flags, trading rules, orders, or
account balances were changed for this documentation update. No new backtest
was run, and historical performance comments are not promoted to product claims.

For an operational check, verify the deployed commit, the account type and DTE
scope, applicable feature switches, authorized customer percentage, fresh
broker balances, actual order status, and reconciliation evidence independently.
