import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * AN ALERT THAT DOES NOT REACH A PHONE IS NOT AN ALERT.
 *
 * `@here` does not push. A whole family of IronForge alerts landed in a Discord
 * channel nobody was looking at, and the standing fix — "get the Discord user ID so
 * `<@id>` can ping" — was never done.
 *
 * 🚨 It also was never necessary. `ALERT_NTFY_TOPIC` has been configured on
 * ironforge-customer the whole time, and ntfy IS a phone push. The watchdog and the
 * "has not traded" heartbeat now go out over it. Discord keeps the readable record.
 */

const SMS = readFileSync(join(__dirname, '..', 'sms.ts'), 'utf8')
const SCANNER = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

describe('the ops push uses the channels that actually reach a phone', () => {
  it('sends over ntfy, which was configured all along', () => {
    const fn = SMS.slice(SMS.indexOf('export async function sendOpsPush('))
    expect(fn).toMatch(/isNtfyConfigured\(\)/)
    expect(fn).toMatch(/https:\/\/ntfy\.sh\//)
  })

  it('raises ntfy priority for a critical alert so it breaks through a quiet phone', () => {
    const fn = SMS.slice(SMS.indexOf('export async function sendOpsPush('))
    expect(fn).toMatch(/Priority: args\.severity === 'critical' \? 'high' : 'default'/)
  })

  it('spends an SMS segment or a Twilio charge ONLY on a critical alert', () => {
    // "the watchdog healed something" is an FYI. It does not deserve a text message.
    const fn = SMS.slice(SMS.indexOf('export async function sendOpsPush('))
    const gated = fn.slice(fn.indexOf("if (args.severity === 'critical') {"))
    expect(gated).toMatch(/isSmsGatewayConfigured\(\)/)
    expect(gated).toMatch(/isTwilioConfigured\(\)/)
    // ...and those must NOT appear before the gate.
    const before = fn.slice(0, fn.indexOf("if (args.severity === 'critical') {"))
    expect(before).not.toMatch(/isTwilioConfigured\(\)\s*\)\s*\{/)
  })

  it('does NOT post to Discord — postOpsAlert already does, and two is noise', () => {
    const fn = SMS.slice(SMS.indexOf('export async function sendOpsPush('))
    expect(fn).not.toMatch(/sendViaDiscord/)
  })

  it('says so out loud when no phone channel is configured', () => {
    const fn = SMS.slice(SMS.indexOf('export async function sendOpsPush('))
    expect(fn).toMatch(/NO phone push/)
    expect(fn).toMatch(/skipped: true/)
  })
})

describe('both alarms are wired to it', () => {
  it('the watchdog pushes its result', () => {
    const fn = SCANNER.slice(
      SCANNER.indexOf('const summary = summarizeWatchdogRun('),
      SCANNER.indexOf('const parts = ['),
    )
    expect(fn).toMatch(/void sendOpsPush\(\{/)
    expect(fn).toMatch(/severity: summary\.severity/)
    // Discord embed still goes out alongside it.
    expect(fn).toMatch(/void postOpsAlert\(\{/)
  })

  it('the "has not traded" heartbeat pushes at critical', () => {
    const fn = SCANNER.slice(SCANNER.indexOf('async function tradeHeartbeatCheck('))
    expect(fn).toMatch(/void sendOpsPush\(\{[\s\S]{0,300}?severity: 'critical'/)
    expect(fn).toMatch(/has not traded in \$\{verdict\.silentDays\} trading days/)
  })

  it('neither can take a scan cycle down', () => {
    // An alert path that kills the thing it is alerting about is worse than silence.
    const wd = SCANNER.slice(
      SCANNER.indexOf('const summary = summarizeWatchdogRun('),
      SCANNER.indexOf('const parts = ['),
    )
    expect(wd).toMatch(/sendOpsPush\([\s\S]{0,400}?\}\)\.catch\(/)
  })
})
