import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * gap audit #184/#216: "adding a second agent starts a 5 CALENDAR-day trial, not 5
 * trading days." createSubscriptionCheckout (the legacy add-agent path) and
 * upgradeCommunityToBot (the Community -> first-agent upgrade) must set Stripe's
 * trial_end to the same far HOLD timestamp createTrialingSubscription already uses for
 * the main enrollment path, never trial_period_days or `now + 5 days` — the trading-day
 * ledger (trial-close.ts) is what ends the trial at the real length.
 */

const ORIGINAL_KEY = process.env.STRIPE_SECRET_KEY

beforeEach(() => {
  process.env.STRIPE_SECRET_KEY = 'sk_test_' + 'a'.repeat(24)
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-05T12:00:00Z'))
})

afterEach(() => {
  process.env.STRIPE_SECRET_KEY = ORIGINAL_KEY
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function mockFetchOnce(body: unknown) {
  const spy = vi.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    json: async () => body,
  } as unknown as Response)
  return spy
}

describe('createSubscriptionCheckout — trial_end is a far hold, not trial_period_days', () => {
  it('never sends trial_period_days', async () => {
    const { createSubscriptionCheckout, TRIAL_HOLD_DAYS } = await import('../stripe')
    const spy = mockFetchOnce({ id: 'cs_1', url: 'https://checkout.stripe.com/cs_1' })

    await createSubscriptionCheckout({
      customerId: 'cus_1',
      priceId: 'price_1',
      userId: 'user_1',
      bot: 'flame',
      trialDays: 5,
      successUrl: 'https://x/success',
      cancelUrl: 'https://x/cancel',
    })

    const [, init] = spy.mock.calls[0]
    const sentBody = String((init as RequestInit).body)
    expect(sentBody).not.toContain('trial_period_days')
    expect(sentBody).toContain('subscription_data%5Btrial_end%5D=')

    const expectedTrialEnd = Math.floor(new Date('2026-10-05T12:00:00Z').getTime() / 1000) + TRIAL_HOLD_DAYS * 86_400
    expect(sentBody).toContain(`subscription_data%5Btrial_end%5D=${expectedTrialEnd}`)
  })

  it('sends no trial fields at all when trialDays is 0', async () => {
    const { createSubscriptionCheckout } = await import('../stripe')
    const spy = mockFetchOnce({ id: 'cs_2', url: 'https://checkout.stripe.com/cs_2' })

    await createSubscriptionCheckout({
      customerId: 'cus_1',
      priceId: 'price_1',
      userId: 'user_1',
      bot: 'flame',
      trialDays: 0,
      successUrl: 'https://x/success',
      cancelUrl: 'https://x/cancel',
    })

    const [, init] = spy.mock.calls[0]
    const sentBody = String((init as RequestInit).body)
    expect(sentBody).not.toContain('trial_end')
    expect(sentBody).not.toContain('trial_period_days')
  })
})

describe('upgradeCommunityToBot — trial_end is the same far hold, not now+trialDays', () => {
  it('uses TRIAL_HOLD_DAYS, not opts.trialDays, for the timestamp', async () => {
    const { upgradeCommunityToBot, TRIAL_HOLD_DAYS } = await import('../stripe')
    const spy = mockFetchOnce({ id: 'sub_1', status: 'trialing' })

    await upgradeCommunityToBot({
      subscriptionId: 'sub_1',
      itemId: 'si_1',
      botPriceId: 'price_1',
      userId: 'user_1',
      bot: 'spark',
      trialDays: 5,
    })

    const [, init] = spy.mock.calls[0]
    const sentBody = String((init as RequestInit).body)
    const expectedTrialEnd = Math.floor(new Date('2026-10-05T12:00:00Z').getTime() / 1000) + TRIAL_HOLD_DAYS * 86_400
    expect(sentBody).toContain(`trial_end=${expectedTrialEnd}`)
    // Would be ~5 days out if the old now+trialDays*86400 math were still in effect.
    const fiveDayTrialEnd = Math.floor(new Date('2026-10-05T12:00:00Z').getTime() / 1000) + 5 * 86_400
    expect(sentBody).not.toContain(`trial_end=${fiveDayTrialEnd}`)
  })
})
