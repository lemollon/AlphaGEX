/**
 * A non-2xx response, carrying the status and the parsed body.
 *
 * `message` deliberately keeps the OLD precedence (`error` first) so no existing screen
 * changes its wording. What is new is that the body survives: a route can answer with a
 * machine code AND a sentence written for the customer, and the caller that knows what
 * that code means can show the sentence.
 *
 * The case that forced this: POST /api/account/deletion-request answers 409 with
 * `error: 'open_positions'` plus a `message` explaining which positions are still live.
 * Rendering the code would have told a customer trying to delete their account, and
 * therefore already unhappy, the literal string "open_positions".
 */
export class ApiError extends Error {
  readonly status: number
  readonly body: Record<string, unknown> | null

  constructor(message: string, status: number, body: Record<string, unknown> | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }

  /** The route's human-readable sentence if it wrote one, else this error's message. */
  get humanMessage(): string {
    const m = this.body?.message
    return typeof m === 'string' && m.trim() ? m : this.message
  }
}
