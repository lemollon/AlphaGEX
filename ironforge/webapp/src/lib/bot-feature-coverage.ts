/**
 * FLAME/SPARK feature-coverage registry.
 *
 * WHY THIS FILE EXISTS (2026-09-28, Leron: "we need to get aligned right now
 * to make sure this never happens again"): FLINT, fast-start/floor, favorable
 * upsize, and the SPARK add-ons were all built into the INTERNAL order path
 * only (tradier.ts placeIcOrderAllAccounts / placeCallSpreadOrderAllAccounts,
 * scanner.ts's production+sandbox branches). App customers mirror trades
 * through a completely separate path (customer-executor/executor.ts
 * mirrorOneOpen/mirrorCloseToCustomers, contracts.ts sizeContracts), and
 * FLINT opens specifically were NEVER mirrored at all (scanner.ts
 * tryOpenFlint never calls mirrorOpenToCustomers). Nobody noticed for weeks.
 *
 * This registry is the single place every FLAME/SPARK env-var feature MUST
 * declare, PER ACCOUNT TYPE, whether it is:
 *   - 'covered'  — the feature's logic actually runs for that account type.
 *                  bot-feature-coverage.test.ts mechanically verifies this
 *                  for 'production'/'sandbox' against the internal-path
 *                  source (tradier.ts, scanner.ts, the *-sizing.ts files)
 *                  and for 'customer' against customer-executor/**.ts plus
 *                  any scanner.ts function that reaches (directly or
 *                  transitively) mirrorOpenToCustomers/mirrorCloseToCustomers.
 *   - 'excluded' — deliberately does NOT run for that account type. Requires
 *                  a `reason` and `approvedBy`. A genuine, not-yet-fixed gap
 *                  is still 'excluded' — say so honestly in the reason
 *                  ("pending (tracked)"), never faked as 'covered'.
 *   - 'n/a'      — the account type doesn't apply to this feature at all
 *                  (e.g. SPARK never places a production order; a pure
 *                  research tracker never touches any account).
 *
 * Update this file in the SAME PR that adds or changes any FLAME/SPARK
 * process.env read. The guard test fails the build otherwise.
 */

/** The three account types every FLAME/SPARK feature must make a decision for. */
export type AccountKind = 'production' | 'sandbox' | 'customer'

export type CoverageStatus = 'covered' | 'excluded' | 'n/a'

export interface CoverageEntry {
  status: CoverageStatus
  /** Required when status === 'excluded'. Plain English — what happens instead, and why. */
  reason?: string
  /** Required when status === 'excluded'. Who approved the exclusion (or, for an honest tracked
   *  gap that hasn't shipped yet, who flagged it and that it is still pending). */
  approvedBy?: string
  /** Optional free-text clarification for 'covered' or 'n/a' entries — e.g. citing the exact
   *  call chain the guard's reachability scan follows, or why an account type doesn't apply. */
  note?: string
}

export interface FeatureCoverage {
  /** Primary/most-recognizable env var for this feature — used as the registry key. */
  flag: string
  /** Every literal env var this feature reads (including the primary `flag`). The guard's
   *  source scan (part a) requires every discovered FLAME_/SPARK_/FLINT_/EBB_/CUSTOMER_/
   *  CALLDIAG_/IRONFORGE_ASSIGNMENT* token to appear in some entry's envVars list. */
  envVars: string[]
  description: string
  coverage: Record<AccountKind, CoverageEntry>
}

const APPROVED_2026_09_26 = "Leron, 2026-09-26 (in-conversation approval; see the module's own header comment for the exact quote)"
const APPROVED_2026_09_27 = "Leron, 2026-09-27 ('Add it now' / 'Yes')"
const TRACKED_GAP = "Leron — flagged in the 2026-09-28 coverage audit (\"we need to get aligned right now to make sure this never happens again\"); tracked, not yet built or decided"

export const BOT_FEATURE_COVERAGE: FeatureCoverage[] = [
  {
    flag: 'FLAME_FAST_START',
    envVars: ['FLAME_FAST_START'],
    description:
      "FLAME customer-account fast-start sizing + hard profit floor (fast-start-sizing.ts, guarded v3). " +
      "Kill switch: unset/off = byte-for-byte unchanged.",
    coverage: {
      production: {
        status: 'covered',
        note: "tradier.ts 'PRODUCTION [Flame]' branch (placeIcOrderAllAccounts) reads isFastStartMode() and applies the phase decision to account 6YB71371.",
      },
      sandbox: {
        status: 'covered',
        note: "tradier.ts 'Sandbox [name]' branch + scanner.ts's FLAME_FAST_START EOD hook (per-account state persistence).",
      },
      customer: {
        status: 'excluded',
        reason:
          "MasterOpen (customer-executor/executor.ts) carries only ticker/strikes/spreadWidth/credit — no contract count " +
          "or fast-start phase. mirrorOpenToCustomers never receives this account's fast-start decision, and customer " +
          "sizing always runs through contracts.ts sizeContracts() independently. Structurally cannot reach customers today.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'SPARK_FAST_START',
    envVars: ['SPARK_FAST_START'],
    description:
      "SPARK's own fast-start rung — same frozen engine as FLAME_FAST_START (fast-start-sizing.ts is bot-parameterized " +
      "via the envVar argument), byte-for-byte isolated from FLAME's.",
    coverage: {
      production: {
        status: 'n/a',
        note: "SPARK never places a production/live order — canPlaceLiveOrders('spark') is hard-coded false in tradier.ts. There is no SPARK production account for this flag to reach.",
      },
      sandbox: {
        status: 'covered',
        note: "tradier.ts 'Sandbox [name]' branch calls isFastStartMode('SPARK_FAST_START') / decideFastStartSizing({envVar:'SPARK_FAST_START'}); scanner.ts's own SPARK_FAST_START EOD hook persists state.",
      },
      customer: {
        status: 'excluded',
        reason: "Same structural gap as FLAME_FAST_START — MasterOpen carries no sizing/phase data, so this never reaches sizeContracts().",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'SPARK_FAVORABLE_UPSIZE',
    envVars: ['SPARK_FAVORABLE_UPSIZE'],
    description: "+1 SPARK contract, house-money-gated, on a favorable-VIX day (spark-favorable-upsize.ts).",
    coverage: {
      production: { status: 'n/a', note: "SPARK never places a production/live order." },
      sandbox: {
        status: 'covered',
        note: "tradier.ts 'Sandbox [name]' branch: isSparkFavorableUpsizeMode() gates decideSparkFavorableUpsize() before sizing.",
      },
      customer: {
        status: 'excluded',
        reason: "Same MasterOpen sizing gap — the +1 contract never reaches the customer mirror.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'SPARK_FLINT',
    envVars: ['SPARK_FLINT'],
    description:
      "FLINT (SPY 0DTE call credit spread) traded on SPARK accounts with its own separate, profits-only budget " +
      "(spark-flint-separate.ts). Frozen by held-out backtest, 2026-09-27.",
    coverage: {
      production: { status: 'n/a', note: "SPARK never places a production/live order." },
      sandbox: {
        status: 'covered',
        note: "scanner.ts gates tryOpenFlint(bot,ct) for bot.name==='spark' on isSparkFlintMode(); tradier.ts's placeCallSpreadOrderAllAccounts labels the sandbox leg 'FLINT/SPARK'.",
      },
      customer: {
        status: 'excluded',
        reason:
          "tryOpenFlint (scanner.ts) is the single FLINT-open function shared by FLAME and SPARK, and it never calls " +
          "mirrorOpenToCustomers — confirmed by direct code read. FLINT opens (including SPARK's separate-budget " +
          "sleeve) have never been mirrored to app customers.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'FLINT_MODE',
    envVars: ['FLINT_MODE', 'FLINT_MAX_CONTRACTS', 'FLINT_GUARD_BUFFER', 'FLINT_OTM_OFFSET', 'FLINT_MIN_CREDIT'],
    description:
      "FLINT — the SPY 0DTE call credit spread engine (flint.ts). FLINT_MODE off|paper|live gates the whole " +
      "sleeve; the other vars are its sizing/strike/credit knobs.",
    coverage: {
      production: {
        status: 'covered',
        note: "tradier.ts placeCallSpreadOrderAllAccounts labels the live leg 'PRODUCTION [name] FLINT' for FLAME's real account.",
      },
      sandbox: {
        status: 'covered',
        note: "Same function's 'SANDBOX [name] FLINT' label, plus scanner.ts tryOpenFlint's paper/sandbox row insert.",
      },
      customer: {
        status: 'excluded',
        reason:
          "*** THE HEADLINE GAP THIS AUDIT WAS OPENED TO FIND. *** tryOpenFlint (scanner.ts) never calls " +
          "mirrorOpenToCustomers under any FLINT_MODE value. FLINT has never mirrored a single open to an app customer.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'EBB_FAVORABLE_UPSIZE',
    envVars: ['EBB_FAVORABLE_UPSIZE'],
    description: "+1 EBB contract on a favorable VIX-decay day, FLAME only (ebb-sizing.ts).",
    coverage: {
      production: {
        status: 'covered',
        note: "tradier.ts 'PRODUCTION [name]: EBB upsize' log line, gated on botName==='flame' && isEbbFavorableUpsizeMode().",
      },
      sandbox: {
        status: 'covered',
        note: "Same gate in tradier.ts's sandbox branch, and scanner.ts's tryOpenFlameBook (bot.name==='flame' && isEbbFavorableUpsizeMode()).",
      },
      customer: {
        status: 'excluded',
        reason:
          "tryOpenFlameBook DOES call mirrorOpenToCustomers later in the same function, but MasterOpen never carries " +
          "the +1-contract decision — the internal book's own finalContracts is not part of MasterOpen, so customers " +
          "never see this upsize regardless of which function it's read from.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'FLINT_FAVORABLE_UPSIZE',
    envVars: ['FLINT_FAVORABLE_UPSIZE'],
    description:
      "+1 FLINT contract when call-side dealer gamma is in the top third of the trailing 20 sessions " +
      "(flint.ts evaluateFlintGammaUpsize). Market-wide decision, shared by paper book and every production/sandbox account.",
    coverage: {
      production: {
        status: 'covered',
        note: "The upsized contract count flows into placeCallSpreadOrderAllAccounts's `contracts` param for the live leg (tradier.ts).",
      },
      sandbox: { status: 'covered', note: "Same upsized count flows into the sandbox leg of the same function." },
      customer: {
        status: 'excluded',
        reason: "Same root cause as FLINT_MODE — tryOpenFlint never mirrors, so this add-on inherits that gap.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'EBB_CUSTOMER_LADDER',
    envVars: ['EBB_CUSTOMER_LADDER'],
    description:
      "equity|profit ladder mode for FLAME's SANDBOX MIRROR accounts (User/Matt/Logan) — NOT app customers, " +
      "despite the name (ebb-sizing.ts ebbCustomerLadderMode).",
    coverage: {
      production: {
        status: 'excluded',
        reason:
          "By explicit design: FLAME's own production account (6YB71371) keeps today's equity ladder regardless of " +
          "this flag — tradier.ts's production branch never reads it. \"the profit ladder for FLAME's customer " +
          "accounts only... SPARK customer sizing must stay exactly as before regardless of the flag.\"",
        approvedBy: APPROVED_2026_09_26,
      },
      sandbox: {
        status: 'covered',
        note: "tradier.ts gates the profit-ladder branch on a literal botName==='flame' check for FLAME's sandbox mirror accounts.",
      },
      customer: {
        status: 'excluded',
        reason:
          "NAMING TRAP: despite \"CUSTOMER\" in the name, this only ever reaches FLAME's sandbox mirror accounts. It is " +
          "never referenced anywhere under customer-executor/. Real app customers get none of this ladder logic.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'FLAME_SKIP_WEEKDAYS',
    envVars: ['FLAME_SKIP_WEEKDAYS', 'FLAME_SKIP_SCOPE'],
    description:
      "Skip EBB and FLINT entries on specific weekdays, FLAME only (flame-skip.ts). Armed 2026-09-27 on the " +
      "Wed+Thu result (RESULT_2k_wednesday_skip.md).",
    coverage: {
      production: {
        status: 'covered',
        note:
          "FLAME_SKIP_SCOPE defaults to 'customers' — production (6YB71371) keeps trading through a skip weekday " +
          "unless an operator explicitly sets FLAME_SKIP_SCOPE=all (shouldSkipAccountForWeekday only skips " +
          "accountType==='production' when scope==='all'). The decision is coded and deliberate; the default is off.",
      },
      sandbox: {
        status: 'covered',
        note: "shouldSkipAccountForWeekday skips every non-production account whenever the weekday matches, regardless of scope.",
      },
      customer: {
        status: 'covered',
        note:
          "scanner.ts's skipCustomerSide (tryOpenFlameBook) gates the ENTIRE block that contains the real " +
          "mirrorOpenToCustomers() call for FLAME — verified by direct code read: when skipCustomerSide is true, the " +
          "customer mirror call is skipped along with the sandbox row insert.",
      },
    },
  },
  {
    flag: 'EDGE_DECAY_MODE',
    envVars: ['EDGE_DECAY_MODE'],
    description:
      "One-sided CUSUM edge-decay alarm (edge-decay.ts). off|notify|enforce; enforce auto-pauses new FLINT/CallDiag " +
      "entries (never EBB) after a Page's-test alarm, resuming after a 10-trade shadow block averages > 0.",
    coverage: {
      production: {
        status: 'covered',
        note: "enforce pauses tryOpenFlint/CallDiag's paper unlock for every account this scan cycle touches, including FLAME's production leg.",
      },
      sandbox: { status: 'covered', note: "Same pause applies to every sandbox account's FLINT/CallDiag entries." },
      customer: {
        status: 'n/a',
        note:
          "Governs FLINT and CallDiag pause state only, and NEITHER strategy is ever mirrored to app customers today " +
          "(FLINT: see FLINT_MODE's customer exclusion; CallDiag: paper-only, no customer mirroring exists at all). " +
          "There is no customer-facing effect to cover or exclude. Revisit if either strategy ever ships to customers.",
      },
    },
  },
  {
    flag: 'CALLDIAG_MODE',
    envVars: ['CALLDIAG_MODE', 'CALLDIAG_MIN_EQUITY'],
    description:
      "CallDiag — IWM 10d/20d call diagonal, PAPER-ONLY sleeve on FLAME accounts, unlocked automatically once an " +
      "account's equity clears CALLDIAG_MIN_EQUITY (calldiag.ts).",
    coverage: {
      production: {
        status: 'covered',
        note: "Paper-tracks against FLAME's real production account equity reading (never places a real order for any account, by design — the CD1 spec itself is 'profits-only' paper).",
      },
      sandbox: { status: 'covered', note: "Same paper-tracking runs against every FLAME sandbox account's equity." },
      customer: {
        status: 'excluded',
        reason:
          "CallDiag is an internal paper-only research sleeve on FLAME's own accounts; the spec was paper-only from " +
          "approval, and it is never referenced under customer-executor/. Deliberate scope, not an oversight.",
        approvedBy: "Leron, 2026-09-27 ('Yes do that' to the profits-only CD1 spec) — paper-only was the explicit ask.",
      },
    },
  },
  {
    flag: 'AFTERNOON_SPREAD_PAPER',
    envVars: ['AFTERNOON_SPREAD_PAPER'],
    description:
      "Paper-only research tracker for the 'dynamic hedge V2' lead (afternoon-spread.ts / afternoon-spread-tracker.ts). " +
      "Logs gate_pass/gate_skip; never places an order.",
    coverage: {
      production: {
        status: 'n/a',
        note: "afternoon-spread-tracker.ts's own file header: 'does the DB/Tradier orchestration and NEVER places an order.' No account type is ever touched by a real or mirrored order from this flag.",
      },
      sandbox: { status: 'n/a', note: "Same — pure logger, no account-type distinction exists to make." },
      customer: { status: 'n/a', note: "Same — pure logger, no account-type distinction exists to make." },
    },
  },
  {
    flag: 'IRONFORGE_ASSIGNMENT_GUARD_BUFFER',
    envVars: ['IRONFORGE_ASSIGNMENT_GUARD_BUFFER'],
    description:
      "Dollar buffer for the 14:57-15:00 CT pre-settlement assignment guard (scanner.ts closeAtRiskBeforeBell). " +
      "Buffer tightened $0.50->$0.25 on 2026-09-17.",
    coverage: {
      production: {
        status: 'covered',
        note: "closeAtRiskBeforeBell queries every open {bot}_positions row for today's expiration, both account_type='production' and 'sandbox', and applies the same buffer to both.",
      },
      sandbox: { status: 'covered', note: "Same query/buffer, account_type='sandbox' rows." },
      customer: {
        status: 'covered',
        note:
          "Indirect, one-hop path (verified 2026-09-28): closeAtRiskBeforeBell calls the shared closePosition(), and " +
          "closePosition's own body directly calls mirrorCloseToCustomers() — so a guard-triggered close on the " +
          "internal book fires the customer mirror close in the same call. The coverage guard's reachability scan " +
          "follows exactly this one-hop call chain (closeAtRiskBeforeBell -> closePosition -> mirrorCloseToCustomers) " +
          "rather than requiring the literal flag name inside customer-executor/.",
      },
    },
  },
  {
    flag: 'CUSTOMER_EXECUTOR_ENABLED',
    envVars: ['CUSTOMER_EXECUTOR_ENABLED'],
    description:
      "Master arm/disarm switch for the entire customer-mirroring subsystem (customer-executor/executor.ts). " +
      "Unset in production — ships disarmed by design.",
    coverage: {
      production: {
        status: 'n/a',
        note: "This gates OPENS into customer accounts only; executor.ts's own header: 'the master bot's own trading must be unaffected by any customer failure.'",
      },
      sandbox: { status: 'n/a', note: "Same — does not gate anything on FLAME/SPARK's own sandbox accounts." },
      customer: {
        status: 'covered',
        note: "isExecutorArmed() reads this directly in customer-executor/executor.ts and gates every mirrorOpenToCustomers call.",
      },
    },
  },
  {
    flag: 'CUSTOMER_FLINT',
    envVars: ['CUSTOMER_FLINT'],
    description:
      "IN-FLIGHT (not yet merged to main as of 2026-09-28). FLINT customer mirroring — profits-only, 1 contract, " +
      "the app-customer counterpart to SPARK_FLINT. Ships disarmed behind CUSTOMER_EXECUTOR_ENABLED + CUSTOMER_FLINT both required.",
    coverage: {
      production: { status: 'n/a', note: "This flag has no meaning for the internal production account — it only ever gates a customer mirror." },
      sandbox: { status: 'n/a', note: "Same — no meaning for internal sandbox accounts." },
      customer: {
        status: 'excluded',
        reason: "In development on a separate branch, not yet merged to main. Pre-registered so the guard demands an explicit coverage decision the moment it lands.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
  {
    flag: 'CUSTOMER_DEPOSIT_FLOOR',
    envVars: ['CUSTOMER_DEPOSIT_FLOOR'],
    description:
      "IN-FLIGHT, NOT YET BUILT anywhere as of 2026-09-28. Intended as app-customers' own equivalent of " +
      "FLAME_FAST_START's deposit floor/CPPI concept.",
    coverage: {
      production: { status: 'n/a', note: "This flag has no meaning for the internal production account." },
      sandbox: { status: 'n/a', note: "This flag has no meaning for internal sandbox accounts." },
      customer: {
        status: 'excluded',
        reason:
          "Not yet built in any branch. Currently impossible without a customer-side floor table and MasterOpen " +
          "carrying sizing data it doesn't carry today. Needs its own design before it can ship.",
        approvedBy: TRACKED_GAP,
      },
    },
  },
]

/** Fast lookup by any of a feature's env vars. */
export function findFeatureCoverageByEnvVar(envVar: string): FeatureCoverage | undefined {
  return BOT_FEATURE_COVERAGE.find((f) => f.envVars.includes(envVar))
}
