// Risk Advisor — advisory dashboard for the validated signal stack.
// ADVISORY ONLY: nothing here feeds a bot. Every signal shown was backtested
// and pre-registered in ironforge-data/risk_advisor (2026-08-12); tiers encode
// evidence strength honestly — "watch" panels are labeled as accumulating
// evidence, not trading signals.
//
// NOTE: Tailwind p-*/m-* are zeroed app-wide — all spacing is inline styles.
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import { ShieldAlert, ShieldCheck, Activity, Eye } from 'lucide-react';
import { API_URL } from '../lib/api';

const S = {
  page: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 64px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: '#8b93a7', fontSize: 13, margin: '0 0 20px' },
  card: {
    background: '#141824', border: '1px solid #232a3d', borderRadius: 12,
    padding: 16, marginBottom: 16,
  },
  pill: (on, color) => ({
    display: 'inline-block', padding: '4px 10px', borderRadius: 999,
    fontSize: 12, fontWeight: 600, marginRight: 8, marginBottom: 6,
    background: on ? color + '22' : '#1a2030',
    color: on ? color : '#5b6478',
    border: `1px solid ${on ? color + '55' : '#232a3d'}`,
  }),
  tierTag: (c) => ({
    fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: c,
    border: `1px solid ${c}55`, borderRadius: 4, padding: '2px 6px',
    marginLeft: 8, verticalAlign: 'middle',
  }),
  row: { display: 'flex', gap: 16, flexWrap: 'wrap' },
  th: { textAlign: 'left', color: '#8b93a7', fontSize: 12, padding: '6px 10px' },
  td: { padding: '6px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
};

const GREEN = '#34d399';
const RED = '#f87171';
const AMBER = '#fbbf24';
const BLUE = '#60a5fa';

export default function RiskAdvisorPage() {
  const [state, setState] = useState(null);
  const [hist, setHist] = useState([]);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [s, h] = await Promise.all([
          fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => r.json()),
          fetch(`${API_URL}/api/spreadworks/risk-advisor/history?days=90`).then(r => r.json()),
        ]);
        if (!live) return;
        setState(s);
        setHist((h.days || []).map(d => ({
          ...d,
          label: d.d.slice(5),
          spike: (d.putv_z > 2 || d.totv_z > 2) ? Math.max(d.putv_z, d.totv_z) : null,
        })));
      } catch (e) {
        if (live) setErr(String(e));
      }
    };
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  if (err) return <div style={S.page}><div style={S.card}>Risk Advisor unavailable: {err}</div></div>;
  if (!state) return <div style={S.page}><div style={S.card}>Loading…</div></div>;

  const sig = state.signals || {};
  const flow = state.flow || {};
  const riskOff = state.headline?.startsWith('RISK-OFF');
  const calm = state.headline?.startsWith('CALM');
  const HeadIcon = riskOff ? ShieldAlert : ShieldCheck;
  const headColor = riskOff ? RED : calm ? GREEN : BLUE;

  // quiet-day shading bands for the ribbon
  const bands = [];
  let start = null;
  hist.forEach((d, i) => {
    if (d.quiet && start === null) start = i;
    if ((!d.quiet || i === hist.length - 1) && start !== null) {
      bands.push([hist[start].label, hist[d.quiet ? i : Math.max(i - 1, start)].label]);
      start = null;
    }
  });

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Risk Advisor</h1>
      <p style={S.sub}>
        Advisory only — no bot reads this. Signals validated & pre-registered
        2026-08-12; tiers reflect evidence strength. As-of close {state.asof_close}.
      </p>

      {/* headline strip */}
      <div style={{ ...S.card, display: 'flex', alignItems: 'center', gap: 12,
                    borderColor: headColor + '55' }}>
        <HeadIcon size={28} color={headColor} />
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: headColor }}>
            {state.headline}
          </div>
          <div style={{ fontSize: 12, color: '#8b93a7', marginTop: 2 }}>
            VIX {state.indices?.vix?.toFixed(1)} · VIX1D {state.indices?.vix1d?.toFixed(1)}
            · VIX9D {state.indices?.vix9d?.toFixed(1)} · VVIX {state.indices?.vvix?.toFixed(0)}
            {sig.p_down2s_ratio != null &&
              <> · P(2σ down) {(100 * sig.p_down2s_ratio).toFixed(1)}%</>}
          </div>
        </div>
      </div>

      {/* deployable signal pills */}
      <div style={S.card}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
          Deployable signals <span style={S.tierTag(GREEN)}>BACKTESTED</span>
        </div>
        <span style={S.pill(sig.backwardation, RED)}>
          backwardation (VIX&gt;VIX3M) — skip entries (+0.09 ret/DD, 7y)
        </span>
        <span style={S.pill(sig.flag_vix1d, AMBER)}>
          VIX1D flag &gt;1% implied — 42.8% prec / 68% recall
        </span>
        <span style={S.pill(flow.spike, RED)}>
          10:00 CT flow spike z&gt;2 — big-move odds 28.6% vs 12.1% (4.8σ)
        </span>
        <span style={S.pill(sig.double_floor, GREEN)}>
          double floor (VVIX&lt;85, VIX&lt;14) — 0.00× next-day tail
        </span>
        <span style={S.pill(sig.inv_9d, AMBER)}>
          9D inversion (VIX9D&gt;VIX)
        </span>
        {flow.status !== 'snapshot' && (
          <div style={{ fontSize: 11, color: '#5b6478', marginTop: 6 }}>
            <Activity size={11} style={{ verticalAlign: -1 }} /> flow: {flow.status}
          </div>
        )}
      </div>

      {/* flow ribbon */}
      <div style={S.card}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
          10:00 CT flow z-scores — trailing 90 sessions
        </div>
        <div style={{ fontSize: 11, color: '#8b93a7', marginBottom: 10 }}>
          Shaded = quiet-VIX sessions (the trap regime). Dots = spike days (z&gt;2).
        </div>
        <div style={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <ComposedChart data={hist} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
              {bands.map(([a, b], i) => (
                <ReferenceArea key={i} x1={a} x2={b} fill={BLUE} fillOpacity={0.07} />
              ))}
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }}
                     interval="preserveStartEnd" minTickGap={40} />
              <YAxis tick={{ fontSize: 10, fill: '#5b6478' }} domain={[-3, 5]} />
              <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d',
                                       fontSize: 12 }} />
              <ReferenceLine y={2} stroke={RED} strokeDasharray="4 4" />
              <ReferenceLine y={0} stroke="#232a3d" />
              <Line dataKey="putv_z" name="put vol z" stroke={RED} dot={false} strokeWidth={1.5} />
              <Line dataKey="totv_z" name="total vol z" stroke={AMBER} dot={false} strokeWidth={1.2} />
              <Line dataKey="otm_call_0dte_z" name="0DTE OTM call z" stroke={GREEN}
                    dot={false} strokeWidth={1.2} />
              <Line dataKey="spike" name="spike" stroke="none"
                    dot={{ r: 4, fill: RED }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* watch tier */}
      <div style={S.card}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
          <Eye size={13} style={{ verticalAlign: -2 }} /> Watch — accumulating
          evidence <span style={S.tierTag(AMBER)}>NOT TRADING SIGNALS</span>
        </div>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>
            <th style={S.th}>candidate</th>
            <th style={S.th}>evidence so far</th>
            <th style={S.th}>status</th>
          </tr></thead>
          <tbody>
            <tr>
              <td style={S.td}>Quiet-day 0DTE OTM-call squeeze tell</td>
              <td style={S.td}>top decile → P(up≥0.75%) 8.1% vs 3.3% base; bottom decile 0.0%. t≈1.5</td>
              <td style={S.td}>underpowered (37 quiet sessions) — sample grows nightly</td>
            </tr>
            <tr>
              <td style={S.td}>Premium-imbalance contrarian</td>
              <td style={S.td}>call-heavy premium → P(up) 2.2% vs 6.4% base. t≈−1.3</td>
              <td style={S.td}>suggestive only</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
