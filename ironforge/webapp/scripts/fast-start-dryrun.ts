/**
 * FLAME_FAST_START + SPARK_FAST_START read-only dry run.
 *
 * Run from the Render shell, from ironforge/webapp:
 *   npx tsx scripts/fast-start-dryrun.ts
 * `tsx` is NOT a devDependency of this package (every other file in
 * scripts/ is plain .js/.mjs run with `node` directly, precisely to avoid
 * needing a TS loader) — `npx tsx` fetches it on demand the first time,
 * which requires the Render shell to reach the npm registry. This script
 * imports the ALREADY-TESTED pure TS modules (fast-start-sizing.ts,
 * ebb-sizing.ts) rather than re-implementing their math in plain JS, which
 * is safer for a real-money diagnostic even at the cost of that one-time
 * dependency fetch. If the Render shell has no registry access, ask an
 * engineer to add `tsx` to package.json devDependencies first.
 *
 * For EVERY FLAME account (every customer/sandbox mirror, PLUS Leron's own
 * account on Tradier 6YB71371) AND EVERY SPARK customer (sandbox mirror)
 * account (2026-09-27, SPARK_FAST_START — SPARK's production pot is
 * paper-only, canPlaceLiveOrders('spark') is hard-coded false, so it is
 * shown for visibility only, same as FLAME's own production account is
 * shown here regardless of its arm state), prints:
 *   - seeded deposit, equity, peak_profit
 *   - phase, floor, trigger level
 *   - normal ladder count, fast-start contract count for EBB/SPARK and
 *     FLINT (FLINT's row is FLAME's shared-budget FLINT only — SPARK's own
 *     FLINT sleeve runs a SEPARATE, independent profits-only budget, see
 *     spark-flint-separate.ts, and is reported in its own line below,
 *     never folded into the same combined-max-loss % figure), and combined
 *     max loss as % of deposit
 * and flags accounts where seeding looks wrong (deposit unknown, equity <
 * deposit, or peak_profit < current profit).
 *
 * WRITES NOTHING. PLACES NO ORDERS. Every DB read below is a plain SELECT —
 * it deliberately does NOT call getOrSeedFastStartState / getOrSeedFlintAccountFloor
 * / getOrRatchetCustomerHighWater, because each of those WRITES (seeds or
 * ratchets) on a cache miss. This script only reads what is already there.
 * An account with no fast_start_state row yet is reported as "NOT SEEDED"
 * with the phase/deposit it WOULD seed to, never as if it already had one.
 */
import { query } from '../src/lib/db'
import { ebbProfitLadderContracts } from '../src/lib/ebb-sizing'
import {
  decideFastStartSizing,
  FAST_START_N,
  FAST_START_STYLE_MULT,
  FAST_START_X,
  seedFastStartState,
} from '../src/lib/fast-start-sizing'

type Bot = 'flame' | 'spark'

const ENV_VAR: Record<Bot, string> = { flame: 'FLAME_FAST_START', spark: 'SPARK_FAST_START' }

interface AccountRef {
  person: string
  accountType: 'sandbox' | 'production'
}

async function listAccountsForBot(bot: Bot): Promise<AccountRef[]> {
  const { resolveEligibleAccounts, flameProductionAccount } = await import('../src/lib/tradier')
  const eligible = await resolveEligibleAccounts(bot, { sandboxOnly: bot === 'spark' })
  const refs: AccountRef[] = eligible.map((a) => ({
    person: a.name,
    accountType: (a.type === 'production' ? 'production' : 'sandbox') as 'sandbox' | 'production',
  }))
  if (bot === 'flame') {
    // resolveEligibleAccounts only includes FLAME's own production account when
    // isFlameLiveArmed() is true (requireArmed: true). This dry run must see it
    // regardless of arm state — read-only, requireArmed: false.
    try {
      const flameProd = flameProductionAccount({ requireArmed: false })
      if (flameProd && !refs.some((r) => r.accountType === 'production' && r.person === flameProd.name)) {
        refs.push({ person: flameProd.name, accountType: 'production' })
      }
    } catch { /* env not configured — fine, just skip */ }
  }
  // SPARK's production pot is paper-only (canPlaceLiveOrders('spark') is
  // hard-coded false in tradier.ts) — sandboxOnly:true above already
  // excludes it, but filter defensively in case that ever changes upstream
  // without this script being updated.
  return bot === 'spark' ? refs.filter((r) => r.accountType === 'sandbox') : refs
}

async function readFlintFloor(person: string, accountType: 'sandbox' | 'production'): Promise<number | null> {
  const rows = await query(
    `SELECT floor_amount FROM flint_account_floor WHERE person = $1 AND account_type = $2`,
    [person, accountType],
  )
  if (rows.length === 0) return null
  const n = Number(rows[0].floor_amount)
  return Number.isFinite(n) ? n : null
}

async function readCustomerHighWater(person: string, accountType: 'sandbox' | 'production'): Promise<number | null> {
  const rows = await query(
    `SELECT high_water FROM ebb_customer_high_water WHERE person = $1 AND account_type = $2`,
    [person, accountType],
  )
  if (rows.length === 0) return null
  const n = Number(rows[0].high_water)
  return Number.isFinite(n) ? n : null
}

async function readFastStartState(
  person: string,
  accountType: 'sandbox' | 'production',
  bot: Bot,
): Promise<{ phase: 1 | 2; deposit: number; peakProfit: number; triggeredAt: string | null } | null> {
  try {
    const rows = await query(
      `SELECT phase, deposit, peak_profit, triggered_at FROM fast_start_state
        WHERE person = $1 AND account_type = $2 AND bot = $3`,
      [person, accountType, bot],
    )
    if (rows.length === 0) return null
    const phase = Number(rows[0].phase)
    const deposit = Number(rows[0].deposit)
    const peakProfit = Number(rows[0].peak_profit)
    if ((phase !== 1 && phase !== 2) || !Number.isFinite(deposit)) return null
    return {
      phase: phase as 1 | 2, deposit,
      peakProfit: Number.isFinite(peakProfit) ? peakProfit : 0,
      triggeredAt: rows[0].triggered_at ?? null,
    }
  } catch {
    // fast_start_state may not exist yet on a fresh deploy — that's "not seeded", not an error.
    return null
  }
}

/** Most recent decision-log row's own EBB/FLINT max loss, if this account has
 * ever been evaluated for real — used ONLY to show a % figure in this dry
 * run. Never fabricated; N/A when nothing has been logged yet. */
async function readLastKnownMaxLoss(
  person: string,
  accountType: 'sandbox' | 'production',
  bot: Bot,
): Promise<{ combinedMaxLoss: number; asOf: string } | null> {
  try {
    const rows = await query(
      `SELECT trade_date,
              (COALESCE(ebb_contracts,0) > 0 OR COALESCE(flint_contracts,0) > 0) AS traded,
              floor_amount, budget, phase1_cap_budget, trigger_level
       FROM fast_start_decision_log
       WHERE person = $1 AND account_type = $2 AND bot = $3
       ORDER BY trade_date DESC, evaluated_at DESC
       LIMIT 1`,
      [person, accountType, bot],
    )
    if (rows.length === 0) return null
    // trigger_level = N * combined_ml_ladder -> back out combined_ml_ladder for display.
    const triggerLevel = Number(rows[0].trigger_level)
    if (!Number.isFinite(triggerLevel) || triggerLevel <= 0) return null
    return { combinedMaxLoss: triggerLevel / FAST_START_N, asOf: String(rows[0].trade_date) }
  } catch {
    return null
  }
}

/** SPARK_FLINT's own separate-budget line (spark-flint-separate.ts) — read-only,
 * never seeds/writes. Shows the account's profits-only cushion vs the R1
 * standing rule, independent of SPARK's own fast-start numbers above. */
async function readSparkFlintCushion(
  person: string,
  floor: number | null,
  equity: number | null,
): Promise<string> {
  if (floor == null || equity == null) return 'N/A (deposit or equity unreadable)'
  const cushion = equity - floor
  return `cushion=$${cushion.toFixed(2)} (profits above deposit — FLINT's own R1 gate; SPARK's fast-start floor is NOT used here by design)`
}

async function runBot(bot: Bot): Promise<{ accounts: number; flags: number }> {
  console.log(`\n${'='.repeat(70)}\n${ENV_VAR[bot]} dry run for ${bot.toUpperCase()} — READ ONLY, no writes, no orders.`)
  console.log(`Frozen rule: ${FAST_START_STYLE_MULT}x / X=${(FAST_START_X * 100).toFixed(0)}% / N=${FAST_START_N}${'='.repeat(0)}\n`)

  const { getAllocatedCapitalForAccount } = await import('../src/lib/tradier')

  const accounts = await listAccountsForBot(bot)
  if (accounts.length === 0) {
    console.log(`No ${bot.toUpperCase()} accounts found via resolveEligibleAccounts.`)
    return { accounts: 0, flags: 0 }
  }

  let flagCount = 0

  for (const acct of accounts) {
    console.log(`\n=== [${bot.toUpperCase()}] ${acct.person} [${acct.accountType}] ===`)

    if (acct.accountType === 'production') {
      console.log(`  scope: PRODUCTION — out of scope for ${ENV_VAR[bot]} (customer accounts only).`)
      console.log('  Shown for visibility only; this account keeps its existing equity ladder regardless of the flag.')
    }

    const floor = await readFlintFloor(acct.person, acct.accountType)
    const highWater = await readCustomerHighWater(acct.person, acct.accountType)
    const allocated = await getAllocatedCapitalForAccount(acct.person, acct.accountType).catch(() => null)
    const equity = allocated?.equity ?? null

    const flags: string[] = []
    if (floor === null) flags.push('DEPOSIT UNKNOWN (no flint_account_floor row yet)')
    if (floor !== null && equity !== null && equity < floor) {
      flags.push(`EQUITY ($${equity.toFixed(2)}) < DEPOSIT ($${floor.toFixed(2)}) — account is underwater vs its own floor`)
    }
    const currentProfit = floor !== null && equity !== null ? Math.max(0, equity - floor) : null
    const peakProfit = floor !== null && highWater !== null ? Math.max(0, highWater - floor) : null
    if (currentProfit !== null && peakProfit !== null && peakProfit < currentProfit - 0.005) {
      flags.push(
        `PEAK_PROFIT ($${peakProfit.toFixed(2)}) < CURRENT PROFIT ($${currentProfit.toFixed(2)}) — ` +
        `high-water ratchet looks stale/behind`,
      )
    }

    console.log(`  deposit (flint_account_floor)   : ${floor === null ? 'UNKNOWN' : '$' + floor.toFixed(2)}`)
    console.log(`  equity (live, this cycle)        : ${equity === null ? 'UNREADABLE' : '$' + equity.toFixed(2)}`)
    console.log(`  high_water (ebb_customer_high_water): ${highWater === null ? 'NONE' : '$' + highWater.toFixed(2)}`)
    console.log(`  peak_profit (live high-water calc): ${peakProfit === null ? 'N/A' : '$' + peakProfit.toFixed(2)}`)

    const state = await readFastStartState(acct.person, acct.accountType, bot)
    const effectiveDeposit = state?.deposit ?? floor ?? null

    if (state === null) {
      console.log(
        `  fast_start_state[bot=${bot}]: NOT SEEDED YET — would seed phase=1, deposit=` +
        `${floor === null ? 'UNKNOWN (cannot seed until flint_account_floor exists)' : '$' + floor.toFixed(2)}`,
      )
    } else {
      console.log(
        `  fast_start_state[bot=${bot}]: phase=${state.phase} deposit=$${state.deposit.toFixed(2)} ` +
        `stored_peak_profit=$${state.peakProfit.toFixed(2)} (EOD-only ratchet) triggered_at=${state.triggeredAt ?? 'n/a'}`,
      )
    }

    if (effectiveDeposit !== null) {
      const normalLadder = ebbProfitLadderContracts(bot, effectiveDeposit, peakProfit ?? 0)
      console.log(`  normal (un-multiplied) ${bot === 'spark' ? 'SPARK' : 'EBB'} ladder : ${normalLadder} lot(s)`)

      const lastKnown = await readLastKnownMaxLoss(acct.person, acct.accountType, bot)
      if (lastKnown === null) {
        console.log(
          `  fast-start contracts / combined max loss: N/A — no fast_start_decision_log[bot=${bot}] row yet for ` +
          "this account (needs a live max-loss read; this dry run never fabricates one).",
        )
      } else {
        const seededState = state ? { phase: state.phase, deposit: state.deposit } : seedFastStartState(effectiveDeposit)
        // Uses the STORED peak_profit (EOD-only, matches the real intraday
        // caller's own `skipTriggerCheck: true` contract) when a state row
        // exists; a not-yet-seeded account has no stored figure to read, so
        // this display-only call falls back to the live-computed peakProfit
        // for that ONE case (never for an already-seeded account).
        const displayPeakProfit = state ? state.peakProfit : (peakProfit ?? 0)
        const { decision } = decideFastStartSizing(seededState, {
          ebbCandidateDay: true,
          flintCandidateDay: bot === 'flame', // SPARK's own FLINT is a SEPARATE budget — never folded into this trigger/floor
          ebbMaxLossPerLot: lastKnown.combinedMaxLoss / (bot === 'flame' ? 2 : 1),
          flintMaxLossPerContract: bot === 'flame' ? lastKnown.combinedMaxLoss / 2 : null,
          normalEbbLadder: normalLadder,
          equity: equity ?? effectiveDeposit,
          peakProfit: displayPeakProfit,
        }, { skipTriggerCheck: true, envVar: ENV_VAR[bot] })
        const ebbMlDisplay = lastKnown.combinedMaxLoss / (bot === 'flame' ? 2 : 1)
        const pctOfDeposit = (decision.ebbContracts * ebbMlDisplay +
          decision.flintContracts * (bot === 'flame' ? lastKnown.combinedMaxLoss / 2 : 0)) / effectiveDeposit * 100
        console.log(
          `  fast-start (as of last logged day ${lastKnown.asOf}): phase=${decision.phase} ` +
          `${bot}=${decision.ebbContracts}${bot === 'flame' ? ` flint=${decision.flintContracts}` : ''} ` +
          `floor=$${decision.floor?.toFixed(2) ?? 'n/a'} trigger=$${decision.triggerLevel?.toFixed(2) ?? 'n/a'} ` +
          `combined_max_loss≈${pctOfDeposit.toFixed(1)}% of deposit`,
        )
        console.log(
          `  NOTE: ${bot === 'flame' ? 'EBB/FLINT max-loss split above is an ESTIMATE for display only (halved from the last logged combined figure)' : 'SPARK max-loss above is the last logged figure'} — the real numbers come from today's live option quotes, not this script.`,
        )
      }

      if (bot === 'spark') {
        const flintNote = await readSparkFlintCushion(acct.person, floor, equity)
        console.log(`  SPARK_FLINT (separate budget, spark-flint-separate.ts): ${flintNote}`)
      }
    } else {
      console.log('  fast-start contracts: N/A (deposit unknown)')
    }

    if (flags.length > 0) {
      flagCount += flags.length
      for (const f of flags) console.log(`  ⚠️  FLAG: ${f}`)
    }
  }

  console.log(`\n[${bot.toUpperCase()}] Done. ${accounts.length} account(s) checked, ${flagCount} flag(s) raised.`)
  return { accounts: accounts.length, flags: flagCount }
}

async function main() {
  console.log('FLAME_FAST_START + SPARK_FAST_START dry run — READ ONLY, no writes, no orders.')

  const flame = await runBot('flame')
  const spark = await runBot('spark')

  console.log(
    `\nGRAND TOTAL: ${flame.accounts + spark.accounts} account(s) checked ` +
    `(${flame.accounts} FLAME, ${spark.accounts} SPARK), ${flame.flags + spark.flags} flag(s) raised. ` +
    `No writes, no orders.`,
  )
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('[fast-start-dryrun] failed:', err)
    process.exit(1)
  })
