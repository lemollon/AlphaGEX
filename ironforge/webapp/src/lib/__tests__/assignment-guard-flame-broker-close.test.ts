import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { canPlaceLiveOrders, isFlameLiveArmed, isProductionBot as tradierIsProductionBot } from '../tradier'

/**
 * THE GUARD FIRED, THE BROKER NEVER HEARD ABOUT IT.
 *
 * Leron, 2026-09-27: "turn on the guard for all accounts" — the $0.25 assignment
 * guard (closeAtRiskBeforeBell) must actually buy back FLAME's live spread near
 * the close, on every account: production 'Flame' (Tradier 6YB71371) and every
 * sandbox/customer mirror.
 *
 * closeAtRiskBeforeBell already selects every open FLAME/SPARK position without
 * filtering by account_type (see the sibling describe block below) and always
 * calls the shared `closePosition()`. But `closePosition()` only attempts the
 * real Tradier buy-back when `shouldCloseSandbox` is true, and that flag came
 * from `isProductionBotClose = isProductionBot(bot.name)` — the scanner's LOCAL
 * isProductionBot(), which is SPARK + KINDLE only (never FLAME, armed or not).
 * So every closePosition() call for FLAME — including the assignment guard's,
 * with mustCloseNow=true and no next cycle before expiry — skipped the broker
 * order entirely and only booked the DB row closed. The paper/DB position read
 * "closed"; the real Tradier spread stayed open into settlement, unmitigated.
 *
 * This is the SAME shape of bug already fixed once in this file for the
 * production-only catch-up path (2026-08-31, see
 * live-catch-up-inside-entry-window.test.ts) — local isProductionBot() silently
 * excluding FLAME. The fix is the identical, already-proven pattern: OR in
 * canPlaceLiveOrders(bot.name), which is isFlameLiveArmed() for FLAME and false
 * for SPARK, so SPARK's (and FLINT's, which never touches this function)
 * routing is byte-identical to before.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

const ENV_KEYS = ['IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID'] as const
const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'test-key',
  TRADIER_FLAME_ACCOUNT_ID: 'test-account',
} as const

function setEnv(vars: Record<string, string>) {
  for (const k of ENV_KEYS) delete process.env[k]
  Object.assign(process.env, vars)
}

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

/** The body of closePosition, from its signature to the next top-level fn. */
function closePositionBody(): string {
  const start = SRC.indexOf('async function closePosition(')
  expect(start, 'closePosition must exist').toBeGreaterThan(-1)
  const rest = SRC.slice(start + 1)
  const end = rest.search(/\n(?:async )?function \w+\(/)
  return end === -1 ? rest : rest.slice(0, end)
}

/** The body of closeAtRiskBeforeBell (the FLAME/SPARK assignment guard). */
function guardBody(): string {
  const start = SRC.indexOf('async function closeAtRiskBeforeBell(')
  expect(start, 'closeAtRiskBeforeBell must exist').toBeGreaterThan(-1)
  const rest = SRC.slice(start + 1)
  const end = rest.search(/\n(?:async )?function \w+\(/)
  return end === -1 ? rest : rest.slice(0, end)
}

describe('closePosition attempts the real broker close for an armed FLAME, not just SPARK/KINDLE', () => {
  it('isProductionBotClose ORs in canPlaceLiveOrders — the 2026-08-31 catch-up fix, reused', () => {
    expect(closePositionBody()).toContain(
      'const isProductionBotClose = isProductionBot(bot.name) || canPlaceLiveOrders(bot.name)',
    )
  })

  it('the widened flag still feeds the exact same shouldCloseSandbox expression', () => {
    // Only the RHS of isProductionBotClose changed; the rest of the routing
    // (production vs sandbox account, expired-contract skip) is untouched.
    expect(closePositionBody()).toMatch(/shouldCloseSandbox = isProductionBotClose && !isExpiredContract/)
  })

  it('canPlaceLiveOrders is FLAME-when-armed and never SPARK — SPARK/KINDLE routing is unchanged', () => {
    setEnv(ARMED)
    expect(isFlameLiveArmed()).toBe(true)
    expect(canPlaceLiveOrders('flame')).toBe(true)
    expect(canPlaceLiveOrders('spark')).toBe(false)
    expect(tradierIsProductionBot('spark')).toBe(true) // SPARK's own path is unaffected

    setEnv({})
    expect(canPlaceLiveOrders('flame')).toBe(false) // unarmed FLAME still books paper-only
  })
})

describe('the assignment guard already selects every account — production and sandbox alike', () => {
  it('closeAtRiskBeforeBell does not filter its at-risk query by account_type', () => {
    const body = guardBody()
    const selectStart = body.indexOf('const rows = await query(')
    expect(selectStart, 'the guard must query open same-day positions').toBeGreaterThan(-1)
    const selectSql = body.slice(selectStart, selectStart + 400)
    // Every open position for today's expiration is in scope — production 'Flame',
    // every sandbox test account, and (via mirrorCloseToCustomers downstream in
    // closePosition) every mirrored customer account. Re-adding an account_type
    // filter here would silently exempt an account from the guard again.
    expect(selectSql).not.toMatch(/account_type/)
    expect(selectSql).toMatch(/WHERE status = 'open' AND dte_mode = \$1 AND expiration = \$2/)
  })

  it('the guard hands every at-risk row to the shared closePosition — no per-account branch', () => {
    const body = guardBody()
    expect(body).toContain('const outcome = await closePosition(')
    // Only one closePosition call site in the guard: it does not special-case
    // production vs sandbox before deciding whether to close.
    expect(body.match(/await closePosition\(/g)?.length).toBe(1)
  })
})

describe('customer brokerage mirrors close independently of the broker-close gate', () => {
  it('mirrorCloseToCustomers fires unconditionally on any successful close, including the guard', () => {
    const body = closePositionBody()
    const mirrorIdx = body.indexOf('void mirrorCloseToCustomers(')
    expect(mirrorIdx, 'mirrorCloseToCustomers must be called').toBeGreaterThan(-1)
    // It must not be inside the isProductionBotClose-gated broker-mirror block —
    // real customer accounts (SnapTrade) are a separate mechanism from the
    // operator's own Tradier sandbox/production accounts and must never depend
    // on this flag.
    const shouldCloseIdx = body.indexOf('if (shouldCloseSandbox) {')
    expect(shouldCloseIdx).toBeGreaterThan(-1)
    expect(mirrorIdx).toBeGreaterThan(shouldCloseIdx)
  })
})
