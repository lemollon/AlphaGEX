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

// The action each signal demands when ACTIVE, with its backtested "why".
const PLAYBOOK = [
  { key: 'backwardation', name: 'Backwardation (VIX > VIX3M)',
    action: 'SKIP new premium-selling entries today',
    why: 'Stress is here. Skipping these days improved the condor book from 0.32 to 0.41 return-per-drawdown over 7 years.' },
  { key: 'flag_vix1d', name: 'VIX1D flag (implied 1-day move > 1%)',
    action: 'Reduce size or skip — a ±1% day is more likely than not to matter',
    why: 'When this flag is on, 42.8% of days move ≥1% (vs 26% overall). It catches 68% of all big days.' },
  { key: 'flow_spike', name: '10:00 CT flow spike (put/total vol z > 2)',
    action: 'Same-day risk: avoid new 0DTE exposure; tighten same-day exits',
    why: 'Big rest-of-day move odds jump to 28.6% vs 12.1% base (~4.8σ). Matters for SAME-DAY trades; a 5-day condor should ignore it.' },
  { key: 'double_floor', name: 'Double floor (VVIX<85 & VIX<14)',
    action: 'Safest measured day to SELL premium at normal size',
    why: 'Across 56 such sessions: ZERO next-day moves ≥1.5%. The calmest state in the data.' },
];

export default function RiskAdvisorPage() {
  const [state, setState] = useState(null);
  const [hist, setHist] = useState([]);
  const [score, setScore] = useState(null);
  const [intra, setIntra] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [s, h, sc, ia] = await Promise.all([
          fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/history?days=90`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/scorecard`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/intraday`).then(r => r.json()),
        ]);
        if (!live) return;
        setState(s); setScore(sc); setIntra(ia);
        setHist((h.days || []).map(d => ({
          ...d, label: d.d.slice(5),
          spike: (d.putv_z > 2 || d.totv_z > 2) ? Math.max(d.putv_z, d.totv_z) : null,
        })));
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    const t = setInterval(load, 60 * 1000);       // live: refresh every minute
    return () => { live = false; clearInterval(t); };
  }, []);

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
            ['flow snapshot', 'once/day 10:00–10:35 CT'], ['intraday bars', '5-min, live'],
            ['Discord alerts', '08:05 & 10:06 CT']].map(([k, v]) => (
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
            <div style={{ ...S.small, marginTop: 4 }}>
              As of close {state.asof_close} · VIX {state.indices?.vix?.toFixed(1)} ·
              VIX1D {state.indices?.vix1d?.toFixed(1)} · VIX9D {state.indices?.vix9d?.toFixed(1)} ·
              VVIX {state.indices?.vvix?.toFixed(0)}
            </div>
          </div>
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
              <InfoTip text="Tomorrow's plan, recomputed after each close. Probabilities are calibrated (Albers RVRP adjustment): P(±1% day) is the headline. The grade maps probability to action: normal → reduce size → hedge → stand down." />
            </div>
            {out ? (<>
              <div style={{ fontSize: 14, marginBottom: 8 }}>
                Grade: <b style={{ color: out.grade === 'normal' ? GREEN : out.grade === 'reduce_size' ? AMBER : RED }}>
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
          <div style={S.cardTitle}>Scorecard — is it performing like the backtest said it would?
            <InfoTip text="The tool grading itself. 'Live' columns are computed from actual sessions since deployment vs the 'backtest said' columns — if live drifts materially below backtest, the health rules mark the signal DEGRADED automatically. The tile strip shows the last 20 sessions day by day." />
          </div>
          {score ? (<>
            <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 10 }}>
              <thead><tr>
                <th style={S.th}>claim</th><th style={S.th}>live ({score.window_sessions} sessions)</th>
                <th style={S.th}>backtest said</th>
              </tr></thead>
              <tbody>
                <tr><td style={S.td}>VIX1D flag precision</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>{pct(fs?.precision)}</td>
                    <td style={S.td}>{pct(fs?.backtest_precision)}</td></tr>
                <tr><td style={S.td}>VIX1D flag recall</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>{pct(fs?.recall)}</td>
                    <td style={S.td}>{pct(fs?.backtest_recall)}</td></tr>
                <tr><td style={S.td}>Calibration (Brier, lower = better)</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>{cal?.brier_p_big_adj?.toFixed(3) ?? '—'}</td>
                    <td style={S.td}>{cal?.backtest_brier}</td></tr>
                <tr><td style={S.td}>Big-move rate on flow-spike days</td>
                    <td style={{ ...S.td, fontWeight: 700 }}>{pct(fsp?.big_move_rate_on_spike)} vs {pct(fsp?.big_move_rate_otherwise)} otherwise</td>
                    <td style={S.td}>28.6% vs 12.1%</td></tr>
              </tbody>
            </table>
            <div style={{ ...S.small, marginBottom: 8 }}>
              Recent sessions — ✓ flagged & big move happened · ✗ flagged, stayed quiet (cost: skipped premium) ·
              ● big move it MISSED · − clear day:
            </div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {(score.recent || []).map(r => {
                const c = r.grade === 'hit' ? GREEN : r.grade === 'false_alarm' ? AMBER : r.grade === 'missed' ? RED : '#2a3145';
                const t = r.grade === 'hit' ? '✓' : r.grade === 'false_alarm' ? '✗' : r.grade === 'missed' ? '●' : '−';
                return (
                  <div key={r.d} title={`${r.d}: ret ${r.ret}% — ${r.grade}`}
                       style={{ width: 26, height: 26, borderRadius: 5, background: c + '33',
                                border: `1px solid ${c}`, color: c, fontSize: 12, fontWeight: 700,
                                display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {t}
                  </div>
                );
              })}
            </div>
            {fsp?.note && <div style={{ ...S.small, marginTop: 8 }}>{fsp.note}</div>}
          </>) : <div style={S.small}>computing…</div>}
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
          <div style={S.cardTitle}>10:00 CT flow z-scores — trailing 90 sessions
            <InfoTip text="How unusual today's 10:00 CT option volume is vs the trailing 63 sessions, in z-scores (0 = normal, 2+ = spike). Red = put volume, amber = total volume, green = 0DTE OTM call volume (the squeeze tell). Shaded bands = quiet-VIX regimes where daily signals are blind — exactly where the flow signal earns its keep. One point per session; today's point appears after the 10:00 snapshot." />
          </div>
          <div style={{ ...S.small, marginBottom: 10 }}>
            Shaded = quiet-VIX sessions (the trap regime, where daily signals are blind). Dots = spike days (z&gt;2).
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
        </div>

        {/* 7 ─ HOW TO USE / ALERT PLAYBOOK */}
        <div style={S.card}>
          <div style={S.cardTitle}>How to use this page — and the alerts it will drive
            <InfoTip text="Read top to bottom once; after that, the verdict + alerts are all you need day to day." />
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
            <li><b>Check the verdict each morning before 8:30 CT.</b> It already includes yesterday's closes. RISK-OFF → apply the actions in the playbook table for whichever signals are active.</li>
            <li><b>At ~10:05 CT the flow signal arrives.</b> A spike (z&gt;2) means same-day danger — it fires on ~6% of days and more than doubles big-move odds. It applies to same-day (0DTE) exposure, NOT to multi-day positions.</li>
            <li><b>The outlook card is tomorrow's plan.</b> After the close it updates; its grade (normal / reduce / hedge / stand down) uses calibrated probabilities.</li>
            <li><b>Trust the scorecard, not the promises.</b> If live precision/recall drifts materially below the backtest column for a sustained window, the signal is decaying and we revisit — that is the deal.</li>
            <li><b>Alerts are live (Discord):</b> RISK-OFF morning verdict at 08:05 CT (@here), flow spike at ~10:06 CT (@here), calm floor as a quiet note. Silence at 08:05 means NORMAL — no news is the default.</li>
          </ol>
        </div>

        {/* 7b ─ DIRECTIONAL / LONG-PREMIUM VERDICTS */}
        <div style={S.card}>
          <div style={S.cardTitle}>Directional &amp; long-premium — what the backtests say
            <InfoTip text="You might expect 'don't sell premium' days to be 'buy premium' days. They are not — every directional/long-premium idea below was pre-registered and backtested (registry #18–#22, 2026-08-13). This section exists so you never have to wonder whether it was tried." />
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
      </div>
    </div>
  );
}
