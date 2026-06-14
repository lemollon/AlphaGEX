import { describe, it, expect } from 'vitest'
import { buildBrokerageNote } from '@/lib/attio'

describe('buildBrokerageNote', () => {
  it('targets the given Person record and includes the brokerage + connected timestamp', () => {
    const note = buildBrokerageNote('rec_123', {
      brokerage: 'Tastytrade',
      accountName: 'Individual …4567',
      accountCount: 1,
      connectedAt: '2026-06-14T22:00:00.000Z',
    })
    const data = (note as { data: Record<string, unknown> }).data
    expect(data.parent_object).toBe('people')
    expect(data.parent_record_id).toBe('rec_123')
    expect(data.title).toMatch(/brokerage connected/i)
    const content = String(data.content)
    expect(content).toContain('Tastytrade')
    expect(content).toContain('Individual …4567')
    expect(content).toContain('2026-06-14T22:00:00.000Z')
  })

  it('degrades gracefully when optional fields are missing', () => {
    const note = buildBrokerageNote('rec_x', {})
    const content = String((note as { data: { content: string } }).data.content)
    expect(content).toContain('Brokerage: —')
    expect(content).not.toContain('Account:') // omitted when absent
  })
})
