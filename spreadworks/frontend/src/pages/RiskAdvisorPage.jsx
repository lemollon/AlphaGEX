// Risk Advisor v2 — a PLAYBOOK, not a readout.
// Answers, in order: (1) what should I do RIGHT NOW and why, (2) what is the
// market doing intraday vs what was implied, (3) what's the outlook for the
// next session, (4) how has this tool actually graded out vs its backtest,
// (5) how do I read all of it. ADVISORY ONLY — no bot consumes this.
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip,
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
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [s, h, sc] = await Promise.all([
          fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/history?days=90`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/scorecard`).then(r => r.json()),
        ]);
        if (!live) return;
        setState(s); setScore(sc);
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
          Advisory only — no bot reads this. Every signal here was backtested and
          pre-registered (2026-08-12); the scorecard below grades the tool against
          its own claims, live. Refreshes every minute.
        </p>

        {/* 1 ─ VERDICT */}
        <div style={{ ...S.card, borderColor: headColor + '55', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <HeadIcon size={30} color={headColor} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: headColor }}>{verdict}</div>
            <div style={{ ...S.small, marginTop: 4 }}>
              As of close {state.asof_close} · VIX {state.indices?.vix?.toFixed(1)} ·
              VIX1D {state.indices?.vix1d?.toFixed(1)} · VIX9D {state.indices?.vix9d?.toFixed(1)} ·
              VVIX {state.indices?.vvix?.toFixed(0)}
            </div>
          </div>
        </div>

        {/* 2 ─ PLAYBOOK: what to do right now */}
        <div style={S.card}>
          <div style={S.cardTitle}><Target size={13} style={{ verticalAlign: -2 }} /> What to do right now</div>
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
            <div style={S.cardTitle}><Activity size={13} style={{ verticalAlign: -2 }} /> Live intraday</div>
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
            <div style={S.cardTitle}><TrendingUp size={13} style={{ verticalAlign: -2 }} /> Next-session outlook</div>
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

        {/* 5 ─ SCORECARD: the tool grading itself */}
        <div style={S.card}>
          <div style={S.cardTitle}>Scorecard — is it performing like the backtest said it would?</div>
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

        {/* 6 ─ FLOW RIBBON */}
        <div style={S.card}>
          <div style={S.cardTitle}>10:00 CT flow z-scores — trailing 90 sessions</div>
          <div style={{ ...S.small, marginBottom: 10 }}>
            Shaded = quiet-VIX sessions (the trap regime, where daily signals are blind). Dots = spike days (z&gt;2).
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer>
              <ComposedChart data={hist} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
                {bands.map(([a, b], i) => (
                  <ReferenceArea key={i} x1={a} x2={b} fill={BLUE} fillOpacity={0.07} />
                ))}
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                <YAxis tick={{ fontSize: 10, fill: '#5b6478' }} domain={[-3, 5]} />
                <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }} />
                <ReferenceLine y={2} stroke={RED} strokeDasharray="4 4" />
                <ReferenceLine y={0} stroke="#232a3d" />
                <Line dataKey="putv_z" name="put vol z" stroke={RED} dot={false} strokeWidth={1.5} />
                <Line dataKey="totv_z" name="total vol z" stroke={AMBER} dot={false} strokeWidth={1.2} />
                <Line dataKey="otm_call_0dte_z" name="0DTE OTM call z" stroke={GREEN} dot={false} strokeWidth={1.2} />
                <Line dataKey="spike" name="spike" stroke="none" dot={{ r: 4, fill: RED }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 7 ─ HOW TO USE / ALERT PLAYBOOK */}
        <div style={S.card}>
          <div style={S.cardTitle}>How to use this page — and the alerts it will drive</div>
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
            <li><b>Check the verdict each morning before 8:30 CT.</b> It already includes yesterday's closes. RISK-OFF → apply the actions in the playbook table for whichever signals are active.</li>
            <li><b>At ~10:05 CT the flow signal arrives.</b> A spike (z&gt;2) means same-day danger — it fires on ~6% of days and more than doubles big-move odds. It applies to same-day (0DTE) exposure, NOT to multi-day positions.</li>
            <li><b>The outlook card is tomorrow's plan.</b> After the close it updates; its grade (normal / reduce / hedge / stand down) uses calibrated probabilities.</li>
            <li><b>Trust the scorecard, not the promises.</b> If live precision/recall drifts materially below the backtest column for a sustained window, the signal is decaying and we revisit — that is the deal.</li>
            <li><b>Alerts to be wired</b> (same channels as the vol ladder — Discord/ntfy): RISK-OFF on morning verdict; flow spike within 5 min of the 10:00 snapshot; CALM FLOOR as a quiet daily note, never a push.</li>
          </ol>
        </div>

        {/* 8 ─ WATCH TIER */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            <Eye size={13} style={{ verticalAlign: -2 }} /> Watch — accumulating evidence (NOT trading signals)
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
