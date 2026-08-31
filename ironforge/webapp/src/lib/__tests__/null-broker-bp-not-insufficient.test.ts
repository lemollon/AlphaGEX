/**
 * Regression guard — 2026-08-31 incident.
 *
 * FLAME selected SPY 764/766P @ $0.33 at 13:05 CT and never traded it live.
 * The pre-order buying-power read (`/accounts/.../balances`) timed out after
 * 5s, `getSandboxBuyingPower` returned null, and `placeForAccount` ran
 *
 *     if (bp == null || bp < brokerMarginCheck) { console.warn('Sandbox [...]'); return }
 *
 * so an UNREADABLE balance was reported as "insufficient funds" and the live
 * order was silently abandoned. The paper book still opened the trade, closed
 * it at its profit target, and consumed the day's single trade slot — leaving
 * a win in the ledger that real money never got.
 *
 * The invariant these tests defend: a null from the broker means UNKNOWN, never
 * $0, and it must never share a code path with a real insufficient-funds state.
 */

import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const TRADIER = fs.readFileSync(path.resolve(__dirname, '../tradier.ts'), 'utf-8')
const CONTRACTS = fs.readFileSync(
  path.resolve(__dirname, '../customer-executor/contracts.ts'),
  'utf-8',
)

describe('a null broker buying power is never treated as insufficient funds', () => {
  it('does not collapse the null check and the margin check into one branch', () => {
    // The exact shape that caused the incident.
    expect(TRADIER).not.toMatch(/bp\s*==\s*null\s*\|\|\s*bp\s*<\s*brokerMarginCheck/)
  })

  it('has a dedicated null branch that says UNREADABLE, not insufficient', () => {
    expect(TRADIER).toMatch(/if\s*\(bp\s*==\s*null\)/)
    expect(TRADIER).toMatch(/optionBP UNREADABLE/)
    expect(TRADIER).toMatch(/NOT an insufficient-funds decision/)
  })

  it('keeps the insufficient-funds branch for a balance the broker actually reported', () => {
    expect(TRADIER).toMatch(/if\s*\(bp\s*<\s*brokerMarginCheck\)/)
    expect(TRADIER).toMatch(/insufficient \(need \$/)
  })

  it('retries a transient balance failure before giving up on the order', () => {
    expect(TRADIER).toMatch(/async function readOptionBuyingPowerWithRetry/)
    // The order path must use the retrying reader, not the bare one.
    expect(TRADIER).toMatch(
      /const bp = await readOptionBuyingPowerWithRetry\(acct\.apiKey, accountId, acct\.baseUrl/,
    )
  })

  it('escalates a dropped PRODUCTION order instead of only warning to console', () => {
    expect(TRADIER).toMatch(/async function reportProductionBpUnreadable/)
    expect(TRADIER).toMatch(/await reportProductionBpUnreadable\(botName, acct\.name\)/)
    // It must reach a human and leave a durable row, not just console.warn.
    expect(TRADIER).toMatch(/severity: 'critical'/)
    expect(TRADIER).toMatch(/PRODUCTION_BP_UNREADABLE/)
  })
})

describe('log labels name the account and host that actually failed', () => {
  it('does not hardcode a Sandbox prefix on the buying-power warning', () => {
    // A production drop used to print "Sandbox [Flame]", hiding a live-money
    // failure among sandbox noise.
    expect(TRADIER).not.toMatch(/`Sandbox \[\$\{acct\.name\}\]: optionBP/)
    expect(TRADIER).toMatch(
      /const bpLabel = acct\.type === 'production' \? `PRODUCTION \[\$\{acct\.name\}\]`/,
    )
  })

  it('does not label every HTTP failure as sandbox regardless of the host called', () => {
    expect(TRADIER).not.toMatch(/`Tradier sandbox: \$\{endpoint\} timed out/)
    expect(TRADIER).toMatch(/baseUrl === PRODUCTION_URL \? 'Tradier PRODUCTION' : 'Tradier sandbox'/)
  })
})

describe('customer executor separates unreadable from genuinely empty', () => {
  it('does not share one reason between a null and a zero balance', () => {
    expect(CONTRACTS).not.toMatch(
      /buyingPowerCents\s*==\s*null\s*\|\|\s*s\.buyingPowerCents\s*<=\s*0/,
    )
    expect(CONTRACTS).toMatch(/reason: 'buying_power_unreadable'/)
    expect(CONTRACTS).toMatch(/reason: 'no_buying_power'/)
  })
})
