import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { sendPasswordResetEmail } from '@/lib/email'

const OLD = { ...process.env }
beforeEach(() => {
  vi.restoreAllMocks()
  process.env.RESEND_API_KEY = 'test-key'
  process.env.EMAIL_FROM = 'IronForge <no-reply@ironforge.test>'
})
afterEach(() => { process.env = { ...OLD } })

describe('sendPasswordResetEmail', () => {
  it('skips when not configured', async () => {
    delete process.env.RESEND_API_KEY
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendPasswordResetEmail({ to: 'a@b.com', resetUrl: 'https://x/reset?token=t', firstName: 'Ada' })
    expect(res.skipped).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('posts the reset link to Resend on success', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'e1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await sendPasswordResetEmail({ to: 'ada@b.com', resetUrl: 'https://x/reset?token=abc', firstName: 'Ada' })
    expect(res.sent).toBe(true)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as any).body)
    expect(body.to).toBe('ada@b.com')
    expect(body.subject).toMatch(/reset/i)
    expect(body.html).toContain('https://x/reset?token=abc')
  })
})
