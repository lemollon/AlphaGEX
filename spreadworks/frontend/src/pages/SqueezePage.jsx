// Squeeze Signal — net dealer gamma percentile + VIX-at-highs, the
// prerequisite-not-a-direction-call gate documented in
// backend/bots/gamma_regime.py. ADVISORY ONLY — no bot reads this.
//
// 🚨 2026-09-02 restructure: FOUR SECTIONS, same shape /session took the same
// day. (1) a status row — is this reading usable, and how old is it;
// (2) THE CALL — what to do today, with the real ticket; (3) the net-gamma
// line with the two trigger levels named in plain words; (4) ONE fold,
// "How this signal has done", collapsed by default, holding everything else:
// call history, what SPY did the next session after each verdict, the live
// record, the tape shape, what to watch, the intraday panels, the VIX leg,
// data/job status, the Risk-page overlap, and every evidence table. Nothing
// was deleted — it was moved under the fold. The top three sections are the
// page; the fold is the proof.
//
// Reading rules that survive the restructure:
//   * Blocking outranks the verdict. Stale / capture-failed / unarmed /
//     mixed-source / UNKNOWN all render NO USABLE READING; the ticket is
//     withheld. The page never tells the bots what to do — they trade on
//     their own schedule — so the blocked state says the reading is unusable,
//     not that there is no trade.
//   * Freshness comes from the data, never the browser clock.
//   * The 15:05 CT close is the signal. Everything intraday is context and is
//     labelled as such.
//   * 13px is the floor for prose. SVG tick labels may go to 11.
//
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import { Zap, Radio } from 'lucide-react';
import { API_URL } from '../lib/api';
import CallHistory from '../components/CallHistory';
import ChartMeta, { gammaChartMeta, vixChartMeta } from '../components/ChartMeta';
import TapeShape from '../components/TapeShape';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', GREY = '#9ca3af', DIM = '#8b93a7';
const LIVE = '#c084fc';
const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 13, fontWeight: 700, marginBottom: 10 },
  th: { textAlign: 'left', color: DIM, fontSize: 13, padding: '6px 10px' },
  td: { padding: '6px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
  // 13px is the floor. This used to be 11px and the probe counted hundreds of
  // nodes under the floor on the sibling page; every label here now sits at 13.
  small: { fontSize: 13, color: DIM },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontVariantNumeric: 'tabular-nums' },
  caption: { fontSize: 13, color: '#a8afc0', lineHeight: 1.75 },
  tile: { flex: '1 1 160px', background: '#0e1220', border: '1px solid #232a3d', borderRadius: 10, padding: '12px 14px' },
  tileLabel: { fontSize: 13, color: DIM, marginBottom: 4 },
  tileValue: { fontSize: 22, fontWeight: 700 },
};

const VERDICT_COLOR = {
  SQUEEZE_WATCH: AMBER, NO_SELL: RED, SELL_PREMIUM: GREEN, UNKNOWN: GREY, NEUTRAL: DIM,
};
const VERDICT_LABEL = {
  SQUEEZE_WATCH: 'SQUEEZE WATCH', NO_SELL: 'NO SELL', SELL_PREMIUM: 'SELL PREMIUM',
  UNKNOWN: 'UNKNOWN', NEUTRAL: 'NEUTRAL',
};

function pct(x, d = 1) { return x == null ? '—' : (100 * x).toFixed(d) + '%'; }
function bn(x, d = 2) { return x == null ? '—' : `$${x.toFixed(d)}B`; }
// Signed $bn — matches the outlook API's sign convention (negative = oversold
// side, positive = overbought side). Uses a true minus glyph, not a hyphen.
function signedBn(x, d = 2) { return x == null ? '—' : `${x < 0 ? '−' : '+'}$${Math.abs(x).toFixed(d)}B`; }
// Signed percent for a next-session move: "+0.42%" / "−1.10%".
function signedPct(x, d = 2) {
  return x == null || Number.isNaN(x) ? '—' : `${x < 0 ? '−' : '+'}${Math.abs(100 * x).toFixed(d)}%`;
}

// 🚨 EVERY CHART STATES ITS OWN CADENCE, IN WORDS, ON THE CHART. The two
// intraday panels do not use ChartMeta (they are sub-panels of cards that
// already carry one), so they carry the same three facts inline: how often the
// series loads, when it last did, and when the next point lands.
//
// ⛔ THE NEXT-POINT TIME IS DERIVED FROM THE DATA'S OWN GRID, NOT THE BROWSER
// CLOCK. The recorder writes fixed 10-minute buckets between 08:30 and 15:00
// CT, so last-bucket + 10 is a fact about the schedule rather than a guess
// about now — and when the last bucket IS 15:00 the honest answer is that the
// grid is done for the day, not a time ten minutes into the close.
const GRID_STEP_MIN = 10;
const GRID_CLOSE_MIN = 15 * 60;          // 15:00 CT, the last bucket
const GRID_OPEN_LABEL = '08:30 CT';

function hhmm(mins) {
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:`
       + `${String(mins % 60).padStart(2, '0')}`;
}

function IntradayCadence({ lastMinute, count }) {
  const done = lastMinute >= GRID_CLOSE_MIN;
  const next = Math.min(lastMinute + GRID_STEP_MIN, GRID_CLOSE_MIN);
  return (
    <span style={{ ...S.small, marginLeft: 'auto', textAlign: 'right' }}>
      <b style={{ color: '#c6cbd8' }}>EVERY 10 MIN</b>
      {count != null && ` · ${count} today`}
      {' · last '}<b style={{ color: '#c6cbd8' }}>{hhmm(lastMinute)} CT</b>
      {done
        ? ' · done for today, resumes ' + GRID_OPEN_LABEL
        : <> · next ~<b style={{ color: '#c6cbd8' }}>{hhmm(next)} CT</b></>}
    </span>
  );
}

const PROXIMITY_COLOR = {
  OVERSOLD: AMBER, APPROACHING_OVERSOLD: AMBER, MID_RANGE: GREY,
  APPROACHING_OVERBOUGHT: GREEN, OVERBOUGHT: GREEN,
};
const PROXIMITY_LABEL = {
  OVERSOLD: 'OVERSOLD', APPROACHING_OVERSOLD: 'APPROACHING OVERSOLD', MID_RANGE: 'MID RANGE',
  APPROACHING_OVERBOUGHT: 'APPROACHING OVERBOUGHT', OVERBOUGHT: 'OVERBOUGHT',
};
const PROXIMITY_COPY = {
  OVERSOLD: 'In the squeeze zone. Needs VIX at its highs to trigger.',
  APPROACHING_OVERSOLD: 'Nearing the squeeze zone — watch for VIX to stop decaying.',
  MID_RANGE: 'Neither zone. Historically the widest downside tail sits here — no edge either way.',
  APPROACHING_OVERBOUGHT: 'Nearing the safest state for selling premium.',
  OVERBOUGHT: 'Safest historical state to sell premium into. Zero squeezes have started here.',
};

const FUEL_TOP_DECILE = 0.225;
const PIN_LABEL = { strong: 'STRONG', active: 'ACTIVE', approaching: 'APPROACHING', none: 'NONE' };
const PIN_COLOR = { strong: GREEN, active: GREEN, approaching: AMBER, none: DIM };
const PIN_COPY = {
  strong: 'Top decile of the range — safest measured state to sell premium into.',
  active: 'In the overbought zone — the SELL_PREMIUM state itself.',
  approaching: 'Below the trigger and rising — premium-selling conditions are firming.',
  none: 'Not in pin territory.',
};
// month/quarter end + payrolls Friday raise squeeze odds on oversold days
// (calendar_flags() in gamma_regime.py); opex week suppresses them.
const CALENDAR_FLAGS = [
  { key: 'month_end', label: 'Month end', tone: 'supportive' },
  { key: 'quarter_end', label: 'Quarter end', tone: 'supportive' },
  { key: 'payrolls_friday', label: 'Payrolls Friday', tone: 'supportive' },
  { key: 'opex_week', label: 'Opex week', tone: 'suppressive' },
  { key: 'opex_day', label: 'Monthly opex day', tone: 'suppressive' },
];

// Background jobs that write this page's data. `jobs.last` keys mirror this
// list — a key absent from the payload means that job has never fired.
const JOB_STATUS = [
  { key: 'gamma_capture', label: 'gamma capture', schedule: '15:05 CT, weekdays' },
  { key: 'squeeze_signal', label: 'squeeze signal', schedule: '15:05 CT, weekdays' },
  { key: 'squeeze_proximity_watch', label: 'proximity watch', schedule: '08:05 CT, weekdays' },
  { key: 'squeeze_proximity_pin', label: 'proximity pin', schedule: '08:05 CT, weekdays' },
];

// Range control. FETCH_SESSIONS is what /state is asked for once; the buttons
// slice that locally. 250 ≈ one trading year and is under the endpoint's
// MAX_HISTORY_ROWS=400 clamp.
const FETCH_SESSIONS = 250;
const DEFAULT_RANGE = 90;
const RANGES = [
  { n: 30, label: '30D' },
  { n: 60, label: '60D' },
  { n: 90, label: '90D' },
  { n: 250, label: '1Y' },
];

// The price series' display name. It is also the tooltip's only way to tell a
// dollar price from a dollar-billions gamma reading — see the Tooltip
// formatter — so the Line's `name` and that check must stay the same string.
const PRICE_SERIES = 'SPY close';

// Track-record strip colours — mirrors VERDICT_COLOR but with its own NEUTRAL
// shade so a long neutral run doesn't read as "muted/broken" in the strip.
const SIGNAL_STRIP_COLOR = {
  SQUEEZE_WATCH: AMBER, NO_SELL: RED, SELL_PREMIUM: GREEN, NEUTRAL: '#334155', UNKNOWN: GREY,
};
const VERDICT_ORDER = ['SQUEEZE_WATCH', 'NO_SELL', 'SELL_PREMIUM', 'NEUTRAL', 'UNKNOWN'];

// The regime cell behind "how often does a day like this move more than 1%".
// Mirrors BREAK_CELLS in gamma_regime.py; the API sends the probability and
// the cell key, this only supplies the words.
const BREAK_CELL_WORDS = {
  deep_short_gamma: 'dealers deeply short gamma',
  short_below_flip: 'dealers short gamma',
  long_above_flip: 'dealers long gamma',
};

// Fuel evidence — squeeze rate by fuel sextile (outlook.fuel; research metric,
// not yet the live signal).
const FUEL_SEXTILE_RATES = [
  ['1 (least fuel)', '0.00%'],
  ['2', '0.00%'],
  ['3', '0.75%'],
  ['4', '2.25%'],
  ['5', '7.89%'],
  ['6 (most fuel)', '9.36%'],
];

// Calendar evidence — scheduled flow, measured on oversold days only
// (calendar_flags() in gamma_regime.py).
const CALENDAR_EVIDENCE = [
  { event: 'Month end (≥26th)', rate: '25.35%', mult: '2.52x', n: 71, tone: 'supportive' },
  { event: 'Quarter end', rate: '22.22%', mult: '2.21x', n: 27, tone: 'supportive' },
  { event: 'Payrolls Friday', rate: '20.00%', mult: '1.99x', n: 20, tone: 'supportive' },
  { event: 'Opex week', rate: '6.00%', mult: '0.60x', n: 100, tone: 'suppressive' },
  { event: 'Monthly opex day', rate: '4.35%', mult: '0.43x', n: 23, tone: 'suppressive' },
];

// Falsification — the last 22 times net gamma broke below −$10B (16 shown,
// the rest are unremarkable middles). [date, net gamma, vs flip, fwd 5d,
// 5d max, >+3% rip].
const FALSIFICATION_EPISODES = [
  ['2023-03-02', '−10.2B', '−1.84%', '−1.57%', '+1.67%', false],
  ['2023-08-25', '−11.3B', '−1.50%', '+2.55%', '+2.55%', false],
  ['2023-09-18', '−10.2B', '−1.60%', '−2.57%', '−0.21%', false],
  ['2023-10-19', '−10.5B', '−2.62%', '−3.25%', '−0.66%', false],
  ['2023-10-26', '−11.5B', '−4.11%', '+4.41%', '+4.41%', true],
  ['2024-04-16', '−11.1B', '−2.44%', '+0.42%', '+0.42%', false],
  ['2024-08-08', '−10.1B', '−2.58%', '+4.23%', '+4.23%', true],
  ['2024-09-09', '−10.2B', '−1.57%', '+3.01%', '+3.01%', true],
  ['2025-01-13', '−12.6B', '−2.04%', '+3.73%', '+3.73%', true],
  ['2025-02-26', '−11.3B', '−2.00%', '−1.93%', '−0.06%', false],
  ['2025-03-31', '−12.5B', '−2.87%', '−4.55%', '+0.92%', false],
  ['2025-04-17', '−10.9B', '−5.03%', '+4.60%', '+4.60%', true],
  ['2026-02-06', '−15.5B', '−0.51%', '−1.28%', '+0.48%', false],
  ['2026-03-04', '−11.0B', '−1.02%', '−1.28%', '−0.56%', false],
  ['2026-06-10', '−11.7B', '−3.01%', '+2.14%', '+4.05%', true],
  ['2026-07-24', '−12.9B', '−1.84%', '+1.10%', '+1.10%', false],
];

// Hover "i" circle with an absolutely-positioned tooltip. Mirrors
// RiskAdvisorPage's InfoTip exactly.
function InfoTip({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-block', marginLeft: 6 }}
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <span style={{ cursor: 'help', color: DIM, fontSize: 13, border: `1px solid ${DIM}66`,
                     borderRadius: '50%', width: 16, height: 16, display: 'inline-flex',
                     alignItems: 'center', justifyContent: 'center', verticalAlign: 'middle' }}>i</span>
      {open && (
        <span style={{ position: 'absolute', zIndex: 30, top: 18, left: -8, width: 290,
                       background: '#0e1220', border: '1px solid #2a3145', borderRadius: 8,
                       padding: '10px 12px', fontSize: 13, lineHeight: 1.55, color: '#c6cbd8',
                       fontWeight: 400, boxShadow: '0 6px 20px rgba(0,0,0,.5)' }}>{text}</span>
      )}
    </span>
  );
}

function Pill({ text, color, solid }) {
  return (
    <span style={{
      display: 'inline-block', padding: '3px 9px', borderRadius: 999, fontSize: 13,
      fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap',
      color: solid ? '#0b0e17' : color, background: solid ? color : `${color}22`,
      border: `1px solid ${color}${solid ? '' : '55'}`,
    }}>{text}</span>
  );
}

// A small "CONTEXT — NOT THE SIGNAL" tag for the intraday panels.
function ContextTag() {
  return (
    <span style={{
      fontSize: 13, fontWeight: 700, letterSpacing: '.06em',
      padding: '1px 7px', borderRadius: 999, color: DIM,
      border: `1px solid ${DIM}55`, whiteSpace: 'nowrap',
    }}>CONTEXT — NOT THE SIGNAL</span>
  );
}

// Collapsible card. The outer "How this signal has done" fold remembers
// open/closed across visits via `persistKey` (same try/catch-around-
// localStorage shape /session uses); the folds nested inside it stay plain.
function Fold({ title, meta, children, open: init = false, persistKey }) {
  const [open, setOpen] = useState(() => {
    if (!persistKey) return init;
    try {
      const saved = localStorage.getItem(persistKey);
      return saved == null ? init : saved === '1';
    } catch { return init; }
  });
  const toggle = () => setOpen((o) => {
    const next = !o;
    if (persistKey) {
      try { localStorage.setItem(persistKey, next ? '1' : '0'); } catch { /* noop */ }
    }
    return next;
  });
  return (
    <div style={S.card}>
      <button onClick={toggle} aria-expanded={open}
        style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center',
                 gap: 10, width: '100%', boxSizing: 'border-box' }}>
        <span style={{ color: DIM, fontSize: 13, width: 10 }}>{open ? '▾' : '▸'}</span>
        <span style={{ ...S.cardTitle, marginBottom: 0 }}>{title}</span>
        {meta && <span style={{ ...S.small, marginLeft: 'auto', textAlign: 'right' }}>{meta}</span>}
      </button>
      {open && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
}

// "1 day in 4" from a probability. Rounded, because the card speaks in whole
// days; the exact percentage sits beside it.
function oneIn(p) {
  if (p == null || p <= 0) return null;
  return Math.max(1, Math.round(1 / p));
}

export default function SqueezePage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);
  const [tape, setTape] = useState(null);
  const [intraday, setIntraday] = useState(null);
  const [ipath, setIpath] = useState(null);
  const [intradayErr, setIntradayErr] = useState(null);
  const [rangeN, setRangeN] = useState(DEFAULT_RANGE);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        // Always fetch the WIDEST range and slice client-side. Refetching per
        // range would put a percentile recompute and a signal-history walk on
        // every button press, for data the page already has.
        const r = await fetch(
          `${API_URL}/api/spreadworks/squeeze/state?sessions=${FETCH_SESSIONS}`);
        const d = await r.json();
        // The base case this verdict is a deviation FROM. Failure is swallowed:
        // context must never take the page down.
        fetch(`${API_URL}/api/spreadworks/risk-advisor/tape-shape`)
          .then((x) => x.json()).then((t) => { if (live) setTape(t); })
          .catch(() => {});
        // 🚨 Stamped on a SUCCESSFUL fetch only. Stamping every tick would show
        // a moving "loaded" time over a payload that stopped updating — the
        // exact lie /session's LIVE badge told before 08-18.
        if (live) { setData(d); setLoadedAt(new Date()); }
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    const t = setInterval(load, 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  // Live intraday reading — CONTEXT ONLY, never the signal (see the strip's
  // own caveat copy). Polls only while the tab is visible so a backgrounded
  // tab doesn't keep hammering the ~40-chain-request Tradier pull.
  useEffect(() => {
    let live = true;
    const load = async () => {
      if (document.visibilityState !== 'visible') return;
      try {
        // Today's stored 10-minute gamma path. Cheap — served from the table
        // the scheduled job writes, never a live chain pull.
        fetch(`${API_URL}/api/spreadworks/squeeze/intraday-path`)
          .then((x) => x.json()).then((t) => { if (live) setIpath(t); })
          .catch(() => {});
        const r = await fetch(`${API_URL}/api/spreadworks/squeeze/intraday`);
        const d = await r.json();
        if (live) { setIntraday(d); setIntradayErr(null); }
      } catch (e) { if (live) setIntradayErr(String(e)); }
    };
    load();
    const t = setInterval(load, 60 * 1000);
    const onVis = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      live = false;
      clearInterval(t);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  if (err) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Squeeze signal unavailable: {err}</div></div></div>;
  if (!data) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Loading…</div></div></div>;

  const verdict = data.verdict || 'UNKNOWN';
  const f = data.freshness || {};

  // The range control governs the gamma chart, the VIX chart and the track
  // record together — three views of the same sessions, so letting them drift
  // to different windows would make them impossible to read against each
  // other. Sliced from the tail: newest sessions are always in view.
  const inRange = (rows) => (rows || []).slice(-rangeN);
  const hist = inRange(data.history).map(h => ({ ...h, label: h.trade_date.slice(5) }));
  const rangeLabel = (RANGES.find(r => r.n === rangeN) || {}).label || `${rangeN}`;

  // Shared range buttons. Rendered once, on the chart card — every chart and
  // the track record inside the fold shares this one control.
  const RangePicker = () => (
    <div style={{ display: 'flex', gap: 4 }}>
      {RANGES.map(r => {
        const on = r.n === rangeN;
        // A range wider than the data we hold is dead weight — grey it out
        // rather than silently showing the same chart for two buttons.
        const avail = (data.history || []).length;
        const short = r.n > avail;
        return (
          <button key={r.n} onClick={() => setRangeN(r.n)} disabled={short}
            title={short ? `only ${avail} sessions stored` : `last ${r.n} sessions`}
            style={{
              fontSize: 13, fontWeight: 700, borderRadius: 6, cursor: short ? 'default' : 'pointer',
              padding: '2px 9px', background: on ? '#1c2740' : 'transparent',
              border: `1px solid ${on ? '#3b82f6aa' : '#232a3d'}`,
              color: short ? '#3f4657' : on ? '#c6cbd8' : DIM,
            }}>
            {r.label}
          </button>
        );
      })}
    </div>
  );

  // Contiguous oversold (<=20th pct) / overbought (>=80th pct) zones, for
  // shading the chart — same construction RiskAdvisorPage uses for its
  // quiet-day ribbon.
  const zoneBands = (test) => {
    const bands = []; let start = null;
    hist.forEach((d, i) => {
      const inZone = d.pct != null && test(d.pct);
      if (inZone && start === null) start = i;
      if ((!inZone || i === hist.length - 1) && start !== null) {
        bands.push([hist[start].label, hist[inZone ? i : Math.max(i - 1, start)].label]);
        start = null;
      }
    });
    return bands;
  };
  const oversoldBands = zoneBands(p => p <= 0.20);
  const overboughtBands = zoneBands(p => p >= 0.80);

  // Live intraday point appended to the right edge of the line — a distinct
  // colour, a visible dot, dashed connector from the last close. Omitted
  // entirely (not drawn stale) when the /intraday poll is stale or has no
  // reading.
  const liveOk = !!intraday && !intraday.stale && intraday.net_gex_b != null;
  const chartData = liveOk
    ? hist.map((d, i) => (i === hist.length - 1 ? { ...d, live_gex_b: d.net_gex_b } : d))
        .concat([{ label: 'live', live_gex_b: intraday.net_gex_b, isLive: true }])
    : hist;
  const LiveDot = (props) => {
    const { cx, cy, payload } = props;
    if (!payload?.isLive) return null;
    return <circle cx={cx} cy={cy} r={4} fill={LIVE} stroke="#0b0e17" strokeWidth={1.5} />;
  };

  // ── BLOCKING. A stale / unarmed / unknown / source-mixed read is never
  // actionable no matter what the verdict string says. Source mixing blocks
  // because a percentile is a RANK, and ranking a Tradier-derived reading
  // inside a window of ORATS-derived ones compares two different measurements
  // of the same quantity. See data_freshness().
  const outlookTop = data.outlook || {};
  const sourceMixed = f.window_source_mixed === true;
  const captureFailed = data.capture_health?.state === 'claimed_but_not_stored';
  const notArmed = data.jobs?.scheduler?.registered === false;
  const blocked = sourceMixed || f.stale || captureFailed || notArmed || verdict === 'UNKNOWN';

  let blockedReason = null;
  if (blocked) {
    if (notArmed) {
      blockedReason = 'The capture and alert jobs are not scheduled — nothing is updating this page.';
    } else if (captureFailed) {
      blockedReason = 'The 15:05 capture ran and stored nothing, so this reading will keep ageing.';
    } else if (f.stale) {
      blockedReason = `The newest reading is ${f.gamma_date || '—'}, ${f.gamma_stale_sessions ?? '—'} session(s) behind ${f.expected_date || '—'}.`;
    } else {
      blockedReason = 'The signal could not be computed. UNKNOWN is a block, never a pass.';
    }
    if (sourceMixed) {
      blockedReason = `The 60-session window mixes two data sources — `
        + `${f.window_captured} session(s) from the live capture and `
        + `${f.window_seeded} from the ORATS baseline. A percentile `
        + `ranks a value against its own history; these are not the same measurement.`;
    }
  }
  // The machine reason behind an UNKNOWN — "insufficient_gamma_history:
  // have=12 need=60", or the actual exception. Shown as a second line, never
  // in place of the human sentence above.
  const blockedDetail = blocked ? (data.reason || data.outlook?.reason || null) : null;

  // ── STATUS ROW state. One word for the whole reading, then the detail.
  let statusLabel, statusTone, statusDetail;
  if (notArmed) {
    statusLabel = 'JOBS NOT ARMED'; statusTone = RED;
    statusDetail = `${data.jobs?.scheduler?.reason || ''} Nothing will update this page until the scheduler is running.`.trim();
  } else if (captureFailed) {
    statusLabel = 'CAPTURE FAILED'; statusTone = RED;
    statusDetail = `${data.capture_health?.detail || 'The 15:05 job ran and stored nothing.'} The reading shown is the last one that did store.`;
  } else if (f.reason || f.gamma_stale_sessions == null) {
    statusLabel = 'FRESHNESS UNKNOWN'; statusTone = AMBER;
    statusDetail = f.reason || 'The page could not work out how old this reading is.';
  } else if (f.stale) {
    const behind = f.gamma_stale_sessions;
    statusLabel = `${behind} SESSION${behind === 1 ? '' : 'S'} BEHIND`; statusTone = RED;
    statusDetail = `Newest gamma reading ${f.gamma_date || '—'}, expected ${f.expected_date || '—'}.`
      + (f.legs_mismatch ? ` The two legs are dated apart — gamma ${f.gamma_date || '—'}, VIX ${f.vix_date || '—'}.` : '');
  } else if (sourceMixed) {
    statusLabel = 'MIXED SOURCES'; statusTone = AMBER;
    statusDetail = `Reading from ${data.data_date || '—'} is current, but the ranking window still mixes `
      + `${f.window_captured} live captures with ${f.window_seeded} baseline sessions.`;
  } else {
    statusLabel = 'CURRENT'; statusTone = GREEN;
    statusDetail = `Reading from ${data.data_date || '—'}, taken at the 15:05 CT close.`;
  }
  const nextCapture = (() => {
    const nxt = data.jobs?.scheduler?.jobs?.gamma_capture;
    if (!nxt) return null;
    const d = new Date(nxt);
    if (isNaN(d)) return null;
    return d.toLocaleString('en-US', {
      weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' });
  })();

  // ── THE CALL. Headline + the real ticket. The page never tells the bots
  // what to do — SKIP THE PUT SPREAD is this signal's own advisory verdict,
  // and the blocked state says the reading is unusable, not that there is no
  // trade.
  const TODAY_ACCENT = { SELL_PREMIUM: GREEN, NEUTRAL: GREEN, SQUEEZE_WATCH: AMBER, NO_SELL: RED };
  const todayAccent = blocked ? RED : (TODAY_ACCENT[verdict] || GREY);
  const TODAY_ACTION = {
    SELL_PREMIUM: 'SELL THE PUT SPREAD', NEUTRAL: 'SELL THE PUT SPREAD',
    SQUEEZE_WATCH: 'STAND DOWN FROM SELLING', NO_SELL: 'SKIP THE PUT SPREAD',
  };
  const todayHeadline = blocked ? 'NO USABLE READING' : (TODAY_ACTION[verdict] || 'NOTHING TO ACT ON HERE');

  let ticket = null;
  if (!blocked) {
    if (verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL') {
      // Real strikes, not the rule. Falls back to the formula only if spot is
      // unavailable -- an invented strike is worse than an honest formula.
      ticket = data.ticket?.sell ? (
        <>
          <b style={{ color: GREEN }}>SELL {data.ticket.sell.short_put} PUT</b>
          {' / '}
          <b style={{ color: GREEN }}>BUY {data.ticket.sell.long_put} PUT</b>
          {` · SPY 0DTE · $${data.ticket.sell.width} wide · enter 10:05 CT · hold to settlement · no stop`}
        </>
      ) : 'SPY 0DTE put spread · short strike round(spot) − 2 · $2 wide · enter 10:05 CT · hold to settlement · no stop';
    } else if (verdict === 'SQUEEZE_WATCH') {
      ticket = (
        <>
          Do not sell premium today. Optional long-convexity: buy a SPY call at 0.25 delta, 5–9
          DTE, hold 5 sessions (~$190/contract).{' '}
          <b style={{ color: RED }}>Must be 0.25 delta, NOT at-the-money.</b>
        </>
      );
    } else if (verdict === 'NO_SELL') {
      ticket = 'Skip the put spread entirely. Net gamma is below −$10B.';
    }
  }

  const whyValue = data.gamma_pct != null
    ? `gamma ${pct(data.gamma_pct)} — ${PROXIMITY_LABEL[outlookTop.proximity] || '—'}`
      + (data.vix_ratio != null ? ` · VIX ratio ${data.vix_ratio.toFixed(2)}` : '')
    : '—';

  let riskValue = '—';
  if (!blocked) {
    if (verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL') riskValue = 'worst day −$198 · 20% of a $1,000 account';
    else if (verdict === 'SQUEEZE_WATCH') riskValue = '~$190/contract, wins ~1 in 3';
    else if (verdict === 'NO_SELL') riskValue = 'nothing at risk — no position';
  }

  // How often a day in this regime cell moved more than 1% — measured, not
  // the verdict. Absent from older payloads; the line simply does not render.
  const breakP = data.break_prob;
  const breakWords = BREAK_CELL_WORDS[data.break_cell];
  const breakN = oneIn(breakP);

  // ── NEXT-SESSION SCORECARD (inside the fold). Built from the sliced
  // signal_history rows and their `fwd1_pct` — what SPY's close did the next
  // session, from sw_spy_daily's own closes. Rows without a next close are
  // left out of every average, never counted as zero.
  const sh = inRange(data.signal_history);
  const fwdByVerdict = {};
  sh.forEach((r) => {
    const g = fwdByVerdict[r.verdict] || (fwdByVerdict[r.verdict] = { n: 0, withFwd: 0, sum: 0, up: 0, worst: null, best: null });
    g.n += 1;
    if (r.fwd1_pct == null) return;
    g.withFwd += 1;
    g.sum += r.fwd1_pct;
    if (r.fwd1_pct > 0) g.up += 1;
    if (g.worst == null || r.fwd1_pct < g.worst) g.worst = r.fwd1_pct;
    if (g.best == null || r.fwd1_pct > g.best) g.best = r.fwd1_pct;
  });
  const fwdCov = data.fwd_coverage || null;
  const fwdKnown = sh.some((r) => r.fwd1_pct != null);

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>Squeeze</h1>
        <p style={S.sub}>
          Dealer gamma rank plus VIX at its highs — a veto for short premium and a prerequisite for a
          squeeze, never a direction call. Advisory only; no bot reads this.
        </p>

        {/* ── 1. STATUS ROW. Is this reading usable, how old is it, when does
            it next change. Derived from the payload's own freshness block,
            never the browser clock. Always rendered, including when fine —
            a quiet check and a missing one must not look the same. */}
        <div style={{
          ...S.card, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          borderColor: `${statusTone}55`, background: `${statusTone}0d`, marginBottom: 12,
        }}>
          <Radio size={15} color={statusTone} />
          <Pill text={statusLabel} color={statusTone} solid={statusTone === RED} />
          <span style={{ fontSize: 13, color: statusTone === RED ? '#e6e9f0' : '#c6cbd8' }}>
            {statusDetail}
          </span>
          <span style={{ ...S.small, ...S.mono, marginLeft: 'auto', textAlign: 'right' }}>
            {f.captured_sessions != null && f.window_sessions != null
              && `${f.captured_sessions} of ${f.window_sessions} sessions from a live capture · `}
            {nextCapture ? `next reading ${nextCapture} CT` : 'next reading not scheduled'}
            {loadedAt && ` · page loaded ${loadedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
          </span>
        </div>

        {/* ── 2. THE CALL. Answers "what do I do today" with the actual ticket
            parameters, not a state label. Blocking beats the verdict. */}
        <div style={{ ...S.card, borderColor: todayAccent + '66', background: `${todayAccent}0d` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <Zap size={26} color={todayAccent} style={{ flexShrink: 0 }} />
            <div style={{ fontSize: 24, fontWeight: 700, color: todayAccent, letterSpacing: '-.01em' }}>{todayHeadline}</div>
            <div style={{ ...S.small, marginLeft: 4 }}>
              {VERDICT_LABEL[verdict] || verdict}{data.data_date ? ` · from ${data.data_date}` : ''}
            </div>
          </div>

          {blocked && (
            <div style={{ fontSize: 14, color: '#e6e9f0', marginTop: 8, lineHeight: 1.55, maxWidth: '70ch' }}>
              {blockedReason}{' '}
              <span style={{ color: DIM }}>
                Don’t act on this page today. The bots trade on their own schedule; the Risk page
                has today’s tickets.
              </span>
            </div>
          )}
          {blockedDetail && (
            <div style={{ ...S.small, ...S.mono, marginTop: 4, wordBreak: 'break-word' }}>
              {blockedDetail}
            </div>
          )}

          {ticket && (
            <div style={{
              fontSize: 14, color: '#e6e9f2', background: '#0e1220', border: '1px solid #232a3d',
              borderRadius: 10, padding: '12px 14px', marginTop: 12, wordBreak: 'break-word',
            }}>
              {ticket}
            </div>
          )}
          {!blocked && data.ticket?.sell && (verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL') && (
            /* Which spot the strikes came from, and when they stop being
               true. The entry is 10:05 CT and the real strike derives from
               spot at that moment; anything computed off the prior close is
               indicative and has to say so. */
            <div style={{ ...S.small, marginTop: 6 }}>
              Strikes from spot {data.ticket.spot} ({data.ticket.spot_source})
              {data.ticket.spot_source !== 'live' &&
                ' — indicative. Re-derive from spot at 10:05 CT before sending.'}
            </div>
          )}

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
            <div>
              <div style={S.small}>WHY</div>
              <div style={{ fontSize: 13.5 }}>{whyValue}</div>
            </div>
            <div>
              <div style={S.small}>RISK</div>
              <div style={{ fontSize: 13.5 }}>{riskValue}</div>
            </div>
            <div>
              <div style={S.small}>SIZE</div>
              <div style={{ fontSize: 13.5 }}>about $5,000 to run both sides; below that, one side only</div>
            </div>
          </div>

          {/* Measured, not asserted: how often a day in this regime cell has
              moved more than 1%. The one number that turns "short gamma" from
              a label into a size decision. */}
          {breakP != null && breakWords && (
            <div style={{ fontSize: 13.5, color: '#c6cbd8', marginTop: 12, lineHeight: 1.55, maxWidth: '70ch' }}>
              On days like this — <b style={{ color: '#e6e9f0' }}>{breakWords}</b> — SPY has moved more
              than 1% about <b style={{ color: '#e6e9f0' }}>1 day in {breakN}</b> ({pct(breakP)}
              {data.break_sample ? `, ${data.break_sample}` : ''}).
            </div>
          )}

          <p style={{ ...S.small, margin: '10px 0 0' }}>
            Advisory — this page moves nothing, and no bot reads it. Neither trade has been
            forward-tested.
          </p>
        </div>

        {/* ── 3. THE LINE. Net dealer gamma with the two trigger levels named
            in plain words. One control (the range) for this chart and
            everything inside the fold. */}
        <div style={S.card}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ ...S.cardTitle, marginBottom: 0 }}>Net dealer gamma — last {rangeLabel}</span>
            <span style={{ marginLeft: 'auto' }}><RangePicker /></span>
          </div>
          {/* Fed the SIGNAL series' own last row — see ChartMeta's note on
              why the top-level state fields are the wrong source. */}
          <ChartMeta {...gammaChartMeta(data, hist.length ? hist[hist.length - 1] : null)} />
          {hist.length ? (() => {
            const chartOutlook = data.outlook || {};
            return (
              <>
                <div style={{ width: '100%', height: 260, overflowX: 'auto', minWidth: 0 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                      {oversoldBands.map(([a, b], i) => (
                        <ReferenceArea key={`os-${i}`} x1={a} x2={b} fill={AMBER} fillOpacity={0.08} />
                      ))}
                      {overboughtBands.map(([a, b], i) => (
                        <ReferenceArea key={`ob-${i}`} x1={a} x2={b} fill={GREEN} fillOpacity={0.08} />
                      ))}
                      <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                      <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#5b6478' }} tickFormatter={v => `${v.toFixed(0)}B`} />
                      <YAxis yAxisId="price" orientation="right" tick={{ fontSize: 11, fill: '#5b6478' }}
                             domain={['dataMin - 5', 'dataMax + 5']} tickFormatter={v => `$${v.toFixed(0)}`} />
                      <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 13 }}
                               /* Recharts hands the formatter the series' `name` PROP, not its
                                  dataKey — match on the NAME. SPY's close shares this tooltip and
                                  a blanket $bn suffix rendered it as "$770.56B". */
                               formatter={(v, name) => {
                                 const num = Number(v);
                                 if (!Number.isFinite(num)) return ['—', name];
                                 return [name === PRICE_SERIES ? `$${num.toFixed(2)}`
                                                               : `$${num.toFixed(2)}B`, name];
                               }} />
                      <Legend
                        /* Recharts writes an absolute pixel width onto the legend
                           wrapper from its first measurement; width:100% overrides
                           it so the legend tracks the container on a phone. */
                        wrapperStyle={{ fontSize: 13, width: '100%' }}
                        formatter={v => <span style={{ color: '#8b93a7' }}>{v}</span>} />
                      <ReferenceLine yAxisId="left" y={0} stroke="#232a3d" />
                      {chartOutlook.oversold_trigger_b != null && (
                        <ReferenceLine yAxisId="left" y={chartOutlook.oversold_trigger_b} stroke={AMBER} strokeDasharray="3 3"
                                       label={{ value: `squeeze zone starts ${signedBn(chartOutlook.oversold_trigger_b)}`, position: 'insideBottomRight', fill: AMBER, fontSize: 11 }} />
                      )}
                      {chartOutlook.overbought_trigger_b != null && (
                        <ReferenceLine yAxisId="left" y={chartOutlook.overbought_trigger_b} stroke={GREEN} strokeDasharray="3 3"
                                       label={{ value: `safe-to-sell zone starts ${signedBn(chartOutlook.overbought_trigger_b)}`, position: 'insideTopRight', fill: GREEN, fontSize: 11 }} />
                      )}
                      <Line yAxisId="left" dataKey="net_gex_b" name="net gamma ($B)" stroke="#60a5fa" dot={false} strokeWidth={1.8} />
                      {/* Warm grey, NOT slate — slate reads as a second blue line
                          next to the gamma series. */}
                      <Line yAxisId="price" dataKey="spot" name={PRICE_SERIES} stroke="#d6d3d1" dot={false} strokeWidth={1.2} />
                      {liveOk && (
                        <Line yAxisId="left" dataKey="live_gex_b" name="live (not the signal)" stroke={LIVE} strokeWidth={1.8}
                              strokeDasharray="4 4" dot={<LiveDot />} isAnimationActive={false} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6 }}>
                  The <b style={{ color: '#60a5fa' }}>blue line</b> is net dealer gamma at the 15:05 CT close.
                  Below the <b style={{ color: AMBER }}>dashed amber line</b> ({signedBn(chartOutlook.oversold_trigger_b)})
                  gamma is in the lowest fifth of its last 60 sessions — the squeeze zone, where every SPY
                  squeeze since 2020 began. Above the <b style={{ color: GREEN }}>dashed green line</b>{' '}
                  ({signedBn(chartOutlook.overbought_trigger_b)}) it is in the highest fifth — the safest state to
                  sell premium into. The <b style={{ color: '#d6d3d1' }}>pale line</b> is SPY’s price, for context.
                  {liveOk && (
                    <> The <b style={{ color: LIVE }}>purple point</b> is this minute’s reading — context, not the signal.</>
                  )}
                </div>
              </>
            );
          })() : <div style={S.small}>no history yet — needs the 15:05 CT capture job to run and 60 sessions before the percentile is defined</div>}
        </div>

        {/* ── 4. ONE FOLD, everything else. Collapsed by default — the three
            sections above are the page; this is the proof underneath it.
            Order inside: call history first (the closest thing to a
            scorecard), then what SPY did after each verdict, the live
            record, and the rest in the order it always rendered in. */}
        <Fold title="How this signal has done" persistKey="sw_squeeze_history_fold_open"
              meta={`last ${rangeLabel} · ${sh.length} sessions`}>

          <CallHistory surface="squeeze" title="Squeeze call history" />

          {/* NEXT-SESSION SCORECARD — what SPY's close did the session after
              each verdict, read from sw_spy_daily's own closes (never the
              ORAT forward mark). Averages skip sessions with no next close. */}
          <div style={S.card}>
            <div style={S.cardTitle}>What SPY did the next session — last {rangeLabel}</div>
            {!fwdKnown ? (
              <div style={S.small}>
                {fwdCov?.reason
                  ? `Next-session moves unavailable: ${fwdCov.reason}`
                  : 'Next-session moves are not in this build of the API yet. Every other number below is unaffected.'}
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                  {VERDICT_ORDER.filter((v) => fwdByVerdict[v]).map((v) => {
                    const g = fwdByVerdict[v];
                    const avg = g.withFwd ? g.sum / g.withFwd : null;
                    const c = VERDICT_COLOR[v] || GREY;
                    return (
                      <div key={v} style={{ ...S.tile, borderColor: `${c}44` }}>
                        <div style={{ ...S.tileLabel, color: c, fontWeight: 700 }}>after {VERDICT_LABEL[v] || v}</div>
                        <div style={{ fontSize: 20, fontWeight: 700, color: avg == null ? DIM : avg >= 0 ? GREEN : RED }}>
                          {avg == null ? '—' : signedPct(avg)}
                        </div>
                        <div style={S.small}>
                          {g.withFwd
                            ? `average next day · up ${g.up} of ${g.withFwd} · worst ${signedPct(g.worst)} · best ${signedPct(g.best)}`
                            : `${g.n} session${g.n === 1 ? '' : 's'}, no next close on file yet`}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div style={S.small}>
                  {fwdCov && (
                    <>{fwdCov.sessions_with_fwd} of {fwdCov.sessions_total} fetched sessions have a next-session close on
                    file{fwdCov.first_date ? ` (${fwdCov.first_date} → ${fwdCov.last_date})` : ''}. </>
                  )}
                  Missing sessions are left blank, never counted as zero. A next-day average is a description of
                  what followed, not a forecast — SQUEEZE WATCH is a stand-down, and its average being positive is
                  the reason for it.
                </div>
              </>
            )}
          </div>

          {/* SIGNAL TRACK RECORD — one cell per session, coloured by verdict.
              Summarised from the SLICED rows, not data.signal_summary: a
              track record has to describe the window you are looking at. */}
          {(() => {
            const counts = {};
            sh.forEach(r => { counts[r.verdict] = (counts[r.verdict] || 0) + 1; });
            const n = sh.length;
            const lastWith = (v) => {
              for (let i = sh.length - 1; i >= 0; i--) if (sh[i].verdict === v) return sh[i].trade_date;
              return null;
            };
            const current = n ? sh[n - 1].verdict : null;
            let run = 0;
            for (let i = sh.length - 1; i >= 0 && sh[i].verdict === current; i--) run++;
            return (
              <div style={S.card}>
                <div style={S.cardTitle}>What this signal has printed — last {rangeLabel}</div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>current state</div>
                    <div style={{ fontSize: 17, fontWeight: 700, color: VERDICT_COLOR[current] || GREY }}>
                      {VERDICT_LABEL[current] || current || '—'}
                    </div>
                    <div style={S.small}>{n ? `${run} session${run === 1 ? '' : 's'}` : '—'}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>last SQUEEZE WATCH</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>{lastWith('SQUEEZE_WATCH') || `none in ${rangeLabel}`}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>last NO SELL</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>{lastWith('NO_SELL') || `none in ${rangeLabel}`}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>window</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>
                      {n} sessions{n ? `, ${sh[0].trade_date} → ${sh[n - 1].trade_date}` : ''}
                    </div>
                  </div>
                </div>

                {sh.length ? (
                  <div style={{ display: 'flex', height: 22, borderRadius: 6, overflow: 'hidden', marginBottom: 8 }}>
                    {sh.map((s, i) => (
                      <div key={i}
                           title={`${s.trade_date} — ${s.verdict} · pct ${pct(s.pct)} · gamma ${bn(s.net_gex_b)} · VIX ratio ${s.vix_ratio == null ? '—' : s.vix_ratio.toFixed(2)}`
                             + (s.fwd1_pct != null ? ` · next session ${signedPct(s.fwd1_pct)}` : '')}
                           style={{ flex: '1 1 0', background: SIGNAL_STRIP_COLOR[s.verdict] || GREY }} />
                    ))}
                  </div>
                ) : <div style={S.small}>no signal history yet</div>}

                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
                  {Object.entries(counts).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: DIM }}>
                      <span style={{ width: 10, height: 10, borderRadius: 3, background: SIGNAL_STRIP_COLOR[k] || GREY, display: 'inline-block' }} />
                      {VERDICT_LABEL[k] || k} · {v} ({n ? (100 * v / n).toFixed(1) : '0.0'}%)
                    </div>
                  ))}
                </div>

                <div style={S.small}>
                  Each session is labelled with the verdict its own 15:05 CT close produced — the verdict
                  that was actionable the NEXT morning, which is how the alert consumes it.
                </div>
              </div>
            );
          })()}

          {/* LIVE RECORD — the only numbers on this page that are not a
              backtest. A live sample, however small, outranks a 898-trade
              backtest when the question is "is this working NOW". */}
          {(() => {
            const L = data.ledger || {};
            const n = L.n_settled || 0;
            const wr = L.win_rate;
            const bt = L.backtest_win_rate;
            const off = (wr != null && bt != null) ? (wr - bt) : null;
            return (
              <div style={S.card}>
                <div style={S.cardTitle}>Live record since the signal shipped</div>
                {L.reason && <div style={{ ...S.small, marginBottom: 8 }}>{L.reason}</div>}
                {n === 0 ? (
                  <div style={{ fontSize: 13, color: '#c6cbd8' }}>
                    No settled sessions yet. The first decision is recorded at the 08:05 CT
                    alert and settles at that session's close.
                    <div style={{ ...S.caption, marginTop: 6 }}>
                      Until this fills, every number on this page is a backtest.
                    </div>
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                      <div style={S.tile}>
                        <div style={S.tileLabel}>live win rate</div>
                        <div style={S.tileValue}>{pct(wr)}</div>
                        <div style={S.small}>{L.wins}/{n} settled</div>
                      </div>
                      <div style={S.tile}>
                        <div style={S.tileLabel}>backtest claim</div>
                        <div style={S.tileValue}>{pct(bt)}</div>
                        <div style={S.small}>over {L.backtest_n} trades</div>
                      </div>
                      <div style={S.tile}>
                        <div style={S.tileLabel}>difference</div>
                        <div style={{ ...S.tileValue,
                                      color: off == null ? GREY : off < -0.10 ? RED : GREEN }}>
                          {off == null ? '—' : `${off >= 0 ? '+' : ''}${(off * 100).toFixed(1)}pts`}
                        </div>
                        <div style={S.small}>live vs backtest</div>
                      </div>
                      <div style={S.tile}>
                        <div style={S.tileLabel}>worst breach</div>
                        <div style={S.tileValue}>
                          {L.worst_breach == null ? '—' : `$${Number(L.worst_breach).toFixed(2)}`}
                        </div>
                        <div style={S.small}>of $2 max</div>
                      </div>
                    </div>
                    <div style={S.small}>
                      {L.n_decisions} decision(s) recorded, {L.n_traded} traded,
                      {' '}{L.n_decisions - L.n_traded} stood down
                      {L.first_date ? `, ${L.first_date} → ${L.last_date}` : ''}.
                      {n < 30 && ' A sample this small cannot confirm or refute the backtest yet.'}
                    </div>
                  </>
                )}
                {L.n_priced > 0 && (
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4,
                                marginBottom: 10 }}>
                    <div style={S.tile}>
                      <div style={S.tileLabel}>live $/trade</div>
                      <div style={{ ...S.tileValue,
                                    color: (L.pnl_per_trade ?? 0) >= 0 ? GREEN : RED }}>
                        {L.pnl_per_trade == null ? '—' : `$${L.pnl_per_trade.toFixed(2)}`}
                      </div>
                      <div style={S.small}>backtest ${L.backtest_per_trade}</div>
                    </div>
                    <div style={S.tile}>
                      <div style={S.tileLabel}>live total</div>
                      <div style={{ ...S.tileValue,
                                    color: (L.pnl_total ?? 0) >= 0 ? GREEN : RED }}>
                        {L.pnl_total == null ? '—' : `$${L.pnl_total.toFixed(2)}`}
                      </div>
                      <div style={S.small}>{L.n_priced} priced entr{L.n_priced === 1 ? 'y' : 'ies'}</div>
                    </div>
                    <div style={S.tile}>
                      <div style={S.tileLabel}>worst day</div>
                      <div style={{ ...S.tileValue, color: RED }}>
                        {L.worst_day == null ? '—' : `$${L.worst_day.toFixed(2)}`}
                      </div>
                      <div style={S.small}>backtest −$198</div>
                    </div>
                  </div>
                )}
                <div style={{ ...S.caption, marginTop: 8 }}>
                  Dollars come from the 10:05 CT entry quote, crossing the spread the way the
                  backtest measured it — short sold at the bid, long bought at the ask. Mid-to-mid
                  would flatter every entry by exactly what a real order gives up.
                  {L.n_settled > L.n_priced && (
                    <> <b style={{ color: AMBER }}>{L.n_settled - L.n_priced} settled session(s)
                    could not be priced</b> and are excluded from the dollar figures — an assumed
                    credit would turn "not measured" into a number you could average.</>
                  )}
                </div>
              </div>
            );
          })()}

          <TapeShape data={tape} />

          {/* WHAT TO WATCH — trigger levels, which leg is missing, fuel, pin,
              calendar. Built from the 15:05 capture; the live recompute is
              shown beside it, never instead of it. */}
          {(() => {
            const outlook = data.outlook || {};
            const legs = outlook.legs || {};
            const cal = outlook.calendar || {};
            const pColor = PROXIMITY_COLOR[outlook.proximity] || GREY;
            const gammaPctNow = data.gamma_pct != null ? Math.min(100, Math.max(0, data.gamma_pct * 100)) : null;
            const fuelPct = outlook.fuel != null ? Math.abs(outlook.fuel) * 100 : null;
            const fuelTopDecile = fuelPct != null && Math.abs(outlook.fuel) >= FUEL_TOP_DECILE;

            if (outlook.reason) {
              return (
                <div style={{ ...S.card, opacity: 0.6 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                    <span style={S.cardTitle}>What to watch</span>
                    <span style={{ ...S.small, marginLeft: 'auto' }}>official reading: 15:05 CT capture</span>
                  </div>
                  <div style={{ fontSize: 13.5, color: '#c6cbd8' }}>Outlook unavailable</div>
                  <div style={{ ...S.small, marginTop: 6 }}>{outlook.reason}</div>
                </div>
              );
            }

            return (
              <div style={S.card}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <span style={S.cardTitle}>What to watch</span>
                  <span style={{ ...S.small, marginLeft: 'auto' }}>official reading: 15:05 CT capture</span>
                </div>

                {outlook.proximity && (
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: pColor, marginBottom: 4 }}>
                    {PROXIMITY_LABEL[outlook.proximity] || outlook.proximity}
                    <InfoTip text="Which zone the percentile is in. OVERSOLD is the squeeze prerequisite; OVERBOUGHT is the safest measured state to sell into." />
                  </div>
                )}
                {outlook.proximity && (
                  <div style={{ fontSize: 13, color: '#c6cbd8', marginBottom: 12 }}>
                    {PROXIMITY_COPY[outlook.proximity] || ''}
                  </div>
                )}

                {/* Live recompute — same maths, this minute's gamma. */}
                {(() => {
                  const lo = intraday?.live_outlook;
                  if (!lo || !lo.proximity) return null;
                  const same = lo.proximity === outlook.proximity;
                  const c = PROXIMITY_COLOR[lo.proximity] || GREY;
                  return (
                    <div style={{
                      padding: '9px 11px', borderRadius: 8, marginBottom: 12,
                      background: '#0e1220',
                      border: `1px solid ${same ? '#1c2233' : `${AMBER}55`}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ ...S.small, letterSpacing: '.05em', textTransform: 'uppercase' }}>
                          right now
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: c }}>
                          {PROXIMITY_LABEL[lo.proximity] || lo.proximity}
                        </span>
                        {!same && (
                          <span style={{ fontSize: 13, fontWeight: 700, color: AMBER }}>
                            ≠ the 15:05 reading
                          </span>
                        )}
                        <span style={{ ...S.small, marginLeft: 'auto' }}>
                          recomputed every 60s from the live chain
                        </span>
                      </div>
                      <div style={{ ...S.small, marginTop: 3, lineHeight: 1.5 }}>
                        {lo.gap_to_oversold_b != null && (
                          <>gamma {signedBn(intraday.net_gex_b)} ·{' '}
                          {lo.gap_to_oversold_b <= 0
                            ? <b style={{ color: AMBER }}>already through the oversold trigger</b>
                            : <>{bn(lo.gap_to_oversold_b)} from oversold</>}</>
                        )}
                        {lo.legs?.vix_ratio != null && (
                          <> · VIX ratio {lo.legs.vix_ratio.toFixed(2)}
                          {lo.legs.vix_at_highs
                            ? <b style={{ color: AMBER }}> — at its highs</b>
                            : <> ({(0.95 - lo.legs.vix_ratio).toFixed(2)} short of 0.95)</>}</>
                        )}
                      </div>
                      <div style={{ ...S.small, marginTop: 3 }}>
                        Advisory. The verdict above is still the 15:05 capture — this is
                        where the levels sit this minute, not a new call.
                      </div>
                    </div>
                  );
                })()}

                {/* 1 — how close are we */}
                <div style={{ ...S.small, marginBottom: 4 }}>
                  How close are we — gamma percentile
                  <InfoTip text="Where net dealer gamma sits within its own trailing 60 sessions. The rank is a much stronger signal than the level: a −$4B print can be oversold in a calm month and unremarkable in a volatile one." />
                </div>
                <div style={{ position: 'relative', height: 24, background: '#0e1220', border: '1px solid #232a3d', borderRadius: 6 }}>
                  <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '20%', background: AMBER, opacity: 0.18 }} />
                  <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '20%', background: GREEN, opacity: 0.18 }} />
                  {gammaPctNow != null && (
                    <div style={{ position: 'absolute', left: `calc(${gammaPctNow.toFixed(1)}% - 1px)`, top: -3, bottom: -3, width: 2, background: '#e6e9f2' }} />
                  )}
                </div>
                {/* The moving "current" label gets its OWN row under the bar and
                    the two fixed trigger labels the row below it — sharing a row
                    put "current 86.7%" straight through the overbought label
                    exactly when the reading was interesting. */}
                <div style={{ position: 'relative', marginTop: 4, height: 18, overflow: 'hidden' }}>
                  {gammaPctNow != null && (
                    <span style={{
                      ...S.small, color: '#c6cbd8', position: 'absolute',
                      left: `${Math.min(92, Math.max(8, gammaPctNow)).toFixed(1)}%`,
                      transform: 'translateX(-50%)', whiteSpace: 'nowrap',
                    }}>
                      current {pct(data.gamma_pct)}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <span style={S.small}>oversold ≤ {signedBn(outlook.oversold_trigger_b)}</span>
                  <span style={S.small}>overbought ≥ {signedBn(outlook.overbought_trigger_b)}</span>
                </div>
                {outlook.pct_trend_5d != null && (() => {
                  const falling = outlook.pct_trend_5d < 0;
                  const nearOversold = outlook.proximity === 'OVERSOLD' || outlook.proximity === 'APPROACHING_OVERSOLD';
                  const nearOverbought = outlook.proximity === 'OVERBOUGHT' || outlook.proximity === 'APPROACHING_OVERBOUGHT';
                  const showDestination = falling ? nearOversold : nearOverbought;
                  return (
                    <div style={{ ...S.small, marginBottom: 12 }}>
                      percentile {falling ? 'falling' : 'rising'} {Math.abs(outlook.pct_trend_5d * 100).toFixed(1)}pts over 5 sessions
                      {showDestination && (falling ? ' — moving toward the squeeze zone' : ' — moving away from the squeeze zone')}
                    </div>
                  );
                })()}

                {/* 2 — what would have to happen */}
                <div style={{ ...S.small, marginBottom: 4 }}>What would have to happen</div>
                <div style={{ fontSize: 13, marginBottom: 4 }}>
                  {outlook.gap_to_oversold_b == null || outlook.oversold_trigger_b == null ? '—'
                    : outlook.gap_to_oversold_b > 0
                      ? <>Squeeze trigger — gamma must fall to <b>{signedBn(outlook.oversold_trigger_b)}</b> ({bn(outlook.gap_to_oversold_b)} away)</>
                      : <>Squeeze trigger — already through {signedBn(outlook.oversold_trigger_b)} (gamma at {bn(data.net_gex_b)})</>}
                </div>
                <div style={{ fontSize: 13, marginBottom: 12 }}>
                  {outlook.gap_to_overbought_b == null || outlook.overbought_trigger_b == null ? '—'
                    : outlook.gap_to_overbought_b > 0
                      ? <>Overbought trigger — gamma must rise to <b>{signedBn(outlook.overbought_trigger_b)}</b> ({bn(outlook.gap_to_overbought_b)} away)</>
                      : <>Overbought trigger — already through {signedBn(outlook.overbought_trigger_b)} (gamma at {bn(data.net_gex_b)})</>}
                </div>

                {/* 3 — which leg is missing */}
                <div style={{ ...S.small, marginBottom: 4 }}>Which leg is missing — SQUEEZE WATCH needs both</div>
                {[
                  { ok: legs.gamma_oversold, label: 'Gamma oversold (≤ 20th percentile)' },
                  { ok: legs.vix_at_highs, label: 'VIX at highs (ratio ≥ 0.95)',
                    sub: legs.vix_at_highs === false && legs.vix_ratio != null && legs.vix_gap != null
                      ? `VIX ratio ${legs.vix_ratio.toFixed(2)} — needs to rise ${legs.vix_gap.toFixed(2)} to clear 0.95`
                      : null },
                ].map((row, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: i === 0 ? 0 : 6 }}>
                    <span style={{ fontWeight: 700, color: row.ok == null ? GREY : row.ok ? GREEN : RED, width: 14, flexShrink: 0 }}>
                      {row.ok == null ? '−' : row.ok ? '✓' : '✗'}
                    </span>
                    <div>
                      <div style={{ fontSize: 13 }}>{row.label}</div>
                      {row.sub && <div style={{ ...S.small, color: AMBER, marginTop: 2 }}>{row.sub}</div>}
                    </div>
                  </div>
                ))}

                {/* 4 — fuel: forced dealer hedging vs a normal day's volume */}
                <div style={{ ...S.small, marginTop: 16, marginBottom: 4 }}>
                  Fuel — forced hedging vs a normal day's volume
                  <InfoTip text="Forced dealer hedging per 1% move, as a share of a normal day's dollar volume. net_gex is literally dollars-per-1%-move, so its size against SPY's own liquidity says whether dealer flow can dominate the tape. Median 9.4%; top sextile 17.5–56.8%." />
                </div>
                <div style={{ fontSize: 13, marginBottom: 12 }}>
                  {fuelPct == null ? (
                    <>
                      <span>—</span>
                      {outlook.fuel_reason && <span style={S.small}> ({outlook.fuel_reason})</span>}
                    </>
                  ) : (
                    <>
                      <b style={{ color: fuelTopDecile ? AMBER : '#c6cbd8' }}>{fuelPct.toFixed(1)}%</b>
                      {' '}— dealers must trade {fuelPct.toFixed(1)}% of a normal day's volume per 1% move,
                      {outlook.fuel > 0 ? ' an accelerant (short gamma)' : ' a dampener (long gamma)'}
                      {fuelTopDecile && <span style={{ color: AMBER, fontWeight: 700 }}> · top decile</span>}
                      {outlook.adv_b != null && <span style={S.small}> · {bn(outlook.adv_b)}/day avg volume</span>}
                    </>
                  )}
                </div>

                {/* 5 — pin strength */}
                <div style={{ ...S.small, marginBottom: 4 }}>
                  Pin strength
                  <InfoTip text="How hard dealer hedging is damping the tape, read off the same percentile as the verdict. Higher means more pinning. Zero squeezes have ever started in the top quartile." />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <span style={{ fontWeight: 700, fontSize: 13, color: PIN_COLOR[outlook.pin_strength] || GREY }}>
                    {PIN_LABEL[outlook.pin_strength] || '—'}
                  </span>
                  <span style={S.small}>{PIN_COPY[outlook.pin_strength] || ''}</span>
                </div>

                {/* 6 — calendar strip: only flags that are actually true render. */}
                <div style={{ ...S.small, marginBottom: 4 }}>Scheduled flow today</div>
                {(() => {
                  const activeFlags = CALENDAR_FLAGS.filter(({ key }) => !!cal[key]);
                  if (!activeFlags.length) {
                    return <div style={{ ...S.small, marginBottom: 4 }}>No scheduled flow today.</div>;
                  }
                  return (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                      {activeFlags.map(({ key, label, tone }) => {
                        const color = tone === 'supportive' ? AMBER : GREEN;
                        return (
                          <span key={key} style={{
                            fontSize: 13, fontWeight: 700, padding: '3px 8px', borderRadius: 999,
                            background: color + '22',
                            border: `1px solid ${color}66`,
                            color,
                          }}>
                            {label}
                          </span>
                        );
                      })}
                    </div>
                  );
                })()}
                {cal.month_end && (
                  <div style={S.small}>
                    Month end raises squeeze odds 2.52x on oversold days — but was 0-for-9 in both
                    2024 and 0-for-9 in 2025. A tilt, never a trigger.
                  </div>
                )}
              </div>
            );
          })()}

          {/* LIVE INTRADAY — context only, never the verdict. */}
          {(() => {
            const iv = intraday || {};
            const stale = !!iv.stale;
            return (
              <div style={{ ...S.card, padding: '10px 14px', opacity: stale ? 0.55 : 1 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                  <span style={{ ...S.cardTitle, marginBottom: 0 }}>Live intraday</span>
                  <ContextTag />
                </div>
                {intradayErr ? (
                  <div style={{ fontSize: 13, color: DIM }}>unavailable: {intradayErr}</div>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 8 }}>
                      <div>
                        <div style={S.small}>net gamma now</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{bn(iv.net_gex_b)}</div>
                      </div>
                      <div>
                        <div style={S.small}>SPY spot (live)</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{iv.spot == null ? '—' : `$${Number(iv.spot).toFixed(2)}`}</div>
                      </div>
                      <div>
                        <div style={S.small}>vs last close ({bn(iv.last_close_b)})</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{signedBn(iv.delta_b)}</div>
                      </div>
                      <div>
                        <div style={S.small}>percentile if this were the close</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{pct(iv.pct_if_now)}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: 13, color: AMBER, lineHeight: 1.5, marginBottom: 8 }}>
                      "vs last close" subtracts a live Tradier chain from an ORATS-derived baseline. Those two
                      paths have not been reconciled — on 2026-08-14 they read $6.30B and $3.50B for the same
                      session while spot matched to the cent. Treat this delta as pipeline difference, not as a
                      move in gamma, until the 15:05 capture has run against both.
                    </div>
                    {stale ? (
                      <div style={{ fontSize: 13, color: DIM }}>
                        Market is closed — no live reading is taken. The figures above resume
                        during market hours; the last stored close is shown for context.
                      </div>
                    ) : (
                      <div style={{ fontSize: 13, color: DIM, lineHeight: 1.5 }}>
                        Sampled at 10:00 CT this lands in a different percentile zone than the close 22% of
                        the time. The signal above uses the 15:05 CT reading and is what has seven years of
                        evidence behind it.
                      </div>
                    )}
                    {iv.reason && iv.reason !== 'market_closed' && (
                      <div style={{ fontSize: 13, color: DIM, marginTop: 4 }}>{iv.reason}</div>
                    )}
                  </>
                )}
              </div>
            );
          })()}

          {/* TODAY'S INTRADAY GAMMA PATH — a SEPARATE chart on purpose. The
              daily chart is one point per session and IS the signal. This is
              a 10-minute path through today and is NOT — an intraday sample
              lands in the wrong percentile zone 21.6% of the time against
              its own close. */}
          {(() => {
            const rows = (ipath?.rows || []).filter((r) => r.net_gex_b != null);
            const today = rows.length ? rows[rows.length - 1].trade_date : null;
            const pts = rows.filter((r) => r.trade_date === today)
              .map((r) => ({ ...r, label: hhmm(r.minute_ct) }));
            return (
              <div style={S.card}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <span style={S.cardTitle}>Gamma through today — every 10 minutes</span>
                  <ContextTag />
                  {pts.length > 0 && (
                    <IntradayCadence count={pts.length}
                                     lastMinute={pts[pts.length - 1].minute_ct} />
                  )}
                </div>
                {pts.length >= 2 ? (
                  (() => {
                    // THE Y-DOMAIN MUST CONTAIN THE TRIGGERS. A bare autoscale
                    // fits the day's wiggle and pushes the oversold line clean
                    // off the chart, so the one number that decides the zone is
                    // invisible exactly when gamma is nowhere near it.
                    const os = data.outlook?.oversold_trigger_b;
                    const ob = data.outlook?.overbought_trigger_b;
                    const gs = pts.map((r) => r.net_gex_b).filter((v) => v != null);
                    const cand = [...gs, os, ob, 0].filter((v) => v != null);
                    const lo = Math.min(...cand), hi = Math.max(...cand);
                    const pad = Math.max(0.4, (hi - lo) * 0.12);
                    const last = pts[pts.length - 1];
                    const first = pts[0];
                    const prior = data.net_gex_b;   // the 15:05 reading in force
                    const dayMove = last?.net_gex_b != null && first?.net_gex_b != null
                      ? last.net_gex_b - first.net_gex_b : null;
                    const spotMove = last?.spot != null && first?.spot != null
                      ? last.spot - first.spot : null;
                    return (
                      <>
                      <div style={{ width: '100%', height: 250, overflowX: 'auto', minWidth: 0 }}>
                        <ResponsiveContainer>
                          <ComposedChart data={pts} margin={{ top: 12, right: 58, left: -8, bottom: 0 }}>
                            {os != null && (
                              <ReferenceArea y1={lo - pad} y2={os} yAxisId="g"
                                             fill={AMBER} fillOpacity={0.09} />
                            )}
                            {ob != null && (
                              <ReferenceArea y1={ob} y2={hi + pad} yAxisId="g"
                                             fill={GREEN} fillOpacity={0.09} />
                            )}
                            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#5b6478' }}
                                   interval="preserveStartEnd" minTickGap={40} />
                            <YAxis yAxisId="g" domain={[lo - pad, hi + pad]}
                                   tick={{ fontSize: 11, fill: '#5b6478' }}
                                   tickFormatter={(v) => `${v.toFixed(0)}B`} />
                            <YAxis yAxisId="px" orientation="right" hide
                                   domain={['dataMin - 0.6', 'dataMax + 0.6']} />
                            <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 13 }}
                                     labelFormatter={(l) => `${l} CT`}
                                     formatter={(v, n) => [n === 'SPY'
                                       ? `$${Number(v).toFixed(2)}`
                                       : `$${Number(v).toFixed(2)}B`, n]} />
                            <ReferenceLine yAxisId="g" y={0} stroke="#232a3d" />
                            {prior != null && (
                              <ReferenceLine yAxisId="g" y={prior} stroke="#8b93a7"
                                             strokeDasharray="2 4"
                                             label={{ value: `15:05 ${signedBn(prior)}`,
                                                      position: 'insideTopLeft',
                                                      fill: '#8b93a7', fontSize: 11 }} />
                            )}
                            {os != null && (
                              <ReferenceLine yAxisId="g" y={os} stroke={AMBER} strokeDasharray="3 3"
                                             label={{ value: `oversold ${signedBn(os)}`,
                                                      position: 'insideBottomLeft',
                                                      fill: AMBER, fontSize: 11 }} />
                            )}
                            {ob != null && ob <= hi + pad && (
                              <ReferenceLine yAxisId="g" y={ob} stroke={GREEN} strokeDasharray="3 3"
                                             label={{ value: `overbought ${signedBn(ob)}`,
                                                      position: 'insideTopLeft',
                                                      fill: GREEN, fontSize: 11 }} />
                            )}
                            <Line yAxisId="px" dataKey="spot" name="SPY" stroke="#d6d3d1"
                                  strokeWidth={1} dot={false} isAnimationActive={false}
                                  connectNulls />
                            <Line yAxisId="g" dataKey="net_gex_b" name="net gamma ($B)"
                                  stroke={LIVE} strokeWidth={2} dot={false}
                                  isAnimationActive={false} connectNulls
                                  label={({ index, x, y }) => (index === pts.length - 1 ? (
                                    <text x={Number(x) + 6} y={Number(y) + 4} fill={LIVE}
                                          fontSize={11} fontWeight={700}>
                                      {signedBn(last.net_gex_b)}
                                    </text>
                                  ) : null)} />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>
                      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 8, fontSize: 13 }}>
                        <span style={{ color: DIM }}>
                          since 08:30 gamma{' '}
                          <b style={{ color: dayMove == null ? DIM : dayMove < 0 ? AMBER : GREEN }}>
                            {dayMove == null ? '—'
                              : `${dayMove < 0 ? '−' : '+'}$${Math.abs(dayMove).toFixed(2)}B`}
                          </b>
                          {spotMove != null && (
                            <> · SPY <b style={{ color: '#c6cbd8' }}>
                              {spotMove < 0 ? '−' : '+'}${Math.abs(spotMove).toFixed(2)}
                            </b></>
                          )}
                        </span>
                        {os != null && last?.net_gex_b != null && (
                          <span style={{ color: DIM }}>
                            {last.net_gex_b <= os
                              ? <b style={{ color: AMBER }}>through the oversold trigger right now</b>
                              : <>still <b style={{ color: '#c6cbd8' }}>
                                  ${(last.net_gex_b - os).toFixed(2)}B
                                </b> above the oversold trigger</>}
                          </span>
                        )}
                      </div>
                      </>
                    );
                  })()
                ) : (
                  <div style={{ ...S.caption, marginTop: 6 }}>
                    {ipath?.reason || 'Nothing recorded yet today — points land every 10 minutes '
                      + 'between 08:30 and 15:00 CT.'}
                  </div>
                )}
                <div style={{ ...S.caption, marginTop: 10 }}>
                  The <b style={{ color: LIVE }}>purple line</b> is net dealer gamma, recomputed from
                  the live chain every 10 minutes. The <b style={{ color: '#d6d3d1' }}>pale
                  line</b> is SPY on a hidden right axis — net gamma measured at spot moves when spot
                  moves, so the two together tell you whether dealers repositioned or price just slid
                  down a fixed curve. The <b style={{ color: '#8b93a7' }}>grey dashed line</b> is the
                  15:05 reading the verdict is currently using.
                  {' '}<b style={{ color: '#c6cbd8' }}>Watch it; do not trade off it</b> — sampled
                  intraday, gamma lands in a different zone than its own close 21.6% of the time.
                </div>
              </div>
            );
          })()}

          {/* VIX LEG CHART */}
          {(() => {
            const vh = inRange(data.vix_history).map(v => ({ ...v, label: v.trade_date.slice(5) }));
            const lastVix = vh.length ? vh[vh.length - 1] : null;
            return (
              <div style={S.card}>
                <div style={S.cardTitle}>
                  The VIX leg — VIX ÷ its own 20-session max
                  <InfoTip text="VIX divided by its own maximum over the previous 20 sessions. It measures where VIX sits in its recent range, not its level, so a flat VIX reads 1.00 by construction." />
                </div>
                <ChartMeta {...vixChartMeta(data, lastVix)} />
                {vh.length ? (
                  <div style={{ width: '100%', height: 200, overflowX: 'auto', minWidth: 0 }}>
                    <ResponsiveContainer>
                      <ComposedChart data={vh} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                        {/* The ratio is NOT capped at 1.0 — a session that sets a new
                            high prints above it, and those are the SQUEEZE_WATCH
                            sessions. */}
                        <YAxis yAxisId="ratio" tick={{ fontSize: 11, fill: '#5b6478' }}
                               domain={[0, (dataMax) => Math.max(1.05, Math.ceil(dataMax * 20) / 20)]}
                               tickFormatter={v => Number(v).toFixed(2)} />
                        <YAxis yAxisId="lvl" orientation="right" tick={{ fontSize: 11, fill: '#5b6478' }}
                               domain={['dataMin - 2', 'dataMax + 2']} tickFormatter={v => Number(v).toFixed(0)} />
                        <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 13 }}
                                 formatter={(v, name) => [Number.isFinite(Number(v)) ? Number(v).toFixed(2) : '—', name]} />
                        <Legend wrapperStyle={{ fontSize: 13, width: '100%' }}
                                formatter={v => <span style={{ color: '#8b93a7' }}>{v}</span>} />
                        <ReferenceLine yAxisId="ratio" y={0.95} stroke={AMBER} strokeDasharray="4 4"
                                       label={{ value: '0.95 — at highs', position: 'insideTopRight', fill: AMBER, fontSize: 11 }} />
                        <ReferenceLine yAxisId="ratio" y={0.90} stroke="#7dd3fc" strokeDasharray="4 4"
                                       label={{ value: '0.90 — EBB gate', position: 'insideBottomRight', fill: '#7dd3fc', fontSize: 11 }} />
                        <Line yAxisId="ratio" dataKey="ratio" name="VIX ratio" stroke="#f0abfc" dot={false} strokeWidth={1.8} connectNulls />
                        <Line yAxisId="lvl" dataKey="vix" name="VIX level" stroke="#64748b" dot={false} strokeWidth={1.1} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : <div style={S.small}>no VIX history yet</div>}
                <div style={{ ...S.caption, marginTop: 8 }}>
                  <b style={{ color: '#f0abfc' }}>The pink line</b> is today’s VIX divided by the highest VIX
                  of the last 20 sessions — 1.00 means today is the most fearful of those 20.{' '}
                  <b style={{ color: '#64748b' }}>The grey line</b> is the plain VIX level, on the right.
                  SQUEEZE WATCH needs the pink line at or above <b style={{ color: AMBER }}>0.95</b> while gamma
                  is oversold. Fading fear is what kills the setup.{' '}
                  <b style={{ color: '#7dd3fc' }}>0.90</b> is the gate EBB uses with real money — a
                  different job on the same number; don’t read one as confirming the other.
                  <br />
                  <span style={{ color: '#7c8599' }}>
                    A flat VIX would read 1.00 by construction. Over 1,598 sessions that is a theoretical
                    hole, not a real one: of 161 firings, 9 came on a flat window and only 4 cleared 0.95
                    without also setting a new 20-session high. Median VIX at a firing is 22.3.
                  </span>
                </div>
                {/* VIX RATIO THROUGH TODAY — the missing leg is the one worth
                    watching live; on a daily chart you find out after the close. */}
                {(() => {
                  const rows = (ipath?.rows || []).filter((r) => r.vix_ratio != null);
                  const day = rows.length ? rows[rows.length - 1].trade_date : null;
                  const pts = rows.filter((r) => r.trade_date === day).map((r) => ({
                    ...r, label: hhmm(r.minute_ct),
                  }));
                  if (pts.length < 2) return null;
                  const last = pts[pts.length - 1];
                  return (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #1c2233' }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 13, fontWeight: 700 }}>
                          The VIX leg through today — every 10 minutes
                        </span>
                        <ContextTag />
                        <span style={S.small}>
                          ratio <b style={{ color: '#c6cbd8' }}>{last.vix_ratio.toFixed(2)}</b>
                          {last.vix ? ` · VIX ${last.vix.toFixed(2)}` : ''}
                        </span>
                        <IntradayCadence count={pts.length} lastMinute={last.minute_ct} />
                      </div>
                      <div style={{ width: '100%', height: 150, overflowX: 'auto', minWidth: 0, marginTop: 6 }}>
                        <ResponsiveContainer>
                          <ComposedChart data={pts} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#5b6478' }}
                                   interval="preserveStartEnd" minTickGap={40} />
                            <YAxis tick={{ fontSize: 11, fill: '#5b6478' }}
                                   domain={[(d) => Math.min(0.6, d), (d) => Math.max(1.0, d)]}
                                   tickFormatter={(v) => v.toFixed(2)} />
                            <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 13 }}
                                     formatter={(v) => [Number(v).toFixed(3), 'VIX ratio']} />
                            <ReferenceLine y={0.95} stroke={AMBER} strokeDasharray="4 4"
                                           label={{ value: '0.95 — squeeze leg', position: 'insideTopRight',
                                                    fill: AMBER, fontSize: 11 }} />
                            <ReferenceLine y={0.90} stroke="#7dd3fc" strokeDasharray="2 4" />
                            <Line dataKey="vix_ratio" name="VIX ratio" stroke="#e879f9"
                                  strokeWidth={1.8} dot={false} isAnimationActive={false} />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>
                      <div style={{ ...S.caption, marginTop: 8 }}>
                        Live VIX divided by its own trailing 20-session max.{' '}
                        <b style={{ color: '#c6cbd8' }}>The denominator excludes today</b> — if it
                        included the live tick, a new high would divide itself and pin the ratio at
                        1.00 exactly when it mattered. The verdict still uses the prior close.
                      </div>
                    </div>
                  );
                })()}
              </div>
            );
          })()}

          {/* DATA AND JOB STATUS */}
          <Fold title="Data and job status"
                meta={`${f.captured_sessions ?? '—'} of ${f.window_sessions ?? '—'} from a live capture`}>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <div>
                <div style={S.small}>gamma data</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {f.gamma_date || '—'}
                  {f.gamma_stale_sessions > 0 && (
                    <span style={{ ...S.small, marginLeft: 6 }}>{f.gamma_stale_sessions} session(s) behind</span>
                  )}
                </div>
              </div>
              <div>
                <div style={S.small}>VIX data</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {f.vix_date || '—'}
                  {f.vix_stale_sessions > 0 && (
                    <span style={{ ...S.small, marginLeft: 6 }}>{f.vix_stale_sessions} session(s) behind</span>
                  )}
                </div>
              </div>
              {JOB_STATUS.map(j => {
                const last = data.jobs?.last?.[j.key];
                return (
                  <div key={j.key}>
                    <div style={S.small}>{j.label}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: last ? undefined : AMBER }}>
                      {last || 'never run'}
                    </div>
                    <div style={S.small}>{j.schedule}</div>
                  </div>
                );
              })}
              <div>
                <div style={S.small}>provenance</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {f.captured_sessions ?? '—'} of {f.window_sessions ?? '—'} sessions from a live capture
                </div>
              </div>
              <div>
                <div style={S.small}>percentile window</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {f.window_sessions ?? '—'}/{f.window_needed ?? '—'} sessions
                  <span style={{ marginLeft: 6, fontSize: 13, color: f.window_complete ? GREEN : AMBER }}>
                    {f.window_complete ? 'no gaps' : 'gaps'}
                  </span>
                </div>
              </div>
            </div>
            {f.captured_sessions === 0 && (
              <div style={{ ...S.small, color: AMBER, marginTop: 8 }}>
                Every reading on this page came from the committed CSV baseline, not a live capture.
              </div>
            )}
            {f.window_complete === false && f.window_missing?.length > 0 && (
              <div style={{ ...S.small, color: AMBER, marginTop: 8 }}>
                Missing from the trailing window: {f.window_missing.slice(0, 6).join(', ')}
                {f.window_missing.length > 6 ? ` +${f.window_missing.length - 6} more` : ''}
              </div>
            )}
            {sourceMixed && (
              <div style={{ ...S.small, color: AMBER, marginTop: 8 }}>
                The ranking window will be all live captures after {f.window_seeded} more sessions;
                until then the verdict stays blocked on this page.
              </div>
            )}
            {data.jobs?.reason && (
              <div style={{ ...S.small, color: GREY, marginTop: 8 }}>{data.jobs.reason}</div>
            )}
            <div style={{ ...S.caption, marginTop: 8 }}>
              The signal updates once per session at 15:05 CT. Sessions with no captured reading leave
              a permanent hole in the 60-session percentile window. The morning alert only fires when
              the verdict is not NEUTRAL — a quiet day is silent by design.
            </div>
          </Fold>

          {/* HOW TO READ THE GAMMA CHART — the long version, moved down from
              under the chart so the chart card stays one screen. */}
          <Fold title="How to read the gamma chart">
            <div style={S.caption}>
              <b style={{ color: '#60a5fa' }}>The blue line — "net gamma ($B)" in the key —</b>{' '}
              is how many billions of dollars of SPY the dealers have to buy or sell to stay
              hedged each time SPY moves 1%.
              <br />
              <b style={{ color: '#60a5fa' }}>Below zero</b>, they trade <i>with</i> the move:
              selling as it falls, buying as it rises. That makes moves bigger.{' '}
              <b style={{ color: '#60a5fa' }}>Above zero</b>, they trade against the move and
              the price gets stuck in a range.
              <br />
              <b style={{ color: AMBER }}>Amber background</b> = gamma is in the lowest 20% of
              the last 60 sessions. Every SPY squeeze since 2020 began in amber.{' '}
              <b style={{ color: GREEN }}>Green background</b> = the highest 20%. No squeeze has
              ever begun there, and it has the smallest downside.
              <br />
              <span style={{ color: '#7c8599' }}>
                The shading follows the <i>ranking</i>, not the number. −$4B can be amber in a
                quiet month and unshaded in a wild one. That is on purpose — where a reading
                sits against recent history has proven a far better signal than the raw number.
              </span>
            </div>
            {(() => {
              // Tallest print in the visible window — a possible 1DTE-expiry
              // artifact worth naming.
              const maxRow = hist.reduce((m, d) => (
                d.net_gex_b != null && (m == null || d.net_gex_b > m.net_gex_b) ? d : m
              ), null);
              return maxRow ? (
                <div style={{ ...S.caption, marginTop: 8 }}>
                  The highest reading in this window is {bn(maxRow.net_gex_b)} on {maxRow.trade_date}. Options
                  that expire within a day carry enormous gamma per contract, so one session with a 1-day
                  expiry on the board can set the top of the range — and push every reading below it down
                  the rankings until that day drops out of the trailing 60.
                </div>
              ) : null;
            })()}
            <div style={{ ...S.caption, marginTop: 8 }}>
              This number is worked out from the full option chain, not copied from a data vendor's
              "flip point". Those two disagree often — saying SPY is below the flip point matches
              "net gamma below zero" only 52.4% of the time on the watchtower feed and 45.0% on the
              intraday one, so other pages in this app can tell you the opposite of this one.
              Also: <b style={{ color: '#c6cbd8' }}>"short gamma" and "below the flip" are the same
              thing</b> here — they agree 96.1% of the time. Treating them as two separate reasons to
              take a trade is counting one thing twice.
            </div>
          </Fold>

          {/* HOW THIS OVERLAPS THE RISK PAGE. Measured, because the two pages
              quote the SAME trade — same underlying, same short strike, same
              entry minute — differing only in wing width. */}
          <Fold title="How this overlaps the Risk page" meta="same trade, $5 wing instead of $2">
            <div style={{ fontSize: 13, marginBottom: 8, color: '#c6cbd8' }}>
              The Risk page's EBB recipe is the <b>same trade as this one</b> — same
              underlying, same short strike, same entry minute — with a $5 wing instead
              of $2. Its VIX decay gate already skips at ratio &gt; 0.90; this page's
              VIX leg fires at &gt; 0.95.
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 620 }}>
                <thead><tr>
                  <th style={S.th}>this page's sell-side veto</th>
                  <th style={S.th}>already caught by EBB's gate</th>
                  <th style={S.th}>unique</th>
                </tr></thead>
                <tbody>
                  <tr>
                    <td style={S.td}>SQUEEZE WATCH — stand down</td>
                    <td style={{ ...S.td, color: RED, fontWeight: 700 }}>100%</td>
                    <td style={{ ...S.td, color: RED, fontWeight: 700 }}>nothing</td>
                  </tr>
                  <tr>
                    <td style={S.td}>NO SELL — net gamma ≤ −$10B</td>
                    <td style={S.td}>72.6%</td>
                    <td style={{ ...S.td, color: GREEN, fontWeight: 700 }}>23 of 1,604 (+1.4pts)</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={{ ...S.caption, marginTop: 10 }}>
              Measured over 1,604 sessions. <b style={{ color: '#c6cbd8' }}>Every one of the 161
              SQUEEZE WATCH days is a day EBB would already have skipped</b> — a strict subset,
              not a correlation. So do NOT run both as two sell-side vetoes: that applies one
              variable twice and quietly halves your trade count for nothing. The gamma veto's
              only additive contribution is NO SELL, and it is worth 23 extra skip-days in six
              and a half years.
              <br /><br />
              Where this page is genuinely additive is the <b style={{ color: AMBER }}>buy
              side</b> — the 0.25 delta call. EBB has no long-convexity trade at all, and the
              two sides' monthly P&amp;L correlate +0.165.
            </div>
          </Fold>

          {/* WHAT THE VETO IS WORTH — the honest headline of the evidence. */}
          <Fold title="What the veto is actually worth" meta="always-on vs the gamma veto">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>strategy</th><th style={S.th}>$1,000 becomes</th>
                    <th style={S.th}>CAGR</th><th style={S.th}>return/drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={S.td}>Always-on (no signal)</td>
                    <td style={S.td}>$2,931</td>
                    <td style={S.td}>35.0%</td>
                    <td style={S.td}>0.81</td>
                  </tr>
                  <tr>
                    <td style={S.td}>With the gamma veto</td>
                    <td style={{ ...S.td, fontWeight: 700, color: GREEN }}>$3,728</td>
                    <td style={{ ...S.td, fontWeight: 700, color: GREEN }}>44.1%</td>
                    <td style={{ ...S.td, fontWeight: 700, color: GREEN }}>1.29</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              The veto adds about $1.27 a trade and roughly 9 points of drawdown. That is the whole
              contribution — the edge is the short premium itself, not the signal. Of 17 candidate
              signals scanned against this strategy, none survived; gamma scores t=+0.87 on its own.
              It earns its place as a rare veto, not as an entry trigger.
            </div>
          </Fold>

          {/* HOW TO TRADE THIS — verdict-aware, real-fill backtests. */}
          <Fold title="If the signal changes" meta="the other verdicts, and what each one means">
            {(() => {
              const TRADE_BLOCKS = [
                {
                  key: 'sell', accent: GREEN,
                  active: verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL',
                  title: 'SELL PREMIUM / NEUTRAL — the common case',
                  body: (
                    <>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        SPY 0DTE put spread. Short strike round(spot) − 2, $2 wide. Enter 10:05 CT (11:05 ET),
                        hold to settlement, no stop.
                      </div>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        Real NBBO fills crossing the spread, 898 trades: <b>+$2.18/trade</b>, 83.3%
                        win rate.
                      </div>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        $1,000 → $3,728 over 3.7 years with the gamma veto applied. CAGR 44.1%, max
                        drawdown −35.1%, return/drawdown 1.29.
                      </div>
                      <div style={{ fontSize: 13, color: '#c6cbd8', lineHeight: 1.7, marginBottom: 6 }}>
                        <div>daily mean +$3.35 · median +$19.30 · worst −$198</div>
                        <div>weekly +$15, 116 of 185 up</div>
                        <div>monthly +$62, 29 of 44 up, worst −$423</div>
                        <div>yearly +$569 · +$1,217 · +$314 · +$629</div>
                      </div>
                      <div style={{ fontSize: 13, color: AMBER }}>
                        Worst single day −$198 — 20% of a $1,000 account in one afternoon.
                      </div>
                      <div style={{ fontSize: 13, color: AMBER, marginTop: 6, lineHeight: 1.5 }}>
                        The veto predicts loss SIZE, not loss ARRIVAL. Win rate barely moves with it (66% vs
                        85%) — the losses are bigger, not more frequent. 6 of the 10 worst days were
                        unflagged, and the single worst (2023-12-20, −$197.70) happened in LONG gamma at
                        +$10.8B.
                      </div>
                    </>
                  ),
                },
                {
                  key: 'squeeze', accent: AMBER,
                  active: verdict === 'SQUEEZE_WATCH',
                  title: 'SQUEEZE WATCH',
                  body: (
                    <>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        Stand down from selling. Buy a SPY call at 0.25 delta, 5–9 DTE, hold 5
                        sessions. About $190/contract.
                      </div>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        167 trades: <b>+$57/trade</b>, +37% return on premium, +$9,536 total, positive
                        in 6 of 7 years.
                      </div>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        Wins about one time in three and pays +103% when it lands.
                      </div>
                      <div style={{ fontSize: 13, color: RED, fontWeight: 700 }}>
                        Must be 0.25 delta, NOT at-the-money — at 0.50 delta the same signal LOSES
                        $43/trade versus benchmark. The edge is convexity per dollar, not delta.
                      </div>
                    </>
                  ),
                },
                {
                  key: 'no_sell', accent: RED,
                  active: verdict === 'NO_SELL',
                  title: 'NO SELL',
                  body: (
                    <div style={{ fontSize: 13 }}>
                      Skip the put spread entirely. Fires on roughly 9% of sessions (net gamma below
                      −$10B).
                    </div>
                  ),
                },
              ];

              return (
                <div style={{ opacity: f.stale ? 0.5 : 1 }}>
                  {f.stale && (
                    <div style={{ fontSize: 13, fontWeight: 700, color: AMBER, marginBottom: 10 }}>
                      Stale reading — do not act on this today.
                    </div>
                  )}
                  {TRADE_BLOCKS.map(b => (
                    <div key={b.key} style={{
                      background: '#0e1220', border: `1px solid ${b.active ? b.accent + '66' : '#232a3d'}`,
                      borderRadius: 10, padding: '12px 14px', marginBottom: 12, opacity: b.active ? 1 : 0.6,
                    }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: b.active ? b.accent : DIM, marginBottom: 6 }}>
                        {b.title}
                        {b.active && <span style={{ marginLeft: 8, fontWeight: 700 }}>← current state</span>}
                      </div>
                      {b.body}
                    </div>
                  ))}
                  <div style={{ ...S.small, lineHeight: 1.6 }}>
                    <b style={{ color: '#c6cbd8' }}>Capital.</b> Below $5,000, run one side only — at
                    $1,000 the account can afford just 14 of 61 squeeze signals, which is a different
                    strategy rather than a cheaper one. Both sides together need about $5,000.
                  </div>
                  <div style={{ ...S.caption, marginTop: 8 }}>
                    Neither trade has been forward-tested. The sell side has a blind out-of-sample
                    decade behind it; the buy side is the best of 48 structures searched.
                  </div>
                </div>
              );
            })()}
          </Fold>

          {/* EVIDENCE TABLE */}
          <Fold title="Squeeze rate by gamma percentile" meta="the core evidence">
            <div style={{ ...S.small, marginBottom: 10 }}>
              Squeeze = SPY gains 4% or more within 5 sessions, starting within 3% of a 20-day low. 134 in
              33 years (about 4 a year); 33 fall inside the 2020–2026 gamma window, or 1.99% of sessions.
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 480, marginBottom: 10 }}>
                <thead><tr><th style={S.th}>percentile bucket</th><th style={S.th}>squeeze rate</th></tr></thead>
                <tbody>
                  {[
                    ['0–10 (most oversold)', '10.80%'],
                    ['10–25', '8.54%'],
                    ['25–50', '2.03%'],
                    ['50–75', '0.80%'],
                    ['75–90', '0.00%'],
                    ['90–100 (most overbought)', '0.00%'],
                  ].map(([bucket, rate]) => (
                    <tr key={bucket}>
                      <td style={S.td}>{bucket}</td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{rate}</td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>base rate (all sessions)</td>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>3.38%</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              Gamma oversold + VIX at its highs → <b style={{ color: '#c6cbd8' }}>15.13% squeeze rate, 0.00% crash rate</b> over
              119 sessions. Monotone, zero squeezes in the top quartile. Overbought gamma is NOT a crash signal —
              it is the safest measured state to sell premium.
            </div>
            <div style={{ ...S.caption, marginTop: 8 }}>
              Neither threshold is the best-fitting one. Bottom-decile squeeze rate is 7.8–11.4% at every
              lookback from 30 to 252 sessions and monotone at all of them; 60 shipped, but 120 scores
              better. Every percentile cut from 0.05 to 0.30 gives a 2.5–3.4x lift; 0.20 shipped, but 0.15
              scores better. Decile rank correlation −0.861. Shipping the non-optimal value is deliberate —
              the result is not a knife edge.
            </div>
          </Fold>

          {/* FUEL EVIDENCE TABLE */}
          <Fold title="Squeeze rate by fuel sextile" meta="forced hedging vs liquidity">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 480, marginBottom: 10 }}>
                <thead><tr><th style={S.th}>fuel sextile</th><th style={S.th}>squeeze rate</th></tr></thead>
                <tbody>
                  {FUEL_SEXTILE_RATES.map(([bucket, rate]) => (
                    <tr key={bucket}>
                      <td style={S.td}>{bucket}</td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{rate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              Fuel = forced dealer hedging per 1% move as a share of a normal day's dollar volume. Median
              9.4%; top sextile 17.5–56.8%. Top quintile combined with VIX at its highs reaches 16.49%,
              against 15.13% for the percentile version that shipped first — a better mechanism and
              slightly better numbers, kept alongside the percentile rather than replacing it until it
              has been watched forward.
            </div>
          </Fold>

          {/* CALENDAR EVIDENCE TABLE */}
          <Fold title="Scheduled flow on oversold days" meta="calendar tilts">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>event</th><th style={S.th}>squeeze rate</th><th style={S.th}>vs base</th><th style={S.th}>sessions</th>
                  </tr>
                </thead>
                <tbody>
                  {CALENDAR_EVIDENCE.map(row => (
                    <tr key={row.event}>
                      <td style={S.td}>{row.event}</td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{row.rate}</td>
                      <td style={{ ...S.td, color: row.tone === 'supportive' ? AMBER : GREEN, fontWeight: 700 }}>{row.mult}</td>
                      <td style={S.td}>{row.n}</td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>base rate (oversold days)</td>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>10.08%</td>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>—</td>
                    <td style={{ ...S.td, fontStyle: 'italic' }}>397</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              Measured on oversold days only. Month end clears Bonferroni across the 14 catalyst tests
              (p=0.00018 against a 0.00357 bar) and beats its own year's base in 5 of 7 years — but it was
              0-for-9 in 2024 and 0-for-9 in 2025. A tilt on top of an existing setup, never a trigger on
              its own. Mechanism: month end forces pension and target-date rebalancing into a beaten-down
              tape; opex runs the other way because expiry removes the gamma.
            </div>
          </Fold>

          {/* RECALL TABLE */}
          <Fold title="Recall — what it catches" meta="33 of 33 caught, 3.4% precision">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>filter</th><th style={S.th}>recall</th><th style={S.th}>precision</th><th style={S.th}>lift</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={S.td}>net gamma &lt; 0</td>
                    <td style={S.td}>100%</td>
                    <td style={S.td}>3.4%</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>1.72x</td>
                  </tr>
                  <tr>
                    <td style={S.td}>net gamma &lt; −$5B</td>
                    <td style={S.td}>57.6%</td>
                    <td style={S.td}>4.6%</td>
                    <td style={S.td}>—</td>
                  </tr>
                  <tr>
                    <td style={S.td}>net gamma &lt; −$10B</td>
                    <td style={S.td}>18.2%</td>
                    <td style={S.td}>7.1%</td>
                    <td style={S.td}>—</td>
                  </tr>
                  <tr>
                    <td style={S.td}>VIX ratio &lt; 0.80</td>
                    <td style={S.td}>—</td>
                    <td style={S.td}>—</td>
                    <td style={{ ...S.td, fontWeight: 700, color: RED }}>0.36x</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              Every SPY squeeze since 2020 began with dealers short gamma — 33 of 33, against a 58% base
              rate. But precision is 3.4%: 929 false alarms. Tightening the threshold trades recall for
              precision and never buys much of either. The last row is the one to sit with — a decaying
              VIX has a lift BELOW 1, meaning it is a squeeze AVOIDER. Squeezes start with a median
              VIX ratio of 0.97, fear at its peak. The same ratio is correctly protective for a premium
              seller and actively wrong for anyone hunting squeezes. Both are true at once.
            </div>
          </Fold>

          {/* FALSIFICATION TABLE */}
          <Fold title="What happened the last 22 times gamma went below −$10B" meta="the falsification test">
            <div style={{ ...S.small, marginBottom: 10 }}>
              The evidence above is what supports the signal. This is what breaks it — if deep short
              gamma were a squeeze setup, this table would be mostly green.
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 620, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>episode start</th><th style={S.th}>net gamma</th><th style={S.th}>vs flip</th>
                    <th style={S.th}>fwd 5d</th><th style={S.th}>5d max</th><th style={S.th}>&gt;+3% rip</th>
                  </tr>
                </thead>
                <tbody>
                  {FALSIFICATION_EPISODES.map(([date, gamma, vsFlip, fwd5d, max5d, rip]) => (
                    <tr key={date}>
                      <td style={S.td}>{date}</td>
                      <td style={S.td}>{gamma}</td>
                      <td style={S.td}>{vsFlip}</td>
                      <td style={{ ...S.td, color: fwd5d.startsWith('+') ? GREEN : RED, fontWeight: 700 }}>{fwd5d}</td>
                      <td style={S.td}>{max5d}</td>
                      <td style={{ ...S.td, color: rip ? AMBER : DIM, fontWeight: rip ? 700 : 400 }}>{rip ? 'YES' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={S.small}>
              16 of 22 episodes shown; the rest are unremarkable middles. Full count: 6 of 22 rip (27%),
              mean forward 5-day +0.75%, worst −4.55%. Deep short gamma doubles BOTH tails — it lifts the
              odds of a 5-day rip above +3% from 7.9% to 17.9%, and the odds of a 5-day drop below −3%
              from 3.7% to 6.4%. Read as "get long" it was wrong 16 times out of 22. That is an amplifier,
              not a direction call.
            </div>
          </Fold>
        </Fold>
      </div>
    </div>
  );
}
