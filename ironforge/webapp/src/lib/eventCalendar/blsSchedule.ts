/**
 * Hardcoded BLS / BEA / ISM macro release schedule for the next 12 months.
 *
 * Why hardcoded:
 *   - Finnhub free tier only publishes ~16 days ahead; user wants 3 months
 *     of forward visibility on every release that could move SPY ±2%.
 *   - BLS / BEA / ISM all publish their full annual calendars in advance
 *     and only adjust dates 1-2 times per year for federal holidays.
 *   - 7 events × 12 months ≈ 84 dates, trivial to maintain by hand.
 *
 * Sources for confirmed dates:
 *   - CPI: https://www.bls.gov/schedule/news_release/cpi.htm
 *          https://cpiinflationcalculator.com/cpi-release-schedule/
 *   - PPI: https://www.bls.gov/schedule/news_release/ppi.htm
 *   - NFP / Employment Situation: https://www.bls.gov/schedule/news_release/empsit.htm
 *   - PCE / Personal Income & Outlays: https://www.bea.gov/news/schedule
 *   - GDP: https://www.bea.gov/news/schedule
 *   - ISM Services / Manufacturing PMI: https://www.ismworld.org
 *
 * 2027 dates are extrapolated from BLS / BEA recurring patterns and should
 * be replaced with the official calendar once published (typically Nov of
 * the prior year). They are still useful as "expected windows" for the
 * 12-month grid view; the daily refresh will overwrite halt windows when
 * the official date is known.
 *
 * Time fields are in ET wall-clock; all releases are 8:30 AM ET except
 * ISM (10:00 AM ET). The blackout system stores in CT, so we convert
 * (subtract 1 hour) when seeding.
 */

export type BlsEventType =
  | 'CPI'             // Consumer Price Index — Tier 1
  | 'PPI'             // Producer Price Index — Tier 1 (lower)
  | 'NFP'             // Non-Farm Payrolls / Employment Situation — Tier 1
  | 'PCE'             // Core PCE / Personal Income & Outlays — Tier 2
  | 'GDP'             // GDP advance/second/third estimate — Tier 2
  | 'ISM_SERVICES'    // ISM Services PMI — Tier 2
  | 'JOLTS'           // JOLTs Job Openings — Tier 3
  | 'RETAIL_SALES'    // Retail Sales — Tier 2

export interface BlsRelease {
  date: string         // YYYY-MM-DD
  /** Time in CT (24h). All BLS/BEA = 07:30, ISM = 09:00. */
  time_ct: string
  type: BlsEventType
  /** Display title with reporting period context */
  title: string
}

/**
 * Releases for the next 12 months from May 2026.
 * Dates confirmed from BLS / BEA published 2026 calendars where available;
 * extrapolated from recurring patterns for 2027 Q1.
 */
export const BLS_RELEASES: BlsRelease[] = [
  // ============ MAY 2026 ============
  { date: '2026-05-08', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Apr)' },
  { date: '2026-05-12', time_ct: '07:30', type: 'CPI',          title: 'CPI (Apr)' },
  { date: '2026-05-13', time_ct: '07:30', type: 'PPI',          title: 'PPI (Apr)' },
  { date: '2026-05-15', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Apr)' },
  { date: '2026-05-28', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q1 second estimate)' },
  { date: '2026-05-29', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Apr)' },

  // ============ JUNE 2026 ============
  { date: '2026-06-03', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (May)' },
  { date: '2026-06-05', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (May)' },
  { date: '2026-06-10', time_ct: '07:30', type: 'CPI',          title: 'CPI (May)' },
  { date: '2026-06-11', time_ct: '07:30', type: 'PPI',          title: 'PPI (May)' },
  { date: '2026-06-16', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (May)' },
  { date: '2026-06-25', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q1 third estimate)' },
  { date: '2026-06-26', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (May)' },

  // ============ JULY 2026 ============
  { date: '2026-07-02', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Jun)' }, // shifted from Fri 7/3 (Independence Day observed)
  { date: '2026-07-07', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Jun)' },
  { date: '2026-07-14', time_ct: '07:30', type: 'CPI',          title: 'CPI (Jun)' },
  { date: '2026-07-15', time_ct: '07:30', type: 'PPI',          title: 'PPI (Jun)' },
  { date: '2026-07-16', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Jun)' },
  { date: '2026-07-30', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q2 advance estimate)' },
  { date: '2026-07-31', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Jun)' },

  // ============ AUGUST 2026 ============
  { date: '2026-08-05', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Jul)' },
  { date: '2026-08-07', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Jul)' },
  { date: '2026-08-12', time_ct: '07:30', type: 'CPI',          title: 'CPI (Jul)' },
  { date: '2026-08-13', time_ct: '07:30', type: 'PPI',          title: 'PPI (Jul)' },
  { date: '2026-08-14', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Jul)' },
  { date: '2026-08-27', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q2 second estimate)' },
  { date: '2026-08-28', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Jul)' },

  // ============ SEPTEMBER 2026 ============
  { date: '2026-09-03', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Aug)' },
  { date: '2026-09-04', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Aug)' },
  { date: '2026-09-11', time_ct: '07:30', type: 'CPI',          title: 'CPI (Aug)' },
  { date: '2026-09-14', time_ct: '07:30', type: 'PPI',          title: 'PPI (Aug)' }, // Mon, since 9/12 is Sat
  { date: '2026-09-15', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Aug)' },
  { date: '2026-09-24', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q2 third estimate)' },
  { date: '2026-09-25', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Aug)' },

  // ============ OCTOBER 2026 ============
  { date: '2026-10-02', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Sep)' },
  { date: '2026-10-05', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Sep)' },
  { date: '2026-10-14', time_ct: '07:30', type: 'CPI',          title: 'CPI (Sep)' },
  { date: '2026-10-15', time_ct: '07:30', type: 'PPI',          title: 'PPI (Sep)' },
  { date: '2026-10-16', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Sep)' },
  { date: '2026-10-29', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q3 advance estimate)' },
  { date: '2026-10-30', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Sep)' },

  // ============ NOVEMBER 2026 ============
  { date: '2026-11-04', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Oct)' },
  { date: '2026-11-06', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Oct)' },
  { date: '2026-11-10', time_ct: '07:30', type: 'CPI',          title: 'CPI (Oct)' },
  { date: '2026-11-12', time_ct: '07:30', type: 'PPI',          title: 'PPI (Oct)' }, // shifted from 11/11 Veterans Day
  { date: '2026-11-16', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Oct)' },
  { date: '2026-11-25', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q3 second estimate)' },
  { date: '2026-11-25', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Oct)' }, // shifted earlier from Thanksgiving week

  // ============ DECEMBER 2026 ============
  { date: '2026-12-03', time_ct: '09:00', type: 'ISM_SERVICES', title: 'ISM Services PMI (Nov)' },
  { date: '2026-12-04', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Nov)' },
  { date: '2026-12-10', time_ct: '07:30', type: 'CPI',          title: 'CPI (Nov)' },
  { date: '2026-12-11', time_ct: '07:30', type: 'PPI',          title: 'PPI (Nov)' },
  { date: '2026-12-15', time_ct: '07:30', type: 'RETAIL_SALES', title: 'Retail Sales (Nov)' },
  { date: '2026-12-22', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q3 third estimate)' },
  { date: '2026-12-23', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Nov)' }, // shifted earlier from Christmas week

  // ============ 2027 Q1 (provisional — replace once BLS / BEA publish) ============
  { date: '2027-01-08', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Dec)' },
  { date: '2027-01-13', time_ct: '07:30', type: 'CPI',          title: 'CPI (Dec)' },
  { date: '2027-01-14', time_ct: '07:30', type: 'PPI',          title: 'PPI (Dec)' },
  { date: '2027-01-29', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q4 advance estimate)' },
  { date: '2027-02-05', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Jan)' },
  { date: '2027-02-11', time_ct: '07:30', type: 'CPI',          title: 'CPI (Jan)' },
  { date: '2027-02-12', time_ct: '07:30', type: 'PPI',          title: 'PPI (Jan)' },
  { date: '2027-02-26', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Jan)' },
  { date: '2027-03-05', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Feb)' },
  { date: '2027-03-11', time_ct: '07:30', type: 'CPI',          title: 'CPI (Feb)' },
  { date: '2027-03-12', time_ct: '07:30', type: 'PPI',          title: 'PPI (Feb)' },
  { date: '2027-03-26', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Feb)' },
  { date: '2027-04-02', time_ct: '07:30', type: 'NFP',          title: 'Employment Situation (Mar)' },
  { date: '2027-04-14', time_ct: '07:30', type: 'CPI',          title: 'CPI (Mar)' },
  { date: '2027-04-15', time_ct: '07:30', type: 'PPI',          title: 'PPI (Mar)' },
  { date: '2027-04-29', time_ct: '07:30', type: 'GDP',          title: 'GDP (Q1 advance estimate)' },
  { date: '2027-04-30', time_ct: '07:30', type: 'PCE',          title: 'Personal Income & Outlays / Core PCE (Mar)' },
]
