/**
 * Macro-event playbook: how each scheduled US release historically affects
 * SPY / S&P 500. Used by the calendar UI to give the operator context on
 * WHY a given day is blacked out (or not) and what to expect around it.
 *
 * Sourced from public market research (see `sources` per entry). All
 * findings are summary-level, not trade signals — they are "this is how
 * IV behaves" / "this is the typical post-event whipsaw pattern" notes,
 * meant to make the calendar legible to a human operator.
 *
 * Tier definitions (for SPY):
 *   tier1 — regularly causes a ±1σ+ same-day move; bots MUST be flat
 *   tier2 — occasionally moves SPY ±0.5σ; bots may halt depending on regime
 *   tier3 — informational only; rarely meaningful for SPY in isolation
 */

export type PlaybookTier = 'tier1' | 'tier2' | 'tier3'

export interface EventPlaybook {
  /** Display name for UI */
  display_name: string
  /** Tier ranking by typical SPY impact */
  tier: PlaybookTier
  /** Whether this event triggers a Vigil halt for the IC bots */
  halts_bots: boolean
  /** One-sentence elevator pitch on why this event matters */
  one_liner: string
  /** What the market typically does running INTO the release */
  pre_event: string
  /** What the market typically does AFTER the release */
  post_event: string
  /** Common statistical / behavioral pattern (e.g. "Lucca-Moench drift") */
  pattern: string | null
  /** URLs the playbook is grounded in */
  sources: Array<{ label: string; url: string }>
}

export const EVENT_PLAYBOOKS: Record<string, EventPlaybook> = {
  FOMC: {
    display_name: 'FOMC Rate Decision',
    tier: 'tier1',
    halts_bots: true,
    one_liner: 'Fed sets the overnight rate. The single biggest scheduled vol event in US equities.',
    pre_event:
      'Historically the largest pre-event drift of any macro release. Lucca & Moench (NY Fed Staff Report 512) measured an average +49 bps S&P 500 return in the 24-hour window before scheduled FOMC announcements (1994–2011), accounting for ~80% of the historical equity premium. Note: the same researchers and follow-up work found the drift "essentially disappeared after 2015," so do not size on a directional drift expectation today — but IV still inflates as the runup approaches.',
    post_event:
      'Reliable IV crush at 1:00 PM CT release. Press-conference (SEP) meetings often have a larger post-statement move than non-SEP meetings, and the move can fully reverse by close as the market re-reads the Powell Q&A. Direction is unpredictable; magnitude is large.',
    pattern: 'Pre-event vega runup → release-bar IV crush → frequent late-session reversal',
    sources: [
      { label: 'Lucca & Moench (NY Fed SR 512)', url: 'https://www.newyorkfed.org/research/staff_reports/sr512.html' },
      { label: 'NBER conference paper (PDF)', url: 'https://conference.nber.org/confer/2013/MEs13/Lucca_Moench.pdf' },
      { label: 'Disappearing pre-FOMC drift (PMC)', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7525326/' },
    ],
  },
  CPI: {
    display_name: 'CPI / Inflation Rate',
    tier: 'tier1',
    halts_bots: true,
    one_liner: 'Headline + Core inflation print. The data release that moves SPY the most month-to-month.',
    pre_event:
      'IV inflates noticeably in the 1–2 sessions before release. Premium sellers running IC stops here without halt protection get hit by vega expansion before the print.',
    post_event:
      'Heavy IV crush at 7:30 AM CT release. Equity vol after CPI is roughly 2x the vol after PCE, even though Core PCE is the Fed\'s preferred inflation gauge — CPI prints first and gets disproportionate attention. Multiple market-commentary sources note that a "post-CPI rally regardless of the data" is common, driven by the vol-crush itself rather than the surprise direction.',
    pattern: 'Modest pre-event IV runup → sharp post-print IV crush → bias toward upside resolution from the crush itself',
    sources: [
      { label: 'CPI vs PPI: which moves markets more', url: 'https://blog.pfhmarkets.com/markets-news-events/cpi-vs-ppi-trading/' },
      { label: 'CPI vs PCE inflation tracker', url: 'https://www.datasetiq.com/blog/cpi-vs-pce-core-inflation-tracker' },
    ],
  },
  NFP: {
    display_name: 'Non-Farm Payrolls',
    tier: 'tier1',
    halts_bots: true,
    one_liner: 'Monthly jobs report (first Friday). Most reliable whipsaw pattern of any macro event.',
    pre_event:
      'IV builds modestly into Friday open. Less vega buildup than CPI / FOMC because the release is at 7:30 CT (pre-market) and crashes through the open.',
    post_event:
      'Volatility peaks within 15 minutes of release; spreads widen 3–5x normal. Market commentary across multiple sources notes a recurring whipsaw: a sharp 30–60-second move on the headline number that "loses strength and reverses" within minutes as traders parse the full report (revisions, U-3 vs U-6, average hourly earnings). Especially pronounced in ES/MES futures. The opening-bell direction is rarely the day\'s direction.',
    pattern: 'Headline-driven first-minute spike → fast reversal as full report digests → second move sets day\'s tone',
    sources: [
      { label: 'NFP report trading guide (Plus500)', url: 'https://us.plus500.com/en/newsandmarketinsights/what-is-nfp-nonfarm-payroll' },
      { label: 'NFP-led reversal anatomy (VT Markets)', url: 'https://www.vtmarkets.com/live-updates/after-the-trap-attention-shifts-to-sp-500s-nfp-led-reversal-rebound-anatomy-and-after-hours-forecast-accuracy/' },
      { label: 'Whipsaw trading explanation', url: 'https://www.metrotrade.com/what-is-whipsaw-trading/' },
    ],
  },
  PPI: {
    display_name: 'PPI (Producer Price Index)',
    tier: 'tier2',
    halts_bots: true,
    one_liner: 'Wholesale prices. Released the day before/after CPI; markets treat it as a CPI preview.',
    pre_event:
      'Minor IV drift; the bulk of the inflation-week IV runup is owned by CPI. PPI day acts mostly as positioning into the CPI print.',
    post_event:
      'Markets typically show "little reaction" to PPI in isolation per CNBC and PFH Markets coverage — traders are waiting for CPI. The exception: a large directional surprise in PPI can pre-trade the CPI move, in which case CPI day delivers a smaller move than usual.',
    pattern: 'Often a non-event for SPY on its own; useful as a CPI directional clue',
    sources: [
      { label: 'PPI vs CPI market reaction', url: 'https://blog.pfhmarkets.com/markets-news-events/cpi-vs-ppi-trading/' },
      { label: 'BLS PPI homepage', url: 'https://www.bls.gov/ppi/' },
    ],
  },
  PCE: {
    display_name: 'Core PCE (Personal Consumption Expenditures)',
    tier: 'tier2',
    halts_bots: false,
    one_liner: "Fed's preferred inflation gauge — but CPI prints two weeks earlier so PCE is usually pre-traded.",
    pre_event:
      'Light IV runup compared with CPI. By the time PCE prints, CPI has already moved the market.',
    post_event:
      'Equity vol post-PCE runs ~half of post-CPI vol per multiple market-data analyses. Surprises still matter for Fed-policy expectations but rarely produce the same intraday whipsaw.',
    pattern: '"Better data later" — markets prioritize fast/flawed CPI over slower/cleaner PCE for trading',
    sources: [
      { label: 'Why the Fed prefers PCE', url: 'https://www.institutionalinvestor.com/article/sponsored-content/why-fed-prefers-pce-over-cpi-inflation-insights' },
      { label: 'Inflation reports explained', url: 'https://maseconomics.com/inflation-reports-explained-what-the-cpi-pce-and-ppi-really-mean/' },
    ],
  },
  RETAIL_SALES: {
    display_name: 'Retail Sales',
    tier: 'tier2',
    halts_bots: false,
    one_liner: 'Monthly consumer-spending proxy. Mid-tier mover; surprises in either direction can move SPY 0.3–1%.',
    pre_event: 'Modest IV buildup; not a vega-runup event.',
    post_event:
      'Reaction depends on the macro narrative. In a "soft-landing" tape, a hot Retail Sales print supports equities; in a "rates higher for longer" tape, the same hot print can pressure equities by reviving Fed-hike fears.',
    pattern: 'Bi-modal — same surprise can read bullish or bearish depending on the prevailing rate-cut narrative',
    sources: [
      { label: 'Census Bureau Retail Sales', url: 'https://www.census.gov/retail/index.html' },
    ],
  },
  ISM_SERVICES: {
    display_name: 'ISM Services PMI',
    tier: 'tier2',
    halts_bots: false,
    one_liner: 'Services-sector activity index. More market-relevant than ISM Manufacturing in the post-2010 services-driven economy.',
    pre_event: 'No meaningful IV runup.',
    post_event:
      'Sub-50 prints (contraction) tend to spook equities given services is ~70% of US GDP. Surprises within the 50–55 range produce muted moves.',
    pattern: 'Threshold-driven — the 50 line matters more than the magnitude of the surprise',
    sources: [
      { label: 'ISM Reports', url: 'https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/' },
    ],
  },
  GDP: {
    display_name: 'GDP (Quarterly Estimate)',
    tier: 'tier2',
    halts_bots: false,
    one_liner: 'Quarterly real-GDP print (advance / second / third estimate). Backward-looking; market reaction depends on whether the surprise contradicts the recession/soft-landing narrative.',
    pre_event: 'Mild IV buildup the day before for the advance estimate; second / third estimates are mostly non-events because most of the data is already known.',
    post_event:
      'A surprise advance estimate (especially the headline real-GDP growth and PCE-deflator-within-GDP) can move SPY 0.5–1%. Second and third revisions rarely move the index unless they shift the prior quarter\'s trajectory materially.',
    pattern: 'Advance estimate is the only one that moves SPY; revisions = bond-market only',
    sources: [
      { label: 'BEA GDP', url: 'https://www.bea.gov/data/gdp' },
    ],
  },
  JOLTS: {
    display_name: 'JOLTs Job Openings',
    tier: 'tier3',
    halts_bots: false,
    one_liner: 'Job openings + quits. Watched by the Fed for labor-market tightness; SPY rarely cares.',
    pre_event: 'No detectable IV runup.',
    post_event: 'Single-bar reaction at most. Quits-rate detail occasionally moves bond yields; equity move is usually noise.',
    pattern: 'Background data — useful for narrative context, not for sizing trades around',
    sources: [
      { label: 'BLS JOLTs', url: 'https://www.bls.gov/jlt/' },
    ],
  },
  HOUSING: {
    display_name: 'Housing Data (Starts / Permits / Existing Sales)',
    tier: 'tier3',
    halts_bots: false,
    one_liner: 'Sector-specific. Moves the homebuilder ETF (XHB), barely registers in SPY.',
    pre_event: 'None.',
    post_event: 'Typically background noise for SPY.',
    pattern: 'Sector-rotation signal at most',
    sources: [],
  },
  CONSUMER_SENTIMENT: {
    display_name: 'Michigan Consumer Sentiment',
    tier: 'tier3',
    halts_bots: false,
    one_liner: 'Survey-based sentiment + 1y/5y inflation expectations. The expectations subcomponent occasionally moves rates.',
    pre_event: 'No IV runup.',
    post_event:
      'Headline sentiment number rarely matters. The 5y inflation expectations sub-print can move bond yields when extreme — and that bond move can spill into SPY indirectly.',
    pattern: 'Pay attention only to the inflation-expectations subcomponent',
    sources: [
      { label: 'University of Michigan Consumer Survey', url: 'https://www.sca.isr.umich.edu/' },
    ],
  },
  CUSTOM: {
    display_name: 'Custom Halt',
    tier: 'tier1',
    halts_bots: true,
    one_liner: 'Operator-created blackout window.',
    pre_event: 'N/A — manual.',
    post_event: 'N/A — manual.',
    pattern: null,
    sources: [],
  },
}

/** Fallback for unknown event types: minimal placeholder. */
export const UNKNOWN_PLAYBOOK: EventPlaybook = {
  display_name: 'Macro Event',
  tier: 'tier3',
  halts_bots: false,
  one_liner: 'No playbook entry for this event type yet.',
  pre_event: '—',
  post_event: '—',
  pattern: null,
  sources: [],
}

export function getPlaybook(eventType: string): EventPlaybook {
  return EVENT_PLAYBOOKS[eventType.toUpperCase()] || UNKNOWN_PLAYBOOK
}
