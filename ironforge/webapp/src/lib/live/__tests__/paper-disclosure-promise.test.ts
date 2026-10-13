import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { paperDisclosure, LIVE_BOTS, type LiveBot } from '../bots'
import { isExecutorArmed } from '@/lib/customer-executor/armed'

/**
 * The paper disclosure makes a promise about the READER's money. The badge that
 * triggers it describes IRONFORGE's ledger. Those are independent, and the gap
 * between them is the failure this suite exists to prevent:
 *
 *   `customer-executor/executor.ts` mirrors every opened position to each
 *   activated customer and calls SnapTrade's `placeMlegOrder` — a real market
 *   order in that customer's own brokerage. It fires from the SANDBOX open path,
 *   so the house trade being paper does not stop it. With
 *   CUSTOMER_EXECUTOR_ENABLED set and no Tradier creds present, a customer would
 *   have been shown "no real orders are placed and no real money is at risk"
 *   while their account was being filled.
 *
 * Over-warning costs a sentence. Under-warning costs someone's money.
 */

const SRC = join(__dirname, '..', '..')
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8')

const ORIGINAL = process.env.CUSTOMER_EXECUTOR_ENABLED
afterEach(() => {
  if (ORIGINAL === undefined) delete process.env.CUSTOMER_EXECUTOR_ENABLED
  else process.env.CUSTOMER_EXECUTOR_ENABLED = ORIGINAL
})

describe('paper disclosure never promises more than it knows', () => {
  it.each(LIVE_BOTS)(
    '%s: drops the no-money-at-risk promise when customer orders are live',
    (bot: LiveBot) => {
      const live = paperDisclosure(bot, { customerOrdersLive: true }).toLowerCase()
      expect(live).not.toContain('no real money is at risk')
      expect(live).not.toContain('no real orders are placed')
      // It must still say the RECORD is simulated — that part is true either way.
      expect(live).toContain('simulated')
      // And it must name where the real risk is.
      expect(live).toContain('your own connected brokerage')
    },
  )

  it.each(LIVE_BOTS)('%s: keeps the plain promise when the executor is disarmed', (bot: LiveBot) => {
    const off = paperDisclosure(bot, { customerOrdersLive: false }).toLowerCase()
    expect(off).toContain('no real money is at risk')
  })

  /**
   * The default matters: `paperDisclosure(bot)` with no options is the shape
   * every existing caller used before the flag existed, so a caller that forgets
   * to pass it must not silently get the strong promise back... but it also must
   * not break. It returns the disarmed wording, which is why the ONE caller that
   * matters is pinned separately below.
   */
  it('summary.ts passes the real arm state — not a literal, not nothing', () => {
    const summary = read('live/summary.ts')
    expect(summary).toContain('paperDisclosure(BOT, { customerOrdersLive: isExecutorArmed() })')
    // A hardcoded false here would compile, pass every other test, and re-open
    // the exact hole this suite closes.
    expect(summary).not.toContain('customerOrdersLive: false')
  })

  it('the arm switch has exactly one definition, in a leaf module', () => {
    const armed = read('customer-executor/armed.ts')
    expect(armed).toContain('CUSTOMER_EXECUTOR_ENABLED')
    // A leaf: importing SnapTrade or the DB here would make read paths unable to
    // ask the question, which is how the duplicate env read appeared before.
    expect(armed).not.toMatch(/^import /m)

    const executor = read('customer-executor/executor.ts')
    expect(executor).toContain("from './armed'")
    expect(executor).toContain('export { isExecutorArmed }')
    // The old inline copy must be gone, or the two can drift.
    expect(executor).not.toContain('process.env.CUSTOMER_EXECUTOR_ENABLED')
  })

  it('isExecutorArmed reads the env and defaults closed', () => {
    delete process.env.CUSTOMER_EXECUTOR_ENABLED
    expect(isExecutorArmed()).toBe(false)
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'false'
    expect(isExecutorArmed()).toBe(false)
    // Anything other than the exact string must NOT arm it.
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'TRUE'
    expect(isExecutorArmed()).toBe(false)
    process.env.CUSTOMER_EXECUTOR_ENABLED = 'true'
    expect(isExecutorArmed()).toBe(true)
  })
})
