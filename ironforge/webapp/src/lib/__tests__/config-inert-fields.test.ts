import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The config API claims certain columns are inert — the scanner never reads them, so
 * writing them would make the row describe a strategy the bot does not run.
 *
 * That claim is a HAND-MAINTAINED list sitting in a different file from the code it
 * describes, which is the exact shape of every drift bug in this codebase this week.
 * If someone wires `vix_skip` up in the scanner and forgets to remove it from
 * INERT_FIELDS, the API starts rejecting a field that now matters.
 *
 * So assert the two are consistent by reading both sources.
 */

const SRC = join(__dirname, '..', '..')
const scanner = readFileSync(join(SRC, 'lib', 'scanner.ts'), 'utf8')
const configRoute = readFileSync(join(SRC, 'app', 'api', '[bot]', 'config', 'route.ts'), 'utf8')

/**
 * Column names the scanner maps out of the config row via DB_TO_CFG.
 *
 * Terminated on `\n}` — the closing brace at column 0 — because splitting on `}\n`
 * ran past the end of the object and swept up `flame`, `spark` and `inferno` from the
 * declaration after it. Harmless for the overlap check (a larger set only makes it
 * stricter) but a guard that reports the wrong thing teaches the next reader wrong.
 */
function scannerMappedColumns(): string[] {
  const block = scanner.split('const DB_TO_CFG')[1]?.split('\n}')[0] ?? ''
  return [...block.matchAll(/^\s{2}(\w+):\s*\{/gm)].map((m) => m[1])
}

/** Columns the config route refuses to store. */
function routeInertColumns(): string[] {
  const block = configRoute.split('const INERT_FIELDS')[1]?.split('\n}')[0] ?? ''
  return [...block.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1])
}

describe('config route inert-field list', () => {
  it('finds both lists (the parse itself must not silently return nothing)', () => {
    expect(scannerMappedColumns().length).toBeGreaterThan(5)
    expect(routeInertColumns().length).toBeGreaterThan(3)
  })

  it('never marks a column INERT that the scanner actually reads', () => {
    const mapped = new Set(scannerMappedColumns())
    const wrongly = routeInertColumns().filter((c) => mapped.has(c))
    expect(
      wrongly,
      `these are declared inert but scanner.ts DB_TO_CFG reads them: ${wrongly.join(', ')}`,
    ).toEqual([])
  })

  it('does not claim entry_end or eod_cutoff_et are inert — both ARE parsed from the row', () => {
    // These sit outside DB_TO_CFG (they are "HH:MM" strings parsed separately in
    // loadConfigOverrides), so the DB_TO_CFG check above cannot catch them.
    const inert = routeInertColumns()
    expect(inert).not.toContain('entry_end')
    expect(inert).not.toContain('eod_cutoff_et')
  })

  it('still parses entry_end and eod_cutoff_et in the scanner', () => {
    // If either stops being read, it BELONGS in INERT_FIELDS and the test above
    // must be updated — this is the other half of that pair.
    expect(scanner).toContain('row.entry_end')
    expect(scanner).toContain('row.eod_cutoff_et')
  })

  it('lists the swing bots that ignore stop_loss_pct, matching isSparkStrategy', () => {
    const swing = configRoute.split('const SWING_BOTS')[1]?.split(']')[0] ?? ''
    for (const bot of ['spark', 'spark2', 'kindle']) {
      expect(swing, `${bot} swings and must be listed`).toContain(bot)
    }
  })
})
