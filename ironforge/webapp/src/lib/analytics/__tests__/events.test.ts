import { describe, it, expect } from 'vitest'
import { isAllowedEvent, isAllowedSurface, allowedPropsFor } from '../events'

describe('isAllowedEvent', () => {
  it('accepts every dev-handoff event name', () => {
    for (const name of [
      'cta_click',
      'agent_filter',
      'hero_chart_tab',
      'waitlist_open',
      'waitlist_submit',
      'waitlist_error',
      'section_view',
      'enroll_step_view',
      'enroll_step_complete',
      'enroll_sso',
      'legal_accept_all',
      'agent_selected',
      'broker_connect_start',
      'broker_connect_success',
      'broker_connect_cancel',
      'broker_connect_error',
      'ember_balance_block',
      'billing_trial_started',
      'enroll_complete',
      'app_open',
      'tab_view',
      'period_select',
      'chart_scrub',
      'agent_sheet_open',
      'trade_sheet_open',
      'add_agent_start',
      'add_agent_complete',
      'agent_pause',
      'agent_resume',
      'pause_all',
      'community_post',
      'community_like',
      'community_reply',
      'sparky_question',
      'push_open',
      'theme_toggle',
    ]) {
      expect(isAllowedEvent(name)).toBe(true)
    }
  })

  it('rejects an unknown name', () => {
    expect(isAllowedEvent('totally_made_up')).toBe(false)
    expect(isAllowedEvent(undefined)).toBe(false)
    expect(isAllowedEvent(123)).toBe(false)
  })
})

describe('isAllowedSurface', () => {
  it('accepts web, ios, android only', () => {
    expect(isAllowedSurface('web')).toBe(true)
    expect(isAllowedSurface('ios')).toBe(true)
    expect(isAllowedSurface('android')).toBe(true)
    expect(isAllowedSurface('desktop')).toBe(false)
  })
})

describe('allowedPropsFor', () => {
  it('keeps only props declared for that event', () => {
    const out = allowedPropsFor('cta_click', { cta: 'create_account', placement: 'hero', extra: 'nope' })
    expect(out).toEqual({ cta: 'create_account', placement: 'hero' })
  })

  it('returns null when every prop is dropped or none supplied', () => {
    expect(allowedPropsFor('legal_accept_all', { anything: 1 })).toBeNull()
    expect(allowedPropsFor('cta_click', null)).toBeNull()
  })
})
