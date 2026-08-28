/**
 * FLAME's live account must be VISIBLE to the person who owns it.
 *
 * 2026-08-23: FLAME had been filling real Tradier orders on 6YB71371 since
 * 8/20 and the customer Live page showed nothing. Four separate holes, pinned
 * here so none of them can quietly reopen:
 *
 *   1. `summary.ts` read a broker balance for SPARK only. FLAME's account is
 *      env-credentialed rather than listed in `ironforge_accounts`, and had no
 *      branch of its own, so the operator console read Tradier while the
 *      customer page derived a number from the DB ledger.
 *   2. Every production `paper_account` write is keyed (person, dte_mode,
 *      account_type, is_active). No such row existed, so the writes updated
 *      ZERO rows and returned success — real money moved, the ledger did not.
 *   3. Nothing could create that row: every auto-seed hardcodes 'sandbox'.
 *   4. The customer-facing tagline still described the retired 2DTE product.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { LIVE_BOT_TAGLINE } from '../bots'
import { dteMode } from '@/lib/db'

const SRC = join(__dirname, '..', '..')
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8')

describe('FLAME live-account visibility', () => {
  it('describes the product FLAME actually trades, not the retired 2DTE one', () => {
    // dteMode is the roster's source of truth. If it says 0DTE, customer copy
    // that says "two-day" is a false statement about the customer's own money.
    expect(dteMode('flame')).toBe('0DTE')
    expect(LIVE_BOT_TAGLINE.flame.toLowerCase()).not.toContain('two-day')
    expect(LIVE_BOT_TAGLINE.flame.toLowerCase()).toContain('same-day')
  })

  it('reads FLAME account value from the broker, not from the DB ledger', () => {
    const summary = read('live/summary.ts')
    // The branch must exist AND must be fed by the env-cred balance helper —
    // asserting only that the string "flame" appears would pass on a comment.
    expect(summary).toContain('getFlameProductionBalance')
    expect(summary).toMatch(/BOT === 'flame' && !paper/)

    const tradier = read('tradier.ts')
    expect(tradier).toContain('export async function getFlameProductionBalance')
    // Keyed on credentials, not on the arm switch: disarming FLAME must not
    // blank a real balance its owner is entitled to see.
    expect(tradier).not.toMatch(
      /export async function getFlameProductionBalance[\s\S]{0,400}isFlameLiveArmed\(\)/,
    )
  })

  it('never lets a production ledger write fail silently', () => {
    const scanner = read('scanner.ts')
    expect(scanner).toContain('function warnIfNoProductionLedger')

    // Every UPDATE against a production paper_account row must go through
    // dbExecute (which returns rowCount) rather than query() (which returns
    // rows and therefore cannot tell a 0-row update from a successful one).
    const prodWrites = [
      ...scanner.matchAll(
        // [^`]*? keeps each match inside ONE template literal — a greedy
        // [\s\S]*? runs past the closing backtick and pairs a sandbox call with
        // the NEXT production WHERE, which reports phantom violations.
        /(query|dbExecute)\(\s*`UPDATE \$\{botTable\(bot\.name, 'paper_account'\)\}[^`]*?WHERE account_type = 'production'/g,
      ),
    ]
    expect(prodWrites.length).toBeGreaterThan(0)
    for (const m of prodWrites) {
      expect(m[1]).toBe('dbExecute')
    }
    // ...and each one must be checked.
    expect(
      (scanner.match(/warnIfNoProductionLedger\(/g) ?? []).length,
    ).toBeGreaterThanOrEqual(prodWrites.length)
  })

  it('exposes a way to create the production ledger row', () => {
    // The row cannot be born from a scan: every auto-seed hardcodes 'sandbox'.
    // A repair route is therefore the ONLY path, and it must be idempotent.
    const route = readFileSync(
      join(SRC, '..', 'app', 'api', '[bot]', 'seed-production-ledger', 'route.ts'),
      'utf8',
    )
    expect(route).toContain("'production'")
    expect(route).toContain('confirm')
    // Owner name comes from the same composition the ORDER path uses, so the
    // ledger can never be seeded under a label the trades are not stamped with.
    expect(route).toContain('flameProductionAccount')
    expect(route).toMatch(/An ACTIVE production row already exists/)
  })
})
