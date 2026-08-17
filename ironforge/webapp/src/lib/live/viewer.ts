import type { NextRequest } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { dbQuery, escapeSql } from '@/lib/db'
import { isPublicMode } from '@/lib/auth/access'

/**
 * Account-aware Live page: which live-money bots may this viewer see?
 *
 * - Operators (ops session / magic link): every live bot, with the top-right
 *   account toggle.
 * - Customers: exactly the bots mapped to them in ironforge_customer_bots
 *   (e.g. the SPARK2 account owner sees ONLY spark2). No mapping → NO account
 *   (empty state) — a fresh signup must never see the operator's real money.
 * - Anonymous: NO account (empty state) for the same reason.
 *
 * The API routes enforce this server-side; the client toggle merely renders
 * what `allowedBots` says.
 */

// Registry lives in ./bots (no server imports) so client components can use it
// too. Re-exported here to keep existing server-side import sites unchanged.
export {
  LIVE_BOTS,
  LIVE_BOT_MODE,
  LIVE_BOT_LABEL,
  LIVE_BOT_PILL,
  LIVE_BOT_TAGLINE,
  paperDisclosure,
  accountMode,
  isPaperBot,
  isLiveBot,
} from './bots'
export type { LiveBot, LiveAccountMode } from './bots'

import { LIVE_BOTS, LIVE_BOT_MODE, isLiveBot, type LiveBot, type LiveAccountMode } from './bots'
import { canReadProductionBalance } from '@/lib/tradier'

/**
 * Effective account mode, resolved at request time.
 *
 * LIVE_BOT_MODE is the DECLARED default (client-safe, no env access). FLAME is
 * declared 'paper' and stays that way until it is genuinely armed for live
 * trading — at which point the page must stop showing the paper badge and start
 * reading the production ledger. Resolving here keeps the badge honest in both
 * directions instead of drifting out of sync with the arm switch.
 */
export function resolveAccountMode(bot: LiveBot): LiveAccountMode {
  // 🚨 KEYED ON CREDENTIALS, NOT THE ARM SWITCH (2026-08-17).
  //
  // This read isFlameLiveArmed(), which meant the customer and sandbox surfaces
  // showed FLAME's PAPER ledger until the bot was armed to TRADE — the same
  // read/write conflation fixed in tradier.ts (canReadProductionBalance) and in
  // the live viewer (#2817). Seeing an account is not permission to trade it.
  //
  // canReadProductionBalance('flame') is true when both TRADIER_FLAME_* creds are
  // present, so wherever FLAME has a live account, its live account is what these
  // pages report. Placement is still gated by canPlaceLiveOrders/isFlameLiveArmed
  // and is untouched.
  if (bot === 'flame') return canReadProductionBalance('flame') ? 'production' : 'paper'
  return LIVE_BOT_MODE[bot]
}

export function resolvePaperBots(bots: LiveBot[]): LiveBot[] {
  return bots.filter((b) => resolveAccountMode(b) === 'paper')
}

/**
 * Ledger filter for a bot's customer-facing queries.
 *
 * Production bots (SPARK/SPARK2) read only account_type='production' rows.
 * Paper bots (FLAME) have no production rows by construction — they read the
 * complement, so their pages show the paper ledger instead of rendering empty.
 * NULL account_type is treated as sandbox/paper by the same COALESCE the
 * production filter uses, so the two branches partition the table exactly.
 *
 * Shared by summary.ts and home.ts — both must scope identically or the Home
 * page and the Live page will disagree about the same bot's money.
 */
export function ledgerFilter(bot: LiveBot, modeOverride?: LiveAccountMode): string {
  return (modeOverride ?? resolveAccountMode(bot)) === 'production'
    ? `AND COALESCE(account_type, 'sandbox') = 'production'`
    : `AND COALESCE(account_type, 'sandbox') <> 'production'`
}

/**
 * Restrict a bot's rows to ONE account owner.
 *
 * `{bot}_positions`, `{bot}_paper_account` and `{bot}_equity_snapshots` all carry a
 * `person` column, and scanner.ts already trades each person independently
 * ("Sync PRODUCTION paper_accounts (each person independently)"). The customer read
 * path did not scope to it, so every balance query SUMMED all owners — correct for an
 * operator (the fleet total), and a cross-customer leak the moment a second person's
 * account exists.
 *
 * null/empty => no restriction (operator fleet view). Callers must decide: a CUSTOMER
 * with no person mapping must not be handed an unscoped query.
 */
export function personFilter(person: string | null | undefined): string {
  if (!person) return ''
  return `AND person = '${escapeSql(person)}'`
}

/**
 * ledgerFilter + personFilter — the pair every customer-facing query needs.
 *
 * FAILS CLOSED. personFilter(null) is an EMPTY string, i.e. no restriction, which
 * is correct for an operator's fleet view and catastrophic for a customer: an
 * unscoped production query returns another person's real-money account.
 *
 * That is not hypothetical. On 2026-07-27 the single row in
 * ironforge_customer_bots had person = NULL, so a signed-in customer's Live page
 * rendered the SPARK production account (person 'Logan', a real Tradier account)
 * as "your account" — balance, today's P&L and the open position.
 *
 * So a non-operator with no `person` now gets a query that matches nothing and an
 * honest empty state. Callers must pass isOperator explicitly; the default is
 * false, so a caller that forgets cannot leak.
 */
export function scopeFilter(
  bot: LiveBot,
  person: string | null | undefined,
  isOperator = false,
  /**
   * Explicit ledger choice, for surfaces that let the viewer switch. FLAME has
   * BOTH a $2,000 paper ledger and a live account (6YB71371), and the customer
   * pages must be able to show either — omitted, the bot's default mode wins.
   */
  modeOverride?: LiveAccountMode,
): string {
  if (!isOperator && !person) {
    return `${ledgerFilter(bot, modeOverride)} AND FALSE`
  }
  return `${ledgerFilter(bot, modeOverride)} ${personFilter(person)}`
}

/** Bots that genuinely have both ledgers, so a Paper/Live switch is meaningful. */
export function hasBothLedgers(bot: LiveBot): boolean {
  return bot === 'flame' && canReadProductionBalance('flame')
}

export interface LiveViewer {
  /** null = this viewer is not authorized for any live account (empty state). */
  bot: LiveBot | null
  allowedBots: LiveBot[]
  /**
   * True for operators. Only an operator may be shown an
   * AGGREGATE across every production account of a bot — see summary.ts. A
   * customer must never be handed the fleet total as "your account".
   */
  isOperator: boolean
  /**
   * Account owner (ironforge_accounts.person) for the SELECTED bot, from
   * ironforge_customer_bots.person. null for operators (fleet view) and for
   * customers whose mapping predates per-account scoping.
   */
  person: string | null
  /** bot -> account owner, for multi-bot views (Performance). */
  persons: Record<string, string | null>
  /** Subset of allowedBots currently running on simulated money. Drives the
   *  "Paper" badge on the strategy pills/rail without the client needing env. */
  paperBots: LiveBot[]
  /** users.id of the signed-in customer, for billing/entitlement lookups.
   *  null for operators and anonymous viewers. Never sent to
   *  the client as an identifier to act on — it only sources the plan card. */
  customerId: string | null
}


export async function resolveLiveViewer(req: NextRequest): Promise<LiveViewer> {
  let allowed: LiveBot[] = []
  let isOperator = false
  // bot -> account owner, from ironforge_customer_bots.person. Empty for operators.
  const personByBot = new Map<string, string>()
  let customerId: string | null = null

  {
    try {
      const ops = await getSession()
      // Cookie OR mobile bearer token — getCustomerIdentity reads next/headers exactly
      // as getCustomerSession did, so this single substitution makes all five
      // /api/live/* routes bearer-aware without changing a route signature anywhere.
      //
      // NOTE for future edits: this function takes `req` but must NOT resolve identity
      // from it. Switching to req.cookies would look like a tidy-up and would silently
      // break every mobile read. viewer identity comes from next/headers, deliberately.
      const customer = (await getCustomerIdentity()) ?? { customerId: null as string | null }

      // A CUSTOMER session wins over an operator one.
      //
      // Impersonation ("View as user") works by setting the customer session
      // while the operator session stays put — see api/ops/impersonate. Checking
      // the operator session first therefore defeated it entirely: an operator
      // impersonating a customer still got isOperator = true and the unscoped
      // FLEET view, so /live showed the SPARK production account (person
      // 'Logan', real money) instead of what that customer actually sees.
      //
      // Preferring the customer session makes impersonation mean what it says,
      // and is the safe direction: the worst case is an operator seeing less
      // than they could, which they undo with ?clear=true.
      if (!customer.customerId && ops.userId) {
        allowed = [...LIVE_BOTS]
        isOperator = true
      } else if (!customer.customerId && isPublicMode()) {
        // 🚨 PUBLIC MODE MUST REACH THE SCOPING, NOT JUST THE DOOR.
        //
        // access.ts states the contract: routes that guard themselves AFTER
        // middleware consult isPublicMode() too, "so a service running open is
        // open all the way down instead of serving pages whose APIs still 401".
        // This function did not, so on an open deployment /agents/{bot} and
        // /live returned 200 with allowedBots: [] and rendered an empty page —
        // indistinguishable from a login wall to anyone looking at it, which is
        // exactly the "reads as broken rather than open" failure that comment
        // warns about.
        //
        // Ordered AFTER the customer check so a real session still wins and
        // impersonation keeps working. Cannot leak on the customer domain:
        // IRONFORGE_PUBLIC_MODE is set per-deployment on the operator console
        // and sandbox, never on ironforge.trade, and it is fail-secure — any
        // value but the exact string 'true' leaves the gate enforced.
        allowed = [...LIVE_BOTS]
        isOperator = true
      } else {
        if (customer.customerId) {
          customerId = customer.customerId
          const rows = await dbQuery<{ bot: string; person: string | null }>(
            `SELECT bot, person FROM ironforge_customer_bots WHERE customer_id = $1`,
            [customer.customerId],
          )
          allowed = rows.map((r) => r.bot).filter(isLiveBot)
          for (const r of rows) {
            if (r.person) personByBot.set(r.bot, r.person)
          }
        }
      }
    } catch {
      // Fail closed: no account visibility on any error.
      allowed = []
      isOperator = false
      customerId = null
    }
  }

  const requested = req.nextUrl.searchParams.get('account')
  const bot = isLiveBot(requested) && allowed.includes(requested) ? requested : (allowed[0] ?? null)
  // Operators keep the unscoped fleet view; customers are pinned to their own
  // account when one is mapped.
  const person = isOperator || bot == null ? null : (personByBot.get(bot) ?? null)
  const persons: Record<string, string | null> = {}
  for (const b of allowed) persons[b] = isOperator ? null : (personByBot.get(b) ?? null)
  return { bot, allowedBots: allowed, paperBots: resolvePaperBots(allowed), isOperator, person, persons, customerId }
}
