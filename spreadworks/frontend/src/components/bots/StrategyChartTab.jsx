import { useMemo } from 'react';
import { useStrategyChart } from '../../hooks/useStrategyChart';
import { BOT_THEME, BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';
import { parseLegs, normalizeLegs, legGroups } from '../../lib/legs';

/* ─── Strategy code mapping (matches the spec) ──────────────────── */

const STRATEGY_CODE = {
  iron_butterfly: 'IB',
  double_calendar: 'DC',
  double_diagonal: 'DD',
  iron_condor: 'IC',
  double_diagonal_credit: 'CDD',
  pin_drift_combo: 'PDC',
  long_butterfly: 'LB',
  bull_call_spread: 'BCS',
  bear_call_spread: 'BrCS',
  bull_put_spread: 'BPS',
  bear_put_spread: 'BrPS',
};

// Mirror of backend bots.strategies.CREDIT_STRATEGIES — strategies that collect
// a net credit at entry (entry_price = credit received). Drives the credit vs
// debit label/sign in the summary strip + economics row.
const CREDIT_STRATEGIES = new Set([
  'iron_butterfly', 'iron_condor', 'double_diagonal_credit',
  'bull_put_spread', 'bear_call_spread',
]);

/* ─── Formatting helpers ─────────────────────────────────────────── */

function money(v, { signed = false, decimals = 2, comma = true } = {}) {
  if (v == null || Number.isNaN(v)) return '—';
  const abs = Math.abs(v);
  const opts = comma
    ? { minimumFractionDigits: decimals, maximumFractionDigits: decimals }
    : { useGrouping: false, minimumFractionDigits: decimals, maximumFractionDigits: decimals };
  const str = abs.toLocaleString('en-US', opts);
  if (signed) {
    const sign = v > 0 ? '+' : v < 0 ? '−' : '';
    return `${sign}$${str}`;
  }
  return v < 0 ? `−$${str}` : `$${str}`;
}

function pctText(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v * 100).toFixed(decimals)}%`;
}

function strikeColor(side) {
  return side === 'long' ? '#34d399' : '#fb7185';
}

/* ─── Leg parsing lives in lib/legs.js (parseLegs / normalizeLegs) so it can
   be unit-tested and shared. parseLegs handles both the put/call topology
   (IC/IB/DC/DD) and RIVER's single-type long butterfly. ─────────────────── */

/* ─── Derive position-level metrics from raw position + payoff ───── */

function deriveDisplay({ position, payoff, spot, candles, ticker }) {
  if (!position) return null;

  const strategy = position.strategy;
  const legsMap = parseLegs(position.legs, strategy);
  if (!legsMap) return null;
  // True distinct legs (correct option type + quantity) for the leg chips,
  // split into labeled sub-structures. For SURGE that's butterfly + two
  // calendars so you can tell which strike belongs to which; everything else
  // is a single unlabeled group.
  const groups = legGroups(position.legs, strategy);

  // SURGE's drift calendars sit at body±drift, inside the butterfly wings. The
  // 4-slot geometry only carries the fly core, so surface the calendar strikes
  // separately for the chart to draw + label.
  const rawLegs = Array.isArray(position.legs) ? position.legs : [];
  const extraStrikes = strategy === 'pin_drift_combo' && rawLegs.length >= 8
    ? [
        { strike: Number(rawLegs[4].strike), label: 'call cal' },
        { strike: Number(rawLegs[6].strike), label: 'put cal' },
      ]
    : [];
  const strategyCode = STRATEGY_CODE[strategy] || strategy.toUpperCase();
  const strategyLabel = STRATEGY_LABEL[strategy] || strategy;
  const isCredit = CREDIT_STRATEGIES.has(strategy);
  const contracts = Number(position.contracts || 1);
  const entryPerShare = Number(position.entry_price || 0);
  const netCredit = isCredit ? entryPerShare * 100 * contracts : -entryPerShare * 100 * contracts;
  const unrealized = position.mtm_pnl != null ? Number(position.mtm_pnl) : 0;

  // Pull max profit / max loss from payoff (already contracts-multiplied),
  // fall back to position row if the payoff endpoint hasn't returned yet.
  const maxProfit = payoff?.max_profit
    ?? (position.max_profit != null ? Number(position.max_profit) : null);
  const maxLoss = payoff?.max_loss
    ?? (position.max_loss != null ? Number(position.max_loss) : null);

  const breakevens = payoff?.breakevens || {};
  const beList = [breakevens.lower, breakevens.upper].filter(v => v != null);

  // Sample the curve to compute POP (% of sampled prices with pnl >= 0). The
  // backend already returns this in `probability_of_profit`; recompute here
  // if missing.
  let pop = null;
  if (payoff?.pnl_curve && payoff.pnl_curve.length > 0) {
    const profitable = payoff.pnl_curve.filter(p => p.pnl >= 0).length;
    pop = profitable / payoff.pnl_curve.length;
  }

  // Unrealized % of risk. Risk = absolute max loss (max collateral at risk).
  const riskBase = maxLoss != null ? Math.abs(maxLoss) : Math.max(Math.abs(maxProfit || 0), 1);
  const unrealizedPct = riskBase > 0 ? unrealized / riskBase : 0;

  // Find earliest expiration from legs for the summary strip "exp" badge.
  const exps = position.legs
    ? (Array.isArray(position.legs)
        ? position.legs.map(l => l.expiration).filter(Boolean)
        : [])
    : [];
  const exp = exps.sort()[0] || null;

  return {
    bot: position.bot,
    strategyCode,
    strategyLabel,
    isCredit,
    symbol: ticker,
    exp,
    status: position.status || 'OPEN',
    legs: legsMap,
    groups,
    extraStrikes,
    contracts,
    creditPerContract: isCredit ? entryPerShare : -entryPerShare,
    netCredit,
    spot,
    unrealized,
    unrealizedPct,
    maxProfit,
    maxLoss,
    beList,
    pop,
    pnl_curve: payoff?.pnl_curve || [],
    candles,
  };
}

/* ─── Curve interpolation — for the "Now" marker P&L at spot ─────── */

function interpolatePnlAtPrice(pnlCurve, price) {
  if (!pnlCurve || pnlCurve.length === 0 || price == null) return null;
  for (let i = 0; i < pnlCurve.length - 1; i++) {
    const a = pnlCurve[i];
    const b = pnlCurve[i + 1];
    if ((a.price <= price && b.price >= price) || (a.price >= price && b.price <= price)) {
      const span = (b.price - a.price) || 1;
      const t = (price - a.price) / span;
      return a.pnl + t * (b.pnl - a.pnl);
    }
  }
  return null;
}

/* ─── Strategy summary strip (zoned · per design spec) ──────────── */

function ZoneLabel({ children }) {
  return (
    <span
      style={{
        fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.14em', color: '#64748b',
      }}
    >
      {children}
    </span>
  );
}

function StrategyCodeChip({ code }) {
  return (
    <span
      style={{
        fontFamily: 'JetBrains Mono',
        fontSize: 10, fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.06em',
        color: '#c4b5fd',
        padding: '2px 8px', borderRadius: 4,
        background: 'rgba(167,139,250,0.10)',
        boxShadow: 'inset 0 0 0 1px rgba(167,139,250,0.30)',
      }}
    >
      {code}
    </span>
  );
}

function OpenPill() {
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '2px 8px', borderRadius: 6,
        fontSize: 10, fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.06em',
        color: '#34d399',
        background: 'rgba(52,211,153,0.10)',
        boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.30)',
      }}
    >
      <span
        style={{
          width: 6, height: 6, borderRadius: 9999,
          background: '#34d399',
          animation: 'pulse 2s infinite',
        }}
      />
      OPEN
    </span>
  );
}

// "2026-06-26" -> "6/26". String-split (no Date) to avoid TZ drift.
function fmtExp(exp) {
  if (!exp) return null;
  const p = String(exp).split('-');
  return p.length === 3 ? `${Number(p[1])}/${Number(p[2])}` : String(exp);
}

function LegChip({ l }) {
  if (l.strike == null) return null;
  const isLong = l.side === 'long';
  const color = isLong ? '#34d399' : '#fb7185';
  const bg    = isLong ? 'rgba(52,211,153,0.10)' : 'rgba(251,113,133,0.10)';
  const ring  = isLong ? 'rgba(52,211,153,0.25)' : 'rgba(251,113,133,0.25)';
  const qty   = l.qty > 1 ? `${l.qty}×` : '';
  const letter = l.type === 'call' ? 'C' : 'P';
  const exp = fmtExp(l.expiration);
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <span
        style={{
          fontFamily: 'JetBrains Mono',
          fontSize: 11.5, fontWeight: 600,
          padding: '4px 10px', borderRadius: 6,
          background: bg, color,
          boxShadow: `inset 0 0 0 1px ${ring}`,
        }}
      >
        {qty}{isLong ? '+' : '−'}${l.strike}{letter}
      </span>
      {exp && (
        <span style={{ fontFamily: 'JetBrains Mono', fontSize: 9, color: '#64748b' }}>
          {exp}
        </span>
      )}
    </span>
  );
}

// Sub-structure label shown above a group of leg chips (SURGE only — single-
// structure strategies render one unlabeled group, so the tag is suppressed).
function GroupTag({ label, note }) {
  if (!label) return null;
  return (
    <span
      style={{
        fontSize: 9, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.10em', color: '#7dd3fc',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
      {note && <span style={{ color: '#475569', marginLeft: 4 }}>· {note}</span>}
    </span>
  );
}

function SummaryLegChips({ groups }) {
  const list = Array.isArray(groups) ? groups : [];
  // A single, unlabeled group is the common case — render the chips inline,
  // identical to the old flat layout.
  if (list.length === 1 && !list[0].label) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {list[0].legs.map((l, i) => <LegChip key={i} l={l} />)}
      </div>
    );
  }
  // Combined structures (SURGE): stack labeled rows so each strike is tied to
  // its sub-strategy.
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {list.map((g, gi) => (
        <div key={gi} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', width: 92, flexShrink: 0 }}>
            <GroupTag label={g.label} note={g.note} />
          </span>
          {g.legs.map((l, i) => <LegChip key={i} l={l} />)}
        </div>
      ))}
    </div>
  );
}

function StrategySummaryStrip({ d }) {
  if (!d) return null;
  const positive = d.unrealized >= 0;
  const pnlColor = positive ? '#34d399' : '#fb7185';
  // For credit strategies (BREEZE / FLOW) the entry money is a credit
  // received; for debit strategies (TIDE / DRIFT) it's a debit paid. Same
  // value displayed, just labeled correctly.
  const entryAbs = Math.abs(d.netCredit || 0);
  const entryLabel = d.isCredit ? 'credit' : 'debit';
  const entryColor = d.isCredit ? '#34d399' : '#fcd34d';

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1.2fr 1.6fr 1fr',
        borderRadius: 12,
        overflow: 'hidden',
        background: 'rgba(13,28,46,0.55)',
        backdropFilter: 'blur(12px) saturate(140%)',
        WebkitBackdropFilter: 'blur(12px) saturate(140%)',
        boxShadow:
          'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
        marginBottom: 16,
      }}
    >
      {/* ZONE 1 · STRATEGY */}
      <div style={{ padding: '16px 20px' }}>
        <ZoneLabel>Strategy</ZoneLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 16, fontWeight: 700, color: '#fff' }}>
            {d.symbol}
          </span>
          <StrategyCodeChip code={d.strategyCode} />
          {d.status === 'OPEN' && <OpenPill />}
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10.5, color: '#64748b', marginTop: 6 }}>
          exp {d.exp || '—'}
        </div>
      </div>

      {/* ZONE 2 · POSITION */}
      <div
        style={{
          padding: '16px 20px',
          borderLeft: '1px solid rgba(125,211,252,0.10)',
          borderRight: '1px solid rgba(125,211,252,0.10)',
        }}
      >
        <ZoneLabel>Position</ZoneLabel>
        <div style={{ marginTop: 6 }}>
          <SummaryLegChips groups={d.groups} />
        </div>
        <div
          style={{
            display: 'flex', alignItems: 'baseline', gap: 20,
            fontFamily: 'JetBrains Mono', fontSize: 11.5, color: '#94a3b8',
            marginTop: 8,
          }}
        >
          <span>{d.contracts} ctr</span>
          <span>
            {entryLabel}{' '}
            <span style={{ color: entryColor, fontWeight: 700 }}>
              ${entryAbs.toFixed(2)}
            </span>
          </span>
        </div>
      </div>

      {/* ZONE 3 · LIVE */}
      <div style={{ padding: '16px 20px' }}>
        <ZoneLabel>Live</ZoneLabel>
        <div
          style={{
            fontFamily: 'JetBrains Mono', fontSize: 18, fontWeight: 700,
            display: 'inline-flex', alignItems: 'baseline', gap: 6,
            color: pnlColor, marginTop: 6,
          }}
        >
          {positive ? '+' : '−'}${Math.abs(d.unrealized).toFixed(2)}
          <span style={{ fontSize: 11, opacity: 0.8 }}>
            ({positive ? '+' : '−'}{Math.abs((d.unrealizedPct || 0) * 100).toFixed(1)}%)
          </span>
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11.5, color: '#94a3b8', marginTop: 6 }}>
          spot{' '}
          <span style={{ color: '#fff', fontWeight: 700 }}>
            {d.spot != null ? `$${d.spot.toFixed(2)}` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ─── Cell chrome (used by both economics + greeks rows) ─────────── */

function Cell({ label, value, valueColor = 'white', valueSize = 16, sub }) {
  return (
    <div
      className="rounded-md px-3 py-2.5"
      style={{
        background: 'rgba(7,16,28,0.4)',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.06)',
      }}
    >
      <div className="text-[9.5px] uppercase tracking-[0.14em] font-bold mb-1" style={{ color: '#64748b' }}>
        {label}
      </div>
      <div
        className="sw-mono font-bold"
        style={{ fontSize: valueSize, color: valueColor, lineHeight: 1.1 }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] mt-0.5" style={{ color: '#64748b' }}>{sub}</div>
      )}
    </div>
  );
}

function EconomicsRow({ d }) {
  if (!d) return null;
  const beText = d.beList.length === 2
    ? `${d.beList[0].toFixed(2)}–${d.beList[1].toFixed(2)}`
    : d.beList.length === 1
      ? `${d.beList[0].toFixed(2)}`
      : '—';

  return (
    <div className="grid grid-cols-6 gap-2.5">
      <Cell
        label={d.isCredit ? 'Net Credit' : 'Net Debit'}
        value={money(Math.abs(d.netCredit))}
        valueColor={d.isCredit ? '#34d399' : '#fcd34d'}
      />
      <Cell
        label="Max Profit"
        value={d.maxProfit != null ? money(d.maxProfit) : '—'}
        valueColor="#34d399"
      />
      <Cell
        label="Max Loss"
        value={d.maxLoss != null ? money(d.maxLoss) : '—'}
        valueColor="#fb7185"
      />
      <Cell
        label="POP"
        value={d.pop != null ? `${(d.pop * 100).toFixed(1)}%` : '—'}
        valueColor="#fcd34d"
      />
      <Cell
        label="Breakevens"
        value={beText}
        valueColor="#fcd34d"
        valueSize={13}
      />
      <Cell label="IV" value="—" valueColor="#7dd3fc" />
    </div>
  );
}

function GreeksRow() {
  // Per-position greeks aren't yet wired into the SpreadWorks backend (would
  // need a per-leg Tradier quote at chart-render time). Show placeholders so
  // the layout matches the spec and we can fill these in once the data flows.
  return (
    <div className="grid grid-cols-4 gap-2.5">
      <Cell label="Δ Delta" value="—" valueColor="#7dd3fc" />
      <Cell label="Γ Gamma" value="—" valueColor="#7dd3fc" />
      <Cell label="Θ Theta" value="—" valueColor="#34d399" />
      <Cell label="ν Vega" value="—" valueColor="#7dd3fc" />
    </div>
  );
}

/* ─── The chart itself — IronForge-style hybrid (candles + payoff) ─ */

function ChartCard({ d, theme, botId }) {
  // Memoize the heavy layout calculation so we only recompute when inputs
  // actually move. SVG re-render itself is cheap.
  const layout = useMemo(() => {
    if (!d) return null;
    const candles = d.candles || [];
    const curve = d.pnl_curve || [];
    if (curve.length === 0) return null;

    // ─── Coordinate system (viewBox 1600 × 560) ─────────────────────
    const W = 1600;
    const H = 560;
    const padT = 32;
    const padL = 64;
    const padR = 70;
    const overlayW = 240;
    const gap = 80;
    const volH = 60;
    const xAxisH = 28;
    const chartH = H - padT - volH - xAxisH - 8;
    const volTop = padT + chartH + 8;

    const overlayRight = W - padR;
    const overlayLeft = overlayRight - overlayW;
    const candleEndX = overlayLeft - gap;
    const candleAreaW = candleEndX - padL;

    // ─── Y axis (price) — covers strikes + candle hi/lo ─────────────
    // Verticals only populate two of the four geometry slots, so derive the
    // range from whichever strikes are defined rather than assuming longPut /
    // longCall (the IC/IB outer wings) are always present.
    const extraStrikes = (d.extraStrikes || []).filter(e => e.strike != null);
    const definedStrikes = [d.legs.longPut, d.legs.shortPut, d.legs.shortCall, d.legs.longCall,
      ...extraStrikes.map(e => e.strike)]
      .filter(v => v != null);
    const candleLows = candles.map(c => Number(c.low ?? c.l ?? 0)).filter(v => v > 0);
    const candleHighs = candles.map(c => Number(c.high ?? c.h ?? 0)).filter(v => v > 0);
    const minStrike = Math.min(...definedStrikes);
    const maxStrike = Math.max(...definedStrikes);
    const lo = Math.min(minStrike - 6, ...candleLows);
    const hi = Math.max(maxStrike + 6, ...candleHighs);
    const yMin = Math.floor(lo / 5) * 5;
    const yMax = Math.ceil(hi / 5) * 5;
    const yPx = price => padT + (1 - (price - yMin) / (yMax - yMin)) * chartH;

    // ─── Payoff X scale (THE 180° rotation) ─────────────────────────
    const xZero = (overlayLeft + overlayRight) / 2;
    const inset = 12;
    const maxProfit = d.maxProfit || 1;
    const maxLossAbs = Math.abs(d.maxLoss || 1);
    const profitScale = (xZero - overlayLeft - inset) / Math.max(maxProfit, 1);
    const lossScale = (overlayRight - xZero - inset) / Math.max(maxLossAbs, 1);
    const xPnl = pnl => pnl >= 0
      ? xZero - pnl * profitScale         // profit LEFT
      : xZero + Math.abs(pnl) * lossScale; // loss RIGHT

    // ─── Sample the curve onto the chart's price grid ───────────────
    // We sample 200 points from yMin..yMax and read pnl by interpolating
    // the existing curve (which the backend may have sampled at $1 steps).
    const samples = [];
    const nSamples = 200;
    for (let i = 0; i <= nSamples; i++) {
      const price = yMin + ((yMax - yMin) * i) / nSamples;
      const pnl = interpolatePnlAtPrice(curve, price);
      if (pnl != null) {
        samples.push({ price, pnl, x: xPnl(pnl), y: yPx(price) });
      }
    }

    // Walk samples in price order and split into contiguous same-sign runs.
    // Each run becomes a separate fill polygon closed back to the $0 baseline
    // (xZero) — NOT to the overlay edges. This means the fill shows the
    // ACTUAL profit/loss pocket between the curve and the zero-P&L axis,
    // which is what a payoff diagram is meant to communicate.
    //
    // IC / butterflies have TWO loss segments (below lower BE and above upper
    // BE) with a profit run between them — so filtering by sign yields three
    // distinct runs that must be drawn separately, otherwise SVG draws a
    // diagonal cheat-line between the bottom and top loss tails.
    const runs = [];
    for (const s of samples) {
      const sign = s.pnl >= 0 ? 1 : -1;
      if (runs.length === 0 || runs[runs.length - 1].sign !== sign) {
        runs.push({ sign, pts: [] });
      }
      runs[runs.length - 1].pts.push(s);
    }
    const fillPaths = runs
      .filter(r => r.pts.length >= 2)
      .map(r => {
        const first = r.pts[0];
        const last = r.pts[r.pts.length - 1];
        const body = r.pts
          .map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
          .join(' L');
        // Polygon: follow curve, then close back to xZero at last y, then
        // up to xZero at first y, then Z closes back to the first curve pt.
        const path =
          `M${first.x.toFixed(1)},${first.y.toFixed(1)} L${body} ` +
          `L${xZero.toFixed(1)},${last.y.toFixed(1)} ` +
          `L${xZero.toFixed(1)},${first.y.toFixed(1)} Z`;
        return { sign: r.sign, path };
      });
    const linePath = samples.length > 1
      ? `M${samples.map(s => `${s.x.toFixed(1)},${s.y.toFixed(1)}`).join(' L')}`
      : '';

    // ─── Candles ─────────────────────────────────────────────────────
    const cw = candles.length > 0 ? candleAreaW / candles.length : 0;
    const candleRects = candles.map((c, i) => {
      const open = Number(c.open ?? c.o);
      const high = Number(c.high ?? c.h);
      const low = Number(c.low ?? c.l);
      const close = Number(c.close ?? c.c);
      const isUp = close >= open;
      const cx = padL + i * cw + cw / 2;
      const yHi = yPx(high);
      const yLo = yPx(low);
      const yOpen = yPx(open);
      const yClose = yPx(close);
      const top = Math.min(yOpen, yClose);
      const bottom = Math.max(yOpen, yClose);
      return {
        cx, yHi, yLo, top, bottom,
        w: Math.max(cw * 0.64, 1),
        color: isUp ? '#34d399' : '#fb7185',
      };
    });

    // ─── Volume bars ────────────────────────────────────────────────
    const volMax = candles.length > 0
      ? Math.max(...candles.map(c => Number(c.volume ?? c.vol ?? 0)), 1)
      : 1;
    const volBars = candles.map((c, i) => {
      const open = Number(c.open ?? c.o);
      const close = Number(c.close ?? c.c);
      const vol = Number(c.volume ?? c.vol ?? 0);
      const isUp = close >= open;
      const cx = padL + i * cw + cw / 2;
      const h = (vol / volMax) * (volH - 8);
      return {
        cx, y: volTop + volH - h, h,
        w: Math.max(cw * 0.64, 1),
        color: isUp ? 'rgba(52,211,153,0.45)' : 'rgba(251,113,133,0.45)',
      };
    });

    // ─── Strike lines (span full chart) ─────────────────────────────
    // Dedupe — DC has only 2 unique strikes, IB has 3, DD has 4.
    const strikeMap = new Map();
    const addStrike = (strike, side) => {
      if (strike == null) return;
      const key = String(strike);
      const existing = strikeMap.get(key);
      // If a strike is both long AND short (DC where back=front strike),
      // prefer the long color for the line — visually the strike is "held"
      // long for the back-month leg.
      if (!existing || (side === 'long' && existing.side !== 'long')) {
        strikeMap.set(key, { strike: Number(strike), side });
      }
    };
    addStrike(d.legs.longPut, 'long');
    addStrike(d.legs.longCall, 'long');
    addStrike(d.legs.shortPut, 'short');
    addStrike(d.legs.shortCall, 'short');
    const strikeLines = Array.from(strikeMap.values())
      .filter(s => s.strike >= yMin && s.strike <= yMax)
      .map(s => ({ ...s, y: yPx(s.strike), color: strikeColor(s.side) }));

    // Extra (calendar) strikes — SURGE's drift legs. Drawn amber + labeled so
    // they're distinct from the green/red butterfly wings & body.
    const CAL_COLOR = '#fbbf24';
    const extraLines = extraStrikes
      .filter(e => e.strike >= yMin && e.strike <= yMax)
      .map(e => ({ strike: e.strike, label: e.label, y: yPx(e.strike), color: CAL_COLOR }));

    // ─── X-axis time labels (5 evenly spaced across candle area) ────
    const xAxisLabels = [];
    if (candles.length > 0) {
      const fmt = (ts) => {
        if (!ts) return '';
        try {
          // Tradier timesales returns "time" as ISO or "2026-05-19T13:45:00"
          const d = new Date(ts);
          return d.toLocaleTimeString('en-US', {
            timeZone: 'America/Chicago',
            hour: 'numeric', minute: '2-digit', hour12: true,
          });
        } catch { return ''; }
      };
      const idxs = [0, Math.floor(candles.length / 4), Math.floor(candles.length / 2),
                    Math.floor((candles.length * 3) / 4), candles.length - 1];
      idxs.forEach((idx, i) => {
        if (idx < 0 || idx >= candles.length) return;
        const c = candles[idx];
        xAxisLabels.push({
          x: padL + idx * cw + cw / 2,
          label: fmt(c.time || c.t || c.date),
          anchor: i === 0 ? 'start' : i === 4 ? 'end' : 'middle',
        });
      });
    }

    // ─── Y-axis price ticks ─────────────────────────────────────────
    const range = yMax - yMin;
    const step = range > 60 ? 10 : 5;
    const yTicks = [];
    for (let p = Math.ceil(yMin / step) * step; p <= yMax; p += step) {
      yTicks.push({ price: p, y: yPx(p) });
    }

    // ─── "Now" marker ───────────────────────────────────────────────
    // The dot stays on the curve (spot horizontal line × current-P&L x), but
    // the label is parked in the empty strip just LEFT of the payoff band near
    // the top of the chart, with a thin leader line down to the dot. Floating
    // it next to the dot at spot height (the old behavior) dropped the box
    // squarely on top of the payoff curve's profit pocket AND the cyan spot
    // chip — hiding exactly what the chart exists to show.
    let nowMarker = null;
    if (d.spot != null && d.unrealized != null) {
      const cx = xPnl(d.unrealized);
      const cy = yPx(d.spot);
      const labelW = 158;
      const labelX = Math.max(padL + 4, overlayLeft - labelW - 14);
      const labelY = padT + 14;
      nowMarker = {
        cx, cy,
        labelX,
        labelY,
        labelW,
        labelText: `Now: ${money(d.unrealized, { signed: true })} (${pctText(d.unrealizedPct, 1)})`,
      };
    }

    // ─── Spot line ──────────────────────────────────────────────────
    let spotInfo = null;
    if (d.spot != null && d.spot >= yMin && d.spot <= yMax) {
      spotInfo = { y: yPx(d.spot), label: `$${d.spot.toFixed(2)}` };
    }

    // ─── Breakeven dots (on the $0 baseline) ────────────────────────
    const beDots = d.beList
      .filter(p => p >= yMin && p <= yMax)
      .map(p => ({ y: yPx(p), price: p }));

    return {
      W, H, padT, padL, padR, candleEndX, overlayLeft, overlayRight, xZero,
      chartH, volTop, volH, xAxisH,
      yPx, xPnl, yMin, yMax,
      candleRects, volBars,
      strikeLines, extraLines, yTicks, xAxisLabels,
      fillPaths, linePath,
      nowMarker, spotInfo, beDots,
      maxProfit, maxLoss: maxLossAbs,
    };
  }, [d]);

  if (!d) {
    return (
      <div
        className="rounded-md p-12 text-center"
        style={{
          background: 'rgba(7,16,28,0.4)',
          boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.06)',
        }}
      >
        <div className="text-[13px]" style={{ color: '#94a3b8' }}>
          No active strategy — chart appears when a trade is on.
        </div>
      </div>
    );
  }
  if (!layout) {
    return (
      <div
        className="rounded-md p-12 text-center"
        style={{
          background: 'rgba(7,16,28,0.4)',
          boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.06)',
        }}
      >
        <div className="text-[13px]" style={{ color: '#94a3b8' }}>
          Loading chart data…
        </div>
      </div>
    );
  }

  const L = layout;
  const t = theme;
  const idSuffix = botId;

  return (
    <div
      className="rounded-md p-3"
      style={{
        background: 'rgba(7,16,28,0.4)',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.06)',
      }}
    >
      {/* Header strip */}
      <div className="flex items-center justify-between px-1 mb-2">
        <div className="flex items-baseline gap-3">
          <span className="text-[10px] uppercase tracking-[0.16em] font-bold" style={{ color: '#94a3b8' }}>
            STRATEGY CHART
          </span>
          <span className="text-[10.5px]" style={{ color: '#64748b' }}>
            underlying price · payoff @ expiration on the right
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: '#94a3b8' }}>
          <Legend dot="#34d399" label="Long strike" />
          <Legend dot="#fb7185" label="Short strike" />
          {L.extraLines.length > 0 && <Legend dot="#fbbf24" label="Drift calendar" />}
          <Legend dot="#fcd34d" label="Breakeven · Now" />
          <Legend dot={t.primary} label="Spot" dashed />
        </div>
      </div>

      {/* The chart */}
      <svg viewBox={`0 0 ${L.W} ${L.H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: 'block' }}>
        <defs>
          {/* userSpaceOnUse so the gradient orientation is consistent across
              all fill polygons regardless of each path's bounding box. Light
              at xZero (the $0 baseline), darker toward the corresponding
              max-profit / max-loss edge. */}
          <linearGradient
            id={`pl-pos-${idSuffix}`}
            gradientUnits="userSpaceOnUse"
            x1={L.xZero} y1="0" x2={L.overlayLeft} y2="0"
          >
            <stop offset="0%" stopColor="#34d399" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0.45" />
          </linearGradient>
          <linearGradient
            id={`pl-neg-${idSuffix}`}
            gradientUnits="userSpaceOnUse"
            x1={L.xZero} y1="0" x2={L.overlayRight} y2="0"
          >
            <stop offset="0%" stopColor="#fb7185" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#fb7185" stopOpacity="0.45" />
          </linearGradient>
          <filter id={`glow-${idSuffix}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <clipPath id={`overlay-clip-${idSuffix}`}>
            <rect x={L.overlayLeft} y={L.padT} width={L.overlayRight - L.overlayLeft} height={L.chartH} />
          </clipPath>
        </defs>

        {/* Y-axis price ticks (across candle area only) */}
        {L.yTicks.map((t, i) => (
          <g key={`yt${i}`}>
            <line
              x1={L.padL} y1={t.y} x2={L.candleEndX} y2={t.y}
              stroke="rgba(125,211,252,0.04)" strokeWidth="0.5"
            />
            <text
              x={L.padL - 8} y={t.y + 3.5} textAnchor="end"
              fill="#475569" fontSize="10.5"
              fontFamily="'JetBrains Mono', monospace"
            >
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike horizontal lines — span full chart */}
        {L.strikeLines.map((s, i) => (
          <g key={`s${i}`}>
            <line
              x1={L.padL} y1={s.y} x2={L.overlayRight} y2={s.y}
              stroke={s.color} strokeWidth="1" strokeDasharray="6 5" opacity="0.42"
            />
            {/* Left chip */}
            <g transform={`translate(${L.padL + 4}, ${s.y - 9})`}>
              <rect
                width="46" height="18" rx="3"
                fill="rgba(6,18,31,0.92)" stroke={s.color} strokeWidth="0.8"
              />
              <text
                x="23" y="12.5" textAnchor="middle"
                fill={s.color} fontSize="10.5" fontWeight="700"
                fontFamily="'JetBrains Mono', monospace"
              >
                ${s.strike}
              </text>
            </g>
            {/* Right axis label */}
            <text
              x={L.overlayRight + 6} y={s.y + 3.5}
              fill={s.color} opacity="0.8" fontSize="10"
              fontFamily="'JetBrains Mono', monospace"
            >
              ${s.strike}
            </text>
          </g>
        ))}

        {/* Calendar (drift) strike lines — amber, labeled, dotted to read as
            "interior" markers vs the dashed butterfly wings/body. */}
        {L.extraLines.map((s, i) => (
          <g key={`x${i}`}>
            <line
              x1={L.padL} y1={s.y} x2={L.overlayRight} y2={s.y}
              stroke={s.color} strokeWidth="1" strokeDasharray="2 4" opacity="0.45"
            />
            <g transform={`translate(${L.padL + 4}, ${s.y - 9})`}>
              <rect
                width="72" height="18" rx="3"
                fill="rgba(6,18,31,0.92)" stroke={s.color} strokeWidth="0.8"
              />
              <text
                x="36" y="12.5" textAnchor="middle"
                fill={s.color} fontSize="9" fontWeight="700"
                fontFamily="'JetBrains Mono', monospace"
              >
                {s.label} ${s.strike}
              </text>
            </g>
          </g>
        ))}

        {/* Volume baseline */}
        <line
          x1={L.padL} y1={L.volTop + L.volH}
          x2={L.candleEndX} y2={L.volTop + L.volH}
          stroke="rgba(125,211,252,0.10)" strokeWidth="0.5"
        />

        {/* Volume bars */}
        {L.volBars.map((b, i) => (
          <rect
            key={`v${i}`}
            x={b.cx - b.w / 2} y={b.y} width={b.w} height={b.h}
            fill={b.color}
          />
        ))}

        {/* Candles */}
        {L.candleRects.map((c, i) => (
          <g key={`c${i}`}>
            <line
              x1={c.cx} y1={c.yHi} x2={c.cx} y2={c.yLo}
              stroke={c.color} strokeWidth="1" opacity="0.85"
            />
            <rect
              x={c.cx - c.w / 2} y={c.top}
              width={c.w} height={Math.max(c.bottom - c.top, 1)}
              fill={c.color} opacity="0.95"
            />
          </g>
        ))}

        {/* Overlay band separator (faint dashed vertical at start of band) */}
        <line
          x1={L.overlayLeft - 2} y1={L.padT - 6}
          x2={L.overlayLeft - 2} y2={L.padT + L.chartH + 6}
          stroke="rgba(125,211,252,0.12)" strokeDasharray="2 4"
        />

        {/* $0 P&L baseline */}
        <line
          x1={L.xZero} y1={L.padT}
          x2={L.xZero} y2={L.padT + L.chartH}
          stroke="rgba(125,211,252,0.30)" strokeWidth="1" strokeDasharray="3 5"
        />

        {/* Payoff fills (clipped to overlay band). One polygon per
            contiguous same-sign run so the two loss tails of an Iron Condor
            render as separate fills instead of one connecting cheat-line. */}
        <g clipPath={`url(#overlay-clip-${idSuffix})`}>
          {L.fillPaths.map((f, i) => (
            <path
              key={i}
              d={f.path}
              fill={`url(#${f.sign > 0 ? 'pl-pos' : 'pl-neg'}-${idSuffix})`}
            />
          ))}
          {L.linePath && (
            <path
              d={L.linePath}
              fill="none" stroke={t.primary} strokeWidth="2.2"
              strokeLinecap="round" strokeLinejoin="round"
              filter={`url(#glow-${idSuffix})`}
            />
          )}
        </g>

        {/* Overlay top labels */}
        <text
          x={L.overlayLeft + 4} y={L.padT - 12} textAnchor="start"
          fill="#34d399" fontSize="10" fontWeight="700"
          fontFamily="'JetBrains Mono', monospace"
        >
          +{money(L.maxProfit)}
        </text>
        <text
          x={L.xZero} y={L.padT - 12} textAnchor="middle"
          fill="#94a3b8" fontSize="10" fontWeight="600"
          fontFamily="'JetBrains Mono', monospace"
        >
          $0 P&amp;L
        </text>
        <text
          x={L.overlayRight - 4} y={L.padT - 12} textAnchor="end"
          fill="#fb7185" fontSize="10" fontWeight="700"
          fontFamily="'JetBrains Mono', monospace"
        >
          −{money(L.maxLoss)}
        </text>

        {/* Spot horizontal line + label in the gap */}
        {L.spotInfo && (
          <g>
            <line
              x1={L.padL} y1={L.spotInfo.y}
              x2={L.overlayRight} y2={L.spotInfo.y}
              stroke={t.primary} strokeWidth="1" strokeDasharray="4 4" opacity="0.55"
            />
            <rect
              x={L.candleEndX + 8} y={L.spotInfo.y - 13}
              width="60" height="26" rx="4"
              fill={t.primary}
            />
            <text
              x={L.candleEndX + 38} y={L.spotInfo.y + 4.5} textAnchor="middle"
              fill="#06121f" fontSize="12" fontWeight="700"
              fontFamily="'JetBrains Mono', monospace"
            >
              {L.spotInfo.label}
            </text>
          </g>
        )}

        {/* Breakeven dots */}
        {L.beDots.map((be, i) => (
          <g key={`be${i}`}>
            <circle cx={L.xZero} cy={be.y} r="4" fill="#fcd34d" stroke="#06121f" strokeWidth="1.5" />
            <text
              x={L.xZero - 6} y={be.y + 3.5} textAnchor="end"
              fill="#fcd34d" fontSize="10" fontWeight="700"
              fontFamily="'JetBrains Mono', monospace"
            >
              BE
            </text>
            <text
              x={L.xZero + 8} y={be.y + 3.5}
              fill="#fcd34d" opacity="0.70" fontSize="9.5"
              fontFamily="'JetBrains Mono', monospace"
            >
              ${be.price.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Now marker */}
        {L.nowMarker && (
          <g>
            <circle
              cx={L.nowMarker.cx} cy={L.nowMarker.cy} r="6"
              fill="#fcd34d" stroke="#06121f" strokeWidth="2"
            />
            {/* Thin connector from the spot-line dot up to the offset label */}
            <line
              x1={L.nowMarker.cx} y1={L.nowMarker.cy - 6}
              x2={L.nowMarker.labelX + L.nowMarker.labelW / 2} y2={L.nowMarker.labelY + 13}
              stroke="#fcd34d" strokeWidth="1" opacity="0.55"
            />
            <rect
              x={L.nowMarker.labelX} y={L.nowMarker.labelY - 13}
              width={L.nowMarker.labelW} height="26" rx="4"
              fill="#fcd34d"
            />
            <text
              x={L.nowMarker.labelX + L.nowMarker.labelW / 2} y={L.nowMarker.labelY + 4.5}
              textAnchor="middle" fill="#1e1607"
              fontSize="11.5" fontWeight="700"
              fontFamily="'JetBrains Mono', monospace"
            >
              {L.nowMarker.labelText}
            </text>
          </g>
        )}

        {/* X-axis time labels */}
        {L.xAxisLabels.map((lb, i) => (
          <text
            key={`x${i}`}
            x={lb.x} y={L.H - 8} textAnchor={lb.anchor}
            fill="#475569" fontSize="10.5"
            fontFamily="'JetBrains Mono', monospace"
          >
            {lb.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

function Legend({ dot, label, dashed = false }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {dashed ? (
        <span
          className="inline-block w-3 h-[1.5px]"
          style={{ borderTop: `1.5px dashed ${dot}` }}
        />
      ) : (
        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: dot }} />
      )}
      {label}
    </span>
  );
}

/* ─── Top-level export ─────────────────────────────────────────── */

export default function StrategyChartTab({ bot }) {
  const state = useStrategyChart(bot, 15000);
  const theme = BOT_THEME[bot];
  const d = useMemo(() => {
    if (!state.position) return null;
    return deriveDisplay({
      position: state.position,
      payoff: state.payoff,
      spot: state.spot,
      candles: state.candles,
      ticker: state.ticker,
    });
  }, [state]);

  if (state.loading) {
    return (
      <div className="px-5 py-12 text-center text-[13px]" style={{ color: '#94a3b8' }}>
        Loading strategy chart…
      </div>
    );
  }

  if (!state.position) {
    return (
      <div className="px-5 py-12 text-center" style={{ color: '#94a3b8' }}>
        <div className="text-[13px] mb-1">No active strategy</div>
        <div className="text-[11px]" style={{ color: '#64748b' }}>
          The chart appears when a trade is on.
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-5 flex flex-col gap-5">
      <StrategySummaryStrip d={d} />
      <EconomicsRow d={d} />
      <GreeksRow />
      <ChartCard d={d} theme={theme} botId={bot} />
    </div>
  );
}
