import { describe, it, expect } from 'vitest'
import { classifyScanRow, buildActivityFeed, PROTECTIVE_GATE_LABELS } from '../activityFeed'

/**
 * Compliance-critical invariants: a curated label must NEVER contain the raw
 * internal reason string it was derived from, and an unbroken run of
 * same-reason SCAN rows (the scanner logs one roughly every minute) must
 * collapse to ONE feed entry, never one per row.
 */

describe('classifyScanRow', () => {
  it('maps traded to the lifecycle label', () => {
    const r = classifyScanRow({ action: 'traded', reason: 'traded:CREDIT=1.20' })
    expect(r.kind).toBe('lifecycle')
    expect(r.label).toBe('Opened a new trade')
  })

  it('maps outside_window and outside_entry_window to neutral labels', () => {
    expect(classifyScanRow({ action: 'outside_window', reason: null }).label).toBe('Outside market hours')
    expect(classifyScanRow({ action: 'outside_entry_window', reason: null }).label)
      .toBe("Outside today's entry window")
  })

  it('maps every protective no_trade gate to its exact label', () => {
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:vix_elevated(0.904>0.90)' }))
      .toMatchObject({ label: 'VIX volatility gate held', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:vix_bad_window' }))
      .toMatchObject({ label: 'Waiting for enough VIX history to confirm conditions', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:vix_too_high(45.0>cap32)' }))
      .toMatchObject({ label: 'VIX too high, held for safety', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:event_blackout(FOMC until 2:00 PM CT)' }))
      .toMatchObject({ label: 'Paused for a scheduled market event', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:cooldown_after_first_loss(10:15_CT)' }))
      .toMatchObject({ label: 'Cooling down after a recent loss', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:standdown' }))
      .toMatchObject({ label: 'Cooling down after a recent loss', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:standdown_after_loss' }))
      .toMatchObject({ label: 'Cooling down after a recent loss', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:credit_too_low($0.10 at sd=1.2)' }))
      .toMatchObject({ label: 'Premium too thin to be worth the risk', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:credit_pct_too_low($0.10<5%)' }))
      .toMatchObject({ label: 'Premium too thin to be worth the risk', kind: 'gate' })
    expect(classifyScanRow({ action: 'no_trade', reason: 'skip:neg_gamma_env(net_gex=-1.2e9)' }))
      .toMatchObject({ label: 'Market regime not favorable right now', kind: 'gate' })
  })

  it('shipped labels match the spec table verbatim', () => {
    expect(PROTECTIVE_GATE_LABELS['skip:vix_elevated']).toBe('VIX volatility gate held')
    expect(PROTECTIVE_GATE_LABELS['skip:vix_bad_window']).toBe('Waiting for enough VIX history to confirm conditions')
    expect(PROTECTIVE_GATE_LABELS['skip:vix_too_high']).toBe('VIX too high, held for safety')
    expect(PROTECTIVE_GATE_LABELS['skip:event_blackout']).toBe('Paused for a scheduled market event')
    expect(PROTECTIVE_GATE_LABELS['skip:cooldown_after_first_loss']).toBe('Cooling down after a recent loss')
    expect(PROTECTIVE_GATE_LABELS['skip:standdown']).toBe('Cooling down after a recent loss')
    expect(PROTECTIVE_GATE_LABELS['skip:standdown_after_loss']).toBe('Cooling down after a recent loss')
    expect(PROTECTIVE_GATE_LABELS['skip:credit_too_low']).toBe('Premium too thin to be worth the risk')
    expect(PROTECTIVE_GATE_LABELS['skip:credit_pct_too_low']).toBe('Premium too thin to be worth the risk')
    expect(PROTECTIVE_GATE_LABELS['skip:neg_gamma_env']).toBe('Market regime not favorable right now')
  })

  it('maps an unrecognized/infra no_trade reason to the generic neutral label, never leaking it', () => {
    const infraReasons = ['already_traded_today', 'max_trades_reached(1/1)', 'production_race_guard', 'low_bp($100)']
    for (const reason of infraReasons) {
      const r = classifyScanRow({ action: 'no_trade', reason })
      expect(r.kind).toBe('neutral')
      expect(r.label).toBe('Checking market conditions')
      // Compliance-critical: the raw reason must never leak into the label.
      expect(r.label).not.toContain('production')
      expect(r.label).not.toContain('already_traded')
      expect(r.label).not.toContain('max_trades')
      expect(r.label).not.toContain('low_bp')
    }
  })

  it('maps skip (infra/data) reasons to a generic label', () => {
    expect(classifyScanRow({ action: 'skip', reason: 'tradier_not_configured' }).label)
      .toBe('Checking market data')
    expect(classifyScanRow({ action: 'skip', reason: 'no_spy_quote' }).label)
      .toBe('Checking market data')
  })

  it('maps error to a calm label regardless of the underlying error text, never leaking it', () => {
    const fakeError = 'TypeError: cannot read property strikeWidth of undefined at tryOpenTrade'
    const r = classifyScanRow({ action: 'error', reason: fakeError })
    expect(r.label).toBe('Checking system health')
    expect(r.label).not.toContain('TypeError')
    expect(r.label).not.toContain('strikeWidth')
    expect(r.label).not.toContain('tryOpenTrade')
  })

  it('maps the scan fallback (and anything unrecognized) to a generic label', () => {
    expect(classifyScanRow({ action: 'scan', reason: null }).label).toBe('Scanning the market')
    expect(classifyScanRow({ action: 'some_future_action', reason: null }).label).toBe('Scanning the market')
  })
})

describe('buildActivityFeed', () => {
  it('collapses 15 consecutive same-gate rows one minute apart into ONE ongoing entry', () => {
    const rows = Array.from({ length: 15 }, (_, i) => ({
      logTime: new Date(Date.UTC(2026, 8, 1, 15, 5 + i)).toISOString(), // 15:05Z..15:19Z -> 10:05..10:19 CT
      action: 'no_trade',
      reason: 'skip:vix_elevated(0.904>0.90)',
    }))
    const feed = buildActivityFeed(rows)
    expect(feed).toHaveLength(1)
    expect(feed[0].kind).toBe('gate')
    expect(feed[0].label).toBe('VIX volatility gate held')
    expect(feed[0].isOngoing).toBe(true)
    expect(feed[0].timeLabel).toBe('10:05 AM–10:19 AM CT')
  })

  it('a realistic full day collapses to 3 segments, newest first, only the newest is ongoing', () => {
    const rows: Array<{ logTime: string; action: string; reason: string | null }> = []
    // 8:30–10:04 CT -> outside_entry_window (before the SPARK/FLAME entry window opens)
    for (let m = 0; m <= 94; m += 1) {
      rows.push({
        logTime: new Date(Date.UTC(2026, 8, 1, 13, 30 + m)).toISOString(), // 13:30Z = 8:30 CT
        action: 'outside_entry_window',
        reason: 'Past entry cutoff',
      })
    }
    // 10:05–10:20 CT -> VIX gate held
    for (let m = 0; m <= 15; m += 1) {
      rows.push({
        logTime: new Date(Date.UTC(2026, 8, 1, 15, 5 + m)).toISOString(),
        action: 'no_trade',
        reason: 'skip:vix_elevated(0.904>0.90)',
      })
    }
    // 10:21–15:00 CT -> outside_entry_window again (gate cleared, still outside window in this fixture)
    for (let m = 0; m <= 279; m += 1) {
      rows.push({
        logTime: new Date(Date.UTC(2026, 8, 1, 15, 21 + m)).toISOString(),
        action: 'outside_entry_window',
        reason: 'Past entry cutoff',
      })
    }

    const feed = buildActivityFeed(rows, { max: 100 })
    expect(feed).toHaveLength(3)
    // newest-first: index 0 is the LAST chronological segment (10:21+)
    expect(feed[0].label).toBe("Outside today's entry window")
    expect(feed[0].isOngoing).toBe(true)
    // the middle segment (VIX gate) is NOT ongoing
    expect(feed[1].label).toBe('VIX volatility gate held')
    expect(feed[1].isOngoing).toBe(false)
    // the oldest segment (first outside_entry_window run) is NOT ongoing
    expect(feed[2].label).toBe("Outside today's entry window")
    expect(feed[2].isOngoing).toBe(false)
  })

  it('action traded maps to the lifecycle kind and label inside the built feed', () => {
    const feed = buildActivityFeed([
      { logTime: '2026-09-01T18:30:00Z', action: 'traded', reason: 'traded:CREDIT=1.20' },
    ])
    expect(feed).toHaveLength(1)
    expect(feed[0].kind).toBe('lifecycle')
    expect(feed[0].label).toBe('Opened a new trade')
  })

  it('action error always shows the calm label, never the passed-in error text', () => {
    const fakeError = 'ECONNRESET: socket hang up while fetching /v1/markets/quotes'
    const feed = buildActivityFeed([
      { logTime: '2026-09-01T18:30:00Z', action: 'error', reason: fakeError },
    ])
    expect(feed[0].label).toBe('Checking system health')
    expect(feed[0].label).not.toContain('ECONNRESET')
    expect(feed[0].label).not.toContain('socket hang up')
  })

  it('returns [] for empty input and never throws', () => {
    expect(buildActivityFeed([])).toEqual([])
    expect(() => buildActivityFeed([])).not.toThrow()
  })

  it('opts.max keeps the newest N segments, not the oldest N', () => {
    const rows = [
      { logTime: '2026-09-01T13:30:00Z', action: 'outside_entry_window', reason: null },
      { logTime: '2026-09-01T15:05:00Z', action: 'no_trade', reason: 'skip:vix_elevated(0.91>0.90)' },
      { logTime: '2026-09-01T15:30:00Z', action: 'no_trade', reason: 'skip:standdown' },
      { logTime: '2026-09-01T18:30:00Z', action: 'traded', reason: 'traded:CREDIT=1.20' },
    ]
    const full = buildActivityFeed(rows, { max: 100 })
    expect(full).toHaveLength(4)
    const capped = buildActivityFeed(rows, { max: 2 })
    expect(capped).toHaveLength(2)
    // Newest two: 'traded' (newest) then 'skip:standdown' gate — NOT the oldest two.
    expect(capped[0].label).toBe('Opened a new trade')
    expect(capped[1].label).toBe('Cooling down after a recent loss')
  })
})
