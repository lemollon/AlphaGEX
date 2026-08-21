import { describe, it, expect } from 'vitest'
import { ApiError } from './errors'

/**
 * The case this exists for: a customer taps "Delete my account", the server refuses with
 * 409 `{ error: 'open_positions', message: 'You still have 2 positions…' }`, and the
 * screen must show the sentence, not the code.
 */
describe('ApiError.humanMessage', () => {
  it("prefers the route's sentence over the machine code", () => {
    const e = new ApiError('open_positions', 409, {
      error: 'open_positions',
      message: 'You still have 2 positions that are not settled.',
    })
    expect(e.humanMessage).toBe('You still have 2 positions that are not settled.')
    // The code is still reachable — screens branch on it.
    expect(e.message).toBe('open_positions')
    expect(e.status).toBe(409)
  })

  it('falls back to the code when the route wrote no sentence', () => {
    expect(new ApiError('unauthorized', 401, { error: 'unauthorized' }).humanMessage).toBe(
      'unauthorized',
    )
  })

  it('treats a whitespace-only message as absent', () => {
    // Otherwise the UI renders an empty error box and the customer sees a failure with
    // no text at all, which is worse than showing the code.
    expect(new ApiError('open_positions', 409, { message: '   ' }).humanMessage).toBe(
      'open_positions',
    )
  })

  it('survives a body that is not an object at all', () => {
    // res.json() returns null on an HTML error page from a proxy — a real case, since
    // Render returns HTML for some upstream failures.
    expect(new ApiError('Request failed (502)', 502, null).humanMessage).toBe(
      'Request failed (502)',
    )
  })

  it('ignores a non-string message rather than rendering "[object Object]"', () => {
    expect(new ApiError('bad', 400, { message: { nested: true } }).humanMessage).toBe('bad')
  })
})
