/**
 * Guardrail: every FLAME/SPARK feature must declare coverage for all account
 * types (production 'Flame', sandbox, app customers) in bot-feature-coverage.ts.
 *
 * Built 2026-09-28 after FLINT, fast-start/floor, favorable upsize and the
 * SPARK add-ons were discovered to have been wired into the INTERNAL order
 * path only (tradier.ts / scanner.ts) while app customers mirror through a
 * completely separate path (customer-executor/) that FLINT never reached at
 * all. This test is the mechanism that makes that class of bug loud instead
 * of silent.
 *
 * Three checks:
 *   (a) every FLAME_/SPARK_/FLINT_/EBB_/CUSTOMER_/CALLDIAG_/IRONFORGE_ASSIGNMENT*
 *       token found in tradier.ts, scanner.ts, customer-executor/**, or any
 *       *-sizing.ts file must be registered in BOT_FEATURE_COVERAGE (or be on
 *       the documented non-flag allowlist below).
 *   (b) every registered feature must have a coverage decision
 *       ('covered' | 'excluded' | 'n/a') for ALL THREE account types, and every
 *       'excluded' decision must carry a reason and an approver.
 *   (c) a feature marked 'covered' for app customers must actually be
 *       reachable from the customer path (customer-executor/**.ts, or a
 *       scanner.ts function that calls — directly or transitively —
 *       mirrorOpenToCustomers/mirrorCloseToCustomers); a feature marked
 *       'covered' for production/sandbox must appear in the internal-path
 *       source (tradier.ts, scanner.ts, the *-sizing.ts files).
 *
 * Why a bare-token scan, not a strict `process.env.NAME` regex: this codebase
 * plumbs several flags through a dynamic `process.env[envVar]` read
 * (fast-start-sizing.ts's `isFastStartMode(envVar)`), with the literal name
 * only appearing as a quoted string argument or default parameter value at
 * the call site — never as `process.env.FLAME_FAST_START` in tradier.ts or
 * scanner.ts themselves. A strict dot-notation scan would have missed exactly
 * the flags this guard exists to catch. The tradeoff is picking up some
 * SCREAMING_SNAKE_CASE code constants that aren't env vars at all (e.g.
 * FLAME_VIX_GATE_CEILING) — those are named explicitly in
 * KNOWN_NON_FLAG_TOKENS below, with a reason each, so a new one still forces
 * a human decision instead of silently passing or silently failing.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { BOT_FEATURE_COVERAGE, type AccountKind, type FeatureCoverage } from '../bot-feature-coverage'

const LIB_DIR = path.resolve(__dirname, '..')

const FLAG_TOKEN_RE =
  /\b(FLAME_[A-Z][A-Z0-9_]*|SPARK_[A-Z][A-Z0-9_]*|FLINT_[A-Z][A-Z0-9_]*|EBB_[A-Z][A-Z0-9_]*|CUSTOMER_[A-Z][A-Z0-9_]*|CALLDIAG_[A-Z][A-Z0-9_]*|IRONFORGE_ASSIGNMENT[A-Z0-9_]*)\b/g

/**
 * SCREAMING_SNAKE_CASE tokens matching the flag prefixes that are NOT env
 * vars — plain code constants, table names, or event-type strings. Each one
 * was verified by reading its definition. Adding a new entry here without
 * verifying it first defeats the point of this guard.
 */
const KNOWN_NON_FLAG_TOKENS = new Set<string>([
  'CUSTOMER_AGENTS', // Set<string> of bot names eligible for customer mirroring (executor.ts)
  'CUSTOMER_ORDER_CLOSED', // audit_events event_type string literal (executor.ts)
  'CUSTOMER_ORDER_PLACED', // audit_events event_type string literal (executor.ts)
  'EBB_LADDER_CAP', // numeric ladder-cap constant (ebb-sizing.ts)
  'EBB_LIQUIDITY_SHARE', // numeric constant (ebb-sizing.ts)
  'EBB_MIN_CREDIT_FLOOR_ESTIMATE', // numeric constant (ebb-sizing.ts)
  'EBB_UNKNOWN_LIQUIDITY_LOTS', // numeric constant (ebb-sizing.ts)
  'EBB_UPSIZE_COMMISSION_PER_CONTRACT', // numeric constant (ebb-sizing.ts)
  'EBB_UPSIZE_VIX_RATIO_CEILING', // numeric constant (ebb-sizing.ts)
  'EBB_WING_WIDTH_ESTIMATE', // numeric constant (ebb-sizing.ts)
  'FLAME_BOOKS', // code constant/list (scanner.ts or tradier.ts)
  'FLAME_EOD_CUTOFF_HHMM_CT', // numeric constant (scanner.ts)
  'FLAME_RUNG_USD', // numeric ladder-rung constant (tradier.ts)
  'FLINT_BP_FLOOR_PER_', // regex artifact of FLINT_BP_FLOOR_PER_CONTRACT (word-boundary split); see next entry
  'FLINT_BP_FLOOR_PER_CONTRACT', // numeric constant (flint.ts/scanner.ts)
  'FLINT_COMMISSION_PER_CONTRACT', // numeric constant
  'FLINT_CONTEXT_TABLE', // DB table name string (flint.ts)
  'FLINT_GAMMA_UPSIZE_MIN_SESSIONS', // numeric constant (scanner.ts)
  'FLINT_TABLE', // DB table name string (flint.ts)
  'SPARK_BP_CAP_NEG', // numeric constant (tradier.ts)
  'SPARK_BP_CAP_POS', // numeric constant (tradier.ts)
  'SPARK_FAST_MONITOR_INTERVAL_MS', // numeric constant (tradier.ts)
  'SPARK_FLINT_MAX_CONTRACTS', // exported const = 1 (spark-flint-separate.ts), not an env var
  'SPARK_RUNG_USD', // numeric ladder-rung constant (tradier.ts)
])

const ACCOUNT_KINDS: AccountKind[] = ['production', 'sandbox', 'customer']

function readIfExists(filePath: string): string {
  try {
    return fs.readFileSync(filePath, 'utf8')
  } catch {
    return ''
  }
}

function listTsFilesRecursive(dir: string): string[] {
  let out: string[] = []
  let entries: fs.Dirent[]
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__') continue
      out = out.concat(listTsFilesRecursive(full))
    } else if (entry.name.endsWith('.ts') && !entry.name.endsWith('.test.ts')) {
      out.push(full)
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// Part (a) inputs: the exact file set the task specifies — tradier.ts,
// scanner.ts, customer-executor/**, and every *-sizing.ts file.
// ---------------------------------------------------------------------------
const SIZING_FILES = fs
  .readdirSync(LIB_DIR)
  .filter((f) => f.endsWith('-sizing.ts') && !f.endsWith('.test.ts'))
  .map((f) => path.join(LIB_DIR, f))

const CUSTOMER_EXECUTOR_DIR = path.join(LIB_DIR, 'customer-executor')
const CUSTOMER_EXECUTOR_FILES = listTsFilesRecursive(CUSTOMER_EXECUTOR_DIR)

const TRADIER_PATH = path.join(LIB_DIR, 'tradier.ts')
const SCANNER_PATH = path.join(LIB_DIR, 'scanner.ts')

const SCAN_TARGET_FILES = [TRADIER_PATH, SCANNER_PATH, ...CUSTOMER_EXECUTOR_FILES, ...SIZING_FILES]

function discoverFlagTokens(files: string[]): Set<string> {
  const found = new Set<string>()
  for (const file of files) {
    const text = readIfExists(file)
    const matches = text.match(FLAG_TOKEN_RE) ?? []
    for (const m of matches) found.add(m)
  }
  return found
}

// ---------------------------------------------------------------------------
// Part (c) inputs: build the "customer-reaching" and "internal-reaching" text
// blobs the reachability check verifies 'covered' claims against.
// ---------------------------------------------------------------------------

/** Top-level `function`/`async function` declarations in a file, with body span [start, end). */
function extractTopLevelFunctions(text: string): { name: string; body: string }[] {
  const decl = /^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(/gm
  const starts: { name: string; index: number }[] = []
  let m: RegExpExecArray | null
  while ((m = decl.exec(text))) {
    starts.push({ name: m[1], index: m.index })
  }
  const funcs: { name: string; body: string }[] = []
  for (let i = 0; i < starts.length; i++) {
    const start = starts[i].index
    const end = i + 1 < starts.length ? starts[i + 1].index : text.length
    funcs.push({ name: starts[i].name, body: text.slice(start, end) })
  }
  return funcs
}

const MIRROR_CALL_RE = /\bmirror(?:OpenToCustomers|CloseToCustomers)\s*\(/

/** BFS/fixpoint: functions that call mirror*ToCustomers directly, or call another
 *  such function, transitively, within the same file. */
function findCustomerReachingFunctionBodies(text: string): string[] {
  const funcs = extractTopLevelFunctions(text)
  const reaching = new Set<string>()
  for (const f of funcs) if (MIRROR_CALL_RE.test(f.body)) reaching.add(f.name)

  let changed = true
  while (changed) {
    changed = false
    for (const f of funcs) {
      if (reaching.has(f.name)) continue
      for (const other of reaching) {
        // A call to `other(` anywhere in this function's own body (excluding its own
        // declaration line, which is negligible risk of a self-match on the name).
        if (new RegExp(`\\b${other}\\s*\\(`).test(f.body)) {
          reaching.add(f.name)
          changed = true
          break
        }
      }
    }
  }
  return funcs.filter((f) => reaching.has(f.name)).map((f) => f.body)
}

const scannerText = readIfExists(SCANNER_PATH)
const customerReachingText =
  CUSTOMER_EXECUTOR_FILES.map(readIfExists).join('\n') +
  '\n' +
  findCustomerReachingFunctionBodies(scannerText).join('\n')

const internalReachingFiles = [
  TRADIER_PATH,
  SCANNER_PATH,
  ...SIZING_FILES,
  path.join(LIB_DIR, 'flint.ts'),
  path.join(LIB_DIR, 'flame-skip.ts'),
  path.join(LIB_DIR, 'calldiag.ts'),
  path.join(LIB_DIR, 'spark-flint-separate.ts'),
  path.join(LIB_DIR, 'spark-favorable-upsize.ts'),
  path.join(LIB_DIR, 'edge-decay.ts'),
  path.join(LIB_DIR, 'afternoon-spread.ts'),
]
const internalReachingText = internalReachingFiles.map(readIfExists).join('\n')

// ---------------------------------------------------------------------------
// Shared registry indexes
// ---------------------------------------------------------------------------
const registeredEnvVars = new Set<string>(BOT_FEATURE_COVERAGE.flatMap((f) => f.envVars))

describe('bot-feature-coverage guard', () => {
  it('every FLAME/SPARK env-var flag found in the source is registered', () => {
    const discovered = discoverFlagTokens(SCAN_TARGET_FILES)
    const unregistered: string[] = []
    for (const token of discovered) {
      if (KNOWN_NON_FLAG_TOKENS.has(token)) continue
      if (!registeredEnvVars.has(token)) unregistered.push(token)
    }
    if (unregistered.length > 0) {
      throw new Error(
        `Found ${unregistered.length} FLAME_/SPARK_/FLINT_/EBB_/CUSTOMER_/CALLDIAG_/IRONFORGE_ASSIGNMENT* ` +
          `token(s) in tradier.ts, scanner.ts, customer-executor/, or a *-sizing.ts file that are neither in ` +
          `BOT_FEATURE_COVERAGE nor in KNOWN_NON_FLAG_TOKENS: ${unregistered.join(', ')}. ` +
          `If this is a real env var, add a BOT_FEATURE_COVERAGE entry with a coverage decision for all three ` +
          `account types. If it's a code constant/table name, add it to KNOWN_NON_FLAG_TOKENS with a one-line reason.`,
      )
    }
    // Sanity: this must not be vacuously true — the scan should find real, known flags.
    expect(discovered.has('IRONFORGE_ASSIGNMENT_GUARD_BUFFER')).toBe(true)
    expect(discovered.has('CUSTOMER_EXECUTOR_ENABLED')).toBe(true)
  })

  describe.each(BOT_FEATURE_COVERAGE)('$flag', (feature: FeatureCoverage) => {
    it('has a coverage decision for every account type, and excluded entries have a reason + approver', () => {
      for (const kind of ACCOUNT_KINDS) {
        const entry = feature.coverage[kind]
        if (!entry) {
          throw new Error(`${feature.flag} has no coverage decision for '${kind}' — add 'covered', 'excluded' (with reason+approvedBy), or 'n/a'.`)
        }
        expect(['covered', 'excluded', 'n/a']).toContain(entry.status)
        if (entry.status === 'excluded') {
          if (!entry.reason || entry.reason.trim().length === 0) {
            throw new Error(`${feature.flag} is 'excluded' for '${kind}' but has no reason — every exclusion needs a plain-English reason.`)
          }
          if (!entry.approvedBy || entry.approvedBy.trim().length === 0) {
            throw new Error(`${feature.flag} is 'excluded' for '${kind}' but has no approvedBy — every exclusion needs to name who approved it (or that it's a tracked, unapproved gap).`)
          }
        }
      }
    })

    it("'covered' for app customers is backed by a real reference on the customer path", () => {
      const entry = feature.coverage.customer
      if (entry.status !== 'covered') return
      const found = feature.envVars.some((v) => customerReachingText.includes(v))
      if (!found) {
        throw new Error(
          `${feature.flag} is marked 'covered' for app customers but none of [${feature.envVars.join(', ')}] is ` +
            `referenced under customer-executor/ or in any scanner.ts function that reaches ` +
            `mirrorOpenToCustomers/mirrorCloseToCustomers — add real coverage or mark it 'excluded'.`,
        )
      }
    })

    it("'covered' for production or sandbox is backed by a real reference on the internal path", () => {
      for (const kind of ['production', 'sandbox'] as const) {
        const entry = feature.coverage[kind]
        if (entry.status !== 'covered') continue
        const found = feature.envVars.some((v) => internalReachingText.includes(v))
        if (!found) {
          throw new Error(
            `${feature.flag} is marked 'covered' for ${kind} but none of [${feature.envVars.join(', ')}] is ` +
              `referenced in tradier.ts, scanner.ts, or any *-sizing.ts file — add real coverage or mark it 'excluded'.`,
          )
        }
      }
    })
  })

  it('reachability scan sanity check: tryOpenFlint is NOT customer-reaching, tryOpenFlameBook IS', () => {
    // This pins the exact bug this guard exists to catch. If this ever flips silently,
    // something about the mirror wiring (or this test's parsing) changed and needs eyes.
    const funcs = extractTopLevelFunctions(scannerText)
    const flint = funcs.find((f) => f.name === 'tryOpenFlint')
    const flameBook = funcs.find((f) => f.name === 'tryOpenFlameBook')
    expect(flint, 'tryOpenFlint must exist in scanner.ts').toBeTruthy()
    expect(flameBook, 'tryOpenFlameBook must exist in scanner.ts').toBeTruthy()
    if (flint) expect(MIRROR_CALL_RE.test(flint.body)).toBe(false)
    if (flameBook) expect(MIRROR_CALL_RE.test(flameBook.body)).toBe(true)
  })
})
