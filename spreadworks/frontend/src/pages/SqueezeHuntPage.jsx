// SQUEEZE HUNT — small-cap float-velocity short-squeeze surface.
//
// NOT the dealer gamma-regime "squeeze" signal on the live /squeeze page
// (bots/gamma_regime.py) — different signal, different population, that
// page is untouched. This page reads a standalone research warehouse
// (DuckDB) via /api/spreadworks/squeeze-hunt/*.
//
// Reading order is deliberate and must stay this way:
//   1. THE CALL — how many names hit the PREREG #2 cut today, and the
//      standing "record only, no capital" rule. Never below the fold.
//   2. Today's names, cut names grouped FIRST, one row per symbol with the
//      intraday pace folded in as a sparkline column (it used to be a
//      second full-width table below, which buried the table above it).
//   3. Base rates — reference, not a decision. Collapsed by default.
//   4. Tracked-but-quiet symbols — collapsed.
//
// Base-rate numbers are the pre-registered ones, verbatim. Not recomputed
// here — see the project overview.
import { useEffect, useMemo, useState } from 'react';
import { Flame, TrendingUp, AlertTriangle, ChevronRight, Clock } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';

const THEME = {
  primary: '#fb923c',
  primaryRing: 'rgba(251,146,60,0.30)',
  glow: 'rgba(251,146,60,0.18)',
  green: '#4ade80',
  amber: '#facc15',
  red: '#fb7185',
  dim: '#64748b',
};

/* ── formatting ──────────────────────────────────────────────────── */

// Compact dollars: $298.5M reads instantly, $298,523,620 does not.
function moneyCompact(v) {
  if (v == null || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  const s = v < 0 ? '−' : '';
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${a.toFixed(0)}`;
}

function moneyFull(v) {
  if (v == null || Number.isNaN(v)) return '—';
  return `$${Math.round(v).toLocaleString('en-US')}`;
}

function pct(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(decimals)}%`;
}

// Unsigned percent — a spread or a short-interest level is never "+".
function pctPlain(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${v.toFixed(decimals)}%`;
}

function multiple(v) {
  if (v == null || Number.isNaN(v)) return '—';
  if (v >= 100) return `${Math.round(v).toLocaleString('en-US')}×`;
  if (v >= 10) return `${v.toFixed(0)}×`;
  return `${v.toFixed(1)}×`;
}

// A 48% spread means you cannot get anything near the modelled fill.
// Say so in colour instead of printing a number that looks like the others.
function spreadColor(spreadPct) {
  if (spreadPct == null) return 'var(--color-text-tertiary)';
  if (spreadPct >= 10) return THEME.red;
  if (spreadPct >= 5) return THEME.amber;
  return 'var(--color-text-secondary)';
}

const STATE_STYLE = {
  'STILL FEEDING': { label: 'FEEDING', color: THEME.green },
  'DRYING UP': { label: 'DRYING', color: THEME.amber },
  HALTED: { label: 'HALTED', color: THEME.red },
  BOUNCE: { label: 'BOUNCE', color: '#94a3b8' },
};

function stateStyle(s) {
  return STATE_STYLE[s] || { label: s && s !== '—' ? s : 'NO READ', color: THEME.dim };
}

function isBounce(dayKind) {
  return !!dayKind && dayKind.toUpperCase().includes('BOUNCE');
}

const SWEEP_COLOR = { feeding: THEME.green, drying: THEME.amber, halted: THEME.red };

// Wall-clock HH:MM from the scan's own timestamp.
//
// Use `ts`, NEVER `sweep`. `sweep` is a SLOT LABEL, not a time: the scanner
// rounds each run to the nearest scheduled slot (10:00 / 12:30 / 14:45) so a
// minute of scheduler drift does not create a new bucket. A tape run at 14:00
// is therefore labelled "14:45".
//
// On 2026-08-31 the real 14:45 sweep — the PRIMARY one the forward test reads
// — died on a DNS failure and never ran, yet this page displayed
// "last sweep 14:45" because a 14:00 run wore that label. The page asserted
// that the decisive sweep had happened at the exact moment it had not.
//
// These timestamps are already CT wall-clock, so slice the string; passing
// them through Date() would re-interpret them as UTC and shift the hour.
function clock(ts) {
  return typeof ts === 'string' && ts.length >= 16 ? ts.slice(11, 16) : null;
}

function lastPoint(points) {
  return points && points.length ? points[points.length - 1] : null;
}

/* ── Intraday pace sparkline — dollars per sweep, one bar per sweep ── */

function PaceSpark({ points, width = 118, height = 22 }) {
  if (!points || !points.length) {
    return <div className="text-[11px] text-text-tertiary sw-mono">—</div>;
  }
  const max = Math.max(1, ...points.map((p) => p.dollar_vol || 0));
  return (
    <div className="flex items-end gap-[2px] shrink-0" style={{ width, height }}>
      {points.map((p, i) => (
        <div
          key={i}
          title={`${clock(p.ts) || p.sweep} · ${moneyFull(p.dollar_vol)} · ${p.state || 'no read'}`}
          className="flex-1 rounded-[1px]"
          style={{
            height: `${Math.max(8, ((p.dollar_vol || 0) / max) * 100)}%`,
            background: SWEEP_COLOR[p.state] || '#3f4c5f',
          }}
        />
      ))}
    </div>
  );
}

function SparkLegend() {
  const items = [
    ['Money still arriving', THEME.green],
    ['Drying up', THEME.amber],
    ['Quiet sweep', '#3f4c5f'],
  ];
  return (
    <div className="flex items-center gap-4 text-[10.5px] text-text-tertiary">
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/* ── THE CALL — what to do today, above everything else ───────────── */

function VerdictBar({ loading, error, cutNames, totalNames, asOf, noSiCount, signalDate, isToday }) {
  let headline;
  let color = THEME.primary;
  if (loading) {
    headline = 'Loading today’s tape…';
  } else if (error) {
    headline = 'Warehouse unreachable — nothing to act on';
    color = THEME.red;
  } else if (!totalNames) {
    headline = 'No alert-like names today — nothing to record';
  } else if (!cutNames.length) {
    headline = `No name hits the cut today (${totalNames} alert-like)`;
    color = '#94a3b8';
  } else {
    headline = `${cutNames.length} ${cutNames.length === 1 ? 'name hits' : 'names hit'} the cut today`;
    color = THEME.green;
  }

  return (
    <div
      className="px-5 py-4 rounded-lg mb-5"
      style={{ background: 'rgba(251,146,60,0.06)', boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}` }}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-[10px] uppercase tracking-[0.18em] text-text-tertiary">Today</span>
        <span className="text-[16px] md:text-[18px] font-bold" style={{ color }}>{headline}</span>
        {cutNames.map((s) => (
          <span
            key={s}
            className="px-2 py-0.5 rounded text-[12px] font-bold sw-mono"
            style={{ background: 'rgba(74,222,128,0.16)', color: THEME.green }}
          >
            {s}
          </span>
        ))}
        {(signalDate || asOf) && (
          <span
            className="ml-auto flex items-center gap-1.5 text-[11px] sw-mono"
            style={{ color: isToday === false ? THEME.amber : 'var(--color-text-tertiary)' }}
          >
            <Clock size={11} />
            {/* Only pair a sweep clock with the date when they are the SAME
                day. The signals endpoint returns the newest signal date and
                the tape endpoint the newest tape date, and before the first
                signal of a session those disagree — showing
                "2026-08-31 · last sweep 09:00" reads as one moment when it is
                two different days. */}
            {signalDate
              ? `${signalDate}${isToday && asOf ? ` · last sweep ${asOf}` : ''}`
              : `last sweep ${asOf}`}
          </span>
        )}
      </div>

      {/* A scan that stopped running still renders a full, confident table.
          Say the date is not today rather than letting stale rows read live. */}
      {isToday === false && signalDate && (
        <div
          className="mt-2 px-3 py-2 rounded-md text-[12.5px] leading-relaxed"
          style={{ background: 'rgba(250,204,21,0.10)', boxShadow: 'inset 0 0 0 1px rgba(250,204,21,0.30)', color: '#fde68a' }}
        >
          <strong>This is not today.</strong> The newest scan on record is{' '}
          <strong className="sw-mono">{signalDate}</strong>. Everything below is that day, not the current
          session — check that the 14:45 sweep and the 20:00 screen actually ran before reading anything into it.
        </div>
      )}

      {/* The cut REQUIRES short interest of 10-20%. A name with no trusted SI
          figure cannot qualify, so a "0 hit the cut" headline is partly a
          coverage fact, not a market fact. Say which it is. */}
      {noSiCount > 0 && totalNames > 0 && (
        <div className="mt-2 text-[12.5px] leading-relaxed" style={{ color: '#fde68a' }}>
          <strong>{noSiCount} of {totalNames}</strong> {noSiCount === 1 ? 'name has' : 'names have'} no trusted
          short-interest figure, so {noSiCount === 1 ? 'it' : 'they'} <strong>cannot qualify for the cut</strong>{' '}
          whatever the price does. Read the count above as coverage, not as a market verdict.
        </div>
      )}

      <div className="mt-2 text-[12.5px] leading-relaxed text-text-secondary">
        <strong style={{ color: THEME.red }}>Record only.</strong>{' '}
        The cut is <strong>unproven</strong> — it was found by slicing spent history and is being written to a
        forward ledger. No live capital before the read trigger (150 distinct symbols, or 2028-12-31).
      </div>
    </div>
  );
}

/* ── Base rates — reference. Collapsed by default so it stops shouting ── */

function BaseRates() {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-lg mb-6"
      style={{ background: 'rgba(251,146,60,0.04)', boxShadow: 'inset 0 0 0 1px rgba(251,146,60,0.16)' }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-5 py-3 text-left"
      >
        <AlertTriangle size={14} color={THEME.primary} className="shrink-0" />
        <span className="text-[12px] font-bold uppercase tracking-[0.12em] shrink-0" style={{ color: THEME.primary }}>
          Why these names
        </span>
        <span className="text-[12px] text-text-secondary hidden sm:inline">
          Sub-$5 entries averaged <strong style={{ color: THEME.green }}>+63%</strong>; over $5 averaged{' '}
          <strong style={{ color: THEME.red }}>−49%</strong>.
        </span>
        <ChevronRight
          size={15}
          className="ml-auto shrink-0 transition-transform"
          style={{ color: THEME.primary, transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="px-5 pb-5">
          <div className="text-[11px] text-text-tertiary sw-mono mb-3">
            2021-2026, alert-like days, buying shares, equal weight, held 250 sessions.
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <div className="px-4 py-3 rounded-md sw-glass">
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">Entry ≤ $5</div>
              <div className="text-[19px] font-bold sw-mono" style={{ color: THEME.green }}>+63% average</div>
              <div className="text-[11px] text-text-secondary sw-mono mt-1">
                2,966 trades · 308 symbols · 1 in 5 doubled
              </div>
            </div>
            <div className="px-4 py-3 rounded-md sw-glass">
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">Entry &gt; $5</div>
              <div className="text-[19px] font-bold sw-mono" style={{ color: THEME.red }}>−49% average</div>
              <div className="text-[11px] text-text-secondary sw-mono mt-1">only 3.7% doubled — this is the bag</div>
            </div>
            <div
              className="px-4 py-3 rounded-md sw-glass"
              style={{ boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}` }}
            >
              <div className="text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: THEME.primary }}>
                The cut — under $5 AND short interest 10-20%
              </div>
              <div className="text-[19px] font-bold sw-mono" style={{ color: THEME.green }}>+138% average</div>
              <div className="text-[11px] text-text-secondary sw-mono mt-1">
                303 trades · 99 symbols · 27% doubled · 8% returned 5× · 5% lost more than 80%
              </div>
            </div>
          </div>
          <div
            className="px-4 py-3 rounded-md text-[12px] leading-relaxed"
            style={{
              background: 'rgba(251,191,36,0.08)',
              boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.25)',
              color: '#fde68a',
            }}
          >
            <strong>The shape, not the average, is the trade:</strong> about 1 trade in 5 carries the entire
            return, and the typical trade still loses ~18%. Equal-weight every name and let the winners run —
            a stop cuts off the tail that pays for the rest.
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Signals table ─────────────────────────────────────────────────── */

const COL_HEAD = 'px-3 py-2 text-[10px] uppercase tracking-[0.1em] font-semibold text-text-tertiary';

// Plain English, on hover. Every one of these says what the number MEANS,
// not what it is called — "float turnover" is not self-explanatory to
// anyone who hasn't just read the research.
const COL_TIP = {
  symbol:
    'The ticker. A green rail and "hits the cut" group mean it is under $5 with short interest between 10% and 20% — the pre-registered PREREG #2 cut. A STALE chip means this row has not been swept since the time shown.',
  price:
    'Last price, and how far the stock has moved today. Under $5 at entry is the single biggest divider in the research: sub-$5 names averaged +63%, over-$5 names averaged −49%.',
  dollars:
    'Actual dollars that changed hands today, and how many times a normal day that is. This is the money showing up — a 4,000x day means something happened, not that the stock drifted.',
  float:
    'How many times the entire freely-tradable share count turned over today. Above 1x means every available share changed hands at least once — that is the velocity this whole screen is built to find.',
  si:
    'Percent of shares sold short as of the last FINRA settlement. This is the FUEL that was already sitting there before the run — it is not a live short position, and it predates any move that started after the settlement date. A dash means no trusted figure, which also means the name CANNOT qualify for the cut.',
  pace:
    'Dollars arriving in each sweep through the day, left to right, and where the money stands right now. Green means money is still arriving, amber means it is drying up, grey means a quiet sweep.',
  spread:
    'How wide the bid/ask is, as a percent of price. This is what it costs you to get in and out. Above 10% the modelled fill is fiction — you will not get anything near the price the research assumes.',
};

// A header you can hover has to look like one, or nobody hovers it.
const TIP_STYLE = {
  cursor: 'help',
  textDecoration: 'underline dotted rgba(148,163,184,0.45)',
  textUnderlineOffset: '3px',
};

function GroupHeader({ label, count, color, note }) {
  return (
    <tr>
      <td colSpan={7} className="px-3 pt-4 pb-1.5">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-[11px] font-bold uppercase tracking-[0.14em]" style={{ color }}>
            {label}
          </span>
          <span className="text-[11px] text-text-tertiary sw-mono">{count}</span>
          {note && <span className="text-[11px] text-text-tertiary">· {note}</span>}
        </div>
      </td>
    </tr>
  );
}

function SignalRow({ s, points, stale }) {
  const st = stateStyle(s.money_state);
  const spread = s.spread_pct != null ? s.spread_pct * 100 : null;
  const siInBand =
    s.short_interest_pct != null && s.short_interest_pct >= 10 && s.short_interest_pct <= 20;
  return (
    <tr
      className="border-t border-white/5 hover:bg-white/[0.03]"
      style={s.prereg_cut ? { background: 'rgba(74,222,128,0.05)', boxShadow: 'inset 3px 0 0 #4ade80' } : undefined}
    >
      {/* Symbol */}
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[14px] text-text-primary sw-mono">{s.symbol}</span>
          {s.lottery_setup && (
            <span
              className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider flex items-center gap-1"
              style={{ background: 'rgba(251,146,60,0.18)', color: THEME.primary }}
              title="Confirmed in the lottery ledger today"
            >
              <Flame size={9} /> Ledger
            </span>
          )}
          {/* BOUNCE is the ONLY day-type that carried forward information in
              the research (+26% vs +64%). It used to be visible only when the
              tape had no state at all, so a FEEDING bounce hid the one thing
              worth knowing. It gets its own chip now. */}
          {isBounce(s.day_kind) && (
            <span
              className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
              style={{ background: 'rgba(148,163,184,0.18)', color: '#cbd5e1' }}
              title="A bounce off a prior decline, not a fresh break. These averaged +26% against +64% for the rest — the only day-type that carried any forward information."
            >
              Bounce
            </span>
          )}
          {stale && (
            <span
              className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
              style={{ background: 'rgba(148,163,184,0.15)', color: '#94a3b8' }}
              title="No sweep since this time — these numbers are older than the rest of the table"
            >
              stale {stale}
            </span>
          )}
        </div>
      </td>

      {/* Price + day change */}
      <td className="px-3 py-3 text-right">
        <div className="text-[14px] font-semibold text-text-primary sw-mono">
          ${(s.price ?? 0).toFixed(2)}
        </div>
        <div
          className="text-[11.5px] sw-mono"
          style={{ color: (s.day_chg_pct || 0) >= 0 ? THEME.green : THEME.red }}
        >
          {pct(s.day_chg_pct)}
        </div>
      </td>

      {/* Dollars traded + how abnormal that is */}
      <td className="px-3 py-3 text-right" title={moneyFull(s.dollar_vol)}>
        <div className="text-[14px] font-semibold text-text-primary sw-mono">{moneyCompact(s.dollar_vol)}</div>
        <div className="text-[11.5px] text-text-tertiary sw-mono">
          {s.dollar_x != null ? `${multiple(s.dollar_x)} normal` : '—'}
        </div>
      </td>

      {/* Float turnover — >=1x means the entire float changed hands today */}
      <td className="px-3 py-3 text-right">
        <div
          className="text-[14px] font-semibold sw-mono"
          style={{ color: (s.float_turnover || 0) >= 1 ? THEME.primary : 'var(--color-text-secondary)' }}
          title={
            (s.float_turnover || 0) >= 1
              ? 'The whole float changed hands today'
              : 'Less than the whole float changed hands today'
          }
        >
          {multiple(s.float_turnover)}
        </div>
      </td>

      {/* Short interest — the sub-line only appears when it means something.
          No SI is not a cosmetic blank: the cut needs 10-20%, so the row is
          disqualified outright and must not read as a quiet zero. */}
      <td className="px-3 py-3 text-right">
        <div
          className="text-[14px] font-semibold sw-mono"
          style={{ color: siInBand ? THEME.green : 'var(--color-text-secondary)' }}
          title={
            s.short_interest_pct == null
              ? 'No trusted short-interest figure for this name — it cannot qualify for the cut'
              : undefined
          }
        >
          {pctPlain(s.short_interest_pct)}
        </div>
        {siInBand && <div className="text-[11px]" style={{ color: THEME.green }}>in the band</div>}
        {s.short_interest_pct == null && (
          <div className="text-[11px]" style={{ color: THEME.amber }}>no data — can’t qualify</div>
        )}
      </td>

      {/* Intraday pace + current state */}
      <td className="px-3 py-3">
        <div className="flex items-center gap-3">
          <PaceSpark points={points} />
          <span
            className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider whitespace-nowrap"
            style={{ background: `${st.color}22`, color: st.color }}
          >
            {st.label}
          </span>
        </div>
      </td>

      {/* Spread */}
      <td className="px-3 py-3 text-right">
        <div className="text-[13px] font-semibold sw-mono" style={{ color: spreadColor(spread) }}>
          {pctPlain(spread)}
        </div>
        {spread != null && spread >= 10 && (
          <div className="text-[11px]" style={{ color: spreadColor(spread) }}>hard to fill</div>
        )}
      </td>
    </tr>
  );
}

function SignalsTable({ signals, tape, latestSweep }) {
  const cut = signals.filter((s) => s.prereg_cut);
  const rest = signals.filter((s) => !s.prereg_cut);

  const renderRows = (rows) =>
    rows.map((s) => {
      const points = tape[s.symbol] || [];
      const last = clock(lastPoint(points)?.ts);
      const stale = last && latestSweep && last !== latestSweep ? last : null;
      return <SignalRow key={s.symbol} s={s} points={points} stale={stale} />;
    });

  return (
    <table className="w-full min-w-[1040px] table-fixed">
      <colgroup>
        <col style={{ width: '19%' }} />
        <col style={{ width: '11%' }} />
        <col style={{ width: '15%' }} />
        <col style={{ width: '11%' }} />
        <col style={{ width: '11%' }} />
        <col style={{ width: '23%' }} />
        <col style={{ width: '10%' }} />
      </colgroup>
      <thead>
        <tr className="border-b border-white/5">
          <th className={`${COL_HEAD} text-left`}>
            <span style={TIP_STYLE} title={COL_TIP.symbol}>Symbol</span>
          </th>
          <th className={`${COL_HEAD} text-right`}>
            <span style={TIP_STYLE} title={COL_TIP.price}>Price</span>
          </th>
          <th className={`${COL_HEAD} text-right`}>
            <span style={TIP_STYLE} title={COL_TIP.dollars}>Dollars traded</span>
          </th>
          <th className={`${COL_HEAD} text-right`}>
            <span style={TIP_STYLE} title={COL_TIP.float}>Float turns</span>
          </th>
          <th className={`${COL_HEAD} text-right`}>
            <span style={TIP_STYLE} title={COL_TIP.si}>Short int.</span>
          </th>
          <th className={`${COL_HEAD} text-left`}>
            <span style={TIP_STYLE} title={COL_TIP.pace}>Money through the day</span>
          </th>
          <th className={`${COL_HEAD} text-right`}>
            <span style={TIP_STYLE} title={COL_TIP.spread}>Spread</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {cut.length > 0 && (
          <>
            <GroupHeader
              label="Hits the cut"
              count={cut.length}
              color={THEME.green}
              note="under $5 and short interest 10-20%"
            />
            {renderRows(cut)}
          </>
        )}
        {rest.length > 0 && (
          <>
            <GroupHeader
              label={cut.length ? 'Everything else moving' : 'Alert-like today'}
              count={rest.length}
              color="#94a3b8"
              note={cut.length ? 'outside the cut — watch only' : 'none met the cut'}
            />
            {renderRows(rest)}
          </>
        )}
      </tbody>
    </table>
  );
}

/* ── Quiet symbols — on the tape, no signal. Collapsed. ────────────── */

function QuietSymbols({ entries }) {
  const [open, setOpen] = useState(false);
  if (!entries.length) return null;
  return (
    <div className="rounded-lg sw-glass" style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left"
      >
        <span className="text-[12px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Also on the tape, no signal
        </span>
        <span className="text-[12px] text-text-tertiary sw-mono">{entries.length}</span>
        <ChevronRight
          size={15}
          className="ml-auto transition-transform text-text-tertiary"
          style={{ transform: open ? 'rotate(90deg)' : 'none' }}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-8 gap-y-0">
          {entries.map(([symbol, points]) => (
            <div key={symbol} className="flex items-center gap-3 py-1.5 border-b border-white/5">
              <span className="w-14 shrink-0 font-bold sw-mono text-[12px] text-text-secondary">{symbol}</span>
              <PaceSpark points={points} width={90} height={16} />
              <span className="ml-auto text-[11px] text-text-tertiary sw-mono">
                {clock(lastPoint(points)?.ts) || '—'}
              </span>
            </div>
          ))}
        </div>
      )}
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
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, []);

  const cutNames = useMemo(
    () => signals.filter((s) => s.prereg_cut).map((s) => s.symbol),
    [signals],
  );

  // Latest sweep anywhere on the tape. A symbol whose last sweep is older
  // than this is stale, and its row says so — instead of quietly showing an
  // hours-old number next to a fresh one.
  const latestSweep = useMemo(() => {
    let best = null;
    for (const points of Object.values(tape)) {
      const last = clock(lastPoint(points)?.ts);
      if (last && (best == null || last > best)) best = last;
    }
    return best;
  }, [tape]);

  // How many of today's names have no trusted short-interest figure. The cut
  // needs 10-20%, so each one is disqualified before price is even considered
  // — without this the "0 hit the cut" headline reads as a market fact.
  const noSiCount = useMemo(
    () => signals.filter((s) => s.short_interest_pct == null).length,
    [signals],
  );

  // The date the newest scan covers, taken from the signals themselves. A
  // scheduled task that quietly stopped still renders a full, confident
  // table; this is what catches that.
  const { signalDate, isToday } = useMemo(() => {
    const ts = signals.find((s) => s.signal_ts)?.signal_ts;
    if (!ts) return { signalDate: null, isToday: null };
    const day = String(ts).slice(0, 10);
    const now = new Date();
    const localToday = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    return { signalDate: day, isToday: day === localToday };
  }, [signals]);

  const quietEntries = useMemo(() => {
    const signalled = new Set(signals.map((s) => s.symbol));
    return Object.entries(tape)
      .filter(([sym]) => !signalled.has(sym))
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [tape, signals]);

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <div className="px-4 md:px-8 pt-6 pb-5" style={{ borderBottom: '1px solid rgba(251,146,60,0.18)' }}>
        <div className="max-w-[1400px] mx-auto flex items-center gap-4">
          <div
            className="w-11 h-11 rounded-xl grid place-items-center flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, rgba(251,146,60,0.22) 0%, rgba(251,146,60,0.03) 100%)',
              boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}, 0 0 32px -8px ${THEME.glow}`,
              color: THEME.primary,
            }}
          >
            <TrendingUp size={22} strokeWidth={1.8} />
          </div>
          <div>
            <h1
              className="font-black tracking-[0.04em] leading-none text-[22px] md:text-[28px]"
              style={{ color: THEME.primary }}
            >
              SQUEEZE HUNT
            </h1>
            <p className="text-[12px] text-text-tertiary mt-1.5">
              Small-cap stocks whose whole float turns over in a day &middot; not the dealer-gamma /squeeze page
            </p>
          </div>
        </div>
      </div>

      <div className="px-4 md:px-8 py-6">
        <div className="max-w-[1400px] mx-auto">
          <VerdictBar
            loading={loading}
            error={error}
            cutNames={cutNames}
            totalNames={signals.length}
            asOf={latestSweep}
            noSiCount={noSiCount}
            signalDate={signalDate}
            isToday={isToday}
          />

          <BaseRates />

          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2.5">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary">
              Today&rsquo;s names
            </h2>
            <span className="ml-auto">
              <SparkLegend />
            </span>
          </div>

          <div
            className="rounded-lg sw-glass overflow-x-auto"
            style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}
          >
            {loading ? (
              <div className="px-5 py-12 text-center text-text-tertiary text-[13px]">Loading…</div>
            ) : error ? (
              <div className="px-5 py-12 text-center text-[13px]" style={{ color: THEME.red }}>
                {error}
              </div>
            ) : !signals.length ? (
              <div className="px-5 py-12 text-center text-text-tertiary text-[13px]">
                No alert-like symbols today yet.
              </div>
            ) : (
              <SignalsTable signals={signals} tape={tape} latestSweep={latestSweep} />
            )}
          </div>

          {siSettlementDate && (
            <p className="mt-2.5 mb-6 text-[11px] text-text-tertiary leading-relaxed max-w-[900px]">
              Short interest is the FINRA settlement figure from{' '}
              <strong style={{ color: THEME.primary }}>{siSettlementDate}</strong> — it is the{' '}
              <em>fuel that was already there</em>, not a live short position, and it predates any move that
              started after that date.
            </p>
          )}

          <QuietSymbols entries={quietEntries} />
        </div>
      </div>
    </div>
  );
}
