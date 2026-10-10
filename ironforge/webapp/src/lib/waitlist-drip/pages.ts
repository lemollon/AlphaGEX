/**
 * Server-rendered HTML for the public /email/preferences/[token] and /email/unsubscribe/[token]
 * pages. Plain strings, not React: both paths are Route Handlers so that one URL can answer
 * GET (show state) AND POST (change it) — a page.tsx cannot take a POST, and RFC 8058
 * one-click unsubscribe is a bare form POST from the mail client to the List-Unsubscribe
 * URL with no page load at all.
 *
 * Brand matches the emails: light background, navy/charcoal copy, orange accent.
 */

import { esc } from './render'
import type { PreferenceState } from './sequence'

const CSS = `
  :root { color-scheme: light; }
  body { margin:0; background:#F6F7F9; font-family: Arial, Helvetica, sans-serif; color:#334155; }
  .wrap { max-width:560px; margin:48px auto; padding:0 16px; }
  .card { background:#fff; border:1px solid #E2E8F0; border-radius:12px; padding:32px 36px; }
  .brand { font-size:22px; font-weight:bold; letter-spacing:1px; color:#0F172A; }
  .brand span { color:#FD3D1E; }
  .bar { height:3px; width:56px; background:#FD3D1E; margin:20px 0 24px; }
  h1 { font-size:24px; line-height:1.25; color:#0F172A; margin:0 0 16px; }
  p { font-size:16px; line-height:1.6; margin:0 0 16px; }
  .muted { color:#64748B; font-size:14px; }
  .btn { display:inline-block; background:#FD3D1E; color:#fff; text-decoration:none; padding:12px 20px; border-radius:8px; font-size:15px; font-weight:bold; border:0; cursor:pointer; }
  .btn.secondary { background:#fff; color:#0F172A; border:1px solid #CBD5E1; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .status { padding:12px 16px; border-radius:8px; background:#F1F5F9; font-size:15px; }
  a { color:#334155; }
`

function shell(title: string, body: string): string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${esc(title)} — IronForge</title><style>${CSS}</style></head><body><div class="wrap"><div class="card"><div class="brand">IRON<span>FORGE</span></div><div class="bar"></div>${body}<p class="muted" style="margin-top:28px">IronForge Technologies LLC · <a href="/privacy">Privacy Policy</a></p></div></div></body></html>`
}

function greet(state: PreferenceState): string {
  const n = (state.firstName ?? '').trim()
  return n ? `Hello ${esc(n)},` : 'Hello,'
}

function statusLine(state: PreferenceState): string {
  if (state.unsubscribed) return 'You are <strong>unsubscribed</strong> from IronForge waitlist emails.'
  if (state.status === 'completed') return 'You are subscribed. You have received every email in the launch series.'
  if (state.status === 'suppressed') return 'You are not currently receiving the launch series.'
  return `You are <strong>subscribed</strong> to the IronForge launch series (${state.stage} of ${state.finalStage} sent).`
}

export function preferencesPage(state: PreferenceState, notice?: string): string {
  const noticeHtml = notice ? `<div class="status" style="margin-bottom:16px">${esc(notice)}</div>` : ''
  const action = state.unsubscribed
    ? `<form method="post"><input type="hidden" name="action" value="resubscribe"><button class="btn" type="submit">Resume waitlist emails</button></form>`
    : `<form method="post"><input type="hidden" name="action" value="unsubscribe"><button class="btn secondary" type="submit">Unsubscribe from waitlist emails</button></form>`
  return shell(
    'Email preferences',
    `<h1>Email preferences</h1>
     <p>${greet(state)}</p>
     ${noticeHtml}
     <p>Address: <strong>${esc(state.email)}</strong></p>
     <div class="status">${statusLine(state)}</div>
     <p class="muted" style="margin-top:16px">The waitlist series is the only marketing email IronForge sends today. Account-related messages (sign-in codes, trade approvals) are not affected by this setting.</p>
     <div class="row" style="margin-top:20px">${action}</div>`,
  )
}

/** `preferencesHref` = /email/preferences/<token>; the route knows the token, the page does not. */
export function unsubscribeConfirmPage(state: PreferenceState, preferencesHref: string): string {
  if (state.unsubscribed) return unsubscribedPage(state, preferencesHref)
  return shell(
    'Unsubscribe',
    `<h1>Unsubscribe from waitlist emails?</h1>
     <p>${greet(state)}</p>
     <p>Confirm to stop the IronForge launch series for <strong>${esc(state.email)}</strong>.</p>
     <div class="row">
       <form method="post"><button class="btn" type="submit">Yes, unsubscribe</button></form>
       <a class="btn secondary" href="${esc(preferencesHref)}">Manage preferences</a>
     </div>`,
  )
}

export function unsubscribedPage(state: PreferenceState, preferencesHref: string): string {
  return shell(
    'Unsubscribed',
    `<h1>You're unsubscribed.</h1>
     <p>${greet(state)}</p>
     <p><strong>${esc(state.email)}</strong> will not receive any more IronForge waitlist emails.</p>
     <p class="muted">Changed your mind? You can resume from the <a href="${esc(preferencesHref)}">email preferences</a> page any time.</p>`,
  )
}

export function notFoundPage(): string {
  return shell(
    'Link not recognised',
    `<h1>We couldn't find that link.</h1>
     <p>The preferences link may have been copied incompletely. Open the link from the most recent IronForge email, or write to us at the address in its footer.</p>`,
  )
}
