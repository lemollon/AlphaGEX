// TSUNAMI — LETF trend bot page.
// Same data + behavior as before (status, comparison chart, book, fills);
// the LOOK now matches the other bot dashboards: themed glyph nameplate,
// sw-glass KPI tiles, branded card chrome. TSUNAMI is stock-only (buys and
// sells shares), so instead of payoff/positions tabs it keeps its own
// centerpiece: the indexed comparison chart plus the share book and fills.
import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, CartesianGrid,
} from 'recharts';
import { API_URL as API_BASE } from '../lib/api';
import BotGlyph from '../components/bots/BotGlyph';

// Page theme — mirrors the BOT_THEME shape in lib/botRegistry.js. TSUNAMI
// isn't a registry bot (own engine + routes) so its theme lives here.
// sky-300 to match the nav menu's pinned TSUNAMI row.
const THEME = {
  glyph:       'wave',
  primary:     '#7dd3fc',
  primarySoft: 'rgba(125,211,252,0.10)',
  primaryRing: 'rgba(125,211,252,0.30)',
  glow:        'rgba(125,211,252,0.18)',
  accentBg:    'linear-gradient(135deg, rgba(125,211,252,0.22) 0%, rgba(125,211,252,0.03) 100%)',
};

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

function money(v, { signed = false, decimals = 2 } = {}) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  const abs = Math.abs(v);
  const str = abs.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (signed) return `${sign}$${str}`;
  return v < 0 ? `−$${str}` : `$${str}`;
}

/* ── KPI tile — same chrome as BotDashboard's KpiTile ───────────────── */

function KpiTile({ label, value, sub, mono = true, accent }) {
  return (
    <div
      className="px-5 py-4 rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className={`leading-none ${mono ? 'sw-mono' : ''}`}
        style={{ fontSize: 28, fontWeight: 700, color: accent || 'var(--color-text-primary)' }}
      >
        {value}
      </div>
      <div className="text-[10.5px] uppercase tracking-[0.16em] font-semibold text-text-tertiary mt-3">
        {label}
      </div>
      {sub && (
        <div className="text-[11px] text-text-tertiary mt-1.5 sw-mono">{sub}</div>
      )}
    </div>
  );
}

/* ── Series chip — brand pill, same interaction as before ───────────── */

function Chip({ id, on, held, onClick }) {
  const c = SERIES_COLOR[id] || '#94a3b8';
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full cursor-pointer text-[12px] font-semibold sw-mono transition-all"
      style={{
        color: on ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
        background: on ? 'rgba(148,163,184,0.10)' : 'transparent',
        boxShadow: `inset 0 0 0 1px ${on ? c : 'rgba(100,116,139,0.35)'}`,
        opacity: on ? 1 : 0.7,
      }}
    >
      <span style={{
        width: 14, height: 0, borderTop: `2px ${INVERSE.has(id) ? 'dashed' : 'solid'} ${c}`,
      }} />
      {id}
      {INVERSE.has(id) && (
        <span className="text-[9px] font-bold tracking-wider text-text-secondary">SHORT</span>
      )}
      {held && (
        <span className="text-[9px] font-bold tracking-wider text-sw-green">● HELD</span>
      )}
    </button>
  );
}

/* ── Nameplate header — mirrors BotHeader in BotDashboard ───────────── */

function TsunamiHeader() {
  return (
    <div
      className="px-4 md:px-8 pt-7 pb-6"
      style={{ borderBottom: '1px solid rgba(125,211,252,0.18)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex items-center gap-5 min-w-0">
          {/* Glyph tile */}
          <div
            className="w-16 h-16 rounded-2xl grid place-items-center flex-shrink-0"
            style={{
              background: THEME.accentBg,
              boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}, 0 0 32px -8px ${THEME.glow}`,
              color: THEME.primary,
            }}
          >
            <BotGlyph kind={THEME.glyph} size={32} strokeWidth={1.6} />
          </div>

          {/* Nameplate */}
          <div className="min-w-0">
            <h1
              className="font-black tracking-[0.04em] leading-none text-[28px] md:text-[44px]"
              style={{ color: THEME.primary, textShadow: `0 0 24px ${THEME.glow}` }}
            >
              TSUNAMI
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-2 text-[13.5px] text-text-secondary">
              <span className="font-medium">LETF Trend Engine</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono font-semibold text-white">12 instruments</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono text-text-tertiary">
                stocks only · daily rebalance 14:45 CT
              </span>
            </div>
          </div>
        </div>

        {/* Status badges — no toggle/force-trade: TSUNAMI trades shares on a
            fixed daily rebalance, not on-demand option structures. */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-sw-yellow bg-sw-yellow-dim ring-1 ring-sw-yellow/30">
            Paper
          </span>
          <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-sw-green bg-sw-green-dim ring-1 ring-sw-green/30">
            <span className="relative inline-flex w-1.5 h-1.5">
              <span className="absolute inset-0 rounded-full animate-ping opacity-60 bg-sw-green" />
              <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-sw-green" />
            </span>
            Enabled
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Card shell — matches the sw-glass card chrome on bot pages ─────── */

function Card({ title, subtitle, children, headerRight }) {
  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex flex-wrap items-center justify-between gap-2"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-[14px] font-semibold text-text-primary">{title}</h3>
          {subtitle && <span className="text-[11.5px] text-text-tertiary">{subtitle}</span>}
        </div>
        {headerRight}
      </div>
      {children}
    </div>
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
  const heldCount = book.filter(b => b.shares > 0).length;
  const lastFill = trades.length ? String(trades[0].ts).slice(0, 10) : null;

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <TsunamiHeader />

      <div className="px-4 md:px-8 py-6 space-y-5">
        {/* KPI strip — stock-bot stats: equity / cash / held names / last fill */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiTile
            label="Account Equity"
            value={equity != null ? money(equity) : '…'}
            sub="Allocated · TSUNAMI"
          />
          <KpiTile
            label="Cash"
            value={cash != null ? money(cash) : '…'}
            sub={
              equity != null && cash != null && equity > 0
                ? `${((cash / equity) * 100).toFixed(0)}% of equity uninvested`
                : undefined
            }
          />
          <KpiTile
            label="Positions"
            value={String(heldCount)}
            accent={heldCount > 0 ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)'}
            sub={heldCount > 0 ? 'Names held · shares' : 'All cash'}
          />
          <KpiTile
            label="Last Fill"
            value={
              lastFill
                ? <span className="text-sw-green text-[20px]">{lastFill}</span>
                : <span className="text-text-muted">—</span>
            }
            sub={lastFill ? `${trades.length} recent fills` : 'Awaiting first rebalance'}
          />
        </div>

        {/* Comparison chart — TSUNAMI's centerpiece (stock bot: no payoff
            diagram; the strategy IS relative performance vs its universe). */}
        <Card
          title="TSUNAMI vs. its instruments"
          subtitle="Indexed to 100 at the left edge · dashed = inverse (short-side) products"
        >
          <div className="px-5 pt-4 pb-5">
            <div className="flex flex-wrap gap-1.5 mb-4">
              {tickers.map(t => (
                <Chip key={t} id={t} on={on.has(t)} held={held.has(t)} onClick={() => toggle(t)} />
              ))}
            </div>
            {err && <div className="text-sw-red text-[12px] mb-2">{err}</div>}
            <div className="w-full h-[380px]">
              <ResponsiveContainer>
                <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="rgba(125,211,252,0.06)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }}
                         minTickGap={48} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }} axisLine={false}
                         tickLine={false} domain={['auto', 'auto']} width={44} />
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(13,28,46,0.95)',
                      border: '1px solid rgba(125,211,252,0.25)',
                      borderRadius: 10, fontSize: 12, fontFamily: 'JetBrains Mono',
                    }}
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
        </Card>

        {/* Book + fills — the stock-bot stand-ins for Positions / Trade History */}
        <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
          <Card title="Book" subtitle="Shares held per instrument">
            <div className="px-5 py-3">
              {book.length === 0 && (
                <div className="py-8 text-center text-[12.5px] text-text-tertiary">
                  All cash — no instrument above its 50-day MA (or first rebalance pending).
                </div>
              )}
              {book.map(b => (
                <div
                  key={b.letf}
                  className="flex items-center justify-between py-2.5 text-[13px] text-text-body"
                  style={{ borderBottom: '1px solid rgba(125,211,252,0.06)' }}
                >
                  <span className="inline-flex items-center gap-2 font-bold sw-mono"
                        style={{ color: SERIES_COLOR[b.letf] || 'var(--color-text-primary)' }}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: SERIES_COLOR[b.letf] || '#94a3b8' }} />
                    {b.letf}
                  </span>
                  <span className="sw-mono">
                    {b.shares} sh <span className="text-text-tertiary">@</span> ${Number(b.avg_cost).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Recent Fills" subtitle="Latest buys and sells">
            <div className="px-5 py-3">
              {trades.length === 0 && (
                <div className="py-8 text-center text-[12.5px] text-text-tertiary">
                  No fills yet — first rebalance runs the next trading day at 14:45 CT.
                </div>
              )}
              {trades.slice(0, 12).map((t, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 justify-between py-2.5 text-[12.5px] text-text-body sw-mono"
                  style={{ borderBottom: '1px solid rgba(125,211,252,0.06)' }}
                >
                  <span
                    className="text-[10.5px] font-bold tracking-wider px-1.5 py-0.5 rounded"
                    style={
                      t.side === 'BUY'
                        ? { color: 'var(--color-sw-green)', background: 'var(--color-sw-green-dim)', boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.30)' }
                        : { color: 'var(--color-sw-red)', background: 'var(--color-sw-red-dim)', boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)' }
                    }
                  >
                    {t.side}
                  </span>
                  <span className="font-semibold" style={{ color: SERIES_COLOR[t.letf] || 'var(--color-text-primary)' }}>
                    {t.letf}
                  </span>
                  <span>{t.shares} @ ${Number(t.price).toFixed(2)}</span>
                  <span className="text-text-tertiary">{String(t.ts).slice(0, 10)}</span>
                  <span style={{
                    color: t.realized_pnl > 0 ? 'var(--color-sw-green)'
                         : t.realized_pnl < 0 ? 'var(--color-sw-red)'
                         : 'var(--color-text-tertiary)',
                  }}>
                    {t.realized_pnl != null ? money(t.realized_pnl, { signed: true }) : ''}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
