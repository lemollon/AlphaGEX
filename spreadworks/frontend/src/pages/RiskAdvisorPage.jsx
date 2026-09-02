// Risk Advisor — ONE screen. Answers, in order: what today looks like, what
// to trade, whether skipping risky days would have actually helped, and the
// call log. Advisory only — no bot consumes this. All spacing inline
// (Tailwind p-*/m-* are zeroed app-wide on most pages; this file matches the
// rest of /risk's original inline-style pattern).
import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { API_URL } from '../lib/api';
import FreshnessBar from '../components/FreshnessBar';
import CallHistory from '../components/CallHistory';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', BLUE = '#60a5fa', DIM = '#8b93a7';
const MUTED = '#a8afc0';

const S = {
  wrap: { maxWidth: 960, margin: '0 auto', padding: '24px 16px 64px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { fontSize: 13, color: DIM, margin: '0 0 16px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 14, fontWeight: 700, marginBottom: 10 },
  th: { textAlign: 'left', color: DIM, fontSize: 12, padding: '6px 8px' },
  td: { padding: '6px 8px', fontSize: 13, borderTop: '1px solid #1c2233' },
  note: { fontSize: 13, color: MUTED, lineHeight: 1.6 },
  foot: { fontSize: 13, color: MUTED, lineHeight: 1.6, marginBottom: 6 },
};

// ---- formatting helpers ----------------------------------------------
function money(v) {
  if (v == null || Number.isNaN(v)) return '—';
  const n = Math.round(v);
  return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US');
}
function pct(v, d = 1) {
  return v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`;
}
// 0.2575 -> "26th". The backend ships the percentile as a 0..1 fraction.
function ordinal(n) {
  if (!Number.isFinite(n)) return '—';
  const m100 = n % 100, m10 = n % 10;
  const sfx = m100 >= 11 && m100 <= 13 ? 'th' : m10 === 1 ? 'st' : m10 === 2 ? 'nd' : m10 === 3 ? 'rd' : 'th';
  return `${n}${sfx}`;
}
function stateColor(state) {
  const u = (state || '').toUpperCase();
  if (u.includes('STAND')) return RED;
  if (u.includes('CAUTION')) return AMBER;
  return GREEN;
}
function tWord(t) {
  const a = Math.abs(t ?? NaN);
  if (!Number.isFinite(a)) return '—';
  return a < 1 ? 'weak' : a < 2 ? 'some' : 'strong';
}
// The by_decile row whose [p_lo,p_hi) contains today's p; else the nearest
// bucket by midpoint distance, since a live p can fall exactly on a seam.
function nearestDecile(deciles, p) {
  if (!deciles?.length || p == null) return null;
  const hit = deciles.find(d => p >= d.p_lo && p < d.p_hi);
  if (hit) return hit;
  return deciles.reduce((best, d) => {
    const dist = Math.abs(p - (d.p_lo + d.p_hi) / 2);
    return !best || dist < best.dist ? { ...d, dist } : best;
  }, null);
}
function mergeCurves(none, gate) {
  const map = new Map();
  (none || []).forEach(([d, v]) => map.set(d, { date: d, none: v }));
  (gate || []).forEach(([d, v]) => map.set(d, { ...(map.get(d) || { date: d }), gate: v }));
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

// What each live bot actually runs. SPARK skips when the prior session's VIX
// is above 90% of its 20-day high; FLAME trades every session (gate removed
// 2026-09-02: it cost FLAME ~$509/yr and did not cut drawdown). The backend
// ships this map; the fallback matches it. Everything else here is advisory.
const DEPLOYED_FALLBACK = { spark: 'vix_decay', flame: 'none' };
const GATE_KEYS = ['vix_decay', 'sd60', 'caution60', 'backwardation'];
const gateName = (label) => (label || '').replace(/ - DEPLOYED RULE.*$/, '');
const BOT_KEYS = ['flame', 'spark'];

// ---- growth panel: equity chart + compact stat table -------------------
function EquityPanel({ bot, deployed }) {
  const data = useMemo(() => mergeCurves(bot?.curves?.none, bot?.curves?.vix_decay), [bot]);
  if (!bot) return <div style={S.card}><div style={S.note}>backtest unavailable</div></div>;
  const gateDeployed = deployed === 'vix_decay';
  const g = bot.gates?.none || {};
  const dg = bot.gates?.vix_decay || {};
  const gateLabel = gateDeployed ? 'VIX gate (deployed)' : 'VIX gate (removed 9/2)';
  const p = g.periods || {}, dp = dg.periods || {};
  const cell = (v, extra) => <td style={{ ...S.td, textAlign: 'right', ...(extra || {}) }}>{v}</td>;
  const mw = (x) => (x ? `${money(x.median)} / ${money(x.worst)}` : '—');
  const last = data.length - 1;
  const endLabel = (text, color) => (props) => {
    if (props.index !== last) return null;
    return <text x={props.x + 6} y={props.y + 3} fill={color} fontSize={11} fontWeight={700}>{text}</text>;
  };
  return (
    <div style={{ ...S.card, flex: '1 1 420px', minWidth: 300 }}>
      <div style={S.cardTitle}>{bot.label} from {money(bot.start)}</div>
      <div style={{ fontSize: 12, color: DIM, marginBottom: 6 }}>
        {bot.clock} · {bot.structure} · <span style={{ color: AMBER }}>deployed: {gateDeployed ? 'skip VIX-not-decaying days' : 'trade every session'}</span>
      </div>
      {data.length === 0 ? <div style={S.note}>backtest unavailable</div> : (
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 10, right: 90, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="#1c2233" strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: MUTED }} interval="preserveStartEnd" minTickGap={50} />
              <YAxis tick={{ fontSize: 11, fill: MUTED }} tickFormatter={money} width={64} />
              <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                       formatter={(v, n) => [money(v), n === 'none' ? 'trade every day' : gateLabel]} />
              <Line dataKey="none" name="trade every day" stroke={BLUE} strokeWidth={2} dot={false}
                    isAnimationActive={false} label={endLabel('trade every day', BLUE)} />
              <Line dataKey="gate" name={gateLabel} stroke={AMBER} strokeWidth={2}
                    strokeDasharray="5 4" dot={false} isAnimationActive={false}
                    label={endLabel(gateDeployed ? 'VIX gate (deployed)' : 'VIX gate (removed)', AMBER)} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <table style={{ borderCollapse: 'collapse', width: '100%', marginTop: 10, fontSize: 13 }}>
        <thead><tr>
          <th style={S.th}></th>
          <th style={{ ...S.th, textAlign: 'right', color: BLUE }}>every day{gateDeployed ? '' : ' (deployed)'}</th>
          <th style={{ ...S.th, textAlign: 'right', color: AMBER }}>VIX gate{gateDeployed ? ' (deployed)' : ''}</th>
        </tr></thead>
        <tbody>
          <tr><td style={S.td}>End equity</td>{cell(money(g.end_equity), { fontWeight: 700 })}{cell(money(dg.end_equity), { fontWeight: 700 })}</tr>
          <tr><td style={S.td}>$ per year</td>{cell(money(g.ann))}{cell(money(dg.ann))}</tr>
          <tr><td style={S.td}>Days traded</td>{cell(g.n ?? '—')}{cell(dg.n ?? '—')}</tr>
          <tr><td style={S.td}>Typical (median) day</td>{cell(money(g.median))}{cell(money(dg.median))}</tr>
          <tr><td style={S.td}>Worst day</td>{cell(money(g.worst), { color: RED })}{cell(money(dg.worst), { color: RED })}</tr>
          <tr><td style={S.td}>Worst drawdown</td>{cell(`${money(g.max_dd)} (${pct(g.max_dd_pct, 0)})`, { color: RED })}{cell(`${money(dg.max_dd)} (${pct(dg.max_dd_pct, 0)})`, { color: RED })}</tr>
          <tr><td style={S.td}>Win rate</td>{cell(pct(g.win_rate))}{cell(pct(dg.win_rate))}</tr>
          <tr><td style={S.td}>Daily — median / worst</td>{cell(mw(p.daily))}{cell(mw(dp.daily))}</tr>
          <tr><td style={S.td}>Weekly — median / worst</td>{cell(mw(p.weekly))}{cell(mw(dp.weekly))}</tr>
          <tr><td style={S.td}>Monthly — median / worst</td>{cell(mw(p.monthly))}{cell(mw(dp.monthly))}</tr>
        </tbody>
      </table>
    </div>
  );
}

// ---- gate table: would skipping the risky days have helped? ------------
function GateSection({ growth }) {
  if (!growth) return null;
  const gates = growth.gates || {};
  const bots = growth.bots || {};
  const deployed = growth.deployed || DEPLOYED_FALLBACK;
  return (
    <div style={S.card}>
      <div style={S.cardTitle}>Would skipping the risky days have helped?</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead><tr>
            <th style={S.th}>gate</th><th style={S.th}>bot</th><th style={S.th}>days skipped</th>
            <th style={S.th}>what those days made</th><th style={S.th}>$/yr vs every day</th>
            <th style={S.th}>drawdown change</th><th style={S.th}>evidence</th>
          </tr></thead>
          <tbody>
            {GATE_KEYS.flatMap(gk => BOT_KEYS.map((bk, i) => {
              const bot = bots[bk];
              if (!bot) return null;
              const none = bot.gates?.none, g = bot.gates?.[gk];
              const dAnn = g && none ? g.ann - none.ann : null;
              const dDD = g && none ? g.max_dd - none.max_dd : null;
              return (
                <tr key={gk + bk}>
                  {i === 0 && (
                    <td style={{ ...S.td, fontWeight: 700 }} rowSpan={BOT_KEYS.length}>{gateName(gates[gk]) || gk}</td>
                  )}
                  <td style={S.td}>
                    {bot.label || bk.toUpperCase()}
                    {deployed[bk] === gk && <span style={{ color: AMBER, marginLeft: 6, fontSize: 11, fontWeight: 700 }}>DEPLOYED</span>}
                  </td>
                  <td style={S.td}>{g?.skipped ?? '—'}</td>
                  <td style={{ ...S.td, color: g && g.skipped_pnl < 0 ? RED : undefined }}>{g ? money(g.skipped_pnl) : '—'}</td>
                  <td style={{ ...S.td, color: dAnn > 0 ? GREEN : dAnn < 0 ? RED : undefined }}>{dAnn != null ? money(dAnn) : '—'}</td>
                  <td style={{ ...S.td, color: dDD < 0 ? GREEN : dDD > 0 ? RED : undefined }}>{dDD != null ? money(dDD) : '—'}</td>
                  <td style={S.td}>{g ? tWord(g.skipped_t) : '—'}</td>
                </tr>
              );
            }))}
          </tbody>
        </table>
      </div>
      {BOT_KEYS.map(bk => {
        const bot = bots[bk];
        if (!bot) return null;
        const none = bot.gates?.none, dep = bot.gates?.vix_decay;
        const gateDeployed = deployed[bk] === 'vix_decay';
        let winner = null;
        for (const gk of GATE_KEYS) {
          const g = bot.gates?.[gk];
          if (g && none && g.ann > none.ann && g.max_dd < none.max_dd && Math.abs(g.skipped_t ?? 0) >= 2) { winner = gk; break; }
        }
        const dAnn = dep && none ? dep.ann - none.ann : null;
        const dDD = dep && none ? dep.max_dd - none.max_dd : null;
        return (
          <div key={bk} style={{ fontSize: 13.5, marginTop: 8 }}>
            <b>{bot.label || bk.toUpperCase()}</b> —{' '}
            {dAnn != null && (
              <>deployed rule: {gateDeployed ? 'skip VIX-not-decaying days' : 'trade every session'}. The VIX gate{' '}
              {dAnn < 0 ? 'costs' : 'adds'} {money(Math.abs(dAnn))}/yr and {dDD < 0 ? 'cuts' : 'raises'} the worst drawdown by{' '}
              {money(Math.abs(dDD))} versus trading every day{gateDeployed ? '' : ', which is why FLAME dropped it on 9/2'}.{' '}</>
            )}
            {winner ? `The ${gateName(gates[winner]) || winner} gate beats trading every day with strong evidence.` : 'No gate beats trading every day with strong evidence.'}
          </div>
        );
      })}
    </div>
  );
}

export default function RiskAdvisorPage() {
  const [state, setState] = useState(null);
  const [stateErr, setStateErr] = useState(null);
  const [growth, setGrowth] = useState(null);
  const [growthErr, setGrowthErr] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [recipeErr, setRecipeErr] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      const [sRes, gRes, rRes] = await Promise.allSettled([
        fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => r.json()),
        fetch(`${API_URL}/api/spreadworks/risk-advisor/growth`).then(r => r.json()),
        fetch(`${API_URL}/api/spreadworks/risk-advisor/recipe`).then(r => r.json()),
      ]);
      if (!live) return;
      if (sRes.status === 'fulfilled') { setState(sRes.value); setStateErr(null); setLoadedAt(new Date()); }
      else setStateErr(String(sRes.reason));
      if (gRes.status === 'fulfilled') { setGrowth(gRes.value); setGrowthErr(null); }
      else setGrowthErr(String(gRes.reason));
      if (rRes.status === 'fulfilled') { setRecipe(rRes.value); setRecipeErr(null); }
      else setRecipeErr(String(rRes.reason));
    };
    load();
    const t = setInterval(load, 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  const td = growth?.live_today || growth?.today;
  const normal = td ? (td.state || '').toUpperCase().includes('NORMAL') : true;
  // The percentile ranks today against every session the risk model scored
  // (its p_hist), which is a longer list than the sessions either bot traded.
  const scored = growth?.today?.model?.n;
  const span = growth?.bots?.flame?.span || growth?.bots?.spark?.span;

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        {/* 1 — title */}
        <h1 style={S.h1}>Risk Advisor</h1>
        <p style={S.sub}>What today looks like, what the bots trade, and whether skipping risky days would have helped SPARK and FLAME.</p>
        <FreshnessBar
          state={state?.freshness?.state}
          detail={state?.freshness?.detail}
          legs={state?.freshness?.legs || []}
          loadedAt={loadedAt}
        />
        {stateErr && !state && <div style={{ ...S.card, ...S.note }}>freshness unavailable: {stateErr}</div>}

        {/* 2 — TODAY, the hero */}
        <div style={S.card}>
          {!growth && !growthErr && <div style={S.note}>Loading today's read…</div>}
          {growthErr && <div style={S.note}>backtest unavailable</div>}
          {growth && td && (
            <>
              <div style={{ fontSize: 24, fontWeight: 800, color: stateColor(td.state) }}>{td.state}</div>
              <div style={{ fontSize: 14, marginTop: 8, color: '#e8ebf3' }}>
                Chance of a move bigger than 1% today: <b>{pct(td.p)}</b> (a typical day is {pct(td.base_rate)}).
                Today ranks at the {ordinal(Math.round((td.percentile ?? 0) * 100))} percentile{scored ? ` of ${scored.toLocaleString()} scored sessions` : ''}.
              </div>
              <div style={{ overflowX: 'auto', marginTop: 12 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <caption style={{ captionSide: 'top', textAlign: 'left', fontSize: 12, color: DIM, paddingBottom: 4 }}>
                    What days like today did in the test
                  </caption>
                  <thead><tr>
                    <th style={S.th}>bot</th><th style={S.th}>n days</th><th style={S.th}>median day</th>
                    <th style={S.th}>average day</th><th style={S.th}>worst day</th><th style={S.th}>win rate</th>
                  </tr></thead>
                  <tbody>
                    {BOT_KEYS.map(bk => {
                      const bot = growth.bots?.[bk];
                      const d = nearestDecile(bot?.by_decile, td.p);
                      return (
                        <tr key={bk}>
                          <td style={{ ...S.td, fontWeight: 700 }}>{bot?.label || bk.toUpperCase()}</td>
                          <td style={S.td}>{d?.n ?? '—'}</td>
                          <td style={S.td}>{d ? money(d.median) : '—'}</td>
                          <td style={S.td}>{d ? money(d.per_trade) : '—'}</td>
                          <td style={{ ...S.td, color: d && d.worst < 0 ? RED : undefined }}>{d ? money(d.worst) : '—'}</td>
                          <td style={S.td}>{d ? pct(d.win_rate) : '—'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {td.vix_gate && (
                <div style={{ fontSize: 15, marginTop: 12, fontWeight: 700, color: td.vix_gate.blocked ? RED : GREEN }}>
                  SPARK's gate today: {td.vix_gate.blocked ? 'SPARK SITS OUT' : 'SPARK TRADES'}
                  <span style={{ fontWeight: 400, color: '#c6cbd8' }}>
                    {' '}— the prior VIX close was {Math.round(td.vix_gate.ratio * 100)}% of its 20-day high (rule: skip above {Math.round(td.vix_gate.ceiling * 100)}%). FLAME trades every session.
                  </span>
                </div>
              )}
              <div style={{ fontSize: 13.5, marginTop: 10, color: '#c6cbd8' }}>
                {normal
                  ? 'The risk model reads today as normal. It is advisory; SPARK follows the VIX gate above and FLAME trades every session.'
                  : 'The risk model flags today. In the test, skipping flagged days did not help FLAME and was unproven for SPARK (gate table below). It is advisory; SPARK follows the VIX gate above and FLAME trades every session.'}
              </div>
              {td.computed_from && td.computed_from !== 'live' && (
                <div style={{ ...S.note, marginTop: 8 }}>
                  computed from {td.computed_from === 'file' ? 'a saved file, not a live quote' : td.computed_from}{td.stale ? ' — stale' : ''}
                </div>
              )}
            </>
          )}
        </div>

        {/* 3 — tickets */}
        <div style={S.card}>
          <div style={S.cardTitle}>Today's tickets</div>
          {!recipe && !recipeErr && <div style={S.note}>Loading…</div>}
          {recipeErr && <div style={S.note}>recipe unavailable</div>}
          {recipe && (recipe.tickets?.length ? (
            <>
              {recipe.tickets.map(t => (
                <div key={t.bot} style={{ fontSize: 14, marginBottom: 6 }}>
                  <b>{t.bot}</b> · {t.clock} · sell SPY {t.short}P / buy {t.long}P · ${t.wing} wing · max loss {money(t.max_loss_per_lot)}/lot
                </div>
              ))}
              <div style={{ ...S.foot, marginTop: 8, marginBottom: 0 }}>
                Settle at the close. No stop, no profit target. Live spot {recipe.spot != null ? `$${Number(recipe.spot).toFixed(2)}` : '—'}.
              </div>
            </>
          ) : <div style={S.note}>tickets unavailable</div>)}
        </div>

        {/* 4 — growth panels */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <EquityPanel bot={growth?.bots?.flame} deployed={(growth?.deployed || DEPLOYED_FALLBACK).flame} />
          <EquityPanel bot={growth?.bots?.spark} deployed={(growth?.deployed || DEPLOYED_FALLBACK).spark} />
        </div>
        {growthErr && <div style={{ ...S.card, ...S.note }}>backtest unavailable</div>}

        {/* 5 — gate table */}
        <GateSection growth={growth} />

        {/* 6 — call history */}
        <CallHistory surface="risk" title="Risk call history" />

        {/* 7 — footnotes */}
        <div style={{ ...S.card, marginTop: 16 }}>
          <div style={S.foot}>
            Backtest: {span ? `${span[0]} to ${span[1]}` : 'the tested window'} at real bid/ask fills, $0.70 per lot, one contract, no compounding.
          </div>
          <div style={S.foot}>
            Assignment risk: an in-the-money short put can convert to 100 SPY shares overnight; a large gap can exceed a small account.
          </div>
          <div style={{ ...S.foot, marginBottom: 0 }}>
            The risk model is scored on each year with a model fit only on earlier years.
          </div>
        </div>
      </div>
    </div>
  );
}
