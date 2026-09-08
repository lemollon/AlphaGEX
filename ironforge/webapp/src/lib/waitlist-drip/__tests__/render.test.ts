import { describe, it, expect } from 'vitest'
import { DRIP_EMAILS, DRIP_FINAL_STAGE, DRIP_KICKER, DRIP_SIGNOFF_NAME, DRIP_SIGNOFF_ROLE } from '../copy'
import { esc, greetingFor, renderDripEmail } from '../render'

const links = {
  privacyUrl: 'https://ironforge.example/privacy',
  preferencesUrl: 'https://ironforge.example/email/preferences/tok',
  unsubscribeUrl: 'https://ironforge.example/email/unsubscribe/tok',
}
const address = 'IronForge Technologies LLC\n123 Example St\nAustin, TX 78701'

function render(stage: number, firstName?: string | null) {
  return renderDripEmail({ stage, firstName, links, businessAddress: address, replyTo: 'support@ironforge.trade' })
}

describe('kit copy is complete', () => {
  it('has six emails with subject, preview, title, paragraphs and a disclosure each', () => {
    expect(DRIP_EMAILS.map((e) => e.stage)).toEqual([1, 2, 3, 4, 5, 6])
    expect(DRIP_FINAL_STAGE).toBe(6)
    for (const e of DRIP_EMAILS) {
      expect(e.subject.length, `stage ${e.stage} subject`).toBeGreaterThan(5)
      expect(e.preview.length, `stage ${e.stage} preview`).toBeGreaterThan(5)
      expect(e.title.length, `stage ${e.stage} title`).toBeGreaterThan(0)
      expect(e.paragraphs.length, `stage ${e.stage} paragraphs`).toBeGreaterThanOrEqual(8)
      expect(e.disclosure, `stage ${e.stage} disclosure`).toMatch(/guarantee profits or prevent losses\.$/)
    }
  })

  it('carries the approved subjects verbatim', () => {
    expect(DRIP_EMAILS.map((e) => e.subject)).toEqual([
      'Welcome to IronForge—you’re on the list.',
      'Meet the neighbors behind IronForge',
      'Meet Spark: morning setups. Juicy premium.',
      'Meet Flame: our afternoon trade agent',
      'Your money stays in your brokerage.',
      "Meet Tradier, IronForge's brokerage partner",
    ])
  })

  it('Spark and Flame carry their secondary headline; the others do not', () => {
    expect(DRIP_EMAILS[2].subtitle).toBe('Morning setups. Juicy premium. Defined rules.')
    expect(DRIP_EMAILS[3].subtitle).toBe('Afternoon opportunities. A measured approach.')
    expect(DRIP_EMAILS.filter((e) => e.subtitle).length).toBe(2)
  })

  it('Email 6 carries the Tradier brokerage-services disclosure', () => {
    expect(DRIP_EMAILS[5].disclosure).toMatch(/^Brokerage services are provided by Tradier Brokerage\./)
  })
})

describe('personalization', () => {
  it('"Hello Ada," with a first name, "Hello," as the fallback', () => {
    expect(greetingFor('Ada')).toBe('Hello Ada,')
    expect(greetingFor('')).toBe('Hello,')
    expect(greetingFor('   ')).toBe('Hello,')
    expect(greetingFor(null)).toBe('Hello,')
    expect(greetingFor(undefined)).toBe('Hello,')
  })

  it('renders the greeting into both parts and escapes the name', () => {
    const r = render(1, 'Ada')
    expect(r.html).toContain('Hello Ada,')
    expect(r.text).toContain('Hello Ada,')
    const nameless = render(1, null)
    expect(nameless.html).toContain('>Hello,</p>')
    expect(nameless.text).toContain('\nHello,\n')
    const hostile = render(1, '<img src=x onerror=alert(1)>')
    expect(hostile.html).not.toContain('<img')
    expect(hostile.html).toContain('&lt;img')
  })
})

describe('every stage renders with the required footer', () => {
  for (const e of DRIP_EMAILS) {
    it(`stage ${e.stage}: subject, preview, title, all paragraphs, sign-off, disclosure, links, address`, () => {
      const r = render(e.stage, 'Ada')
      expect(r.subject).toBe(e.subject)
      expect(r.html).toContain(e.preview)
      expect(r.text.startsWith(e.preview)).toBe(true)
      for (const line of e.title) expect(r.html).toContain(line)
      for (const p of e.paragraphs) {
        expect(r.html).toContain(p.text)
        expect(r.text).toContain(p.text)
        if (p.lead) {
          expect(r.html).toContain(`<strong style="color:#0F172A">${p.lead}</strong> ${p.text}`)
          expect(r.text).toContain(`${p.lead} ${p.text}`)
        }
      }
      expect(r.html).toContain(DRIP_KICKER)
      expect(r.html).toContain(esc(DRIP_SIGNOFF_NAME))
      expect(r.text).toContain(DRIP_SIGNOFF_NAME)
      expect(r.html).toContain(DRIP_SIGNOFF_ROLE)
      expect(r.html).toContain(e.disclosure)
      expect(r.text).toContain(e.disclosure)
      // Footer requirements from the kit.
      expect(r.html).toContain('support@ironforge.trade')
      expect(r.html).toContain('123 Example St')
      expect(r.html).toContain('Austin, TX 78701')
      expect(r.html).toContain(`href="${links.privacyUrl}"`)
      expect(r.html).toContain(`href="${links.preferencesUrl}"`)
      expect(r.html).toContain(`href="${links.unsubscribeUrl}"`)
      expect(r.text).toContain(`Unsubscribe: ${links.unsubscribeUrl}`)
      expect(r.text).toContain(`Email preferences: ${links.preferencesUrl}`)
      expect(r.text).toContain(`Privacy Policy: ${links.privacyUrl}`)
    })
  }

  it('is light-background, navy copy, orange accent — and Spark (stage 3) alone uses electric blue', () => {
    const one = render(1)
    expect(one.html).toContain('background:#F6F7F9')
    expect(one.html).toContain('color:#0F172A')
    expect(one.html).toContain('background:#FD3D1E') // accent bar
    expect(one.html).not.toContain('#2563EB')
    const spark = render(3)
    expect(spark.html).toContain('background:#2563EB')
  })
})

describe('refuses to render an incomplete footer', () => {
  it('throws without a business address', () => {
    expect(() => renderDripEmail({ stage: 1, links, businessAddress: '   ' })).toThrow(/IRONFORGE_BUSINESS_ADDRESS/)
  })

  it('throws on a relative link', () => {
    expect(() =>
      renderDripEmail({ stage: 1, links: { ...links, unsubscribeUrl: '/email/unsubscribe/tok' }, businessAddress: address }),
    ).toThrow(/unsubscribeUrl/)
  })

  it('throws on an unknown stage', () => {
    expect(() => renderDripEmail({ stage: 7, links, businessAddress: address })).toThrow(/stage 7/)
  })
})
