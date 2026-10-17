/**
 * ARM RECEIPT — the data half. Builds a real receipt per sleeve by asking the
 * ledgers for an actual order id, never by reading a switch.
 *
 * See lib/arm-receipt.ts for the rule this enforces and why it exists. The
 * short version: a switch is not a fill, a deploy is not a fill, a paper row
 * is not a fill. This module answers "has this sleeve ever placed a real
 * order, and did any of them land in a CUSTOMER account" with the order id
 * attached, so "it's armed" becomes a query with a receipt instead of a
 * claim.
 *
 * 🚨 READ-ONLY. Places no order, sets no switch, writes no row. Every query
 * here is a SELECT. A failure to read is reported as a blocker on the
 * receipt, never swallowed into a cheerful default — an unreadable ledger
 * must never render as "armed", and must never render as "off" either, since
 * both would be a guess.
 */

import { query } from './db'
import {
  ArmProof,
  SleeveArmReceipt,
  ArmLayer,
  worstFirst,
  summarize,
} from './arm-receipt'

/**
 * One sleeve's static wiring facts. `hasOrderPath`/`hasCustomerPath` are
 * stated here rather than inferred, and each carries the evidence in a
 * comment, because "does an executor exist" is a code fact that a SQL query
 * cannot discover — and getting it wrong is precisely how "just flip the
 * switch" became an answer to work that was never built.
 */
interface SleeveSpec {
  sleeve: string
  products: string[]
  switchName: string
  /** Internal ledger table, or null when the sleeve has no internal order ledger. */
  table: string | null
  /** Column holding the broker order id on that table. */
  orderIdCol: string
  /** `strategy` value written to customer_positions, or null when no customer path exists. */
  customerStrategy: string | null
  hasOrderPath: boolean
  hasCustomerPath: boolean
  /** Why it cannot reach the next layer. Null only when fully customer-armed is possible. */
  staticBlocker: string | null
}

/**
 * Every sleeve, enumerated. This list is the thing that must grow whenever a
 * sleeve is added — and bot-feature-coverage.test.ts should fail the build
 * when a sleeve table exists in lib/ with no entry here, so it cannot silently
 * fall out of the report the way STOKE fell out of the coverage registry
 * (its STOKE_ env prefix was not in that test's scan regex).
 */
const SLEEVES: SleeveSpec[] = [
  {
    sleeve: 'EBB (main put spread)',
    products: ['flame', 'spark'],
    switchName: 'CUSTOMER_EXECUTOR_ENABLED',
    table: null, // per-product: {bot}_positions, handled specially below
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'main',
    hasOrderPath: true,
    hasCustomerPath: true,
    staticBlocker: null,
  },
  {
    sleeve: 'FLINT (call spread)',
    products: ['flame', 'spark'],
    switchName: 'CUSTOMER_FLINT',
    table: 'flint_positions',
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'flint',
    hasOrderPath: true,
    hasCustomerPath: true, // mirrorFlintOpenToCustomers, scanner.ts:5321
    staticBlocker: null,
  },
  {
    sleeve: 'XSP swap',
    products: ['flame'],
    switchName: 'XSP_SWAP',
    table: null, // rides the main leg's own ledger
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'xsp',
    hasOrderPath: true,
    hasCustomerPath: true, // executor.ts:622 writes strategy='xsp'
    staticBlocker: null,
  },
  {
    sleeve: 'STOKE',
    products: ['flame'],
    switchName: 'CUSTOMER_STOKE',
    table: 'flame_stoke_positions',
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'stoke',
    hasOrderPath: true, // placeStokeOrderAllAccounts, tradier.ts:6392
    hasCustomerPath: true, // mirrorStokeOpenToCustomers, called from tryOpenStoke (scanner.ts)
    staticBlocker:
      'Customer mirror is wired (mirrorStokeOpenToCustomers) behind CUSTOMER_STOKE. Carried over from the ' +
      'prior entry, not re-verified here: the 2026-10-15 close-ordering bug (the ledger is written before the ' +
      'broker is asked) was recorded as a blocker.',
  },
  {
    sleeve: 'ANVIL (call diagonal)',
    products: ['flame'],
    switchName: 'CUSTOMER_ANVIL',
    table: 'calldiag_positions',
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'anvil',
    hasOrderPath: false, // calldiag-tracker.ts is a paper tracker
    hasCustomerPath: true, // mirrorAnvilOpenToCustomers exists but is uncalled and fails closed
    staticBlocker:
      'mirrorAnvilOpenToCustomers exists but is uncalled and throws fail-closed on purpose: ' +
      'customer_positions carries ONE expiration column, so a diagonal\'s back leg could neither be ' +
      'recorded nor closed. Needs customer_positions.back_expiration DATE NULL (ALTER TABLE ' +
      'customer_positions ADD COLUMN back_expiration DATE NULL) — a production customer-DB migration, ' +
      'and that DB is currently unreachable (empty IP allowlist). Also has no internal order path.',
  },
  {
    sleeve: 'QUENCH (afternoon spread)',
    products: ['flame'],
    switchName: 'CUSTOMER_QUENCH',
    table: 'afternoon_spread_ledger',
    orderIdCol: 'sandbox_order_id',
    customerStrategy: 'quench',
    hasOrderPath: false, // afternoon-spread-live.ts is the switch + cap only; the order fn is unbuilt
    hasCustomerPath: true, // mirrorQuenchOpenToCustomers exists but has NO call site yet
    staticBlocker:
      'No order path yet, so mirrorQuenchOpenToCustomers (customer-executor/executor.ts, hard 1-lot via ' +
      'clampQuenchContracts) has no call site. afternoon-spread-tracker.ts imports zero order functions BY ' +
      'DESIGN (a test asserts the blocklist); placeQuenchOrderAllAccounts is still to build.',
  },
]

/** Read an env switch verbatim. Never normalised to a boolean — see arm-receipt.ts. */
function readSwitch(name: string): string | null {
  const v = process.env[name]
  return v === undefined ? null : v
}

/**
 * Most recent real order on an internal ledger. Returns null when the table
 * has no such row; throws nothing — a missing table is a legitimate "never
 * placed one", but an unreadable table is reported by the caller as a blocker
 * rather than as a confident zero.
 */
async function latestInternalProof(table: string, orderIdCol: string): Promise<ArmProof | null> {
  const rows = await query<{
    order_id: string | number | null
    person: string | null
    account_type: string | null
    open_time: string | Date | null
    entry_credit: string | number | null
  }>(
    `SELECT ${orderIdCol} AS order_id, person, account_type, open_time, entry_credit
       FROM ${table}
      WHERE ${orderIdCol} IS NOT NULL
        AND account_type IN ('production', 'sandbox')
      ORDER BY open_time DESC
      LIMIT 1`,
  )
  const r = rows[0]
  if (!r || r.order_id == null) return null
  return {
    orderId: String(r.order_id),
    account: r.person ?? 'unknown',
    accountType: r.account_type === 'production' ? 'production' : 'sandbox',
    filledAt: r.open_time ? String(r.open_time) : 'unknown',
    fillPrice: r.entry_credit == null ? null : Number(r.entry_credit),
  }
}

/**
 * Most recent real order in a CUSTOMER account for this strategy. This is the
 * only query whose result can justify the word "armed" in the sense Leron
 * means it.
 *
 * Reads the customers database, which is a SEPARATE connection from the
 * internal one — the historical terminology mixup that recorded a
 * sandbox-only rollout as LIVE happened precisely because nobody checked this
 * table.
 */
async function latestCustomerProof(strategy: string): Promise<ArmProof | null> {
  const { customerQuery } = await import('./customers-db')
  const rows = await customerQuery<{
    open_order_id: string | null
    broker_account_id: string | null
    opened_at: string | Date | null
  }>(
    `SELECT open_order_id, broker_account_id, opened_at
       FROM customer_positions
      WHERE strategy = $1 AND open_order_id IS NOT NULL
      ORDER BY opened_at DESC
      LIMIT 1`,
    [strategy],
  )
  const r = rows[0]
  if (!r || !r.open_order_id) return null
  return {
    orderId: String(r.open_order_id),
    account: r.broker_account_id ?? 'unknown',
    accountType: 'customer',
    filledAt: r.opened_at ? String(r.opened_at) : 'unknown',
    fillPrice: null, // customer_positions does not persist the fill price
  }
}

/** Main-leg proof is per-product, since EBB writes to {bot}_positions. */
async function latestMainProof(products: string[]): Promise<ArmProof | null> {
  for (const bot of products) {
    try {
      const p = await latestInternalProof(`${bot}_positions`, 'sandbox_order_id')
      if (p) return p
    } catch {
      /* try the next product; the caller records a blocker if none read */
    }
  }
  return null
}

/**
 * Build every receipt. Each sleeve is wrapped independently: one unreadable
 * ledger degrades that one row to an explicit blocker and leaves every other
 * sleeve's answer intact.
 */
export async function buildArmReceipts(): Promise<{
  receipts: SleeveArmReceipt[]
  summary: ReturnType<typeof summarize>
}> {
  const receipts: SleeveArmReceipt[] = []

  for (const s of SLEEVES) {
    let internal: ArmProof | null = null
    let customer: ArmProof | null = null
    let readError: string | null = null

    try {
      internal = s.table ? await latestInternalProof(s.table, s.orderIdCol) : await latestMainProof(s.products)
    } catch (e: unknown) {
      readError = `internal ledger unreadable: ${e instanceof Error ? e.message : String(e)}`
    }

    if (s.customerStrategy) {
      try {
        customer = await latestCustomerProof(s.customerStrategy)
      } catch (e: unknown) {
        readError = [readError, `customer ledger unreadable: ${e instanceof Error ? e.message : String(e)}`]
          .filter(Boolean)
          .join('; ')
      }
    }

    // The layer is decided by PROOF, in descending order. A switch value
    // never promotes a layer — that inversion is the whole bug this file
    // exists to kill.
    let layer: ArmLayer = 'OFF'
    if (customer) layer = 'CUSTOMER'
    else if (internal) layer = 'INTERNAL'
    else if (readSwitch(s.switchName)) layer = 'PAPER'

    const blocker =
      layer === 'CUSTOMER'
        ? null
        : readError
          ? `UNKNOWN — ${readError}. This is NOT a determination that it is off.`
          : (s.staticBlocker ??
             (s.customerStrategy
               ? `Code path exists (strategy='${s.customerStrategy}') but no customer order has ever been recorded. ` +
                 `Check ${s.switchName} and per-customer eligibility.`
               : 'No customer path.'))

    receipts.push({
      sleeve: s.sleeve,
      products: s.products,
      switchName: s.switchName,
      switchValue: readSwitch(s.switchName),
      layer,
      proof: { internal, customer },
      blocker,
      hasOrderPath: s.hasOrderPath,
      hasCustomerPath: s.hasCustomerPath,
    })
  }

  const ordered = worstFirst(receipts)
  return { receipts: ordered, summary: summarize(ordered) }
}
