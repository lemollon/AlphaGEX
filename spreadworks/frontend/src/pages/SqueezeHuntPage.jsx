// SQUEEZE HUNT — small-cap float-velocity short-squeeze surface.
//
// NOT the dealer gamma-regime "squeeze" signal on the live /squeeze page
// (bots/gamma_regime.py) — different signal, different population, that
// page is untouched. This page reads a standalone research warehouse
// (DuckDB) via /api/spreadworks/squeeze-hunt/*.
//
// Three sections per spec: today's alert-like symbols (sorted by dollars
// traded), a money-pace view per symbol across the day's sweeps, and a
// prominent base-rate panel with the pre-registered numbers baked in
// verbatim (not recomputed here — see PREREG constants below).
import { useEffect, useState } from 'react';
import { Flame, TrendingUp, AlertTriangle } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';

const THEME = {
  primary: '#fb923c',
  primarySoft: 'rgba(251,146,60,0.10)',
  primaryRing: 'rgba(251,146,60,0.30)',
  glow: 'rgba(251,146,60,0.18)',
};

function money(v, decimals = 0) {
  if (v == null || Number.isNaN(v)) return '—';
  const abs = Math.abs(v);
  const str = abs.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return v < 0 ? `−$${str}` : `$${str}`;
}

function pct(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(decimals)}%`;
}

function num(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toFixed(decimals);
}

const STATE_COLOR = {
  'STILL FEEDING': '#4ade80',
  'DRYING UP': '#facc15',
  'HALTED': '#fb7185',
  'BOUNCE': '#94a3b8',
};

/* ── Base-rate panel — exact pre-registered numbers, do not recompute ── */

function BaseRatePanel() {
  return (
    <div
      className="px-5 py-5 rounded-lg mb-6"
      style={{
        background: 'rgba(251,146,60,0.05)',
        boxShadow: 'inset 0 0 0 1px rgba(251,146,60,0.20)',
      }}
    >
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={16} color={THEME.primary} />
        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em]" style={{ color: THEME.primary }}>
          Base Rates — Small-Cap Velocity Squeeze
        </h2>
      </div>

      <div className="text-[11px] text-text-tertiary mb-4 sw-mono">
        Population: bars_hold 2021-2026, alert-like days, buying SHARES, equal weight, 250-session hold.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div className="px-4 py-3 rounded-md sw-glass">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">Entry ≤ $5</div>
          <div className="text-[20px] font-bold sw-mono" style={{ color: '#4ade80' }}>mean +63%</div>
          <div className="text-[11px] text-text-secondary sw-mono mt-1">
            n=2,966 across 308 symbols &middot; 19.9% doubled
          </div>
        </div>
        <div className="px-4 py-3 rounded-md sw-glass">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">Entry &gt; $5</div>
          <div className="text-[20px] font-bold sw-mono" style={{ color: '#fb7185' }}>mean −49%</div>
          <div className="text-[11px] text-text-secondary sw-mono mt-1">3.7% doubled</div>
        </div>
        <div className="px-4 py-3 rounded-md sw-glass" style={{ boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}` }}>
          <div className="text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: THEME.primary }}>
            Best cut — sub-$5 AND SI 10-20%
          </div>
          <div className="text-[20px] font-bold sw-mono" style={{ color: '#4ade80' }}>mean +138%</div>
          <div className="text-[11px] text-text-secondary sw-mono mt-1">
            n=303 across 99 symbols &middot; 27.1% doubled &middot; 8.3% returned 5x &middot; 5.0% lost more than 80%
          </div>
        </div>
      </div>

      <div
        className="px-4 py-3 rounded-md mb-3 text-[12px] leading-relaxed"
        style={{ background: 'rgba(251,191,36,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.25)', color: '#fde68a' }}
      >
        <strong>Shape warning:</strong> ~20% of trades carry the whole return; the median trade still loses
        ~18%. Equal weight, let winners run — a stop truncates the tail that pays.
      </div>

      <div
        className="px-4 py-3 rounded-md text-[12px] leading-relaxed font-semibold"
        style={{ background: 'rgba(251,113,133,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)', color: '#fda4af' }}
      >
        PREREG #2 — UNPROVEN. Found by slicing spent history; recorded to a forward ledger only. No live
        capital before the read trigger.
      </div>
    </div>
  );
}

/* ── Money-pace mini table — dollar_vol by sweep, per symbol ─────────── */

function MoneyPaceRow({ symbol, points }) {
  const max = Math.max(1, ...points.map((p) => p.dollar_vol || 0));
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-white/5 last:border-0">
      <div className="w-16 shrink-0 font-bold sw-mono text-[12px] text-text-primary">{symbol}</div>
      <div className="flex-1 flex items-end gap-1 h-8">
        {points.map((p, i) => (
          <div
            key={i}
            title={`${p.sweep}: ${money(p.dollar_vol)} (${p.state || 'n/a'})`}
            className="flex-1 rounded-sm"
            style={{
              height: `${Math.max(6, ((p.dollar_vol || 0) / max) * 100)}%`,
              background: p.state === 'feeding' ? '#4ade80' : p.state === 'drying' ? '#facc15' : '#475569',
              opacity: 0.85,
            }}
          />
        ))}
      </div>
      <div className="w-24 shrink-0 text-right text-[11px] sw-mono text-text-tertiary">
        {points.length ? points[points.length - 1].sweep : '—'}
      </div>
    </div>
  );
}

/* ── Signals table ─────────────────────────────────────────────────── */

function SignalsTable({ signals, siSettlementDate }) {
  if (!signals.length) {
    return (
      <div className="px-5 py-10 text-center text-text-tertiary text-[13px]">
        No alert-like symbols today yet.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      {siSettlementDate && (
        <div className="px-4 pt-3 pb-1 text-[10.5px] text-text-tertiary sw-mono">
          Short interest as of FINRA settlement <strong style={{ color: THEME.primary }}>{siSettlementDate}</strong>
          {' '}— fuel BEFORE the run, not a live short position. It predates any move that started after it.
        </div>
      )}
      <table className="w-full text-[12.5px] sw-mono">
        <thead>
          <tr className="text-left text-text-tertiary text-[10.5px] uppercase tracking-[0.1em]">
            <th className="px-4 py-2">Symbol</th>
            <th className="px-4 py-2 text-right">Price</th>
            <th className="px-4 py-2 text-right">Day Chg</th>
            <th className="px-4 py-2 text-right">$ Traded</th>
            <th className="px-4 py-2 text-right">$ vs Normal</th>
            <th className="px-4 py-2 text-right">Float Turnover</th>
            <th className="px-4 py-2 text-right">Short Interest{siSettlementDate ? ` (${siSettlementDate})` : ''}</th>
            <th className="px-4 py-2">Money State</th>
            <th className="px-4 py-2 text-right">Spread %</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr
              key={s.symbol}
              className="border-t border-white/5 hover:bg-white/[0.02]"
              style={s.prereg_cut ? { background: 'rgba(74,222,128,0.06)', boxShadow: 'inset 3px 0 0 #4ade80' } : undefined}
            >
              <td className="px-4 py-2.5 font-bold text-text-primary">
                <div className="flex items-center gap-2">
                  {s.symbol}
                  {s.prereg_cut && (
                    <span
                      className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
                      style={{ background: 'rgba(74,222,128,0.18)', color: '#4ade80' }}
                      title="Sub-$5 AND short interest 10-20% — the PREREG #2 cut, on today's own numbers"
                    >
                      PREREG #2 CUT
                    </span>
                  )}
                  {s.lottery_setup && (
                    <span
                      className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider flex items-center gap-1"
                      style={{ background: 'rgba(251,146,60,0.18)', color: THEME.primary }}
                    >
                      <Flame size={9} /> Lottery Setup
                    </span>
                  )}
                </div>
              </td>
              <td className="px-4 py-2.5 text-right">${num(s.price, 2)}</td>
              <td className="px-4 py-2.5 text-right" style={{ color: (s.day_chg_pct || 0) >= 0 ? '#4ade80' : '#fb7185' }}>
                {pct(s.day_chg_pct)}
              </td>
              <td className="px-4 py-2.5 text-right text-text-primary font-semibold">{money(s.dollar_vol)}</td>
              <td className="px-4 py-2.5 text-right">{s.dollar_x != null ? `${num(s.dollar_x)}x` : '—'}</td>
              <td className="px-4 py-2.5 text-right">{s.float_turnover != null ? `${num(s.float_turnover)}x` : '—'}</td>
              <td className="px-4 py-2.5 text-right">
                {s.short_interest_pct != null ? `${num(s.short_interest_pct)}%` : '—'}
              </td>
              <td className="px-4 py-2.5">
                <span
                  className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                  style={{
                    background: `${STATE_COLOR[s.money_state] || '#64748b'}22`,
                    color: STATE_COLOR[s.money_state] || '#94a3b8',
                  }}
                >
                  {s.money_state}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">{s.spread_pct != null ? pct(s.spread_pct * 100) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function SqueezeHuntPage() {
  const [signals, setSignals] = useState([]);
  const [tape, setTape] = useState({});
  const [siSettlementDate, setSiSettlementDate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [sigRes, tapeRes] = await Promise.all([
          fetch(`${API_BASE}/api/spreadworks/squeeze-hunt/signals`),
          fetch(`${API_BASE}/api/spreadworks/squeeze-hunt/tape`),
        ]);
        if (!sigRes.ok) throw new Error(`signals ${sigRes.status}`);
        if (!tapeRes.ok) throw new Error(`tape ${tapeRes.status}`);
        const sigData = await sigRes.json();
        const tapeData = await tapeRes.json();
        if (!cancelled) {
          setSignals(sigData.signals || []);
          setTape(tapeData.symbols || {});
          setSiSettlementDate(sigData.si_settlement_date || null);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'load failed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const iv = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <div
        className="px-4 md:px-8 pt-7 pb-6"
        style={{ borderBottom: '1px solid rgba(251,146,60,0.18)' }}
      >
        <div className="flex items-center gap-4">
          <div
            className="w-14 h-14 rounded-2xl grid place-items-center flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, rgba(251,146,60,0.22) 0%, rgba(251,146,60,0.03) 100%)',
              boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}, 0 0 32px -8px ${THEME.glow}`,
              color: THEME.primary,
            }}
          >
            <TrendingUp size={26} strokeWidth={1.8} />
          </div>
          <div>
            <h1 className="font-black tracking-[0.04em] leading-none text-[24px] md:text-[36px]" style={{ color: THEME.primary }}>
              SQUEEZE HUNT
            </h1>
            <p className="text-[12.5px] text-text-tertiary mt-1.5">
              Small-cap float-velocity short squeeze &middot; not the dealer gamma /squeeze page
            </p>
          </div>
        </div>
      </div>

      <div className="px-4 md:px-8 py-6">
        <BaseRatePanel />

        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
          Today's Signals
        </h2>
        <div className="rounded-lg sw-glass mb-6" style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}>
          {loading ? (
            <div className="px-5 py-10 text-center text-text-tertiary text-[13px]">Loading…</div>
          ) : error ? (
            <div className="px-5 py-10 text-center text-[13px]" style={{ color: '#fb7185' }}>
              {error}
            </div>
          ) : (
            <SignalsTable signals={signals} siSettlementDate={siSettlementDate} />
          )}
        </div>

        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
          Money Pace — Dollars by Sweep
        </h2>
        <div className="rounded-lg sw-glass" style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}>
          {loading ? (
            <div className="px-5 py-10 text-center text-text-tertiary text-[13px]">Loading…</div>
          ) : Object.keys(tape).length === 0 ? (
            <div className="px-5 py-10 text-center text-text-tertiary text-[13px]">No tape yet today.</div>
          ) : (
            Object.entries(tape).map(([symbol, points]) => (
              <MoneyPaceRow key={symbol} symbol={symbol} points={points} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
