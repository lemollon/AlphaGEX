/**
 * Finnhub economic-calendar fetcher + parser for the IronForge event blackout.
 *
 * Free-tier endpoint: GET https://finnhub.io/api/v1/calendar/economic
 *   ?from=YYYY-MM-DD&to=YYYY-MM-DD&token=<API_KEY>
 *
 * Returns US high-impact macro events that can move SPY > 1 standard deviation:
 *   - FOMC rate decisions (excluding minutes/speeches/projections/testimony)
 *   - CPI / Core CPI (Consumer Price Index)
 *   - PPI / Core PPI (Producer Price Index)
 *   - NFP (Nonfarm Payrolls / Employment Situation)
 *
 * Each match returns its event_type so downstream blackout windows can be
 * customized per event class later if needed.
 */

export type FinnhubEventType = 'FOMC' | 'CPI' | 'PPI' | 'NFP'

export interface FinnhubFomcEvent {
  date: string   // YYYY-MM-DD in CT
  time: string   // HH:MM in CT (24h)
  title: string
  event_type: FinnhubEventType
}

// Per-type match patterns. Order matters: FOMC is checked first so
// "FOMC Member Powell speaks on CPI" is classified as FOMC, not CPI.
const TYPE_PATTERNS: Array<{ type: FinnhubEventType; re: RegExp }> = [
  { type: 'FOMC', re: /FOMC|Fed Interest Rate|Federal Funds/i },
  { type: 'CPI',  re: /\bCPI\b|Consumer Price Index/i },
  { type: 'PPI',  re: /\bPPI\b|Producer Price Index/i },
  { type: 'NFP',  re: /\bNFP\b|Nonfarm Payrolls?|Non-Farm Payrolls?|Employment Situation/i },
]

// Exclude commentary / summary / forecast events that match the patterns
// above but rarely produce ±2σ moves on their own.
//   - "Minutes" → summary of a prior meeting
//   - "Speaks" / "Speech" / "Testimony" → individual remarks, no surprise data
//   - "Projection" / "Forecast" → published baseline estimates, not actuals
//   - "Revision" / "Revised" → after-the-fact corrections
export const FOMC_EXCLUDE_RE = /Minutes|Speaks|Speech|Projection|Forecast|Testimony|Revision|Revised/i

/**
 * Convert a Finnhub UTC timestamp ("2025-06-18 18:00:00") to CT date + HH:MM.
 */
function utcToCtDateTime(finnhubUtc: string): { date: string; time: string } {
  const iso = finnhubUtc.replace(' ', 'T') + 'Z'
  const d = new Date(iso)
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  const parts = dtf.formatToParts(d).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour === '24' ? '00' : parts.hour}:${parts.minute}`,
  }
}

/**
 * Parse Finnhub `/calendar/economic` response.
 * Returns US high-impact macro events tagged with their FinnhubEventType.
 *
 * Function name kept (parseFinnhubFomcEvents) for backward-compat with
 * existing callers; despite the name, returns FOMC + CPI + PPI + NFP.
 */
export function parseFinnhubFomcEvents(json: any): FinnhubFomcEvent[] {
  if (!json || !Array.isArray(json.economicCalendar)) return []
  const out: FinnhubFomcEvent[] = []
  for (const row of json.economicCalendar) {
    if (!row) continue
    if (row.country !== 'US') continue
    if ((row.impact || '').toLowerCase() !== 'high') continue
    if (typeof row.event !== 'string') continue
    if (FOMC_EXCLUDE_RE.test(row.event)) continue
    let matched: FinnhubEventType | null = null
    for (const { type, re } of TYPE_PATTERNS) {
      if (re.test(row.event)) { matched = type; break }
    }
    if (!matched) continue
    if (typeof row.time !== 'string') continue
    const { date, time } = utcToCtDateTime(row.time)
    out.push({ date, time, title: row.event, event_type: matched })
  }
  return out
}

/**
 * Fetch macro events from Finnhub for a date range.
 * Throws on non-2xx; caller is responsible for catching + logging.
 */
export async function fetchFinnhubFomcEvents(
  fromDate: string,
  toDate: string,
  apiKey: string,
): Promise<FinnhubFomcEvent[]> {
  const url = `https://finnhub.io/api/v1/calendar/economic?from=${fromDate}&to=${toDate}&token=${encodeURIComponent(apiKey)}`
  const res = await fetch(url, { method: 'GET' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`Finnhub returned ${res.status}: ${body.slice(0, 200)}`)
  }
  const json = await res.json()
  return parseFinnhubFomcEvents(json)
}
