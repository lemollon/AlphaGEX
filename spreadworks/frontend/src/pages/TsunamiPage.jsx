// TSUNAMI — LETF trend bot page.
// Replaces the options-era "structures" concept with what this bot actually
// is: a comparison time series (TSUNAMI equity vs each instrument, indexed
// to 100) with per-ticker filter chips, the live book, and recent fills.
import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, CartesianGrid,
} from 'recharts';
import { API_URL as API_BASE } from '../lib/api';

// Fixed categorical order — hue follows the ticker, never its rank.
const SERIES_COLOR = {
  TSUNAMI: '#f8fafc', // the system line — near-white, bold
  TSLL: '#22d3ee',
  AMDL: '#f97316',
  NVDL: '#4ade80',
  CONL: '#a78bfa',
  MSTU: '#facc15',
  BITX: '#fb7185',
  ETHU: '#38bdf8',
  IONX: '#c084fc',
  UXRP: '#2dd4bf',
  SBIT: '#fb7185',  // inverses share their asset hue but render dashed
  ETHD: '#38bdf8',
  SMST: '#facc15',
};
const INVERSE = new Set(['SBIT', 'ETHD', 'SMST']);
// Default view: system + the 5 core longs. Everything togglable.
const DEFAULT_ON = new Set(['TSUNAMI', 'TSLL', 'AMDL', 'NVDL', 'CONL', 'MSTU']);

const card = {
  background: 'rgba(7,16,28,0.55)', border: '1px solid rgba(148,163,184,0.15)',
  borderRadius: 16, padding: 16,
};

function Chip({ id, on, held, onClick }) {
  const c = SERIES_COLOR[id] || '#94a3b8';
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 10px', borderRadius: 9999, cursor: 'pointer',
        fontSize: 12, fontWeight: 600,
        color: on ? '#e2e8f0' : '#64748b',
        background: on ? 'rgba(148,163,184,0.12)' : 'transparent',
        border: `1px solid ${on ? c : 'rgba(100,116,139,0.35)'}`,
        opacity: on ? 1 : 0.7,
      }}
    >
      <span style={{
        width: 14, height: 0, borderTop: `2px ${INVERSE.has(id) ? 'dashed' : 'solid'} ${c}`,
      }} />
      {id}
      {INVERSE.has(id) && <span style={{ fontSize: 9, color: '#94a3b8' }}>SHORT</span>}
      {held && <span style={{ fontSize: 9, color: '#4ade80' }}>● HELD</span>}
    </button>
  );
}

export default function TsunamiPage() {
  const [status, setStatus] = useState(null);
  const [cmp, setCmp] = useState(null);
  const [err, setErr] = useState(null);
  const [on, setOn] = useState(DEFAULT_ON);

  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        const [s, c] = await Promise.all([
          fetch(`${API_BASE}/api/tsunami/trend/status`).then(r => r.json()),
          fetch(`${API_BASE}/api/tsunami/trend/comparison`).then(r => r.json()),
        ]);
        if (!dead) { setStatus(s); setCmp(c); }
      } catch (e) {
        if (!dead) setErr(String(e));
      }
    })();
    return () => { dead = true; };
  }, []);

  const held = useMemo(() => new Set(cmp?.held || []), [cmp]);
  const tickers = useMemo(() => ['TSUNAMI', ...(cmp?.tickers || [])], [cmp]);
  const points = cmp?.points || [];

  const toggle = (id) => setOn(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const equity = status?.equity ?? null;
  const cash = status?.cash ?? null;
  const book = status?.book || [];
  const trades = status?.recent_trades || [];

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 16, display: 'grid', gap: 16 }}>
      {/* nameplate + stat strip */}
      <div style={{ ...card, display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'baseline' }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#e2e8f0' }}>🌊 TSUNAMI</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            LETF trend engine · long 2x + crypto inverse side · daily rebalance 14:45 CT · paper
          </div>
        </div>
        {[['Equity', equity != null ? `$${equity.toFixed(2)}` : '—'],
          ['Cash', cash != null ? `$${cash.toFixed(2)}` : '—'],
          ['Positions', book.filter(b => b.shares > 0).length],
        ].map(([k, v]) => (
          <div key={k}>
            <div style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase' }}>{k}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{v}</div>
          </div>
        ))}
      </div>

      {/* comparison chart + filters */}
      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
          TSUNAMI vs. its instruments — indexed to 100
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 10 }}>
          Every line starts at 100 at the left edge of the window. Dashed lines are the
          inverse (short-side) products. Click a chip to show/hide a series.
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
          {tickers.map(t => (
            <Chip key={t} id={t} on={on.has(t)} held={held.has(t)} onClick={() => toggle(t)} />
          ))}
        </div>
        {err && <div style={{ color: '#fb7185', fontSize: 12 }}>{err}</div>}
        <div style={{ width: '100%', height: 380 }}>
          <ResponsiveContainer>
            <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="rgba(148,163,184,0.10)" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }}
                     minTickGap={48} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false}
                     tickLine={false} domain={['auto', 'auto']} width={44} />
              <Tooltip
                contentStyle={{ background: 'rgba(7,16,28,0.95)', border: '1px solid rgba(148,163,184,0.25)', borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(v, name) => [Number(v).toFixed(1), name]}
              />
              <ReferenceLine y={100} stroke="rgba(148,163,184,0.35)" strokeDasharray="2 4" />
              {tickers.filter(t => on.has(t)).map(t => (
                <Line key={t} type="monotone" dataKey={t} dot={false} connectNulls
                      stroke={SERIES_COLOR[t] || '#94a3b8'}
                      strokeWidth={t === 'TSUNAMI' ? 2.6 : 1.4}
                      strokeDasharray={INVERSE.has(t) ? '5 4' : undefined} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* book + trades */}
      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <div style={card}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 10 }}>Book</div>
          {book.length === 0 && <div style={{ fontSize: 12, color: '#64748b' }}>All cash — no instrument above its 50-day MA (or first rebalance pending).</div>}
          {book.map(b => (
            <div key={b.letf} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(148,163,184,0.08)', fontSize: 13, color: '#cbd5e1' }}>
              <span style={{ fontWeight: 700, color: SERIES_COLOR[b.letf] || '#e2e8f0' }}>{b.letf}</span>
              <span>{b.shares} sh @ ${Number(b.avg_cost).toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div style={card}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0', marginBottom: 10 }}>Recent fills</div>
          {trades.length === 0 && <div style={{ fontSize: 12, color: '#64748b' }}>No fills yet — first rebalance runs the next trading day at 14:45 CT.</div>}
          {trades.slice(0, 12).map((t, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(148,163,184,0.08)', fontSize: 12, color: '#cbd5e1' }}>
              <span style={{ color: t.side === 'BUY' ? '#4ade80' : '#fb7185', fontWeight: 700 }}>{t.side}</span>
              <span style={{ fontWeight: 600 }}>{t.letf}</span>
              <span>{t.shares} @ ${Number(t.price).toFixed(2)}</span>
              <span style={{ color: '#64748b' }}>{String(t.ts).slice(0, 10)}</span>
              <span style={{ color: t.realized_pnl > 0 ? '#4ade80' : t.realized_pnl < 0 ? '#fb7185' : '#64748b' }}>
                {t.realized_pnl != null ? `$${Number(t.realized_pnl).toFixed(2)}` : ''}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
