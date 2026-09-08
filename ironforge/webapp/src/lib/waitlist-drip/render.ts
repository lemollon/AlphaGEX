/**
 * Waitlist drip renderer — HTML + plain-text parts for one stage.
 *
 * Copy comes from copy.ts untouched; this module only lays it out. Brand per the kit: light
 * background, navy/charcoal copy, IronForge orange accents (Spark, Email 3, may use electric
 * blue). Table-based, inline-styled markup because that is what mail clients render.
 *
 * Personalization: `Hello {first_name},` when a first name is known, else `Hello,` — the
 * kit's fallback. The name is HTML-escaped; it came from a public form.
 *
 * Footer (kit "Implementation" requirements): monitored reply-to (also visible as text),
 * business address, privacy link, preferences link, unsubscribe link, and the per-email
 * approved disclosure. The business address is NOT in this repo (the contact page says
 * "available on request"), so it comes from IRONFORGE_BUSINESS_ADDRESS and the render
 * REFUSES to produce an email without it — a CAN-SPAM footer with a blank where the address
 * goes is worse than no send.
 */

import { supportEmail } from '@/lib/support-address'
import { DRIP_GREETING, DRIP_KICKER, DRIP_SIGNOFF_NAME, DRIP_SIGNOFF_ROLE, dripEmailForStage, type DripEmail } from './copy'

/** Brand palette (kit: light background, navy/charcoal copy, orange accents). */
const BRAND = {
  bg: '#F6F7F9',
  card: '#FFFFFF',
  navy: '#0F172A',
  charcoal: '#334155',
  muted: '#64748B',
  rule: '#E2E8F0',
  orange: '#FD3D1E',
  /** Electric blue — Spark's accent (Email 3 only, per the kit). */
  spark: '#2563EB',
} as const

export interface DripLinks {
  privacyUrl: string
  preferencesUrl: string
  unsubscribeUrl: string
}

export interface RenderInput {
  stage: number
  /** May be empty/undefined → "Hello," fallback. */
  firstName?: string | null
  links: DripLinks
  /** Postal address for the footer. Read from IRONFORGE_BUSINESS_ADDRESS by the caller. */
  businessAddress: string
  /** Monitored reply-to shown in the footer; defaults to supportEmail(). */
  replyTo?: string
}

export interface RenderedEmail {
  stage: number
  subject: string
  html: string
  text: string
}

export function esc(s: string): string {
  return s.replace(/[<>&"']/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' })[c] as string)
}

/** Business address from the environment; '' when unset. Multi-line allowed with "\n" or " | ". */
export function businessAddressFromEnv(): string {
  return (process.env.IRONFORGE_BUSINESS_ADDRESS ?? '').trim()
}

/** First name → "Hello Ada," / "Hello," (kit fallback). Whitespace-only counts as unknown. */
export function greetingFor(firstName?: string | null): string {
  const name = (firstName ?? '').trim()
  return name ? `${DRIP_GREETING} ${name},` : `${DRIP_GREETING},`
}

function addressLines(address: string): string[] {
  return address
    .split(/\n|\s\|\s/)
    .map((l) => l.trim())
    .filter(Boolean)
}

function paragraphHtml(p: { lead?: string; text: string }): string {
  const lead = p.lead ? `<strong style="color:${BRAND.navy}">${esc(p.lead)}</strong> ` : ''
  return `<p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:${BRAND.charcoal}">${lead}${esc(p.text)}</p>`
}

function htmlFor(e: DripEmail, input: RenderInput, replyTo: string): string {
  const accent = e.stage === 3 ? BRAND.spark : BRAND.orange
  const greeting = esc(greetingFor(input.firstName))
  const title = e.title.map((l) => esc(l)).join('<br>')
  const subtitle = e.subtitle
    ? `<p style="margin:0 0 24px;font-size:18px;line-height:1.4;color:${accent};font-weight:bold">${esc(e.subtitle)}</p>`
    : ''
  const body = e.paragraphs.map(paragraphHtml).join('\n')
  const address = addressLines(input.businessAddress).map(esc).join('<br>')
  const { privacyUrl, preferencesUrl, unsubscribeUrl } = input.links

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>${esc(e.subject)}</title>
</head>
<body style="margin:0;padding:0;background:${BRAND.bg};font-family:Arial,Helvetica,sans-serif;color:${BRAND.charcoal}">
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:${BRAND.bg};opacity:0">${esc(e.preview)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:${BRAND.bg}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:${BRAND.card};border-radius:12px;border:1px solid ${BRAND.rule}">
<tr><td style="padding:32px 40px 8px">
  <div style="font-size:22px;font-weight:bold;letter-spacing:1px;color:${BRAND.navy}">IRON<span style="color:${BRAND.orange}">FORGE</span></div>
  <div style="font-size:11px;letter-spacing:2px;color:${BRAND.muted};margin-top:6px">${esc(DRIP_KICKER)}</div>
  <div style="height:3px;width:56px;background:${accent};margin:20px 0 28px"></div>
  <h1 style="margin:0 0 ${e.subtitle ? '8px' : '24px'};font-size:28px;line-height:1.25;color:${BRAND.navy}">${title}</h1>
  ${subtitle}
  <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:${BRAND.charcoal}">${greeting}</p>
${body}
  <p style="margin:28px 0 0;font-size:16px;line-height:1.6;color:${BRAND.charcoal}"><strong style="color:${BRAND.navy}">${esc(DRIP_SIGNOFF_NAME)}</strong><br>${esc(DRIP_SIGNOFF_ROLE)}</p>
</td></tr>
<tr><td style="padding:24px 40px 32px">
  <div style="border-top:1px solid ${BRAND.rule};padding-top:20px;font-size:12px;line-height:1.6;color:${BRAND.muted}">
    <p style="margin:0 0 12px">${esc(e.disclosure)}</p>
    <p style="margin:0 0 12px">Questions? Reply to this email or write to <a href="mailto:${esc(replyTo)}" style="color:${BRAND.charcoal}">${esc(replyTo)}</a>.</p>
    <p style="margin:0 0 12px">${address}</p>
    <p style="margin:0"><a href="${esc(privacyUrl)}" style="color:${BRAND.charcoal}">Privacy Policy</a> &nbsp;·&nbsp; <a href="${esc(preferencesUrl)}" style="color:${BRAND.charcoal}">Email preferences</a> &nbsp;·&nbsp; <a href="${esc(unsubscribeUrl)}" style="color:${BRAND.charcoal}">Unsubscribe</a></p>
  </div>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>`
}

function textFor(e: DripEmail, input: RenderInput, replyTo: string): string {
  const lines: string[] = []
  lines.push(e.preview, '')
  lines.push('IRONFORGE', DRIP_KICKER, '')
  lines.push(...e.title)
  if (e.subtitle) lines.push(e.subtitle)
  lines.push('')
  lines.push(greetingFor(input.firstName), '')
  for (const p of e.paragraphs) {
    lines.push(p.lead ? `${p.lead} ${p.text}` : p.text, '')
  }
  lines.push(DRIP_SIGNOFF_NAME, DRIP_SIGNOFF_ROLE, '')
  lines.push('—', '')
  lines.push(e.disclosure, '')
  lines.push(`Questions? Reply to this email or write to ${replyTo}.`, '')
  lines.push(...addressLines(input.businessAddress), '')
  lines.push(`Privacy Policy: ${input.links.privacyUrl}`)
  lines.push(`Email preferences: ${input.links.preferencesUrl}`)
  lines.push(`Unsubscribe: ${input.links.unsubscribeUrl}`)
  return lines.join('\n')
}

/**
 * Render one stage. Throws on an unknown stage or a missing business address — both are
 * configuration errors the caller must surface, never paper over.
 */
export function renderDripEmail(input: RenderInput): RenderedEmail {
  const e = dripEmailForStage(input.stage)
  if (!e) throw new Error(`waitlist drip: no copy for stage ${input.stage}`)
  if (!input.businessAddress.trim()) {
    throw new Error('waitlist drip: IRONFORGE_BUSINESS_ADDRESS is unset — refusing to render a footer without a postal address')
  }
  for (const [k, v] of Object.entries(input.links)) {
    if (!/^https?:\/\//.test(v)) throw new Error(`waitlist drip: ${k} is not an absolute URL`)
  }
  const replyTo = input.replyTo ?? supportEmail()
  return {
    stage: e.stage,
    subject: e.subject,
    html: htmlFor(e, input, replyTo),
    text: textFor(e, input, replyTo),
  }
}
