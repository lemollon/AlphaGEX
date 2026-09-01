import { describe, it, expect } from 'vitest'
import { isProtectiveSkip, countProtectiveSkipDays } from '../riskProtection'

/**
 * Honest-count invariants: this must never inflate a single blocked day into
 * many (the scanner logs the same reason roughly once a minute), and it must
 * never count a day where the bot actually traded despite an earlier soft
 * block, or an infra/operational skip that has nothing to do with risk
 * management.
 */

describe('isProtectiveSkip', () => {
  it('counts each listed protective gate', () => {
    expect(isProtectiveSkip('skip:standdown')).toBe(true)
    expect(isProtectiveSkip('skip:credit_too_low($0.1200 at sd=1.2)')).toBe(true)
    expect(isProtectiveSkip('skip:event_blackout(FOMC until Sep 1, 2:00 PM CT)')).toBe(true)
    expect(isProtectiveSkip('skip:vix_elevated(0.904>0.90)')).toBe(true)
    expect(isProtectiveSkip('skip:vix_bad_window')).toBe(true)
    expect(isProtectiveSkip('skip:vix_too_high(45.0>cap32)')).toBe(true)
    expect(isProtectiveSkip('skip:cooldown_after_first_loss(first_loss=10:15_CT,20m_left)')).toBe(true)
    expect(isProtectiveSkip('skip:standdown_after_loss')).toBe(true)
    expect(isProtectiveSkip('skip:credit_pct_too_low($0.10 < 5% of $5 width)')).toBe(true)
    expect(isProtectiveSkip('skip:neg_gamma_env(net_gex=-1.20e+09)')).toBe(true)
  })

  it('does not count operational/infra skips', () => {
    expect(isProtectiveSkip('outside_entry_window')).toBe(false)
    expect(isProtectiveSkip('skip:already_traded_today')).toBe(false)
    expect(isProtectiveSkip('skip:max_trades_reached')).toBe(false)
    expect(isProtectiveSkip('skip:no_paper_balance($0)')).toBe(false)
    expect(isProtectiveSkip('skip:no_quote')).toBe(false)
    expect(isProtectiveSkip('skip:bad_collateral')).toBe(false)
    expect(isProtectiveSkip('skip:unknown_bot(xyz)')).toBe(false)
    expect(isProtectiveSkip('skip:tradier_not_configured')).toBe(false)
    expect(isProtectiveSkip('skip:production_race_guard')).toBe(false)
    expect(isProtectiveSkip('skip:production_only_no_fills')).toBe(false)
    expect(isProtectiveSkip('skip:production_backoff(3 consecutive rejects)')).toBe(false)
    expect(isProtectiveSkip('skip:production_stale_positions_blocking(1 stale)')).toBe(false)
    expect(isProtectiveSkip('skip:production_requires_tradier(paper_only_mode)')).toBe(false)
    expect(isProtectiveSkip('skip:production_order_failed(timeout)')).toBe(false)
    expect(isProtectiveSkip('skip:production_primary_no_fill')).toBe(false)
    expect(isProtectiveSkip('skip:sandbox_race_guard')).toBe(false)
    expect(isProtectiveSkip('skip:insufficient_bp($100 < $250/contract)')).toBe(false)
    expect(isProtectiveSkip('skip:low_bp($100)')).toBe(false)
  })

  it('is safe on null, undefined, and empty input — never throws', () => {
    expect(isProtectiveSkip(null)).toBe(false)
    expect(isProtectiveSkip(undefined)).toBe(false)
    expect(isProtectiveSkip('')).toBe(false)
  })
})

describe('countProtectiveSkipDays', () => {
  it('collapses many same-day rows (one per scan minute) into ONE protected day', () => {
    const logs = [
      { logTime: '2026-09-01T15:05:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-01T15:06:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-01T15:07:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-01T15:20:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
    ]
    const count = countProtectiveSkipDays({ logs, tradedCtDates: new Set() })
    expect(count).toBe(1)
  })

  it('excludes a day where the bot traded despite an earlier protective skip', () => {
    const logs = [
      { logTime: '2026-09-01T15:05:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-01T15:06:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
    ]
    // The CT date for these UTC timestamps (mid-afternoon UTC = morning CT).
    const count = countProtectiveSkipDays({ logs, tradedCtDates: new Set(['2026-09-01']) })
    expect(count).toBe(0)
  })

  it('does not count a day with only outside_entry_window rows', () => {
    const logs = [
      { logTime: '2026-09-01T12:00:00Z', reason: 'outside_entry_window' },
      { logTime: '2026-09-01T12:01:00Z', reason: 'outside_entry_window' },
    ]
    expect(countProtectiveSkipDays({ logs, tradedCtDates: new Set() })).toBe(0)
  })

  it('does not count a day with only an infra (production_race_guard) reason', () => {
    const logs = [
      { logTime: '2026-09-01T14:00:00Z', reason: 'skip:production_race_guard' },
    ]
    expect(countProtectiveSkipDays({ logs, tradedCtDates: new Set() })).toBe(0)
  })

  it('counts skip:standdown, skip:credit_too_low, and skip:event_blackout individually', () => {
    expect(countProtectiveSkipDays({
      logs: [{ logTime: '2026-09-01T14:00:00Z', reason: 'skip:standdown' }],
      tradedCtDates: new Set(),
    })).toBe(1)
    expect(countProtectiveSkipDays({
      logs: [{ logTime: '2026-09-02T14:00:00Z', reason: 'skip:credit_too_low($0.10 at sd=1.2)' }],
      tradedCtDates: new Set(),
    })).toBe(1)
    expect(countProtectiveSkipDays({
      logs: [{ logTime: '2026-09-03T14:00:00Z', reason: 'skip:event_blackout(FOMC until 2:00 PM CT)' }],
      tradedCtDates: new Set(),
    })).toBe(1)
  })

  it('counts two distinct protective days as 2', () => {
    const logs = [
      { logTime: '2026-09-01T15:05:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-02T14:10:00Z', reason: 'skip:standdown' },
    ]
    expect(countProtectiveSkipDays({ logs, tradedCtDates: new Set() })).toBe(2)
  })

  it('skips rows with a null or empty reason without throwing', () => {
    const logs = [
      { logTime: '2026-09-01T15:05:00Z', reason: null },
      { logTime: '2026-09-01T15:06:00Z', reason: '' },
      { logTime: '2026-09-01T15:07:00Z', reason: 'skip:vix_elevated(0.91>0.90)' },
    ]
    expect(() => countProtectiveSkipDays({ logs, tradedCtDates: new Set() })).not.toThrow()
    expect(countProtectiveSkipDays({ logs, tradedCtDates: new Set() })).toBe(1)
  })
})
