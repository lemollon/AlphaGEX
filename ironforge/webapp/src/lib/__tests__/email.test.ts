import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isEmailConfigured, sendVerificationEmail } from '@/lib/email'

const OLD = { ...process.env }

beforeEach(() => {
  vi.restoreAllMocks()
  process.env.RESEND_API_KEY = 'test-key'
  process.env.EMAIL_FROM = 'IronForge <no-reply@ironforge.test>'
})
afterEach(() => {
  process.env = { ...OLD }
})

describe('isEmailConfigured', () => {
  it('is true only when both key and from are set', () => {
    expect(isEmailConfigured()).toBe(true)
    delete process.env.RESEND_API_KEY
    expect(isEmailConfigured()).toBe(false)
  })
})

describe('sendVerificationEmail', () => {
  it('skips (no send) when not configured', async () => {
    delete process.env.RESEND_API_KEY
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendVerificationEmail({ to: 'a@b.com', verifyUrl: 'https://x/verify', firstName: 'Ada' })
    expect(res.skipped).toBe(true)
    expect(res.sent).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('posts to Resend with the recipient and link, returns sent on 200', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'e1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendVerificationEmail({ to: 'ada@b.com', verifyUrl: 'https://x/verify?token=abc', firstName: 'Ada' })
    expect(res.sent).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('api.resend.com/emails')
    expect((init as any).headers.Authorization).toBe('Bearer test-key')
    const body = JSON.parse((init as any).body)
    expect(body.to).toBe('ada@b.com')
    expect(body.from).toContain('ironforge.test')
    expect(body.html).toContain('https://x/verify?token=abc')
  })

  it('returns sent=false with an error on a non-2xx response', async () => {
    const fetchMock = vi.fn(async () => new Response('nope', { status: 422 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendVerificationEmail({ to: 'a@b.com', verifyUrl: 'https://x', firstName: 'A' })
    expect(res.sent).toBe(false)
    expect(res.error).toBeTruthy()
  })
})
