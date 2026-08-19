// ChartMeta — the three questions a chart must answer about itself.
//
// A chart with no clock on it is a chart you cannot act on. Every plot in this
// app was missing all three of these, and the numbers were already in the
// payloads — the same unlabelled-not-broken defect as the GEX profile's LIVE
// badge and the /risk freshness block before [[FreshnessBar]].
//
//   AS OF     which session (or minute) the last point belongs to
//   NOW       what the series currently reads, and which zone that is
//   NEXT      when the next point lands
//
// 🚨 FOUR RULES, three of them learned by getting it wrong somewhere else in
// this app:
//
//  1. AS-OF COMES FROM THE DATA, NEVER THE BROWSER CLOCK. The old LIVE badge
//     read the browser clock and sat green over a feed that had stopped.
//     `asOf` here is a value out of the payload; this component never derives
//     it from Date.now().
//
//  2. NEXT-UPDATE COMES FROM THE SCHEDULER, NEVER A HARDCODED CRON STRING.
//     The captions on these charts already say "Updates once per session at
//     15:05 CT" — prose that stays confidently correct after the job dies.
//     `nextAt` must be the scheduler's own next_run_time. When the scheduler
//     is not registered the honest render is "unknown", never a guess.
//
//  3. A COUNTDOWN IS THE ONE PLACE THE BROWSER CLOCK IS THE RIGHT SOURCE —
//     "how long until this absolute instant" is a clock question. But it is
//     only safe because nextAt is absolute and carries its own offset, so it
//     resolves the same in any timezone. A past nextAt renders OVERDUE, never
//     "in −3h": a stalled scheduler must look wrong, not merely negative.
//
//  4. STALE IS MEASURED AGAINST THE EXPECTED SESSION, NOT AGAINST TODAY.
//     These are prior-close series by design. Grading them against today
//     paints them red every morning, and a warning that cries wolf daily is
//     one nobody reads. The caller passes `behind` (sessions behind expected)
//     already computed server-side.
import { useEffect, useState } from 'react';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', DIM = '#8b93a7';

const S = {
  row: {
    display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'stretch',
    margin: '0 0 10px',
  },
  cell: {
    flex: '1 1 150px', minWidth: 0, padding: '7px 10px', borderRadius: 8,
    background: '#0e1220', border: '1px solid #1c2233',
  },
  label: {
    fontSize: 10, color: DIM, letterSpacing: '.05em', textTransform: 'uppercase',
    marginBottom: 3, whiteSpace: 'nowrap',
  },
  value: {
    fontSize: 13, fontWeight: 700,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontVariantNumeric: 'tabular-nums',
  },
  note: { fontSize: 10.5, color: DIM, marginTop: 2, lineHeight: 1.35 },
};

/** Whole-minute countdown. Ticks on its own so the number never goes stale
 *  under a tab left open — the failure that made the old badge lie. */
function useNow(enabled) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(() => force((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, [enabled]);
  return Date.now();
}

/** "in 3h 52m" / "in 41m" / null when it is not in the future. */
function until(ms) {
  if (!(ms > 0)) return null;
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `in ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `in ${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `in ${d}d ${h % 24}h`;
}

function Cell({ label, value, note, color }) {
  return (
    <div style={{ ...S.cell, ...(color ? { borderColor: `${color}44` } : null) }}>
      <div style={S.label}>{label}</div>
      <div style={{ ...S.value, color: color || '#e6e9f0' }}>{value}</div>
      {note && <div style={{ ...S.note, ...(color ? { color } : null) }}>{note}</div>}
    </div>
  );
}

/**
 * @param {string} asOf     the last point's own date/time, straight from the payload
 * @param {string} asOfNote what that session is (e.g. "prior close — the signal")
 * @param {string} asOfTone 'ok' | 'warn' | 'bad' | 'none' — grade the as-of cell
 *                 EXPLICITLY, for series where sessions-behind is not the right
 *                 measure (a live tape, a once-a-day snapshot). Wins over `behind`.
 * @param {number} behind   sessions behind the EXPECTED session (0 = current). null = unknown
 * @param {string} reading  the current value, preformatted by the caller
 * @param {string} zone     what that value means right now (e.g. "APPROACHING OVERSOLD")
 * @param {string} zoneColor colour for the reading + zone
 * @param {string} nextAt   ISO instant of the next scheduled update, from the SCHEDULER
 * @param {string} cadence  what that update is (e.g. "15:05 CT capture")
 * @param {boolean} armed   false when the scheduler is known to be down; null = unknown
 * @param {object} nextOverride  {value, note, tone} for a CONTINUOUS feed that has
 *                 no next scheduled instant. ⛔ Only legitimate when the cadence is
 *                 something the client itself controls (this app's own 60s poll) or
 *                 the feed is provably closed. Never a place to restate a cron time.
 */
export default function ChartMeta({
  asOf, asOfNote, asOfTone, behind, reading, zone, zoneColor, nextAt, cadence,
  armed, nextOverride,
}) {
  const nextMs = nextAt ? Date.parse(nextAt) : NaN;
  const valid = Number.isFinite(nextMs);
  const now = useNow(valid);

  // ── AS OF ────────────────────────────────────────────────────────────────
  // 🚨 AMBER IS A WARNING AND MUST BE EARNED. The first deploy of this
  // component derived the colour from `behind` alone, so the two /risk charts
  // — which have no sessions-behind concept at all — rendered a permanent
  // amber "as of 12:30" over a tape that was perfectly current. A warning that
  // is on when nothing is wrong is the cry-wolf failure this whole component
  // exists to prevent, shipped inside it. Series that are not graded by
  // session now pass an explicit asOfTone instead.
  const TONE = { ok: null, warn: AMBER, bad: RED, none: null };
  const stale = behind != null && behind > 0;
  const asOfColor = asOfTone ? TONE[asOfTone]
    : stale ? RED : behind === 0 ? null : AMBER;
  const asOfText = asOfTone ? asOfNote
    : stale ? `${behind} session${behind === 1 ? '' : 's'} behind`
    : behind === 0 ? (asOfNote || 'current for this session')
    : (asOfNote || 'freshness unknown');

  // ── NEXT ─────────────────────────────────────────────────────────────────
  // ⛔ Every branch that cannot prove a next run says so. None of them fall
  // back to the cron time written in the caption.
  let nextValue, nextNote, nextColor;
  if (nextOverride) {
    nextValue = nextOverride.value;
    nextNote = nextOverride.note;
    nextColor = nextOverride.tone || null;
  } else if (armed === false) {
    nextValue = 'NOT SCHEDULED';
    nextNote = 'the job is not armed — this chart will not update on its own';
    nextColor = RED;
  } else if (!valid) {
    nextValue = 'unknown';
    nextNote = armed === true
      ? 'the job is armed but reported no next run'
      : 'no next-run time in the payload';
    nextColor = AMBER;
  } else {
    const left = until(nextMs - now);
    if (left) {
      nextValue = left;
      nextNote = `${new Date(nextMs).toLocaleString([], {
        weekday: 'short', hour: '2-digit', minute: '2-digit',
      })}${cadence ? ` · ${cadence}` : ''}`;
    } else {
      // Past due. Not "in −3h" — a stalled job has to read as wrong.
      nextValue = 'OVERDUE';
      nextNote = `was due ${new Date(nextMs).toLocaleString([], {
        weekday: 'short', hour: '2-digit', minute: '2-digit',
      })} and has not run`;
      nextColor = RED;
    }
  }

  return (
    <div style={S.row}>
      <Cell label="as of" value={asOf || '—'} note={asOfText} color={asOfColor} />
      <Cell label="reading now" value={reading || '—'} note={zone} color={zoneColor} />
      <Cell label="next update" value={nextValue} note={nextNote} color={nextColor} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Squeeze payload -> props.
//
// 🚨 BOTH HELPERS TAKE THE CHART'S OWN LAST PLOTTED ROW, NOT THE TOP-LEVEL
// STATE FIELDS. The first version of this file read `data.vix_ratio` and
// `freshness.vix_date` and would have shipped a genuine mislabel: on
// 2026-08-19 those were 0.765 and 2026-08-19 — but 0.765 is TUESDAY's value
// (the one the verdict is built from) while the newest stored row is
// Wednesday's 0.735. That renders yesterday's number under today's date,
// which is the exact defect this component exists to remove.
//
// Sourcing as-of and reading from the same row makes them incapable of
// disagreeing, whatever the range picker is set to.
// ─────────────────────────────────────────────────────────────────────────────

/** Both charts' next update is gamma_capture: the 15:05 CT job is what closes
 *  the session both series are keyed on. */
function schedOf(data) {
  const s = data?.jobs?.scheduler || {};
  return { nextAt: s.jobs?.gamma_capture || null, armed: s.registered ?? null };
}

/**
 * @param {object} data  the /squeeze/state payload
 * @param {object} last  the last row of the SIGNAL series actually drawn
 *                       ({trade_date, net_gex_b, pct}) — never the live dot,
 *                       which the page is explicit is "not the signal".
 */
export function gammaChartMeta(data, last) {
  const f = data?.freshness || {};
  const o = data?.outlook || {};
  const g = last?.net_gex_b, px = last?.pct;
  // The verdict is built from the newest stored session, so when the chart's
  // tail IS that session the proximity label describes it. If a future range
  // control ever ends the chart earlier, drop the label rather than attach
  // today's zone to an older point.
  const isCurrent = !last?.trade_date || !f.gamma_date
    || last.trade_date === f.gamma_date;
  const prox = isCurrent ? o.proximity : null;
  return {
    asOf: last?.trade_date || f.gamma_date || data?.data_date || null,
    asOfNote: 'prior close — the session this signal is built from',
    behind: isCurrent ? (f.gamma_stale_sessions ?? null) : null,
    reading: g == null ? '—' : `${g < 0 ? '−' : '+'}$${Math.abs(g).toFixed(2)}B`,
    zone: px == null ? 'percentile unknown'
      : `${(100 * px).toFixed(0)}th pct of trailing 60${prox ? ` · ${prox.replace(/_/g, ' ')}` : ''}`,
    zoneColor: prox === 'OVERSOLD' || prox === 'APPROACHING_OVERSOLD' ? AMBER
      : prox === 'OVERBOUGHT' || prox === 'APPROACHING_OVERBOUGHT' ? GREEN
      : null,
    cadence: 'the 15:05 CT capture',
    ...schedOf(data),
  };
}

/**
 * @param {object} data  the /squeeze/state payload
 * @param {object} last  the last row of vix_history actually drawn
 *                       ({trade_date, ratio})
 */
export function vixChartMeta(data, last) {
  const f = data?.freshness || {};
  const r = last?.ratio;
  const gap = r == null ? null : 0.95 - r;

  // 🚨 THE CHART'S NEWEST POINT AND THE VERDICT'S VIX LEG ARE ROUTINELY
  // DIFFERENT ROWS, and that is not a fault. VIX posts early in the day, so
  // today's ratio is already plotted while the verdict still runs off the
  // prior close. Naming the split is the whole point — a reader comparing the
  // chart's last point to the signal card above it would otherwise think one
  // of them is wrong.
  const legLags = data?.vix_ratio != null && last?.trade_date
    && f.vix_date && last.trade_date === f.vix_date
    && Math.abs(data.vix_ratio - r) > 1e-9;

  return {
    asOf: last?.trade_date || f.vix_date || null,
    asOfNote: legLags
      ? `today's row is plotted; the signal leg still uses ${data.vix_ratio.toFixed(2)} from the prior close`
      : 'VIX posts earlier in the day than the gamma capture',
    behind: last?.trade_date && f.vix_date && last.trade_date === f.vix_date
      ? (f.vix_stale_sessions ?? null) : null,
    reading: r == null ? '—' : r.toFixed(2),
    zone: r == null ? 'trigger distance unknown'
      : r >= 0.95 ? 'at its own 20-session high — the squeeze leg is LIVE'
      : `${gap.toFixed(2)} below the 0.95 trigger — still decaying`,
    zoneColor: r != null && r >= 0.95 ? AMBER : null,
    cadence: 'next session closes at the 15:05 CT capture',
    ...schedOf(data),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Risk Advisor payload -> props.
// ─────────────────────────────────────────────────────────────────────────────

function riskSched(state) {
  const s = state?.jobs?.scheduler || {};
  return { armed: s.registered ?? null, jobs: s.jobs || {} };
}

/**
 * Today's tape vs the expected move. A CONTINUOUS feed, not a scheduled one:
 * bars append as the session runs and this page refetches every 60s.
 *
 * 🚨 "every 60s" is only honest while the tape is actually open. Outside the
 * session the bars stop and a cell still promising a minute-by-minute refresh
 * would be cry-wolf in reverse — the quiet failure that let /session sit green
 * over a feed that had stopped 30 minutes earlier. The override therefore
 * reports the feed's own status, not the poll timer, whenever it is not 'ok'.
 *
 * @param {object} intra  /risk-advisor/intraday payload
 * @param {object} state  /risk-advisor/state payload (for the expected move)
 */
export function tapeChartMeta(intra, state) {
  const bars = intra?.bars || [];
  const last = bars.length ? bars[bars.length - 1] : null;
  const band = intra?.band_pct;
  const chg = last?.chg_pct;
  const used = band && chg != null ? Math.abs(chg) / band : null;
  const open = intra?.status === 'ok' && bars.length > 0;

  // 🚨 GRADED BY LAG, NOT BY SESSION — and measured server-clock against
  // server-clock. `generated_at` is when the backend built this payload and
  // `t` is the last bar it had; the gap between them is the tape's real lag,
  // computed without ever consulting the browser. That matters: /session's
  // first version derived liveness from the browser clock and sat green over
  // a feed that had stopped 30 minutes earlier.
  //
  // Sessions-behind is the WRONG measure here and passing it produced a
  // permanent amber over a perfectly current tape on the first deploy.
  let lagMin = null;
  if (last?.t && intra?.generated_at) {
    const gen = new Date(intra.generated_at);
    const [bh, bm] = last.t.split(':').map(Number);
    if (Number.isFinite(bh) && Number.isFinite(bm) && !isNaN(gen)) {
      // Same-day comparison in the server's own reported wall time.
      lagMin = (gen.getHours() * 60 + gen.getMinutes()) - (bh * 60 + bm);
    }
  }
  // Bars are 5-minute; anything past ~12 minutes means the feed has stopped.
  const lagBad = lagMin != null && lagMin > 12;

  return {
    asOf: last?.t || null,
    asOfNote: !last
      ? 'no bars yet — the tape starts at the 08:30 CT open'
      : lagBad
        ? `no new bar for ${lagMin} minutes — the tape has stopped`
        : `last 5-minute bar${intra?.snapshot_t ? ` · flow snapshot read at ${intra.snapshot_t}` : ''}`,
    asOfTone: !last ? 'warn' : lagBad ? 'bad' : 'ok',
    reading: chg == null ? '—' : `${chg >= 0 ? '+' : '−'}${Math.abs(chg).toFixed(2)}%`,
    zone: used == null
      ? 'expected move unavailable'
      : `${(100 * used).toFixed(0)}% of the ±${band.toFixed(2)}% expected move used`
        + (used >= 1 ? ' — already bigger than options priced' : ''),
    zoneColor: used != null && used >= 1 ? RED : used != null && used >= 0.75 ? AMBER : null,
    nextOverride: open
      ? { value: '≤ 60s', note: 'this page refetches the tape every 60 seconds' }
      : {
          value: 'not updating',
          note: intra?.status && intra.status !== 'ok'
            ? `feed reports "${intra.status}" — bars are not arriving`
            : 'no bars in this payload',
          tone: AMBER,
        },
  };
}

/**
 * The flow z-score history — one 10:00 CT reading per session.
 *
 * Its as-of is `flow.captured_at`, the moment the snapshot was actually taken,
 * NOT asof_close: this series is the only thing on /risk keyed to an intraday
 * capture rather than a prior close, and dating it by the close would hide a
 * snapshot that never ran.
 *
 * @param {object} state /risk-advisor/state payload
 * @param {object} last  last row of the plotted history ({d, putv_z, totv_z, ...})
 */
export function flowChartMeta(state, last) {
  const flow = state?.flow || {};
  const { armed, jobs } = riskSched(state);
  const z = [flow.putv_z, flow.totv_z].filter((x) => x != null);
  const peak = z.length ? Math.max(...z) : null;
  const cap = flow.captured_at ? String(flow.captured_at).slice(0, 16).replace('T', ' ') : null;

  // 🚨 "10:00" IS NOT STALE AT 14:00. This series is one reading per session,
  // taken once at 10:00 CT — its age in hours is meaningless and grading it
  // that way would paint the chart amber every afternoon. The only question
  // that matters is whether TODAY's snapshot landed at all.
  const landed = flow.status === 'snapshot';

  return {
    asOf: cap || last?.d || null,
    asOfNote: landed
      ? "today's 10:00 CT snapshot is in"
      : flow.status
        ? `snapshot status: ${flow.status} — today's reading has not landed`
        : 'no snapshot recorded for today',
    asOfTone: landed ? 'ok' : 'warn',
    reading: peak == null ? '—' : `z ${peak >= 0 ? '+' : '−'}${Math.abs(peak).toFixed(2)}`,
    zone: peak == null ? 'no flow reading'
      : flow.spike ? 'SPIKE — above the z>2 threshold the signal fires on'
      : `largest of put-vol and total-vol z · fires above 2.00`,
    zoneColor: flow.spike ? RED : peak != null && peak >= 1.5 ? AMBER : null,
    // The 10:06 job is what writes tomorrow's point.
    nextAt: jobs.risk_flow_spike || null,
    cadence: 'the 10:06 CT snapshot',
    armed,
  };
}
