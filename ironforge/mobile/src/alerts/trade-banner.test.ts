import { describe, it, expect } from 'vitest'
import { tradeBannerFromNotification } from '@/alerts/trade-banner'

describe('tradeBannerFromNotification', () => {
  it('returns null for a notification that is not a trade open/close', () => {
    expect(
      tradeBannerFromNotification({ title: 'x', body: 'y', data: { kind: 'brokerage_health' } }),
    ).toBeNull()
    expect(tradeBannerFromNotification({ title: 'x', body: 'y', data: null })).toBeNull()
    expect(tradeBannerFromNotification({ title: 'x', body: 'y' })).toBeNull()
  })

  it('builds a banner from a trade_opened push, routed to the trade when trade_id is present', () => {
    const b = tradeBannerFromNotification({
      title: 'Spark opened a trade',
      body: '3 contracts',
      data: { kind: 'trade_opened', agent: 'spark', trade_id: 'abc123' },
    })
    expect(b).toEqual({
      bot: 'spark',
      title: 'Spark opened a trade',
      subtitle: '3 contracts',
      href: '/trade/abc123',
      kind: 'trade_opened',
    })
  })

  it('builds a banner from a trade_closed push, falling back to the agent sheet with no trade_id', () => {
    const b = tradeBannerFromNotification({
      title: 'Flame closed a trade',
      body: '+$120.00',
      data: { kind: 'trade_closed', agent: 'flame' },
    })
    expect(b).toEqual({
      bot: 'flame',
      title: 'Flame closed a trade',
      subtitle: '+$120.00',
      href: '/agents/flame',
      kind: 'trade_closed',
    })
  })

  it('falls back to a generic title/subtitle when the push carries none', () => {
    const opened = tradeBannerFromNotification({ data: { kind: 'trade_opened' } })
    expect(opened?.title).toBe('Trade opened')
    expect(opened?.subtitle).toBe('')
    expect(opened?.bot).toBeNull()
    expect(opened?.href).toBeNull()

    const closed = tradeBannerFromNotification({ data: { kind: 'trade_closed' } })
    expect(closed?.title).toBe('Trade closed')
  })

  it('ignores an unrecognized agent string rather than guessing a mascot', () => {
    const b = tradeBannerFromNotification({
      data: { kind: 'trade_opened', agent: 'not-a-real-bot' },
    })
    expect(b?.bot).toBeNull()
  })
})
