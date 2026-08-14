// Risk Advisor v2 — a PLAYBOOK, not a readout.
// Answers, in order: (1) what should I do RIGHT NOW and why, (2) what is the
// market doing intraday vs what was implied, (3) what's the outlook for the
// next session, (4) how has this tool actually graded out vs its backtest,
// (5) how do I read all of it. ADVISORY ONLY — no bot consumes this.
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import { ShieldAlert, ShieldCheck, Activity, Eye, Target, TrendingUp } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', BLUE = '#60a5fa', DIM = '#8b93a7';
const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 13, fontWeight: 700, marginBottom: 10 },
  th: { textAlign: 'left', color: DIM, fontSize: 12, padding: '6px 10px' },
  td: { padding: '6px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
  small: { fontSize: 11, color: DIM },
  big: { fontSize: 20, fontWeight: 700 },
};

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

function pct(x, d = 1) { return x == null ? '—' : (100 * x).toFixed(d) + '%'; }

// Null-safe one-line label for a flow_pm[clock] entry — no snapshot yet
// shows the status string, otherwise the worse of the two z-scores.
function pmLabel(e) {
  if (!e) return '—';
  if (e.status !== 'snapshot') return e.status;
  const z = Math.max(e.putv_z ?? -Infinity, e.totv_z ?? -Infinity);
  const zt = Number.isFinite(z) ? z.toFixed(1) : '—';
  return e.spike ? `SPIKE z${zt}` : `z${zt}`;
}

// The action each signal demands when ACTIVE, with its backtested "why".
// `plain` = what the signal means in everyday speech — the page must never
// require the reader to decode a z-score or an index name to act correctly.
const PLAYBOOK = [
  { key: 'backwardation', name: 'Backwardation (VIX > VIX3M)',
    plain: 'In plain English: short-term fear is higher than long-term fear — the market is in stress RIGHT NOW.',
    action: 'DO NOT open new premium-selling trades today',
    why: 'Stress is here. Skipping these days improved the condor book from 0.32 to 0.41 return-per-drawdown over 7 years.' },
  { key: 'flag_vix1d', name: 'VIX1D flag (implied 1-day move > 1%)',
    plain: 'In plain English: options are pricing a bigger-than-1% move by tomorrow — a swing day is likely.',
    action: 'Sell SMALLER than usual, or skip today',
    why: 'When this flag is on, 42.8% of days move ≥1% (vs 26% overall). It catches 68% of all big days.' },
  { key: 'flow_spike', name: '10:00 CT flow spike (put/total vol z > 2)',
    plain: 'In plain English: unusually heavy option buying this morning vs the last 3 months — someone is bracing for a move TODAY.',
    action: 'No new SAME-DAY (0DTE) trades; tighten today’s exits. Multi-day trades: ignore this one',
    why: 'Big rest-of-day move odds jump to 28.6% vs 12.1% base (~4.8σ). Matters for SAME-DAY trades; a 5-day condor should ignore it.'
      + ' Re-checked at 12:00 (29.3% vs 17.0%) and 13:30 CT (17.0% vs 8.4%) — a fade note posts if a morning spike does not persist.'
      + ' A rolling watcher also polls every 10 minutes between 10:36 and 14:00 CT (registry #39: 34.2% vs 22.4% base, 1.53x) to catch a spike the three fixed clocks miss — it stays silent if a fixed clock already caught it.' },
  { key: 'double_floor', name: 'Double floor (VVIX<85 & VIX<14)',
    plain: 'In plain English: the market is unusually calm AND calm about staying calm — the best measured day to sell premium.',
    action: 'GREEN LIGHT: sell premium at your normal size',
    why: 'Across 56 such sessions: ZERO next-day moves ≥1.5%. The calmest state in the data.' },
];

// Plain-speech glossary — every term the page uses, defined once.
const GLOSSARY = [
  ['VIX / VIX3M / VIX9D', 'Fear gauges: the price of insurance on the S&P over the next 30 days / 3 months / 9 days. Higher = more expected movement.'],
  ['VIX1D', 'Same idea for just the NEXT DAY. VIX1D of 16 ≈ options pricing a ±1% move by tomorrow.'],
  ['VVIX', 'The fear gauge OF the fear gauge — how nervous the market is about VIX itself jumping. Under 85 = genuinely relaxed.'],
  ['Backwardation', 'Short-term insurance costing MORE than long-term. Normally it’s the reverse; when it flips, stress is happening now.'],
  ['z-score (flow z)', 'How unusual today is vs the last 63 sessions. z=0 typical, z=2 ≈ top 2% unusual. Spike = z above 2.'],
  ['Expected move', 'The size of day the options market has paid for, from VIX1D. The intraday chart’s band; past 100% budget = a bigger day than priced.'],
  ['0DTE / DTE', 'Days To Expiry. 0DTE = expires today (same-day trades). "Nearest exp 3 DTE" = closest position expiry is 3 trading days out.'],
  ['Precision / recall', 'Precision 42.8%: when the flag fires, a big move follows 42.8% of the time (vs 26% for any random day). Recall 68%: of all big days, the flag catches 68%.'],
  ['Brier score', 'Accuracy of probability forecasts — lower is better. 0.168 backtested; the scorecard degrades the signal if live drifts above ~0.22.'],
  ['ret/DD', 'Yearly profit divided by worst losing streak (drawdown). 0.41 = makes 41% of its worst dip back per year. Our bar for "worth trading" is 0.5+.'],
  ['Quiet day', 'Previous close had VIX under 16. The regime where daily warning signals are mostly blind — the flow snapshot exists to cover it.'],
  ['Pre-registered', 'The test’s rule and pass bar were written down BEFORE seeing results — so a "winner" can’t be an after-the-fact cherry-pick.'],
];

// Phase-aware window-status text for the recipe card — mirrors the phases
// GET /recipe emits (before_am/am_open/between/pm_open/done/weekend). The
// clock literals here match the ebb/ebb_pm registry windows the backend
// reads from (10:05-10:20 and 13:05-13:10 CT).
function recipeWindowLabel(r) {
  if (!r) return null;
  const m = r.minutes_to_next_window;
  switch (r.phase) {
    case 'before_am': return `next window 10:05 CT in ${m}m`;
    case 'am_open': return 'AM window OPEN now (until 10:20 CT)';
    case 'between': return `PM window 13:05 CT in ${m}m`;
    case 'pm_open': return 'PM window OPEN now (until 13:10 CT)';
    case 'done': return 'done for today — next: tomorrow 10:05 CT';
    case 'weekend': return 'weekend — next window Monday 10:05 CT';
    default: return null;
  }
}

// The three validated flow clocks, CT. Used for the "next check" countdown.
const FLOW_CLOCKS_CT = [[10, 0], [12, 0], [13, 30]];

function nextFlowCheck() {
  const now = new Date();
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  const mins = ct.getHours() * 60 + ct.getMinutes();
  const isWeekday = ct.getDay() >= 1 && ct.getDay() <= 5;
  if (isWeekday) {
    for (const [h, m] of FLOW_CLOCKS_CT) {
      if (mins < h * 60 + m) {
        const mm = h * 60 + m - mins;
        return { label: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')} CT`,
                 in: mm >= 60 ? `${Math.floor(mm / 60)}h ${mm % 60}m` : `${mm}m` };
      }
    }
  }
  const nextDay = ct.getDay() === 5 && mins >= 13 * 60 + 30 ? 'Monday'
    : ct.getDay() === 6 || ct.getDay() === 0 ? 'Monday' : 'tomorrow';
  return { label: '10:00 CT', in: nextDay };
}

export default function RiskAdvisorPage() {
  const [state, setState] = useState(null);
  const [hist, setHist] = useState([]);
  const [score, setScore] = useState(null);
  const [intra, setIntra] = useState(null);
  const [err, setErr] = useState(null);
  const [range, setRange] = useState(90);         // 0 = "Today" clock view
  const [tick, setTick] = useState(0);            // 30s countdown re-render
  const [alog, setAlog] = useState(null);
  const [ebb, setEbb] = useState(null);
  const [recipe, setRecipe] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const days = range === 0 ? 30 : range;    // Today view still needs recent context
        const [s, h, sc, ia, al, eb, rc] = await Promise.all([
          fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/history?days=${days}`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/scorecard`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/intraday`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/alert-log`).then(r => r.json()).catch(() => null),
          fetch(`${API_URL}/api/spreadworks/bots/ebb/status`).then(r => r.json()).catch(() => null),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/recipe`).then(r => r.json()).catch(() => null),
        ]);
        if (!live) return;
        setState(s); setScore(sc); setIntra(ia); setAlog(al); setEbb(eb); setRecipe(rc);
        setHist((h.days || []).map(d => ({
          ...d, label: d.d.slice(5),
          spike: (d.putv_z > 2 || d.totv_z > 2) ? Math.max(d.putv_z, d.totv_z) : null,
        })));
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    const t = setInterval(load, 60 * 1000);       // live: refresh every minute
    const t2 = setInterval(() => setTick(x => x + 1), 30 * 1000);
    return () => { live = false; clearInterval(t); clearInterval(t2); };
  }, [range]);

  if (err) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Risk Advisor unavailable: {err}</div></div></div>;
  if (!state) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Loading…</div></div></div>;

  const sig = state.signals || {}, flow = state.flow || {};
  const liveQ = state.live, out = state.outlook;
  const active = {
    backwardation: sig.backwardation, flag_vix1d: sig.flag_vix1d,
    flow_spike: !!flow.spike, double_floor: sig.double_floor,
  };
  const activeRisk = active.backwardation || active.flag_vix1d || active.flow_spike;
  const headColor = activeRisk ? RED : active.double_floor ? GREEN : BLUE;
  const HeadIcon = activeRisk ? ShieldAlert : ShieldCheck;

  // one-sentence verdict — the thing to read if you read nothing else
  const verdict = activeRisk
    ? 'RISK-OFF — at least one backtested danger signal is active. Follow the actions below.'
    : active.double_floor
      ? 'CALM FLOOR — statistically the safest state to sell premium at normal size.'
      : 'NORMAL — no signal active. Bots at normal size; nothing to do.';
  // the explicit instruction — no decoding required
  const todayAction = activeRisk
    ? 'TODAY: DO NOT SELL PREMIUM — reduce or skip. And do NOT buy premium instead: that was backtested and loses even more on days like this. Flat is the trade.'
    : active.double_floor
      ? 'TODAY: GREEN LIGHT — the best measured kind of day to sell premium at normal size.'
      : 'TODAY: trade your normal plan at normal size. Nothing here asks for a change.';

  // quiet-day shading for the ribbon
  const bands = []; let start = null;
  hist.forEach((d, i) => {
    if (d.quiet && start === null) start = i;
    if ((!d.quiet || i === hist.length - 1) && start !== null) {
      bands.push([hist[start].label, hist[d.quiet ? i : Math.max(i - 1, start)].label]);
      start = null;
    }
  });

  const fs = score?.flag_vix1d, cal = score?.calibration, fsp = score?.flow_spike;

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>Risk Advisor</h1>
        <p style={S.sub}>
          Advisory only — no bot reads this. Every signal was backtested and pre-registered
          (2026-08-12); the scorecard grades the tool against its own claims, live.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '0 0 20px' }}>
          {[['page refresh', 'every 60s'], ['index closes', 'daily, cached 30 min'],
            ['flow checks', '10:00 · 12:00 · 13:30 CT + rolling every 10m 10:36-14:00'],
            ['intraday bars', '5-min, live'],
            ['Discord alerts', '08:05 · 08:06 EM · 10:06 · 12:06 · 13:36 · rolling */10 · breach watch CT']].map(([k, v]) => (
            <span key={k} style={{ fontSize: 11, color: DIM, border: '1px solid #232a3d',
                                   borderRadius: 6, padding: '3px 8px' }}>
              <b style={{ color: '#c6cbd8' }}>{k}</b> · {v}
            </span>
          ))}
        </div>

        {/* 1 ─ VERDICT */}
        <div style={{ ...S.card, borderColor: headColor + '55', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <HeadIcon size={30} color={headColor} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: headColor }}>{verdict}
              <InfoTip text="The one-line answer for today, from yesterday's closes. RISK-OFF = a backtested danger signal is active — follow the playbook table. CALM FLOOR = statistically the safest premium-selling state. NORMAL = no signal, trade normal size. Recomputed on every refresh; the underlying index closes update once per day after the close." />
            </div>
            <div style={{ fontSize: 13.5, marginTop: 6, color: '#c6cbd8' }}>{todayAction}</div>
            {state.macro && (state.macro.today || state.macro.next) && (
              <div style={{ ...S.small, marginTop: 6 }}>
                {state.macro.today
                  ? <span style={{ color: AMBER, fontWeight: 700 }}>📅 {state.macro.today} TODAY — announcement days run hotter; treat warnings with extra respect. </span>
                  : null}
                {state.macro.next && <span>Next macro event: {state.macro.next.label} on {state.macro.next.d}. </span>}
                <span>Sourced from the Fed &amp; BLS official schedules.</span>
              </div>
            )}
            <div style={{ ...S.small, marginTop: 4 }}>
              As of close {state.asof_close} · VIX {state.indices?.vix?.toFixed(1)} ·
              VIX1D {state.indices?.vix1d?.toFixed(1)} · VIX9D {state.indices?.vix9d?.toFixed(1)} ·
              VVIX {state.indices?.vvix?.toFixed(0)}
            </div>
          </div>
        </div>

        {/* 1b ─ THE RECIPE: today's validated manual ticket (registry #23b/#41) */}
        <div style={S.card}>
          <div style={S.cardTitle}>Today's validated trade — the recipe
            <InfoTip text="The one daily edge that survived 44 registered backtests (registry #23b/#41): SPY same-day put spreads at two fixed clocks. $12.19/trade AM + $9.57/trade PM per 1-lot, positive all 5 blind years each, at real NBBO fills. EBB and EBB-PM run exactly this on paper — this card is for your manual ticket." />
          </div>
          {recipe && recipe.status === 'ok' ? (() => {
            const greyed = recipe.phase === 'weekend' || recipe.phase === 'done';
            const label = recipeWindowLabel(recipe);
            const windowOpen = recipe.phase === 'am_open' || recipe.phase === 'pm_open';
            return (<>
              <div
                onClick={() => navigator.clipboard?.writeText(
                  `SELL SPY ${recipe.short_strike}P / BUY ${recipe.long_strike}P — expires TODAY (${recipe.expiration})`)}
                title="Click to copy the ticket"
                style={{ fontSize: 18, fontWeight: 700, cursor: 'copy',
                         color: greyed ? DIM : '#e8ebf3' }}>
                SELL SPY {recipe.short_strike}P / BUY {recipe.long_strike}P — expires TODAY ({recipe.expiration})
              </div>
              <div style={{ ...S.small, marginTop: 4, color: greyed ? DIM : undefined }}>
                at spot ${recipe.spot?.toFixed?.(2) ?? recipe.spot}
              </div>
              {label && (
                <div style={{ fontSize: 13, marginTop: 6, fontWeight: 600,
                              color: windowOpen ? GREEN : DIM }}>
                  {label}
                </div>
              )}
              {recipe.credit_now != null && (
                <div style={{ fontSize: 13, marginTop: 8,
                              color: recipe.meets_floor ? GREEN : AMBER }}>
                  credit right now ≈ ${recipe.credit_now.toFixed(2)} — {recipe.meets_floor ? 'above' : 'BELOW'} the $0.10 validated floor
                  {!recipe.meets_floor && ' — skip if it stays below at entry time'}
                </div>
              )}
              <div style={{ ...S.small, marginTop: 10 }}>
                Size: 1 contract per $2,500–3,000 allocated. Worst observed day −$484/lot — the $5 wing is the survival mechanism.
              </div>
              <div style={{ marginTop: 10, padding: '10px 12px', background: '#2a1220',
                            border: `1px solid ${RED}55`, borderRadius: 8 }}>
                <div style={{ fontSize: 12.5, color: RED, fontWeight: 700 }}>
                  NO stop-loss and NO profit-target — exits were tested three separate ways and every one collapses the edge to ~$0. Settle at the close IS the trade.
                </div>
                <div style={{ fontSize: 12.5, color: RED, fontWeight: 700, marginTop: 6 }}>
                  Do NOT skip flagged days on this recipe — its backtest INCLUDES them; the calm-day gate was tested and cut the edge from $12.19 to $6.00/trade. The verdict above governs your OTHER trading.
                </div>
              </div>
              <div style={{ ...S.small, marginTop: 8 }}>
                Rich-credit days (top third vs trailing 63) averaged $14.90/trade vs $8.47 on lean days — registry #44; informational until the sizing step is validated.
              </div>
              <div style={{ ...S.small, marginTop: 8 }}>
                AM results: $12.19/tr, ret/DD 2.06 · PM: $9.57/tr, ret/DD 2.67 · pair ≈ $21.72/day per lot-pair, 5/5 blind years — n=930 sessions at NBBO fills.
              </div>
            </>);
          })() : (
            <div style={S.small}>
              {recipe?.status === 'no quote' ? 'quote unavailable' : 'recipe unavailable'}
            </div>
          )}
        </div>

        {/* 2 ─ PLAYBOOK: what to do right now */}
        <div style={S.card}>
          <div style={S.cardTitle}><Target size={13} style={{ verticalAlign: -2 }} /> What to do right now
            <InfoTip text="Each row is one validated signal. ACTIVE rows are lit — do what the action column says. The last column is the backtested evidence for WHY. SHARP/DEGRADED chips are the tool grading itself live: DEGRADED means live results fell below the backtest band and the signal should not be trusted until re-validated." />
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>
              <th style={S.th}>signal</th><th style={S.th}>state</th>
              <th style={S.th}>action when active</th><th style={S.th}>what the backtest says</th>
            </tr></thead>
            <tbody>
              {PLAYBOOK.map(p => {
                const h = score?.health?.[p.key === 'flow_spike' ? 'flow_spike' : p.key]?.status;
                const hc = h === 'DEGRADED' ? RED : h === 'sharp' ? GREEN : DIM;
                return (
                <tr key={p.key} style={{ opacity: active[p.key] ? 1 : 0.55 }}>
                  <td style={{ ...S.td, fontWeight: 600 }}>{p.name}
                    {h && <span style={{ fontSize: 9, fontWeight: 700, color: hc,
                      border: `1px solid ${hc}55`, borderRadius: 4, padding: '1px 5px',
                      marginLeft: 6, verticalAlign: 'middle' }}>
                      {h === 'DEGRADED' ? 'DEGRADED' : h === 'sharp' ? 'SHARP' : '…'}
                    </span>}
                    <div style={{ ...S.small, fontWeight: 400, marginTop: 3 }}>{p.plain}</div>
                  </td>
                  <td style={{ ...S.td, color: active[p.key] ? (p.key === 'double_floor' ? GREEN : RED) : DIM, fontWeight: 700 }}>
                    {active[p.key] ? 'ACTIVE' : 'off'}
                  </td>
                  <td style={S.td}>{p.action}</td>
                  <td style={{ ...S.td, ...S.small }}>{p.why}</td>
                </tr>
              ); })}
            </tbody>
          </table>
          {score?.health && Object.values(score.health).some(h => h.status === 'DEGRADED') && (
            <div style={{ fontSize: 12, color: RED, marginTop: 8, fontWeight: 600 }}>
              ⚠ A signal is DEGRADED — its live results have fallen below the backtest band.
              Treat it as unreliable until the research repo re-validates it.
            </div>
          )}
          {flow.status !== 'snapshot' && (
            <div style={{ ...S.small, marginTop: 8 }}>
              <Activity size={11} style={{ verticalAlign: -1 }} /> flow signal: {flow.status}
            </div>
          )}
          {state.flow_pm && (
            <div style={{ ...S.small, marginTop: 4 }}>
              afternoon re-checks: 12:00 {pmLabel(state.flow_pm['12:00'])} · 13:30 {pmLabel(state.flow_pm['13:30'])}
            </div>
          )}
          {state.flow_rolling && (
            <div style={{ ...S.small, marginTop: 4 }}>
              rolling watcher (10:36–14:00 CT, every 10m): {pmLabel({
                status: state.flow_rolling.captured_at ? 'snapshot' : 'no reading yet',
                putv_z: state.flow_rolling.putv_z, totv_z: state.flow_rolling.totv_z,
                spike: (state.flow_rolling.putv_z ?? -Infinity) > 2 || (state.flow_rolling.totv_z ?? -Infinity) > 2,
              })}{state.flow_rolling.fired_today ? ' · alerted today' : ''}
            </div>
          )}
        </div>

        {/* 3 ─ LIVE INTRADAY */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ ...S.card, flex: '1 1 300px' }}>
            <div style={S.cardTitle}><Activity size={13} style={{ verticalAlign: -2 }} /> Live intraday
              <InfoTip text="Live SPY vs what options implied for today. The bar fills as today's |move| consumes the VIX1D-implied expected move — past 100% the day is already bigger than options priced. Quote refreshes every 60s during market hours." />
            </div>
            {liveQ ? (<>
              <div style={S.big}>
                SPY {liveQ.last?.toFixed(2)}{' '}
                <span style={{ color: (liveQ.chg_pct ?? 0) >= 0 ? GREEN : RED, fontSize: 15 }}>
                  {(liveQ.chg_pct ?? 0) >= 0 ? '+' : ''}{liveQ.chg_pct?.toFixed(2)}%
                </span>
              </div>
              {liveQ.move_budget_used != null && (<>
                <div style={{ ...S.small, margin: '10px 0 4px' }}>
                  Expected-move budget used (|move| vs the {liveQ.expected_move_pct?.toFixed(2)}% VIX1D-implied day):
                </div>
                <div style={{ background: '#1a2030', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                  <div style={{
                    width: Math.min(100, 100 * liveQ.move_budget_used) + '%', height: '100%',
                    background: liveQ.move_budget_used > 1 ? RED : liveQ.move_budget_used > 0.6 ? AMBER : GREEN,
                  }} />
                </div>
                <div style={{ ...S.small, marginTop: 4 }}>
                  {pct(liveQ.move_budget_used, 0)} — past 100% the day has already exceeded what options implied.
                </div>
              </>)}
            </>) : <div style={S.small}>quote unavailable</div>}
          </div>

          {/* 4 ─ FORWARD OUTLOOK */}
          <div style={{ ...S.card, flex: '1 1 300px' }}>
            <div style={S.cardTitle}><TrendingUp size={13} style={{ verticalAlign: -2 }} /> Next-session outlook
              <InfoTip text="Tomorrow's plan, recomputed after each close. Probabilities are calibrated (Albers RVRP adjustment): P(±1% day) is the headline. The grade maps probability to action: normal → reduce size → widen strikes or skip → stand down." />
            </div>
            {out ? (<>
              <div style={{ fontSize: 14, marginBottom: 8 }}>
                Grade: <b style={{ color: out.grade === 'normal' ? GREEN : out.grade === 'stand_down' ? RED : AMBER }}>
                  {out.grade.replace('_', ' ').toUpperCase()}</b>
                {out.flag_vix1d && <span style={{ color: AMBER }}> · FLAG ON</span>}
              </div>
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <tbody>
                  <tr><td style={S.td}>P(±1% day)</td><td style={{ ...S.td, fontWeight: 700 }}>{pct(out.p_big_adj)}</td>
                      <td style={{ ...S.td, ...S.small }}>calibrated</td></tr>
                  <tr><td style={S.td}>P(down ≤ −1%)</td><td style={{ ...S.td, fontWeight: 700 }}>{pct(out.p_down_adj)}</td>
                      <td style={{ ...S.td, ...S.small }}>calibrated</td></tr>
                  <tr><td style={S.td}>P(2σ down-tail)</td><td style={{ ...S.td, fontWeight: 700 }}>{pct(out.p_down2s)}</td>
                      <td style={{ ...S.td, ...S.small }}>vs 2.3% neutral</td></tr>
                  <tr><td style={S.td}>Implied move</td><td style={{ ...S.td, fontWeight: 700 }}>±{out.implied_move_pct?.toFixed(2)}%</td>
                      <td style={{ ...S.td, ...S.small }}>from VIX1D {out.vix1d?.toFixed(1)}</td></tr>
                </tbody>
              </table>
              <div style={{ fontSize: 13, marginTop: 8, padding: '8px 10px',
                            background: '#1a2030', borderRadius: 8 }}>
                <b>How to trade it:</b>{' '}
                {out.grade === 'normal' && 'run tomorrow at your normal plan and size — nothing here asks for a change.'}
                {out.grade === 'reduce_size' && 'cut the size of any new premium-selling entries tomorrow; keep the structure the same.'}
                {out.grade === 'widen_or_skip' && 'widen strikes further from the money on tomorrow\'s entries, or skip the day entirely.'}
                {out.grade === 'stand_down' && 'no new premium-selling entries tomorrow, full stop. Flat — not switched to the other side.'}
                {' '}<span style={S.small}>(EBB is unaffected by design — its validated edge includes every regime, and gating it was tested and made it worse.)</span>
              </div>
              <div style={{ ...S.small, marginTop: 6 }}>From closes of {out.asof_close}. Updates after each close.</div>
            </>) : <div style={S.small}>outlook needs VIX1D + return history — retrying</div>}
          </div>
        </div>

        {/* INTRADAY CHART: today's tape vs the expected move */}
        <div style={S.card}>
          <div style={S.cardTitle}>Today's tape vs the expected move
            <InfoTip text="Today's SPY 5-minute path vs the VIX1D expected-move band (grey). Price escaping the band = an outsized day in progress. The dashed vertical line marks the 10:00 CT flow snapshot — the one moment each day the flow-spike signal reads. Updates every minute." />
          </div>
          {intra?.bars?.length ? (() => {
            const b = intra.band_pct || 1;
            const ext = Math.max(b * 1.3, ...intra.bars.map(x => Math.abs(x.chg_pct ?? 0) * 1.1));
            const hasSnap = intra.bars.some(x => x.t <= '10:00');
            return (
              <div style={{ width: '100%', height: 220 }}>
                <ResponsiveContainer>
                  <ComposedChart data={intra.bars} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                    {intra.band_pct != null && (
                      <ReferenceArea y1={-b} y2={b} fill={AMBER} fillOpacity={0.05} />
                    )}
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                    <YAxis domain={[-ext, ext]} ticks={[-b, -b / 2, 0, b / 2, b]}
                           tickFormatter={v => `${v.toFixed(2)}%`}
                           tick={{ fontSize: 10, fill: '#5b6478' }} />
                    <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                             formatter={v => (v == null ? '—' : `${Number(v).toFixed(2)}%`)} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <ReferenceLine y={0} stroke="#232a3d" />
                    {intra.band_pct != null && (<>
                      <ReferenceLine y={b} stroke={AMBER} strokeDasharray="4 4" />
                      <ReferenceLine y={-b} stroke={AMBER} strokeDasharray="4 4" />
                    </>)}
                    {hasSnap && <ReferenceLine x="10:00" stroke={DIM} strokeDasharray="3 3" />}
                    <Line dataKey="chg_pct" name="SPY % vs prev close" stroke={BLUE} dot={false} strokeWidth={1.8} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            );
          })() : <div style={S.small}>{intra?.status || 'no intraday data yet — bars appear after the 8:30 CT open'}</div>}
        </div>

        {/* 5 ─ SCORECARD: the tool grading itself */}
        <div style={S.card}>
          <div style={S.cardTitle}>Report card — is the tool keeping its promises?
            <InfoTip text="Every claim this page makes was a promise from a backtest. This card checks each promise against what ACTUALLY happened in live sessions. Read the verdict line first; the table is the evidence. If live results fall materially below promise, the signal is automatically marked DEGRADED and should not be trusted until re-validated." />
          </div>
          {score ? (() => {
            const H = score.health || {};
            const graded = Object.entries(H).filter(([, v]) => ['sharp', 'DEGRADED', 'warming_up'].includes(v?.status));
            const bad = graded.filter(([, v]) => v.status === 'DEGRADED').map(([k]) => k);
            const warming = graded.filter(([, v]) => v.status === 'warming_up').map(([k]) => k);
            const rec = score.recent || [];
            const n = { hit: 0, false_alarm: 0, missed: 0, clear: 0 };
            rec.forEach(r => { n[r.grade] = (n[r.grade] || 0) + 1; });
            return (<>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10,
                            color: bad.length ? RED : GREEN }}>
                {bad.length
                  ? `⚠ BELOW PROMISE: ${bad.join(', ')} — treat as unreliable until re-validated.`
                  : `✅ Verdict right now: every graded signal is performing inside its promised range.`}
                {warming.length > 0 && <span style={{ color: DIM, fontWeight: 400 }}>
                  {' '}({warming.join(', ')} still collecting enough live data to judge)</span>}
              </div>
              <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 10 }}>
                <thead><tr>
                  <th style={S.th}>the promise</th>
                  <th style={S.th}>what actually happened ({score.window_sessions} live sessions)</th>
                  <th style={S.th}>promised</th>
                </tr></thead>
                <tbody>
                  <tr><td style={S.td}>When the danger flag fires, a big day follows
                        <div style={S.small}>VIX1D flag precision — higher is better</div></td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{pct(fs?.precision)} of flagged days moved ≥1%</td>
                      <td style={S.td}>{pct(fs?.backtest_precision)}</td></tr>
                  <tr><td style={S.td}>Most big days get flagged in advance
                        <div style={S.small}>VIX1D flag recall — higher is better</div></td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{pct(fs?.recall)} of big days were caught</td>
                      <td style={S.td}>{pct(fs?.backtest_recall)}</td></tr>
                  <tr><td style={S.td}>The printed probabilities are honest
                        <div style={S.small}>Brier score — LOWER is better; 0 = perfect</div></td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{cal?.brier_p_big_adj?.toFixed(3) ?? '—'}</td>
                      <td style={S.td}>{cal?.backtest_brier} (degrades above ~0.22)</td></tr>
                  <tr><td style={S.td}>Morning volume spikes mark dangerous days
                        <div style={S.small}>big-move rate on spike days vs ordinary days</div></td>
                      <td style={{ ...S.td, fontWeight: 700 }}>{pct(fsp?.big_move_rate_on_spike)} vs {pct(fsp?.big_move_rate_otherwise)}</td>
                      <td style={S.td}>28.6% vs 12.1%</td></tr>
                </tbody>
              </table>
              <div style={{ ...S.small, marginBottom: 6 }}>
                <b style={{ color: '#c6cbd8' }}>Last {rec.length} sessions in words:</b>{' '}
                <span style={{ color: GREEN }}>{n.hit} correct warning{n.hit === 1 ? '' : 's'}</span> ·{' '}
                <span style={{ color: AMBER }}>{n.false_alarm} false alarm{n.false_alarm === 1 ? '' : 's'} (cost: premium skipped for nothing)</span> ·{' '}
                <span style={{ color: RED }}>{n.missed} big day{n.missed === 1 ? '' : 's'} MISSED</span> ·{' '}
                {n.clear} correctly-quiet day{n.clear === 1 ? '' : 's'}. Missed days are the expensive kind — watch that number.
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {rec.map(r => {
                  const c = r.grade === 'hit' ? GREEN : r.grade === 'false_alarm' ? AMBER : r.grade === 'missed' ? RED : '#2a3145';
                  const t = r.grade === 'hit' ? '✓' : r.grade === 'false_alarm' ? '✗' : r.grade === 'missed' ? '●' : '−';
                  return (
                    <div key={r.d} title={`${r.d}: SPY ${r.ret > 0 ? '+' : ''}${r.ret}% — ${r.grade.replace('_', ' ')}`}
                         style={{ width: 26, height: 26, borderRadius: 5, background: c + '33',
                                  border: `1px solid ${c}`, color: c, fontSize: 12, fontWeight: 700,
                                  display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {t}
                    </div>
                  );
                })}
              </div>
              {fsp?.note && <div style={{ ...S.small, marginTop: 8 }}>{fsp.note}</div>}
            </>);
          })() : <div style={S.small}>computing…</div>}
        </div>

        {/* 5b ─ THE EVIDENCE: full backtest results behind every signal */}
        <div style={S.card}>
          <div style={S.cardTitle}>The evidence — full backtest results
            <InfoTip text="Every number that drives this page, with its base rate and sample. A hit rate without its base rate lies. All trials were pre-registered (hypothesis fixed before results were seen) in ironforge-data/risk_advisor/trials_registry.md; signals from close t−1, tradeable next session — no look-ahead." />
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 10 }}>
            <thead><tr>
              <th style={S.th}>signal</th><th style={S.th}>backtest result</th>
              <th style={S.th}>base rate / sample</th>
            </tr></thead>
            <tbody>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>Backwardation skip</td>
                <td style={S.td}>Condor book <b>0.32 → 0.41 ret/DD</b> when skipping these days</td>
                <td style={{ ...S.td, ...S.small }}>economic test on the real SPY condor stream, 7 years</td>
              </tr>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>VIX1D flag</td>
                <td style={S.td}><b>42.8% precision / 68% recall</b> on ≥1% days</td>
                <td style={{ ...S.td, ...S.small }}>vs 26% of all days moving ≥1% — flag ≈ doubles the odds</td>
              </tr>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>10:00 CT flow spike</td>
                <td style={S.td}>Big rest-of-day move <b>28.6% vs 12.1%</b> (~4.8σ), fires 5.6% of days</td>
                <td style={{ ...S.td, ...S.small }}>904 sessions 2023→. Magnitude only — direction tested, all t &lt; 1. Gating 5-DTE condors on it FAILS (0.24→0.21 ret/DD): same-day signal, same-day use</td>
              </tr>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>Double floor</td>
                <td style={S.td}><b>0 of 56</b> sessions moved ≥1.5% next day</td>
                <td style={{ ...S.td, ...S.small }}>strongest state in the data — but a small sample, weight accordingly</td>
              </tr>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>Outlook probabilities</td>
                <td style={S.td}>Raw VIX1D = best ranker (<b>PR-AUC 0.466</b>); RVRP-adjusted = best calibration (<b>Brier ~0.168</b>)</td>
                <td style={{ ...S.td, ...S.small }}>beat HAR-RV models (0.37–0.40) and a 12-feature ML model (0.033 — failed its gate, scrapped). Adjusted for printed probabilities, raw for flagging — pattern replicated 3×</td>
              </tr>
              <tr>
                <td style={{ ...S.td, fontWeight: 600 }}>2σ down-tail</td>
                <td style={S.td}>Near-unpredictable: best signal PR-AUC <b>0.049 vs 0.014</b> base (3.5× lift, weak)</td>
                <td style={{ ...S.td, ...S.small }}>shown for context; nothing on this page gates on it, deliberately</td>
              </tr>
            </tbody>
          </table>
          <div style={S.small}>
            Standard: every claim rests on multi-year windows including blind years — a 2-year walk-forward
            once read +1.28 on a strategy that was −0.05 over 5 blind years. Ideas that failed this bar
            (direction layers, regime arrows, long premium, ML model) are documented in the directional
            panel below instead of being quietly dropped.
          </div>
        </div>

        {/* 6 ─ FLOW RIBBON */}
        <div style={S.card}>
          <div style={S.cardTitle}>Option-flow unusualness — one reading per check
            <InfoTip text="How unusual SPY option volume is vs the trailing 63 sessions at the same clock, in z-scores (0 = normal, 2+ = spike). Red = put volume, amber = total volume, green = 0DTE OTM call volume (the squeeze tell). Shaded bands = quiet-VIX regimes where daily signals are blind — exactly where the flow signal earns its keep. Checks run at 10:00, 12:00 and 13:30 CT; alerts fire minutes after each." />
          </div>
          {(() => {
            void tick;                                   // 30s re-render for the countdown
            const nxt = nextFlowCheck();
            const cap = flow.captured_at
              ? new Date(flow.captured_at).toLocaleTimeString('en-US',
                  { hour: '2-digit', minute: '2-digit', hour12: false }) + ' CT'
              : null;
            return (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
                            marginBottom: 10 }}>
                <span style={{ fontSize: 11.5, color: '#c6cbd8', border: '1px solid #232a3d',
                               borderRadius: 6, padding: '3px 8px' }}>
                  last reading: <b>{cap || 'none yet today'}</b> · next check: <b>{nxt.label}</b> (in {nxt.in})
                </span>
                <span style={{ display: 'flex', gap: 4 }}>
                  {[[0, 'Today'], [30, '30d'], [90, '90d'], [180, '180d'], [365, 'Max']].map(([v, l]) => (
                    <button key={v} onClick={() => setRange(v)}
                      style={{ fontSize: 11, padding: '3px 9px', borderRadius: 6, cursor: 'pointer',
                               border: `1px solid ${range === v ? BLUE : '#232a3d'}`,
                               background: range === v ? 'rgba(96,165,250,0.12)' : 'transparent',
                               color: range === v ? BLUE : DIM, fontWeight: 600 }}>
                      {l}
                    </button>
                  ))}
                </span>
              </div>
            );
          })()}
          {range === 0 ? (
            <div>
              <div style={{ ...S.small, marginBottom: 10 }}>
                Today's three validated checks. z above 2 = spike (alerted); dashes = check not reached
                or its capture window was missed.
              </div>
              <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 560 }}>
                <thead><tr><th style={S.th}>check (CT)</th><th style={S.th}>put z</th>
                  <th style={S.th}>total z</th><th style={S.th}>state</th></tr></thead>
                <tbody>
                  {[['10:00', flow], ['12:00', state.flow_pm?.['12:00']], ['13:30', state.flow_pm?.['13:30']]].map(([k, f]) => {
                    const sp = f?.spike;
                    return (
                      <tr key={k}>
                        <td style={{ ...S.td, fontWeight: 600 }}>{k}</td>
                        <td style={S.td}>{f?.putv_z != null ? f.putv_z.toFixed(1) : '—'}</td>
                        <td style={S.td}>{f?.totv_z != null ? f.totv_z.toFixed(1) : '—'}</td>
                        <td style={{ ...S.td, fontWeight: 700,
                                     color: sp ? RED : f?.putv_z != null ? GREEN : DIM }}>
                          {sp ? 'SPIKE' : f?.putv_z != null ? 'normal' : (f?.status || 'pending')}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (<>
          <div style={{ ...S.small, marginBottom: 10 }}>
            10:00 CT reading, one point per session, trailing {range} sessions. Shaded = quiet-VIX
            regimes (the trap zone). Dots = spike days (z&gt;2).
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer>
              <ComposedChart data={hist} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                {bands.map(([a, b], i) => (
                  <ReferenceArea key={i} x1={a} x2={b} fill={BLUE} fillOpacity={0.07} />
                ))}
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                <YAxis tick={{ fontSize: 10, fill: '#5b6478' }}
                       domain={[d => Math.floor(Math.min(d, -3)), d => Math.ceil(Math.max(d, 5))]}
                       tickFormatter={v => Number(v).toFixed(0)} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#141824", border: "1px solid #232a3d", fontSize: 12 }} formatter={v => (v == null ? "—" : Number(v).toFixed(2))} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={2} stroke={RED} strokeDasharray="4 4" />
                <ReferenceLine y={0} stroke="#232a3d" />
                <Line dataKey="putv_z" name="put vol z" stroke={RED} dot={false} strokeWidth={1.5} />
                <Line dataKey="totv_z" name="total vol z" stroke={AMBER} dot={false} strokeWidth={1.2} />
                <Line dataKey="otm_call_0dte_z" name="0DTE OTM call z" stroke={GREEN} dot={false} strokeWidth={1.2} />
                <Line dataKey="spike" name="spike" stroke="none" dot={{ r: 4, fill: RED }} legendType="none" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          </>)}
        </div>

        {/* 7 ─ HOW TO USE / ALERT PLAYBOOK */}
        <div style={S.card}>
          <div style={S.cardTitle}>How to use this page — and the alerts it will drive
            <InfoTip text="Read top to bottom once; after that, the verdict + alerts are all you need day to day." />
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
            <li><b>Check the verdict each morning before 8:30 CT.</b> It already includes yesterday's closes. RISK-OFF → apply the actions in the playbook table for whichever signals are active.</li>
            <li><b>At ~10:05 CT the flow signal arrives.</b> A spike (z&gt;2) means same-day danger — it fires on ~6% of days and more than doubles big-move odds. It applies to same-day (0DTE) exposure, NOT to multi-day positions.</li>
            <li><b>A rolling watcher fills the gaps between clocks.</b> Every 10 minutes from 10:36 to 14:00 CT it checks the same z&gt;2 test against a per-minute baseline (registry #39). It only speaks up if the fixed 10:00/12:00/13:30 clocks missed the spike — no duplicate pings.</li>
            <li><b>The outlook card is tomorrow's plan.</b> After the close it updates; its grade (normal / reduce / widen-or-skip / stand down) uses calibrated probabilities.</li>
            <li><b>Trust the scorecard, not the promises.</b> If live precision/recall drifts materially below the backtest column for a sustained window, the signal is decaying and we revisit — that is the deal.</li>
            <li><b>Alerts are live (Discord):</b> RISK-OFF morning verdict at 08:05 CT (@here), flow spike at ~10:06 CT (@here), the rolling watcher any 10-minute mark 10:36–14:00 CT (@here, once per day, only if the fixed clocks missed it), calm floor as a quiet note. Silence at 08:05 means NORMAL — no news is the default.</li>
          </ol>
        </div>

        {/* 7b ─ DIRECTIONAL / LONG-PREMIUM VERDICTS */}
        <div style={S.card}>
          <div style={S.cardTitle}>Tested and REJECTED — the page will never suggest these
            <InfoTip text="You might expect 'don't sell premium' days to be 'buy premium' days. They are not — every directional/long-premium idea below was pre-registered and backtested (registry #18–#22, 2026-08-13) FOR THE PURPOSE OF REJECTING OR CONFIRMING IT. Red rows are ideas we tested to kill, so you never have to wonder whether they were tried. Nothing in this table is a trade suggestion." />
          </div>
          <div style={{ fontSize: 12.5, color: RED, fontWeight: 600, marginBottom: 10 }}>
            ⛔ Everything marked NO below was backtested in order to REJECT it. These are anti-recommendations —
            documented so the same tempting idea never has to be wondered about twice.
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 10 }}>
            <thead><tr>
              <th style={S.th}>idea</th><th style={S.th}>verdict</th><th style={S.th}>evidence</th>
            </tr></thead>
            <tbody>
              <tr>
                <td style={S.td}>Buy straddles/premium on flagged days</td>
                <td style={{ ...S.td, color: RED, fontWeight: 700 }}>NO — flat, not long</td>
                <td style={{ ...S.td, ...S.small }}>1-2DTE ATM straddles at the ask LOSE MORE on flag days (−$19.63/trade vs −$14.42 all days, negative 4/4 blind years). The flag comes from option prices — the market already charges for the move.</td>
              </tr>
              <tr>
                <td style={S.td}>Direction from GEX sign (neg gamma = momentum)</td>
                <td style={{ ...S.td, color: RED, fontWeight: 700 }}>NO edge</td>
                <td style={{ ...S.td, ...S.small }}>First-hour moves continue to the close 54.5% under negative gamma vs 54.7% positive vs 54.6% baseline — GEX sign adds nothing intraday.</td>
              </tr>
              <tr>
                <td style={S.td}>Trend/vol regime arrows (grind-up → calls, down-risk → puts)</td>
                <td style={{ ...S.td, color: RED, fontWeight: 700 }}>NO edge</td>
                <td style={{ ...S.td, ...S.small }}>"Down-risk" regime days bounce (46% directional hit rate); "grind-up" days return less than an average day. This page will never show direction arrows built on these.</td>
              </tr>
              <tr>
                <td style={S.td}>Quiet-day squeeze tell → speculative calls</td>
                <td style={{ ...S.td, color: AMBER, fontWeight: 700 }}>WATCH — promotion-gated</td>
                <td style={{ ...S.td, ...S.small }}>The one live directional candidate (tracked below). Becomes a page recommendation only by hitting its pre-registered promotion rule, never by eyeballing.</td>
              </tr>
              <tr>
                <td style={S.td}>Conditional single-leg buys (UPDRAFT / REVERSAL / EM-BREACH / AFTERBURN)</td>
                <td style={{ ...S.td, color: AMBER, fontWeight: 700 }}>PAPER — earning evidence</td>
                <td style={{ ...S.td, ...S.small }}>Four call/put-buying bots run these ideas live on paper in the fleet. A lead graduates on positive paper P&amp;L, and that becomes the buy-side playbook here.</td>
              </tr>
            </tbody>
          </table>
          <div style={S.small}>
            Bottom line: when this page says stand down, the validated action is <b>reduce or skip</b> — not switch sides.
            Registry: ironforge-data/risk_advisor/trials_registry.md #18–#22.
          </div>
        </div>

        {/* 8 ─ WATCH TIER */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            <Eye size={13} style={{ verticalAlign: -2 }} /> Watch — accumulating evidence (NOT trading signals)
            <InfoTip text="Candidates with promising but underpowered evidence. They are NOT tradeable signals — they graduate to the playbook only by hitting the pre-registered promotion rule, never by eyeballing." />
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr><th style={S.th}>candidate</th><th style={S.th}>evidence so far</th><th style={S.th}>status</th></tr></thead>
            <tbody>
              <tr>
                <td style={S.td}>Quiet-day 0DTE OTM-call squeeze tell</td>
                <td style={S.td}>top decile → P(up≥0.75%) 8.1% vs 3.3% base; bottom decile 0.0%</td>
                <td style={S.td}>
                  {(() => {
                    const pr = score?.promotion?.squeeze_tell;
                    if (!pr) return 'underpowered — sample grows nightly';
                    const f = Math.min(100, 100 * pr.quiet_sessions_have / pr.quiet_sessions_needed);
                    return (<>
                      <div style={{ fontSize: 12, marginBottom: 4 }}>
                        {pr.quiet_sessions_have}/{pr.quiet_sessions_needed} quiet sessions toward promotion
                      </div>
                      <div style={{ background: '#1a2030', borderRadius: 4, height: 6, maxWidth: 220 }}>
                        <div style={{ width: f + '%', height: '100%', background: AMBER, borderRadius: 4 }} />
                      </div>
                      <div style={{ fontSize: 10, color: DIM, marginTop: 3 }}>{pr.rule}</div>
                    </>);
                  })()}
                </td>
              </tr>
              <tr>
                <td style={S.td}>Premium-imbalance contrarian</td>
                <td style={S.td}>call-heavy premium → P(up) 2.2% vs 6.4% base</td>
                <td style={S.td}>suggestive only</td>
              </tr>
            </tbody>
          </table>
        </div>
        {/* 8b ─ EBB: the strategy these signals protect */}
        {ebb && !ebb.error && (
          <div style={S.card}>
            <div style={S.cardTitle}>EBB — the paper strategy these signals protect
              <InfoTip text="The validated 0DTE put-spread paper bot (registry #23b: $12.19/trade, 5/5 blind years). It trades EVERY day by design — the signals on this page are for YOUR discretionary and multi-day risk; gating EBB on them was tested and made it worse. Its full card lives on the Bots page." />
            </div>
            <div style={{ fontSize: 13.5 }}>
              Status: <b style={{ color: ebb.enabled ? GREEN : AMBER }}>{ebb.enabled ? 'ARMED (paper)' : 'paused'}</b>
              {' '}· today {ebb.today_pnl != null ? `$${(ebb.today_pnl + (ebb.unrealized_pnl || 0)).toFixed(0)}` : '—'}
              {' '}· equity ${ebb.equity_mtm?.toLocaleString?.() ?? ebb.equity_mtm}
              {' '}· open positions {ebb.open_positions ?? 0}
              {' '}· <span style={S.small}>trades post to Discord at open (~10:06 CT) and settle (after close)</span>
            </div>
          </div>
        )}

        {/* 8c ─ ALERT HISTORY */}
        <div style={S.card}>
          <div style={S.cardTitle}>Alert history — what actually fired
            <InfoTip text="Every alert the system actually posted to Discord, newest first, from the same dedupe log that guarantees one post per signal per day. If a day is missing here, nothing fired — silence means NORMAL. The page and the channel tell one story." />
          </div>
          {alog?.alerts?.length ? (
            <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 640 }}>
              <tbody>
                {alog.alerts.map((a, i) => (
                  <tr key={i}>
                    <td style={{ ...S.td, whiteSpace: 'nowrap', fontWeight: 600 }}>{a.d}</td>
                    <td style={{ ...S.td, color: a.what.includes('@here') ? '#fca5a5' : '#c6cbd8' }}>{a.what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div style={S.small}>no alerts posted yet — silence means NORMAL</div>}
        </div>

        {/* 9 ─ GLOSSARY: every term in plain speech */}
        <div style={S.card}>
          <div style={S.cardTitle}>What the words mean — plain-speech glossary
            <InfoTip text="Every term this page uses, defined once in everyday language. If anything on the page still requires decoding after this, that is a bug — report it and the page changes." />
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <tbody>
              {GLOSSARY.map(([term, def]) => (
                <tr key={term}>
                  <td style={{ ...S.td, fontWeight: 600, whiteSpace: 'nowrap', verticalAlign: 'top' }}>{term}</td>
                  <td style={{ ...S.td, ...S.small, fontSize: 13 }}>{def}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
