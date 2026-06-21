import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { sendTradeApprovalEmail } from '@/lib/email'

const OLD = { ...process.env }
beforeEach(() => {
  vi.restoreAllMocks()
  process.env.RESEND_API_KEY = 'test-key'
  process.env.EMAIL_FROM = 'IronForge <no-reply@ironforge.test>'
})
afterEach(() => { process.env = { ...OLD } })

describe('sendTradeApprovalEmail', () => {
  it('skips when not configured', async () => {
    delete process.env.RESEND_API_KEY
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendTradeApprovalEmail({
      to: 'a@b.com', firstName: 'Ada', summary: 'BUY 5 AAPL (Market)', approveUrl: 'https://x/account/trades',
    })
    expect(res.skipped).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('posts the approve link + trade summary to Resend on success', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'e1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendTradeApprovalEmail({
      to: 'ada@b.com', firstName: 'Ada', summary: 'BUY 5 AAPL (Market)', approveUrl: 'https://x/account/trades',
    })
    expect(res.sent).toBe(true)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body)
    expect(body.to).toBe('ada@b.com')
    expect(body.subject).toMatch(/approve/i)
    expect(body.html).toContain('https://x/account/trades')
    expect(body.html).toContain('BUY 5 AAPL (Market)')
  })

  it('reports an error when Resend rejects', async () => {
    const fetchMock = vi.fn(async () => new Response('bad', { status: 422 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendTradeApprovalEmail({
      to: 'ada@b.com', firstName: 'Ada', summary: 'SELL 1 TSLA (Market)', approveUrl: 'https://x/account/trades',
    })
    expect(res.sent).toBe(false)
    expect(res.error).toMatch(/Resend 422/)
  })
})
