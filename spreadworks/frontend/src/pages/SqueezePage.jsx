// Squeeze Signal — net dealer gamma percentile + VIX-at-highs, the
// prerequisite-not-a-direction-call gate documented in
// backend/bots/gamma_regime.py. ADVISORY ONLY — no bot reads this.
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import { Zap } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', GREY = '#9ca3af', DIM = '#8b93a7';
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
const WHAT_TO_DO = {
  SQUEEZE_WATCH: 'Stand down from selling — long-convexity setup (0.25Δ call, 5–9 DTE).',
  NO_SELL: 'Skip the put spread today.',
  SELL_PREMIUM: 'Gamma overbought — historically the safest state to sell into.',
  UNKNOWN: 'Signal unavailable — treat as BLOCK, do not trade the rule.',
  NEUTRAL: 'No signal active — trade your normal plan at normal size.',
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

export default function SqueezePage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch(`${API_URL}/api/spreadworks/squeeze/state`);
        const d = await r.json();
        if (live) setData(d);
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    const t = setInterval(load, 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  if (err) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Squeeze signal unavailable: {err}</div></div></div>;
  if (!data) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Loading…</div></div></div>;

  const verdict = data.verdict || 'UNKNOWN';
  const color = VERDICT_COLOR[verdict] || GREY;
  const hist = (data.history || []).map(h => ({ ...h, label: h.trade_date.slice(5) }));

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

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>Squeeze Signal</h1>
        <p style={S.sub}>
          Net dealer gamma percentile + VIX-at-highs. Advisory only — no bot reads this.
          A prerequisite for a squeeze and a strong veto for short premium — never a direction call.
        </p>

        {/* VERDICT BANNER */}
        <div style={{ ...S.card, borderColor: color + '55', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <Zap size={30} color={color} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color }}>
              {VERDICT_LABEL[verdict] || verdict}
            </div>
            <div style={{ fontSize: 13.5, marginTop: 6, color: '#c6cbd8' }}>
              {WHAT_TO_DO[verdict] || ''}
            </div>
            {data.reason && (
              <div style={{ ...S.small, marginTop: 6 }}>{data.reason}</div>
            )}
            <div style={{ ...S.small, marginTop: 6 }}>
              As of {data.asof} · prior session {data.prior_date || '—'}
            </div>
          </div>
        </div>

        {/* OUTLOOK — what to watch */}
        {(() => {
          const outlook = data.outlook || {};
          const legs = outlook.legs || {};
          const pColor = PROXIMITY_COLOR[outlook.proximity] || GREY;
          const gammaPctNow = data.gamma_pct != null ? Math.min(100, Math.max(0, data.gamma_pct * 100)) : null;

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
                </div>
              )}
              {outlook.proximity && (
                <div style={{ fontSize: 13, color: '#c6cbd8', marginBottom: 12 }}>
                  {PROXIMITY_COPY[outlook.proximity] || ''}
                </div>
              )}

              {/* 1 — how close are we */}
              <div style={{ ...S.small, marginBottom: 4 }}>How close are we — gamma percentile</div>
              <div style={{ position: 'relative', height: 24, background: '#0e1220', border: '1px solid #232a3d', borderRadius: 6 }}>
                <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '20%', background: AMBER, opacity: 0.18 }} />
                <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '20%', background: GREEN, opacity: 0.18 }} />
                {gammaPctNow != null && (
                  <div style={{ position: 'absolute', left: `calc(${gammaPctNow.toFixed(1)}% - 1px)`, top: -3, bottom: -3, width: 2, background: '#e6e9f2' }} />
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, marginBottom: 12 }}>
                <span style={S.small}>oversold ≤ {signedBn(outlook.oversold_trigger_b)}</span>
                <span style={{ ...S.small, textAlign: 'center' }}>current {pct(data.gamma_pct)}</span>
                <span style={S.small}>overbought ≥ {signedBn(outlook.overbought_trigger_b)}</span>
              </div>
              {outlook.pct_trend_5d != null && (
                <div style={{ ...S.small, marginBottom: 12 }}>
                  percentile {outlook.pct_trend_5d < 0 ? 'falling' : 'rising'} {Math.abs(outlook.pct_trend_5d * 100).toFixed(1)}pts over 5 sessions
                  {' — '}{outlook.pct_trend_5d < 0 ? 'moving toward the squeeze zone' : 'moving away from the squeeze zone'}
                </div>
              )}

              {/* 2 — what would have to happen */}
              <div style={{ ...S.small, marginBottom: 4 }}>What would have to happen</div>
              <div style={{ fontSize: 13, marginBottom: 4 }}>
                {outlook.gap_to_oversold_b == null || outlook.oversold_trigger_b == null ? '—'
                  : outlook.gap_to_oversold_b > 0
                    ? <>Squeeze trigger — gamma must fall to <b>{signedBn(outlook.oversold_trigger_b)}</b> ({outlook.gap_to_oversold_b.toFixed(2)}B away)</>
                    : <>Squeeze trigger — already through {signedBn(outlook.oversold_trigger_b)} (gamma at {bn(data.net_gex_b)})</>}
              </div>
              <div style={{ fontSize: 13, marginBottom: 12 }}>
                {outlook.gap_to_overbought_b == null || outlook.overbought_trigger_b == null ? '—'
                  : outlook.gap_to_overbought_b > 0
                    ? <>Overbought trigger — gamma must rise to <b>{signedBn(outlook.overbought_trigger_b)}</b> ({outlook.gap_to_overbought_b.toFixed(2)}B away)</>
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
            </div>
          );
        })()}

        {/* STAT TILES */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <div style={S.tile}>
            <div style={S.tileLabel}>Gamma percentile</div>
            <div style={S.tileValue}>{pct(data.gamma_pct)}</div>
          </div>
          <div style={S.tile}>
            <div style={S.tileLabel}>Net gamma</div>
            <div style={S.tileValue}>{bn(data.net_gex_b)}</div>
          </div>
          <div style={S.tile}>
            <div style={S.tileLabel}>VIX ratio</div>
            <div style={S.tileValue}>{data.vix_ratio == null ? '—' : data.vix_ratio.toFixed(2)}</div>
          </div>
        </div>

        {/* CHART */}
        <div style={S.card}>
          <div style={S.cardTitle}>Net dealer gamma — last 90 sessions</div>
          {hist.length ? (
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <ComposedChart data={hist} margin={{ top: 6, right: 12, left: -8, bottom: 0 }}>
                  {oversoldBands.map(([a, b], i) => (
                    <ReferenceArea key={`os-${i}`} x1={a} x2={b} fill={AMBER} fillOpacity={0.08} />
                  ))}
                  {overboughtBands.map(([a, b], i) => (
                    <ReferenceArea key={`ob-${i}`} x1={a} x2={b} fill={GREEN} fillOpacity={0.08} />
                  ))}
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#5b6478' }} interval="preserveStartEnd" minTickGap={40} />
                  <YAxis tick={{ fontSize: 10, fill: '#5b6478' }} tickFormatter={v => `${v.toFixed(0)}B`} />
                  <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                           formatter={(v, name) => [name === 'net_gex_b' ? `$${Number(v).toFixed(2)}B` : v, name]} />
                  <ReferenceLine y={0} stroke="#232a3d" />
                  <Line dataKey="net_gex_b" name="net gamma ($B)" stroke="#60a5fa" dot={false} strokeWidth={1.8} />
                </ComposedChart>
              </ResponsiveContainer>
              <div style={{ ...S.small, marginTop: 8 }}>
                Amber shading = oversold (≤20th trailing percentile) · green shading = overbought (≥80th).
              </div>
            </div>
          ) : <div style={S.small}>no history yet — needs the 15:05 CT capture job to run and 60 sessions before the percentile is defined</div>}
        </div>

        {/* EVIDENCE TABLE */}
        <div style={S.card}>
          <div style={S.cardTitle}>The evidence — squeeze rate by gamma percentile</div>
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
          <div style={S.small}>
            Gamma oversold + VIX at its highs → <b style={{ color: '#c6cbd8' }}>15.13% squeeze rate, 0.00% crash rate</b> (n=119).
            Monotone, zero squeezes in the top quartile. Overbought gamma is NOT a crash signal —
            it is the safest measured state to sell premium.
          </div>
        </div>
      </div>
    </div>
  );
}
