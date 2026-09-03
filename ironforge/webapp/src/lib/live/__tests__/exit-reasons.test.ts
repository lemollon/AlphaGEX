import { describe, it, expect } from 'vitest'
import { classifyExitReason } from '../exit-reasons'

describe('classifyExitReason', () => {
  it('maps profit_target reasons', () => {
    expect(classifyExitReason('profit_target_30pct')).toEqual({ code: 'profit_target', text: 'Profit target hit' })
  })

  it('maps stop loss reasons', () => {
    expect(classifyExitReason('stop_loss_2x')).toEqual({ code: 'stop_loss', text: 'Stop loss hit' })
  })

  it('maps manual/force closes', () => {
    expect(classifyExitReason('manual_close')).toEqual({
      code: 'manual_close',
      text: 'Closed manually by operator',
    })
    expect(classifyExitReason('force_close_eod')).toEqual({
      code: 'manual_close',
      text: 'Closed manually by operator',
    })
  })

  it('maps expired', () => {
    expect(classifyExitReason('expired')).toEqual({ code: 'expired', text: 'Expired' })
  })

  it('falls back to auto_close for any other non-empty scanner reason', () => {
    expect(classifyExitReason('eod_cutoff')).toEqual({ code: 'auto_close', text: 'Auto-closed before expiry' })
    expect(classifyExitReason('swing_green_bank')).toEqual({ code: 'auto_close', text: 'Auto-closed before expiry' })
    expect(classifyExitReason('trailing_lockin')).toEqual({ code: 'auto_close', text: 'Auto-closed before expiry' })
    expect(classifyExitReason('broker_gone_close')).toEqual({ code: 'auto_close', text: 'Auto-closed before expiry' })
  })

  it('falls back to other for null/undefined/empty', () => {
    expect(classifyExitReason(null)).toEqual({ code: 'other', text: 'Other' })
    expect(classifyExitReason(undefined)).toEqual({ code: 'other', text: 'Other' })
    expect(classifyExitReason('')).toEqual({ code: 'other', text: 'Other' })
  })

  it('is case-insensitive', () => {
    expect(classifyExitReason('STOP_LOSS_2X')).toEqual({ code: 'stop_loss', text: 'Stop loss hit' })
  })

  it('never lets scanner shorthand leak into the customer-facing text', () => {
    const cases = ['stop_loss_2x_triggered', 'profit_target_30pct', 'eod_cutoff', 'trailing_lockin']
    for (const reason of cases) {
      const { text } = classifyExitReason(reason)
      expect(text).not.toMatch(/_/)
      expect(text).not.toMatch(/\d/)
    }
  })
})
