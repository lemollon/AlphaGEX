import { describe, it, expect } from 'vitest'
import {
  canTransitionEnrollment, canTransitionBrokerage, canTransitionAgentConfig,
  canTransitionTrading, canTransitionTrial, TERMINAL,
  ENROLLMENT_TRANSITIONS, TRADING_TRANSITIONS, TRIAL_TRANSITIONS, AGENT_CONFIG_TRANSITIONS,
} from '../states'
import { evaluateActivation, type ActivationInput } from '../activation'
import {
  isEligibleTradingDay, advanceTrial, trialLabel,
  TRIAL_ELIGIBLE_DAYS, DEFAULT_TRIAL_DAY_POLICY,
} from '../trading-days'

/* ── state machines ─────────────────────────────────────────────────── */

describe('state machines', () => {
  it('terminal states never transition out', () => {
    for (const s of TERMINAL.enrollment) expect(ENROLLMENT_TRANSITIONS[s]).toEqual([])
    for (const s of TERMINAL.agentConfig) expect(AGENT_CONFIG_TRANSITIONS[s]).toEqual([])
    for (const s of TERMINAL.trading) expect(TRADING_TRANSITIONS[s]).toEqual([])
    for (const s of TERMINAL.trial) expect(TRIAL_TRANSITIONS[s]).toEqual([])
  })

  it('the trial can ONLY be opened from not_started (§7: starts in the activation tx)', () => {
    expect(canTransitionTrial('not_started', 'active')).toBe(true)
    // Nothing may reopen a finished trial — that would hand out a second free run.
    expect(canTransitionTrial('completed', 'active')).toBe(false)
    expect(canTransitionTrial('converted', 'active')).toBe(false)
    expect(canTransitionTrial('canceled', 'active')).toBe(false)
  })

  it('trading cannot jump straight to active — it must pass through activating', () => {
    expect(canTransitionTrading('inactive', 'active')).toBe(false)
    expect(canTransitionTrading('inactive', 'activating')).toBe(true)
    expect(canTransitionTrading('activating', 'active')).toBe(true)
  })

  it('a revoked/reauth brokerage must re-authorize, never flip back to connected', () => {
    expect(canTransitionBrokerage('revoked', 'connected')).toBe(false)
    expect(canTransitionBrokerage('reauth_required', 'connected')).toBe(false)
    expect(canTransitionBrokerage('revoked', 'connecting')).toBe(true)
  })

  it('a stale agent config must be re-validated, not reused', () => {
    expect(canTransitionAgentConfig('stale', 'valid')).toBe(false)
    expect(canTransitionAgentConfig('stale', 'draft')).toBe(true)
    expect(canTransitionAgentConfig('draft', 'valid')).toBe(true)
  })

  it('enrollment branches to setup_required (Automate) or complete (Community)', () => {
    expect(canTransitionEnrollment('billing_pending', 'setup_required')).toBe(true)
    expect(canTransitionEnrollment('billing_pending', 'complete')).toBe(true)
    // No skipping legal.
    expect(canTransitionEnrollment('draft', 'billing_pending')).toBe(false)
  })
})

/* ── activation predicate ───────────────────────────────────────────── */

const READY: ActivationInput = {
  membership: 'active',
  paymentMethodValid: true,
  staleLegalDocuments: [],
  brokerage: 'connected',
  accountEligible: true,
  agentConfig: 'valid',
  killSwitchEngaged: false,
  riskAcknowledged: true,
  authorizationAcknowledged: true,
  previewCurrent: true,
}

describe('activation predicate (§4)', () => {
  it('activates only when every condition holds', () => {
    expect(evaluateActivation(READY)).toEqual({ ok: true, blockers: [] })
  })

  it('FAILS CLOSED on empty input — an omitted field never reads as satisfied', () => {
    const d = evaluateActivation({})
    expect(d.ok).toBe(false)
    // Every single gate should object, not just the first.
    expect(d.blockers.length).toBe(9)
  })

  it.each([
    ['membership', { membership: 'past_due' as const }, 'MEMBERSHIP_NOT_ACTIVE'],
    ['payment', { paymentMethodValid: false }, 'PAYMENT_METHOD_INVALID'],
    ['legal', { staleLegalDocuments: ['TRADING_AUTH'] }, 'LEGAL_ACCEPTANCE_STALE'],
    ['brokerage', { brokerage: 'revoked' as const }, 'BROKERAGE_NOT_CONNECTED'],
    ['account', { accountEligible: false }, 'BROKER_ACCOUNT_INELIGIBLE'],
    ['agent', { agentConfig: 'stale' as const }, 'AGENT_CONFIG_NOT_VALID'],
    ['kill switch', { killSwitchEngaged: true }, 'KILL_SWITCH_ENGAGED'],
    ['acks', { riskAcknowledged: false }, 'ACKNOWLEDGMENTS_MISSING'],
    ['preview', { previewCurrent: false }, 'PREVIEW_STALE'],
  ])('%s alone blocks activation', (_label, patch, code) => {
    const d = evaluateActivation({ ...READY, ...patch })
    expect(d.ok).toBe(false)
    expect(d.blockers.map((b) => b.code)).toContain(code)
  })

  it('past_due may NOT open new trading (payment failed after trial, §11)', () => {
    expect(evaluateActivation({ ...READY, membership: 'past_due' }).ok).toBe(false)
  })

  it("setup_ready MAY activate — the v2 order has no subscription row until activation creates it", () => {
    expect(evaluateActivation({ ...READY, membership: 'setup_ready' })).toEqual({ ok: true, blockers: [] })
  })

  it("setup_ready still requires a valid payment method — it never waives the card check", () => {
    const d = evaluateActivation({ ...READY, membership: 'setup_ready', paymentMethodValid: false })
    expect(d.ok).toBe(false)
    expect(d.blockers.map((b) => b.code)).toContain('PAYMENT_METHOD_INVALID')
  })

  it("a bare 'pending' membership (no sub row, no setup_required enrollment) still blocks", () => {
    expect(evaluateActivation({ ...READY, membership: 'pending' }).ok).toBe(false)
  })

  it('reports EVERY blocker so the customer is not fixed one at a time', () => {
    const d = evaluateActivation({ ...READY, brokerage: 'not_connected', agentConfig: 'draft', accountEligible: false })
    expect(d.blockers.map((b) => b.code).sort()).toEqual(
      ['AGENT_CONFIG_NOT_VALID', 'BROKERAGE_NOT_CONNECTED', 'BROKER_ACCOUNT_INELIGIBLE'].sort(),
    )
  })

  it('surfaces the exact remediable account reason (§12)', () => {
    const d = evaluateActivation({ ...READY, accountEligible: false, accountIneligibleReason: 'Options approval level 3 is required.' })
    expect(d.blockers[0].message).toBe('Options approval level 3 is required.')
    expect(d.blockers[0].remediable).toBe(true)
  })

  it('marks a platform kill switch NOT remediable — never tell a customer to retry it', () => {
    const d = evaluateActivation({ ...READY, killSwitchEngaged: true })
    expect(d.blockers.find((b) => b.code === 'KILL_SWITCH_ENGAGED')!.remediable).toBe(false)
  })
})

/* ── trading-day trial ──────────────────────────────────────────────── */

// Central-Time dates. 2026-07-04 (Sat) / 2026-07-03 observed Independence Day.
const wed = () => new Date(2026, 6, 8)   // Wed 2026-07-08
const sat = () => new Date(2026, 6, 11)  // Sat
const sun = () => new Date(2026, 6, 12)  // Sun
const xmas = () => new Date(2026, 11, 25) // Christmas Day (Fri)

describe('eligible trading days (§7)', () => {
  it('a normal weekday counts', () => {
    expect(isEligibleTradingDay({ ct: wed() })).toEqual({ eligible: true })
  })

  it('weekends never count — this is the whole reason it is not calendar days', () => {
    expect(isEligibleTradingDay({ ct: sat() })).toEqual({ eligible: false, reason: 'weekend' })
    expect(isEligibleTradingDay({ ct: sun() })).toEqual({ eligible: false, reason: 'weekend' })
  })

  it('a full market holiday never counts', () => {
    expect(isEligibleTradingDay({ ct: xmas() })).toEqual({ eligible: false, reason: 'market_holiday' })
  })

  it('OUR outage is not the customer\'s trial day', () => {
    expect(isEligibleTradingDay({ ct: wed(), platformDisabled: true }))
      .toEqual({ eligible: false, reason: 'platform_disabled' })
  })

  it('fails CLOSED past the calendar horizon rather than charging on a guess', () => {
    const beyond = new Date(2099, 6, 8)
    expect(isEligibleTradingDay({ ct: beyond }).eligible).toBe(false)
    expect(isEligibleTradingDay({ ct: beyond }).reason).toBe('calendar_not_covered')
  })

  it('default policy counts paused / no-trade days, which is what stops an endless trial', () => {
    expect(DEFAULT_TRIAL_DAY_POLICY.countUserPausedDays).toBe(true)
    expect(isEligibleTradingDay({ ct: wed(), userPaused: true }).eligible).toBe(true)
    expect(isEligibleTradingDay({ ct: wed(), noQualifyingTrade: true }).eligible).toBe(true)
  })

  it('policy flags are honoured when flipped', () => {
    const p = { ...DEFAULT_TRIAL_DAY_POLICY, countUserPausedDays: false }
    expect(isEligibleTradingDay({ ct: wed(), userPaused: true }, p))
      .toEqual({ eligible: false, reason: 'user_paused' })
  })

  it('exchange-closed reasons beat policy flags — a weekend is never billable', () => {
    const p = { ...DEFAULT_TRIAL_DAY_POLICY, countUserPausedDays: false }
    expect(isEligibleTradingDay({ ct: sat(), userPaused: true }, p).reason).toBe('weekend')
  })
})

describe('trial ledger', () => {
  it('only eligible days advance it', () => {
    expect(advanceTrial(0, { eligible: false, reason: 'weekend' }).daysUsed).toBe(0)
    expect(advanceTrial(0, { eligible: true }).daysUsed).toBe(1)
  })

  it('converts exactly at five and never over-counts', () => {
    let used = 0
    for (let i = 0; i < 10; i++) used = advanceTrial(used, { eligible: true }).daysUsed
    expect(used).toBe(TRIAL_ELIGIBLE_DAYS)
    expect(advanceTrial(used, { eligible: true }).shouldConvert).toBe(true)
  })

  it('does not convert early', () => {
    expect(advanceTrial(3, { eligible: true }).shouldConvert).toBe(false)
    expect(advanceTrial(4, { eligible: true }).shouldConvert).toBe(true)
  })

  it('labels TRADING days, never calendar days (§3 PLAN-01)', () => {
    expect(trialLabel(0)).toBe('5 of 5 trading days left')
    expect(trialLabel(4)).toBe('1 of 5 trading day left')
    expect(trialLabel(5)).toBe('Trial complete')
    expect(trialLabel(0)).not.toMatch(/calendar/i)
  })
})
