import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The two EBB variants must stay separate.
 *
 * `botStructure()` took the bot name and discarded it (`_name`, unused), so the
 * 2026-08-16 cutover gave SPARK the cell that registry #49r's walk-forward had
 * selected for FLAME's 13:05 clock. Measured on the AM clock 2022-11 → 2026-08
 * (1 lot, net $0.70/lot, n=941), FLAME's cell is the worst of the nine AM cells:
 * $5.78/trade, ret/DD 1.18, 4/5 years — against $11.14 and 1.87 for EBB's own
 * registered AM structure.
 *
 * Read from source rather than importing: scanner.ts starts the scanner on import.
 */
const SRC = readFileSync(join(process.cwd(), 'src/lib/scanner.ts'), 'utf8')

describe('EBB structure is per-clock, not shared', () => {
  const start = SRC.indexOf('function botStructure(')
  const fn = SRC.slice(start, start + SRC.slice(start).indexOf('\n}') + 2)

  it('takes the bot name and actually uses it', () => {
    expect(fn).not.toMatch(/function botStructure\(\s*_name/)
    expect(fn).toMatch(/name === 'spark'/)
  })

  it('SPARK (AM 10:05) runs EBB as registered — spot−$2, $5 wing', () => {
    expect(fn).toMatch(/name === 'spark'\) return \{ otmAbs: 2\.0, width: 5 \}/)
  })

  it('FLAME (PM 13:05) is unchanged — spot−$1, $2 wing, the #49r walk-forward cell', () => {
    // The fallthrough. FLAME trades this live; it must not move.
    expect(fn).toMatch(/return \{ otmAbs: 1\.0, width: 2 \}/)
  })

  it('the two clocks do not share one structure', () => {
    const cells = (fn.match(/otmAbs: [\d.]+, width: \d+/g) ?? [])
    expect(new Set(cells).size).toBeGreaterThan(1)
  })
})

/**
 * FLAME's clock is correct and deliberate — 13:05–13:10 CT, the PM tranche.
 * Pinned because "unify the two bots" is exactly how SPARK lost its structure.
 */
describe('the clocks stay put', () => {
  it('FLAME enters in the afternoon (13:05–13:10 CT)', () => {
    const line = SRC.split('\n').find((l) => l.trimStart().startsWith('flame:')) ?? ''
    expect(line).toContain('entry_start: 1305')
    expect(line).toContain('entry_end: 1310')
  })
  it('SPARK enters in the morning (10:05–10:20 CT)', () => {
    const line = SRC.split('\n').find((l) => l.trimStart().startsWith('spark:')) ?? ''
    expect(line).toContain('entry_start: 1005')
    expect(line).toContain('entry_end: 1020')
  })
})
