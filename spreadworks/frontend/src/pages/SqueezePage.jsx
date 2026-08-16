// Squeeze Signal — net dealer gamma percentile + VIX-at-highs, the
// prerequisite-not-a-direction-call gate documented in
// backend/bots/gamma_regime.py. ADVISORY ONLY — no bot reads this.
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import { Zap } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', GREY = '#9ca3af', DIM = '#8b93a7';
const LIVE = '#c084fc';
const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 13, fontWeight: 700, marginBottom: 10 },
  th: { textAlign: 'left', color: DIM, fontSize: 12, padding: '6px 10px' },
  td: { padding: '6px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
  small: { fontSize: 11, color: DIM },
  tile: { flex: '1 1 160px', background: '#0e1220', border: '1px solid #232a3d', borderRadius: 10, padding: '12px 14px' },
  tileLabel: { fontSize: 11, color: DIM, marginBottom: 4 },
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
      <span style={{ cursor: 'help', color: DIM, fontSize: 11, border: `1px solid ${DIM}66`,
                     borderRadius: '50%', width: 14, height: 14, display: 'inline-flex',
                     alignItems: 'center', justifyContent: 'center', verticalAlign: 'middle' }}>i</span>
      {open && (
        <span style={{ position: 'absolute', zIndex: 30, top: 18, left: -8, width: 290,
                       background: '#0e1220', border: '1px solid #2a3145', borderRadius: 8,
                       padding: '10px 12px', fontSize: 12, lineHeight: 1.55, color: '#c6cbd8',
                       fontWeight: 400, boxShadow: '0 6px 20px rgba(0,0,0,.5)' }}>{text}</span>
      )}
    </span>
  );
}

// Section header — breaks the page's flat card hierarchy into named zones.
function Zone({ label, children }) {
  return (
    <div>
      <div style={{
        textTransform: 'uppercase', fontSize: 11, letterSpacing: 1.2, color: DIM, fontWeight: 700,
        borderBottom: '1px solid #232a3d', marginTop: 28, marginBottom: 12, paddingBottom: 6,
      }}>
        {label}
      </div>
      {children}
    </div>
  );
}

// Collapsible card — the evidence lives here so the page reads "verdict
// first, proof on demand" instead of six screens of justification before
// the fold.
function Collapse({ title, subtitle, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={S.card}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
        textAlign: 'left', padding: 0, color: 'inherit', font: 'inherit',
      }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>
          <span style={{ display: 'inline-block', width: 14 }}>{open ? '▾' : '▸'}</span>
          {title}
        </span>
        {subtitle && <span style={S.small}>{subtitle}</span>}
      </button>
      {open && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
}

export default function SqueezePage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [intraday, setIntraday] = useState(null);
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
        if (live) setData(d);
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

  // The range control governs the gamma chart, the VIX chart and the track
  // record together — three views of the same sessions, so letting them drift
  // to different windows would make them impossible to read against each
  // other. Sliced from the tail: newest sessions are always in view.
  const inRange = (rows) => (rows || []).slice(-rangeN);
  const hist = inRange(data.history).map(h => ({ ...h, label: h.trade_date.slice(5) }));
  const rangeLabel = (RANGES.find(r => r.n === rangeN) || {}).label || `${rangeN}`;

  // Shared range buttons. Rendered once in "What would change this" — every
  // chart and the track record below it shares this one control.
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
              fontSize: 11, fontWeight: 700, borderRadius: 6, cursor: short ? 'default' : 'pointer',
              padding: '3px 9px', background: on ? '#1c2740' : 'transparent',
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

  // Live intraday point appended to the right edge of the 90-session line —
  // a distinct colour, a visible dot, dashed connector from the last close.
  // Omitted entirely (not drawn stale) when the /intraday poll is stale or
  // has no reading.
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

  // THE TODAY CARD — one screen, real ticket parameters, not a state label.
  // Blocking takes precedence over the verdict: a stale/unarmed/unknown read
  // is never actionable no matter what the verdict string says.
  const outlookTop = data.outlook || {};
  // Source mixing blocks too: a percentile is a RANK, and ranking a
  // Tradier-derived reading inside a window of ORATS-derived ones compares two
  // different measurements of the same quantity. See data_freshness().
  const sourceMixed = data.freshness?.window_source_mixed === true;
  const blocked = sourceMixed
    || data.freshness?.stale
    || data.capture_health?.state === 'claimed_but_not_stored'
    || data.jobs?.scheduler?.registered === false
    || verdict === 'UNKNOWN';

  let blockedReason = null;
  if (blocked) {
    if (data.jobs?.scheduler?.registered === false) {
      blockedReason = 'The capture and alert jobs are not scheduled — nothing is updating this page.';
    } else if (data.capture_health?.state === 'claimed_but_not_stored') {
      blockedReason = 'The 15:05 capture ran and stored nothing, so this reading will keep ageing.';
    } else if (data.freshness?.stale) {
      blockedReason = `The newest reading is ${data.freshness.gamma_date || '—'}, ${data.freshness.gamma_stale_sessions ?? '—'} session(s) behind ${data.freshness.expected_date || '—'}.`;
    } else {
      blockedReason = 'The signal could not be computed. UNKNOWN is a block, never a pass.';
    }
    if (sourceMixed) {
      blockedReason = `The 60-session window mixes two data sources — `
        + `${data.freshness.window_captured} session(s) from the live capture and `
        + `${data.freshness.window_seeded} from the ORATS baseline. A percentile `
        + `ranks a value against its own history; these are not the same measurement.`;
    }
  }
  // The machine reason behind an UNKNOWN — "insufficient_gamma_history:
  // have=12 need=60", or the actual exception. Without it a blocked page tells
  // you it is blocked and nothing about why, which is the one moment the
  // detail is worth most. Shown as a second line, never in place of the
  // human sentence above.
  const blockedDetail = blocked ? (data.reason || data.outlook?.reason || null) : null;

  const TODAY_ACCENT = { SELL_PREMIUM: GREEN, NEUTRAL: GREEN, SQUEEZE_WATCH: AMBER, NO_SELL: RED };
  const todayAccent = blocked ? RED : (TODAY_ACCENT[verdict] || GREY);

  const TODAY_ACTION = {
    SELL_PREMIUM: 'SELL THE PUT SPREAD', NEUTRAL: 'SELL THE PUT SPREAD',
    SQUEEZE_WATCH: 'STAND DOWN FROM SELLING', NO_SELL: 'NO TRADE TODAY',
  };
  const todayHeadline = blocked ? 'DO NOT TRADE THIS TODAY' : (TODAY_ACTION[verdict] || 'NO TRADE TODAY');

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
          {` · SPY 0DTE · $${data.ticket.sell.width} wide · enter 11:05 ET · hold to settlement · no stop`}
        </>
      ) : 'SPY 0DTE put spread · short strike round(spot) − 2 · $2 wide · enter 11:05 ET · hold to settlement · no stop';
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
    : '—';

  let riskValue = '—';
  if (!blocked) {
    if (verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL') riskValue = 'worst day −$198 · 20% of a $1,000 account';
    else if (verdict === 'SQUEEZE_WATCH') riskValue = '~$190/contract, wins ~1 in 3';
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>Squeeze Signal</h1>
        <p style={S.sub}>
          Net dealer gamma percentile + VIX-at-highs. Advisory only — no bot reads this.
          A prerequisite for a squeeze and a strong veto for short premium — never a direction call.
        </p>

        {/* CAPTURE FAILED SILENTLY — the loudest thing on the page.
            capture_gamma calls _dedup_ok BEFORE pulling the chain, so a run
            that claims the slot and then dies leaves a ledger entry and no
            row. Staleness alone would not catch it on day one: the data is
            only one session old, so the STALE bar below stays quiet while the
            job is in fact dead. This is the shape of every silent failure
            this page has had. */}
        {data.capture_health?.state === 'claimed_but_not_stored' && (
          <div style={{
            background: RED + '20', border: `1px solid ${RED}88`, borderRadius: 10,
            padding: '10px 14px', marginBottom: 10, fontSize: 12.5, lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 700, color: RED }}>
              CAPTURE FAILED — the 15:05 job ran and stored nothing.
            </div>
            <div style={{ marginTop: 4, color: '#c6cbd8' }}>
              {data.capture_health.detail || ''} The reading below is the last one that
              did store, so it will keep ageing until this is fixed.
            </div>
          </div>
        )}

        {/* JOBS NOT ARMED — worse than "never run", and indistinguishable from
            it without this. If the scheduler never attached, the capture will
            not fire tonight, tomorrow, or ever, and every readout on the page
            quietly freezes at whatever the CSV last held. */}
        {data.jobs?.scheduler?.registered === false && (
          <div style={{
            background: RED + '20', border: `1px solid ${RED}88`, borderRadius: 10,
            padding: '10px 14px', marginBottom: 10, fontSize: 12.5, lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 700, color: RED }}>
              JOBS NOT ARMED — the capture and alert are not scheduled.
            </div>
            <div style={{ marginTop: 4, color: '#c6cbd8' }}>
              {data.jobs.scheduler.reason || ''} Nothing will update this page until the
              scheduler is running.
            </div>
          </div>
        )}

        {/* FRESHNESS — the verdict banner used to print today's calendar date
            regardless of how old the underlying gamma reading was. This bar
            makes staleness impossible to miss; it renders nothing when the
            reading is current. */}
        {data.freshness?.reason ? (
          <div style={{ ...S.small, marginBottom: 10 }}>{data.freshness.reason}</div>
        ) : data.freshness?.stale ? (
          <div style={{
            background: (data.freshness.legs_mismatch ? RED : AMBER) + '18',
            border: `1px solid ${(data.freshness.legs_mismatch ? RED : AMBER)}66`,
            borderRadius: 10, padding: '10px 14px', marginBottom: 10, fontSize: 12.5, lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 700, color: AMBER }}>
              STALE — the newest gamma reading is {data.freshness.gamma_date || '—'},{' '}
              {data.freshness.gamma_stale_sessions ?? '—'} session(s) behind {data.freshness.expected_date || '—'}.
              This verdict is not today's.
            </div>
            {data.freshness.legs_mismatch && (
              <div style={{ marginTop: 4, color: '#c6cbd8' }}>
                The two legs are dated apart — gamma {data.freshness.gamma_date || '—'}, VIX {data.freshness.vix_date || '—'}.
              </div>
            )}
          </div>
        ) : null}

        {/* TODAY CARD — the centrepiece. Answers "what do I do today" with the
            actual ticket parameters, not a state label. Blocking beats the
            verdict; see `blocked` above. */}
        <div style={{ ...S.card, borderColor: todayAccent + '55' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <Zap size={30} color={todayAccent} style={{ flexShrink: 0 }} />
            <div style={{ fontSize: 26, fontWeight: 700, color: todayAccent }}>{todayHeadline}</div>
            <div style={{ ...S.small, marginLeft: 4 }}>{VERDICT_LABEL[verdict] || verdict}</div>
          </div>

          {blocked && (
            <div style={{ fontSize: 13, color: RED, marginTop: 6, lineHeight: 1.5 }}>{blockedReason}</div>
          )}
          {!blocked && data.ticket?.sell && (
            /* Which spot the strikes came from, and when they stop being
               true. The entry is 11:05 ET and the real strike derives from
               spot at that moment; anything computed off the prior close is
               indicative and has to say so. */
            <div style={{ ...S.small, marginTop: 6 }}>
              Strikes from spot {data.ticket.spot} ({data.ticket.spot_source})
              {data.ticket.spot_source !== 'live' &&
                ' — indicative. Re-derive from spot at 11:05 ET before sending.'}
            </div>
          )}
          {blockedDetail && (
            <div style={{ ...S.small, marginTop: 4, fontFamily: 'ui-monospace, monospace',
                          wordBreak: 'break-word' }}>
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

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: DIM }}>WHY</div>
              <div style={{ fontSize: 13 }}>{whyValue}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: DIM }}>RISK</div>
              <div style={{ fontSize: 13 }}>{riskValue}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: DIM }}>SIZE</div>
              <div style={{ fontSize: 13 }}>about $5,000 to run both sides; below that, one side only</div>
            </div>
          </div>

          <div style={{ ...S.small, marginTop: 12 }}>
            Reading from {data.data_date || '—'} · {data.freshness?.captured_sessions ?? '—'} of{' '}
            {data.freshness?.window_sessions ?? '—'} sessions from a live capture
            {/* Next refresh belongs on the face, not a click down: "is this
                number about to change?" is part of reading the number. */}
            {(() => {
              const nxt = data.jobs?.scheduler?.jobs?.gamma_capture;
              if (!nxt) return null;
              const d = new Date(nxt);
              if (isNaN(d)) return null;
              return <> · next reading {d.toLocaleString('en-US', {
                weekday: 'short', hour: 'numeric', minute: '2-digit',
                timeZone: 'America/Chicago' })} CT</>;
            })()}
            <InfoTip text="This page is ADVISORY ONLY — no bot reads it. Neither trade has been forward-tested: the sell side has a blind out-of-sample decade behind it, the buy side is the best of 48 structures searched." />
          </div>
        </div>

        <Zone label="What would change this">
          {/* OUTLOOK — what to watch */}
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
                  <div style={S.cardTitle}>What to watch</div>
                  <div style={{ fontSize: 13.5, color: '#c6cbd8' }}>Outlook unavailable</div>
                  <div style={{ ...S.small, marginTop: 6 }}>{outlook.reason}</div>
                </div>
              );
            }

            return (
              <div style={S.card}>
                <div style={S.cardTitle}>What to watch</div>

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
                {/* The moving "current" label gets its OWN row under the bar, and
                    the two fixed trigger labels get the row below it. They shared
                    one row at first, which put "current 86.7%" straight through
                    "overbought ≥ +$3.66B" — the marker sits near an end exactly
                    when the reading is interesting, so the collision is the
                    common case, not the edge case. Wrapped in overflow:hidden so
                    the label can never push the row wider than the card on a
                    narrow screen. */}
                <div style={{ position: 'relative', marginTop: 4, height: 16, overflow: 'hidden' }}>
                  {gammaPctNow != null && (
                    <span style={{
                      ...S.small, color: '#c6cbd8', position: 'absolute', fontSize: 10,
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
                <div style={{ ...S.small, marginBottom: 4 }}>Which leg is missing — SQUEEZE_WATCH needs both</div>
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

                {/* 6 — calendar strip: scheduled flow, color-coded by direction.
                    Only flags that are actually true render — a static list
                    made every chip look live even on a day with nothing
                    scheduled. */}
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
                            fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 999,
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

          {/* LIVE INTRADAY — context only, never the verdict. Deliberately
              quieter than the banner above: no colour block, small muted
              header, plain card border. */}
          {(() => {
            const iv = intraday || {};
            const stale = !!iv.stale;
            return (
              <div style={{ ...S.card, padding: '10px 14px', opacity: stale ? 0.55 : 1 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: DIM, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 8 }}>
                  Live intraday — context only, not the signal
                </div>
                {intradayErr ? (
                  <div style={{ fontSize: 12, color: DIM }}>unavailable: {intradayErr}</div>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 8 }}>
                      <div>
                        <div style={{ fontSize: 10, color: DIM }}>net gamma now</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{bn(iv.net_gex_b)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: DIM }}>SPY spot (live)</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{iv.spot == null ? '—' : `$${Number(iv.spot).toFixed(2)}`}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: DIM }}>vs last close ({bn(iv.last_close_b)})</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{signedBn(iv.delta_b)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: DIM }}>percentile if this were the close</div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{pct(iv.pct_if_now)}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: AMBER, lineHeight: 1.5, marginBottom: 8 }}>
                      "vs last close" subtracts a live Tradier chain from an ORATS-derived baseline. Those two
                      paths have not been reconciled — on 2026-08-14 they read $6.30B and $3.50B for the same
                      session while spot matched to the cent. Treat this delta as pipeline difference, not as a
                      move in gamma, until the 15:05 capture has run against both.
                    </div>
                    {stale ? (
                      /* Not "the last available reading" — the backend no longer
                         pulls at all while the market is shut, because out of
                         hours Tradier serves stale quotes and rendering those as
                         a live delta showed gamma "moving" on a closed market. */
                      <div style={{ fontSize: 11, color: DIM }}>
                        Market is closed — no live reading is taken. The figures above resume
                        during market hours; the last stored close is shown for context.
                      </div>
                    ) : (
                      <div style={{ fontSize: 11, color: DIM, lineHeight: 1.5 }}>
                        Sampled at 10:00 CT this lands in a different percentile zone than the close 22% of
                        the time. The signal above uses the 15:05 CT reading and is what has seven years of
                        evidence behind it.
                      </div>
                    )}
                    {iv.reason && iv.reason !== 'market_closed' && (
                      <div style={{ fontSize: 11, color: DIM, marginTop: 4 }}>{iv.reason}</div>
                    )}
                  </>
                )}
              </div>
            );
          })()}

          {/* One range control for the gamma chart, VIX chart and track
              record together — three views of the same sessions. */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={S.small}>chart range</span>
            <RangePicker />
          </div>

          {/* CHART */}
          <div style={S.card}>
            <div style={S.cardTitle}>Net dealer gamma — last {rangeLabel}</div>
            {hist.length ? (() => {
              const chartOutlook = data.outlook || {};
              // Tallest print in the visible window — used to flag a possible
              // 1DTE-expiry artifact in the caption below.
              const maxRow = hist.reduce((m, d) => (
                d.net_gex_b != null && (m == null || d.net_gex_b > m.net_gex_b) ? d : m
              ), null);
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
                        <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                        <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#5b6478' }} tickFormatter={v => `${v.toFixed(0)}B`} />
                        <YAxis yAxisId="price" orientation="right" tick={{ fontSize: 10, fill: '#5b6478' }}
                               domain={['dataMin - 5', 'dataMax + 5']} tickFormatter={v => `$${v.toFixed(0)}`} />
                        <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                                 /* Recharts hands the formatter the series' `name` PROP, not its
                                    dataKey — so the old `name === 'net_gex_b'` branch never matched
                                    and tooltips rendered raw unformatted numbers. Match on the NAME,
                                    which does work. Not every series is $bn any more: SPY's close
                                    shares this tooltip and a blanket $bn suffix rendered it as
                                    "$770.56B". */
                                 formatter={(v, name) => {
                                   const num = Number(v);
                                   if (!Number.isFinite(num)) return ['—', name];
                                   return [name === PRICE_SERIES ? `$${num.toFixed(2)}`
                                                                 : `$${num.toFixed(2)}B`, name];
                                 }} />
                        <Legend
                          /* Recharts writes an absolute pixel width onto the legend
                             wrapper from its first measurement. At a phone width that
                             stale value (~1034px) does not shrink, and because it is a
                             normal child it drags the chart card -- and the whole zone --
                             wider than the viewport. width:100% overrides it so the
                             legend tracks the container instead of the first render. */
                          wrapperStyle={{ fontSize: 11, width: '100%' }}
                          formatter={v => <span style={{ color: '#8b93a7' }}>{v}</span>} />
                        <ReferenceLine yAxisId="left" y={0} stroke="#232a3d" />
                        {chartOutlook.oversold_trigger_b != null && (
                          <ReferenceLine yAxisId="left" y={chartOutlook.oversold_trigger_b} stroke={AMBER} strokeDasharray="3 3"
                                         /* signedBn, not bn — bn() renders a negative as "$-8.53B"
                                            with an ASCII hyphen; the rest of the page uses a true
                                            minus glyph. */
                                         label={{ value: signedBn(chartOutlook.oversold_trigger_b), position: 'insideBottomRight', fill: AMBER, fontSize: 10 }} />
                        )}
                        {chartOutlook.overbought_trigger_b != null && (
                          <ReferenceLine yAxisId="left" y={chartOutlook.overbought_trigger_b} stroke={GREEN} strokeDasharray="3 3"
                                         label={{ value: signedBn(chartOutlook.overbought_trigger_b), position: 'insideTopRight', fill: GREEN, fontSize: 10 }} />
                        )}
                        <Line yAxisId="left" dataKey="net_gex_b" name="net gamma ($B)" stroke="#60a5fa" dot={false} strokeWidth={1.8} />
                        <Line yAxisId="price" dataKey="spot" name={PRICE_SERIES} stroke="#94a3b8" dot={false} strokeWidth={1.2} />
                        {liveOk && (
                          <Line yAxisId="left" dataKey="live_gex_b" name="live (not the signal)" stroke={LIVE} strokeWidth={1.8}
                                strokeDasharray="4 4" dot={<LiveDot />} isAnimationActive={false} />
                        )}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ ...S.small, marginTop: 8, lineHeight: 1.65 }}>
                    <b style={{ color: '#8b95ab' }}>How to read this.</b> The blue line is net dealer
                    gamma in billions of dollars per 1% move in SPY — how much stock dealers must
                    trade to stay hedged.{' '}
                    <b style={{ color: '#60a5fa' }}>Below the zero line</b> they hedge <i>with</i> the
                    move (selling into weakness, buying into strength), so moves get amplified.
                    <b style={{ color: '#60a5fa' }}> Above it</b> they hedge against the move and the
                    tape gets pinned.
                    <br />
                    <b style={{ color: AMBER }}>Amber shading</b> = gamma in the bottom 20% of its own
                    trailing 60 sessions. Every SPY squeeze since 2020 started in amber.{' '}
                    <b style={{ color: GREEN }}>Green shading</b> = top 20%; zero squeezes have ever
                    started there, and it carries the smallest downside tail.
                    <br />
                    <b style={{ color: '#94a3b8' }}>The grey line</b> is SPY's close on the right axis —
                    gamma is the state of the tape, not a forecast of the price.{' '}
                    <b style={{ color: AMBER }}>Dashed amber</b> and{' '}
                    <b style={{ color: GREEN }}>dashed green</b> lines mark the oversold and overbought
                    gamma triggers.
                    <br />
                    <span style={{ color: '#5b6478' }}>
                      Shading is the <i>percentile</i>, not the level — so it re-bases as the range
                      moves. A −$4B print can be amber in a calm month and unshaded in a volatile one.
                      That is deliberate: the level alone is a much weaker signal than the rank.
                      Updates once per session at 15:05 CT.
                      {liveOk && (
                        <> <b style={{ color: LIVE }}>The dashed purple point</b> is this minute's live
                        reading — context only, not part of the 15:05 CT signal.</>
                      )}
                    </span>
                  </div>
                  {maxRow && (
                    <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6 }}>
                      The tallest print in this window is {bn(maxRow.net_gex_b)} on {maxRow.trade_date}. Near-dated
                      expiries spike per-contract gamma, so a single session with a 1DTE expiry on the board can
                      set the window's top and depress every percentile below it until it rolls out of the
                      trailing 60.
                    </div>
                  )}
                  <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6 }}>
                    This is computed from the chain, not read off a vendor flip point. "Spot below the flip"
                    reproduces net_gex &lt; 0 only 52.4% of the time on the watchtower feed and 45.0% on the
                    intraday one, so other pages in this app can show a contradictory reading. Note also that
                    "short gamma" and "below the flip" are the same variable (96.1% agreement) — never stack
                    them as two conditions.
                  </div>
                </>
              );
            })() : <div style={S.small}>no history yet — needs the 15:05 CT capture job to run and 60 sessions before the percentile is defined</div>}
          </div>

          {/* VIX LEG CHART */}
          {(() => {
            const vh = inRange(data.vix_history).map(v => ({ ...v, label: v.trade_date.slice(5) }));
            const lastVix = vh.length ? vh[vh.length - 1] : null;
            const gapTo95 = lastVix?.ratio != null ? Math.max(0, 0.95 - lastVix.ratio) : null;
            return (
              <div style={S.card}>
                <div style={S.cardTitle}>
                  The VIX leg — VIX ÷ its own 20-session max
                  <InfoTip text="VIX divided by its own maximum over the previous 20 sessions. It measures where VIX sits in its recent range, not its level, so a flat VIX reads 1.00 by construction." />
                </div>
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 10, color: DIM }}>current ratio</div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{lastVix?.ratio == null ? '—' : lastVix.ratio.toFixed(2)}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: DIM }}>gap to 0.95</div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{gapTo95 == null ? '—' : gapTo95.toFixed(2)}</div>
                  </div>
                </div>
                {vh.length ? (
                  <div style={{ width: '100%', height: 200, overflowX: 'auto', minWidth: 0 }}>
                    <ResponsiveContainer>
                      <ComposedChart data={vh} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                        <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                        {/* The ratio is NOT capped at 1.0 — vix_decay_ratio divides by the
                            max of the 20 sessions BEFORE the reading, so a session that sets
                            a new high prints above 1.0. Those are the SQUEEZE_WATCH sessions,
                            i.e. the only ones worth looking at, and a [0, 1] domain flattened
                            every one of them against the top of the plot. */}
                        {/* Both axes carry an explicit id — with two YAxes present, leaving
                            one implicit makes which series binds to which axis depend on
                            declaration order. */}
                        <YAxis yAxisId="ratio" tick={{ fontSize: 10, fill: '#5b6478' }}
                               domain={[0, (dataMax) => Math.max(1.05, Math.ceil(dataMax * 20) / 20)]}
                               /* Without this the computed top of the domain renders as a
                                  raw float ("1.0999978297") and the axis prints garbage. */
                               tickFormatter={v => Number(v).toFixed(2)} />
                        {/* VIX's LEVEL on its own axis. The ratio alone cannot tell a
                            firing at VIX 22 from one at VIX 13, and that is the single
                            thing a reader needs to sanity-check the leg. */}
                        <YAxis yAxisId="lvl" orientation="right" tick={{ fontSize: 10, fill: '#5b6478' }}
                               domain={['dataMin - 2', 'dataMax + 2']} tickFormatter={v => Number(v).toFixed(0)} />
                        <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                                 formatter={(v, name) => [Number.isFinite(Number(v)) ? Number(v).toFixed(2) : '—', name]} />
                        <Legend
                          /* Recharts writes an absolute pixel width onto the legend
                             wrapper from its first measurement. At a phone width that
                             stale value (~1034px) does not shrink, and because it is a
                             normal child it drags the chart card -- and the whole zone --
                             wider than the viewport. width:100% overrides it so the
                             legend tracks the container instead of the first render. */
                          wrapperStyle={{ fontSize: 11, width: '100%' }}
                          formatter={v => <span style={{ color: '#8b93a7' }}>{v}</span>} />
                        <ReferenceLine yAxisId="ratio" y={0.95} stroke={AMBER} strokeDasharray="4 4"
                                       label={{ value: '0.95 — at highs', position: 'insideTopRight', fill: AMBER, fontSize: 10 }} />
                        <ReferenceLine yAxisId="ratio" y={0.90} stroke="#7dd3fc" strokeDasharray="4 4"
                                       label={{ value: '0.90 — EBB gate', position: 'insideBottomRight', fill: '#7dd3fc', fontSize: 10 }} />
                        <Line yAxisId="ratio" dataKey="ratio" name="VIX ratio" stroke="#f0abfc" dot={false} strokeWidth={1.8} connectNulls />
                        <Line yAxisId="lvl" dataKey="vix" name="VIX level" stroke="#64748b" dot={false} strokeWidth={1.1} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : <div style={S.small}>no VIX history yet</div>}
                <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6 }}>
                  SQUEEZE_WATCH needs this at or above 0.95 at the same time gamma is oversold. Above 0.95
                  means fear is still building; below it means fear is decaying, and a decaying VIX is what
                  kills the setup.
                  <br />
                  The ratio measures where VIX sits in its own recent range, not its level, so a perfectly
                  flat VIX would read 1.00 by construction. Measured over 1,598 sessions that is a
                  theoretical hole rather than a live one: of 161 firings, <b style={{ color: '#c6cbd8' }}>9
                  came on a flat window and only 4 cleared 0.95 without also setting an outright new
                  20-session high</b>. Median VIX at a firing is <b style={{ color: '#c6cbd8' }}>22.3</b>,
                  and just 5 of 161 fired below 15 — the leg is not quietly passing in calm tape. The grey
                  line is there so you can check that yourself.
                </div>
                <div style={{ ...S.small, marginTop: 8 }}>
                  Two thresholds are live on this same ratio. This page uses 0.95 as an advisory squeeze leg.
                  EBB ships 0.90 as a real-money gate — a different job on the same number.
                </div>
              </div>
            );
          })()}

          {/* SIGNAL TRACK RECORD */}
          {(() => {
            const sh = inRange(data.signal_history);
            // Summarised from the SLICED rows, not from data.signal_summary.
            // The API computes its summary over everything it returned (250),
            // so pairing it with a 90-session strip printed "NEUTRAL · 149" under
            // 90 cells and a "250 sessions" window tile over a 90-session view.
            // A track record has to describe the window you are looking at.
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
            const summary = {
              counts, n, current,
              sessions_in_state: n ? run : null,
              last_squeeze_watch: lastWith('SQUEEZE_WATCH'),
              last_no_sell: lastWith('NO_SELL'),
              first_date: n ? sh[0].trade_date : null,
              last_date: n ? sh[n - 1].trade_date : null,
            };
            return (
              <div style={S.card}>
                <div style={S.cardTitle}>Track record — what this signal has printed</div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>current state</div>
                    <div style={{ fontSize: 17, fontWeight: 700, color: VERDICT_COLOR[summary.current] || GREY }}>
                      {VERDICT_LABEL[summary.current] || summary.current || '—'}
                    </div>
                    <div style={S.small}>{summary.sessions_in_state != null ? `${summary.sessions_in_state} session${summary.sessions_in_state === 1 ? '' : 's'}` : '—'}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>last SQUEEZE_WATCH</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>{summary.last_squeeze_watch || `none in ${rangeLabel}`}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>last NO_SELL</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>{summary.last_no_sell || `none in ${rangeLabel}`}</div>
                  </div>
                  <div style={S.tile}>
                    <div style={S.tileLabel}>window</div>
                    <div style={{ fontSize: 17, fontWeight: 700 }}>
                      {n} sessions{summary.first_date && summary.last_date ? `, ${summary.first_date} → ${summary.last_date}` : ''}
                    </div>
                  </div>
                </div>

                {sh.length ? (
                  <div style={{ display: 'flex', height: 22, borderRadius: 6, overflow: 'hidden', marginBottom: 8 }}>
                    {sh.map((s, i) => (
                      <div key={i}
                           title={`${s.trade_date} — ${s.verdict} · pct ${pct(s.pct)} · gamma ${bn(s.net_gex_b)} · VIX ratio ${s.vix_ratio == null ? '—' : s.vix_ratio.toFixed(2)}`}
                           style={{ flex: '1 1 0', background: SIGNAL_STRIP_COLOR[s.verdict] || GREY }} />
                    ))}
                  </div>
                ) : <div style={S.small}>no signal history yet</div>}

                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
                  {Object.entries(counts).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: DIM }}>
                      <span style={{ width: 10, height: 10, borderRadius: 3, background: SIGNAL_STRIP_COLOR[k] || GREY, display: 'inline-block' }} />
                      {k} · {v} ({n ? (100 * v / n).toFixed(1) : '0.0'}%)
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

          {/* DATA AND JOB STATUS — moved from a standalone strip so the
              provenance detail doesn't sit above the fold on every load. */}
          <Collapse
            title="Data and job status"
            subtitle={`${data.freshness?.captured_sessions ?? '—'} of ${data.freshness?.window_sessions ?? '—'} from a live capture`}
          >
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 10, color: DIM }}>gamma data</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {data.freshness?.gamma_date || '—'}
                  {data.freshness?.gamma_stale_sessions > 0 && (
                    <span style={{ ...S.small, marginLeft: 6 }}>{data.freshness.gamma_stale_sessions} session(s) behind</span>
                  )}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: DIM }}>VIX data</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {data.freshness?.vix_date || '—'}
                  {data.freshness?.vix_stale_sessions > 0 && (
                    <span style={{ ...S.small, marginLeft: 6 }}>{data.freshness.vix_stale_sessions} session(s) behind</span>
                  )}
                </div>
              </div>
              {/* Per-job last-fire date. These jobs have never run in
                  production — a schedule string alone read as "this is live"
                  when it never has been. */}
              {JOB_STATUS.map(j => {
                const last = data.jobs?.last?.[j.key];
                return (
                  <div key={j.key}>
                    <div style={{ fontSize: 10, color: DIM }}>{j.label}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: last ? undefined : AMBER }}>
                      {last || 'never run'}
                    </div>
                    <div style={S.small}>{j.schedule}</div>
                  </div>
                );
              })}
              <div>
                <div style={{ fontSize: 10, color: DIM }}>provenance</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {data.freshness?.captured_sessions ?? '—'} of {data.freshness?.window_sessions ?? '—'} sessions from a live capture
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: DIM }}>percentile window</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {data.freshness?.window_sessions ?? '—'}/{data.freshness?.window_needed ?? '—'} sessions
                  <span style={{ marginLeft: 6, fontSize: 11, color: data.freshness?.window_complete ? GREEN : AMBER }}>
                    {data.freshness?.window_complete ? 'no gaps' : 'gaps'}
                  </span>
                </div>
              </div>
            </div>
            {data.freshness?.captured_sessions === 0 && (
              <div style={{ ...S.small, color: AMBER, marginTop: 8 }}>
                Every reading on this page came from the committed CSV baseline, not a live capture.
              </div>
            )}
            {data.freshness?.window_complete === false && data.freshness?.window_missing?.length > 0 && (
              <div style={{ ...S.small, color: AMBER, marginTop: 8 }}>
                Missing from the trailing window: {data.freshness.window_missing.slice(0, 6).join(', ')}
                {data.freshness.window_missing.length > 6 ? ` +${data.freshness.window_missing.length - 6} more` : ''}
              </div>
            )}
            {data.jobs?.reason && (
              <div style={{ ...S.small, color: GREY, marginTop: 8 }}>{data.jobs.reason}</div>
            )}
            <div style={{ ...S.small, marginTop: 8 }}>
              The signal updates once per session at 15:05 CT. Sessions with no captured reading leave
              a permanent hole in the 60-session percentile window.
            </div>
            <div style={{ ...S.small, marginTop: 4 }}>
              The morning alert only fires when the verdict is not NEUTRAL — a quiet day is silent by design.
            </div>
          </Collapse>
        </Zone>

        {/* FORWARD RECORD — the only numbers on this page that are not a
            backtest. Placed at the top of the evidence zone deliberately: a
            live sample, however small, outranks a 898-trade backtest when the
            question is "is this working NOW". */}
        <Zone label="Live record since the signal shipped">
          {(() => {
            const L = data.ledger || {};
            const n = L.n_settled || 0;
            const wr = L.win_rate;
            const bt = L.backtest_win_rate;
            const off = (wr != null && bt != null) ? (wr - bt) : null;
            return (
              <div style={S.card}>
                {L.reason && <div style={{ ...S.small, marginBottom: 8 }}>{L.reason}</div>}
                {n === 0 ? (
                  <div style={{ fontSize: 13, color: '#c6cbd8' }}>
                    No settled sessions yet. The first decision is recorded at the 08:05 CT
                    alert and settles at that session's close.
                    <div style={{ ...S.small, marginTop: 6 }}>
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
                <div style={{ ...S.small, marginTop: 8 }}>
                  <b style={{ color: '#c6cbd8' }}>Dollars are not tracked.</b> Outcome needs only
                  the close, which is already stored; P&amp;L needs the credit taken at 11:05 and
                  nothing captures an intraday quote. Recording an invented credit would produce
                  a tidy P&amp;L line that looked like evidence, so this tracks what it can actually
                  measure — whether the short strike held, and by how much it failed.
                </div>
              </div>
            );
          })()}
        </Zone>

        <Zone label="Why believe this">
          {/* WHAT THE VETO IS WORTH — the honest headline of the page. The
              evidence tables above sell the signal; this is what it actually
              adds on top of the strategy that was already there. */}
          <Collapse title="What the veto is actually worth" subtitle="always-on vs the gamma veto">
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
          </Collapse>

          {/* HOW TO TRADE THIS — verdict-aware, real-fill backtests. The page
              explained the state and the evidence but never said what the
              trade is; this closes that gap. Highlights the block matching
              the live verdict, mutes the others. Advisory only — this is
              what the backtest says, not instructions to trade. */}
          <Collapse title="If the signal changes" subtitle="the other verdicts, and what each one means">
            {(() => {
              const TRADE_BLOCKS = [
                {
                  key: 'sell', accent: GREEN,
                  active: verdict === 'SELL_PREMIUM' || verdict === 'NEUTRAL',
                  title: 'SELL_PREMIUM / NEUTRAL — the common case',
                  body: (
                    <>
                      <div style={{ fontSize: 13, marginBottom: 6 }}>
                        SPY 0DTE put spread. Short strike round(spot) − 2, $2 wide. Enter 11:05 ET,
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
                      <div style={{ fontSize: 12, color: '#c6cbd8', lineHeight: 1.7, marginBottom: 6 }}>
                        <div>daily mean +$3.35 · median +$19.30 · worst −$198</div>
                        <div>weekly +$15, 116 of 185 up</div>
                        <div>monthly +$62, 29 of 44 up, worst −$423</div>
                        <div>yearly +$569 · +$1,217 · +$314 · +$629</div>
                      </div>
                      <div style={{ fontSize: 12.5, color: AMBER }}>
                        Worst single day −$198 — 20% of a $1,000 account in one afternoon.
                      </div>
                      <div style={{ fontSize: 12, color: AMBER, marginTop: 6, lineHeight: 1.5 }}>
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
                  title: 'SQUEEZE_WATCH',
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
                      <div style={{ fontSize: 12.5, color: RED, fontWeight: 700 }}>
                        Must be 0.25 delta, NOT at-the-money — at 0.50 delta the same signal LOSES
                        $43/trade versus benchmark. The edge is convexity per dollar, not delta.
                      </div>
                    </>
                  ),
                },
                {
                  key: 'no_sell', accent: RED,
                  active: verdict === 'NO_SELL',
                  title: 'NO_SELL',
                  body: (
                    <div style={{ fontSize: 13 }}>
                      Skip the put spread entirely. Fires on roughly 9% of sessions (net gamma below
                      −$10B).
                    </div>
                  ),
                },
              ];

              return (
                <div style={{ opacity: data.freshness?.stale ? 0.5 : 1 }}>
                  {data.freshness?.stale && (
                    <div style={{ fontSize: 12, fontWeight: 700, color: AMBER, marginBottom: 10 }}>
                      Stale reading — do not act on this today.
                    </div>
                  )}
                  {TRADE_BLOCKS.map(b => (
                    <div key={b.key} style={{
                      background: '#0e1220', border: `1px solid ${b.active ? b.accent + '66' : '#232a3d'}`,
                      borderRadius: 10, padding: '12px 14px', marginBottom: 12, opacity: b.active ? 1 : 0.5,
                    }}>
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: b.active ? b.accent : DIM, marginBottom: 6 }}>
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
                  <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6 }}>
                    Neither trade has been forward-tested. The sell side has a blind out-of-sample
                    decade behind it; the buy side is the best of 48 structures searched.
                  </div>
                </div>
              );
            })()}
          </Collapse>

          {/* EVIDENCE TABLE */}
          <Collapse title="Squeeze rate by gamma percentile" subtitle="the core evidence">
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
              Gamma oversold + VIX at its highs → <b style={{ color: '#c6cbd8' }}>15.13% squeeze rate, 0.00% crash rate</b> (n=119).
              Monotone, zero squeezes in the top quartile. Overbought gamma is NOT a crash signal —
              it is the safest measured state to sell premium.
            </div>
            <div style={{ ...S.small, marginTop: 8 }}>
              Neither threshold is the best-fitting one. Bottom-decile squeeze rate is 7.8–11.4% at every
              lookback from 30 to 252 sessions and monotone at all of them; 60 shipped, but 120 scores
              better. Every percentile cut from 0.05 to 0.30 gives a 2.5–3.4x lift; 0.20 shipped, but 0.15
              scores better. Decile rank correlation −0.861. Shipping the non-optimal value is deliberate —
              the result is not a knife edge.
            </div>
          </Collapse>

          {/* FUEL EVIDENCE TABLE */}
          <Collapse title="Squeeze rate by fuel sextile" subtitle="forced hedging vs liquidity">
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
          </Collapse>

          {/* CALENDAR EVIDENCE TABLE — renders always; the old month_end footnote
              only showed on month-end days, so the tilts were invisible the
              rest of the time. */}
          <Collapse title="Scheduled flow on oversold days" subtitle="calendar tilts">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>event</th><th style={S.th}>squeeze rate</th><th style={S.th}>vs base</th><th style={S.th}>n</th>
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
          </Collapse>

          {/* RECALL TABLE — the page above shows only precision (rate WITHIN a
              bucket); this is how much of the phenomenon each filter actually
              catches. */}
          <Collapse title="Recall — what it catches" subtitle="33 of 33 caught, 3.4% precision">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560, marginBottom: 10 }}>
                <thead>
                  <tr>
                    <th style={S.th}>filter</th><th style={S.th}>recall</th><th style={S.th}>precision</th><th style={S.th}>lift</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={S.td}>net_gex &lt; 0</td>
                    <td style={S.td}>100%</td>
                    <td style={S.td}>3.4%</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>1.72x</td>
                  </tr>
                  <tr>
                    <td style={S.td}>net_gex &lt; −$5B</td>
                    <td style={S.td}>57.6%</td>
                    <td style={S.td}>4.6%</td>
                    <td style={S.td}>—</td>
                  </tr>
                  <tr>
                    <td style={S.td}>net_gex &lt; −$10B</td>
                    <td style={S.td}>18.2%</td>
                    <td style={S.td}>7.1%</td>
                    <td style={S.td}>—</td>
                  </tr>
                  <tr>
                    <td style={S.td}>vix_ratio &lt; 0.80</td>
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
              vix_ratio of 0.97, fear at its peak. The same ratio is correctly protective for a premium
              seller and actively wrong for anyone hunting squeezes. Both are true at once.
            </div>
          </Collapse>

          {/* FALSIFICATION TABLE */}
          <Collapse title="What happened the last 22 times gamma went below −$10B" subtitle="the falsification test">
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
          </Collapse>
        </Zone>
      </div>
    </div>
  );
}
