/**
 * Finnhub economic-calendar fetcher + parser for the IronForge event blackout.
 *
 * Free-tier endpoint: GET https://finnhub.io/api/v1/calendar/economic
 *   ?from=YYYY-MM-DD&to=YYYY-MM-DD&token=<API_KEY>
 *
 * Returns only US high-impact FOMC events.  Other event types (CPI, NFP, PPI)
 * can be added later by extending FOMC_TITLE_RE.
 */

export interface FinnhubFomcEvent {
  date: string   // YYYY-MM-DD in CT
  time: string   // HH:MM in CT (24h)
  title: string
}

const FOMC_TITLE_RE = /FOMC|Fed Interest Rate|Federal Funds/i

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
 * Parse Finnhub `/calendar/economic` response, return only US high-impact FOMC events.
 */
export function parseFinnhubFomcEvents(json: any): FinnhubFomcEvent[] {
  if (!json || !Array.isArray(json.economicCalendar)) return []
  const out: FinnhubFomcEvent[] = []
  for (const row of json.economicCalendar) {
    if (!row) continue
    if (row.country !== 'US') continue
    if ((row.impact || '').toLowerCase() !== 'high') continue
    if (typeof row.event !== 'string' || !FOMC_TITLE_RE.test(row.event)) continue
    if (typeof row.time !== 'string') continue
    const { date, time } = utcToCtDateTime(row.time)
    out.push({ date, time, title: row.event })
  }
  return out
}

/**
 * Fetch FOMC events from Finnhub for a date range.
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
