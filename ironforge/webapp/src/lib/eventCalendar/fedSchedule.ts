/**
 * Hardcoded FOMC meeting schedule sourced directly from the Federal Reserve's
 * public calendar at https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
 *
 * Why hardcoded:
 *   - Finnhub's free tier does not return FOMC rate-decision rows (only
 *     "FOMC Minutes", which are post-hoc summaries we exclude).
 *   - The Fed publishes the schedule years in advance and only adjusts
 *     it once or twice per decade (e.g., COVID emergency meetings).
 *   - 16 dates per 2 years is trivial to maintain by hand.
 *
 * Format: each entry is the SECOND day of the meeting (the rate-decision
 * announcement day). Decisions are released at 2:00 PM ET = 13:00 CT.
 *
 * To extend: open the Fed page, copy the new year's dates, append below.
 */

export interface FedFomcMeeting {
  /** Rate-decision day (the second day of the 2-day meeting) in YYYY-MM-DD */
  date: string
  /** Always "13:00" (CT) — release time for the FOMC statement */
  time_ct: string
  /** Whether this meeting includes a Summary of Economic Projections */
  has_sep: boolean
}

export const FED_FOMC_SCHEDULE: FedFomcMeeting[] = [
  // 2026
  { date: '2026-01-28', time_ct: '13:00', has_sep: false },
  { date: '2026-03-18', time_ct: '13:00', has_sep: true  },
  { date: '2026-04-29', time_ct: '13:00', has_sep: false },
  { date: '2026-06-17', time_ct: '13:00', has_sep: true  },
  { date: '2026-07-29', time_ct: '13:00', has_sep: false },
  { date: '2026-09-16', time_ct: '13:00', has_sep: true  },
  { date: '2026-10-28', time_ct: '13:00', has_sep: false },
  { date: '2026-12-09', time_ct: '13:00', has_sep: true  },
  // 2027
  { date: '2027-01-27', time_ct: '13:00', has_sep: false },
  { date: '2027-03-17', time_ct: '13:00', has_sep: true  },
  { date: '2027-04-28', time_ct: '13:00', has_sep: false },
  { date: '2027-06-09', time_ct: '13:00', has_sep: true  },
  { date: '2027-07-28', time_ct: '13:00', has_sep: false },
  { date: '2027-09-15', time_ct: '13:00', has_sep: true  },
  { date: '2027-10-27', time_ct: '13:00', has_sep: false },
  { date: '2027-12-08', time_ct: '13:00', has_sep: true  },
]

/** Title used for upserts, with SEP suffix when applicable. */
export function fedFomcTitle(m: FedFomcMeeting): string {
  return m.has_sep
    ? 'FOMC Meeting (with Summary of Economic Projections)'
    : 'FOMC Meeting'
}
