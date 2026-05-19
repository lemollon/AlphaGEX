import { useMemo } from 'react';
import { useStrategyChart } from '../../hooks/useStrategyChart';
import { BOT_THEME, BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';

/* ─── Strategy code mapping (matches the spec) ──────────────────── */

const STRATEGY_CODE = {
  iron_butterfly: 'IB',
  double_calendar: 'DC',
  double_diagonal: 'DD',
};

const CREDIT_STRATEGIES = new Set(['iron_butterfly', 'iron_condor']);

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

/* ─── Leg parsing — normalize legs JSON into { longPut, ... } ────── */

function parseLegs(legs) {
  if (!Array.isArray(legs)) return null;
  const out = { longPut: null, shortPut: null, shortCall: null, longCall: null };
  for (const lg of legs) {
    const k = (lg.side === 'long' ? 'long' : 'short') + (lg.type === 'call' ? 'Call' : 'Put');
    out[k] = Number(lg.strike);
  }
  if ([out.longPut, out.shortPut, out.shortCall, out.longCall].some(v => v == null)) {
    return null;
  }
  return out;
}

function legsForLabel(legs) {
  if (!Array.isArray(legs)) return [];
  const order = ['longPut', 'shortPut', 'shortCall', 'longCall'];
  const m = parseLegs(legs);
  if (!m) return [];
  return order.map(k => {
    const isLong = k.startsWith('long');
    const isCall = k.endsWith('Call');
    const isPut = !isCall;
    return {
      side: isLong ? 'long' : 'short',
      type: isCall ? 'call' : 'put',
      strike: m[k],
      glyph: isLong ? '+' : '−',
      letter: isPut ? 'P' : 'C',
    };
  });
}

/* ─── Derive position-level metrics from raw position + payoff ───── */

function deriveDisplay({ position, payoff, spot, candles, ticker }) {
  if (!position) return null;

  const legsMap = parseLegs(position.legs);
  if (!legsMap) return null;

  const strategy = position.strategy;
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

/* ─── Summary strip ─────────────────────────────────────────────── */

function Dot() {
  return <span className="inline-block w-1 h-1 rounded-full mx-2" style={{ background: '#475569' }} />;
}

function SummaryStrip({ d }) {
  if (!d) return null;
  const legs = legsForLabel(
    [
      { side: 'long', type: 'put', strike: d.legs.longPut },
      { side: 'short', type: 'put', strike: d.legs.shortPut },
      { side: 'short', type: 'call', strike: d.legs.shortCall },
      { side: 'long', type: 'call', strike: d.legs.longCall },
    ]
  );

  const unrealColor = d.unrealized >= 0 ? '#34d399' : '#fb7185';

  return (
    <div className="flex items-center flex-wrap gap-y-1.5 px-1 py-0.5">
      <span
        className="sw-mono uppercase tracking-[0.14em] font-bold text-[10px]"
        style={{ color: '#64748b' }}
      >
        {d.strategyCode}
      </span>
      <span className="ml-2 sw-mono text-[14px] font-bold text-white">{d.symbol}</span>
      <span className="ml-2 text-[10.5px] uppercase tracking-[0.14em] font-semibold" style={{ color: '#64748b' }}>
        EXP
      </span>
      <span className="ml-1 sw-mono text-[12px]" style={{ color: '#94a3b8' }}>{d.exp || '—'}</span>
      <span
        className="ml-2 sw-mono text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full"
        style={{
          background: d.status === 'OPEN' ? 'rgba(52,211,153,0.10)' : 'rgba(125,211,252,0.10)',
          color: d.status === 'OPEN' ? '#34d399' : '#94a3b8',
          boxShadow: `inset 0 0 0 1px ${d.status === 'OPEN' ? 'rgba(52,211,153,0.30)' : 'rgba(125,211,252,0.30)'}`,
        }}
      >
        {d.status}
      </span>

      <Dot />
      <span className="sw-mono text-[12px]">
        {legs.map((lg, i) => (
          <span key={i}>
            <span style={{ color: strikeColor(lg.side), fontWeight: 700 }}>
              {lg.glyph}{lg.letter}{lg.strike}
            </span>
            {i === 1 && <span style={{ color: '#64748b' }} className="mx-1">—</span>}
            {i === 2 && <span style={{ color: '#64748b' }} className="mx-1">/</span>}
            {(i === 0 || i === 3) && i !== 3 && <span style={{ color: '#64748b' }} className="mx-1">/</span>}
          </span>
        ))}
      </span>

      <Dot />
      <span className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: '#64748b' }}>
        CONTRACTS
      </span>
      <span className="ml-1.5 sw-mono text-[14px] font-bold text-white">{d.contracts}</span>

      <Dot />
      <span className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: '#64748b' }}>
        {d.isCredit ? 'CREDIT' : 'DEBIT'}
      </span>
      <span
        className="ml-1.5 sw-mono text-[14px] font-bold"
        style={{ color: d.isCredit ? '#34d399' : '#fcd34d' }}
      >
        {money(Math.abs(d.netCredit))}
      </span>

      <Dot />
      <span className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: '#64748b' }}>
        UNREALIZED
      </span>
      <span className="ml-1.5 sw-mono text-[14px] font-bold" style={{ color: unrealColor }}>
        {money(d.unrealized, { signed: true })}{' '}
        <span className="text-[11px] opacity-80">({pctText(d.unrealizedPct)})</span>
      </span>

      <div className="ml-auto flex items-center">
        <span className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: '#64748b' }}>
          SPOT
        </span>
        <span className="ml-1.5 sw-mono text-[14px] font-bold text-white">
          {d.spot != null ? `$${d.spot.toFixed(2)}` : '—'}
        </span>
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
    const strikes = [d.legs.longPut, d.legs.shortPut, d.legs.shortCall, d.legs.longCall];
    const candleLows = candles.map(c => Number(c.low ?? c.l ?? 0)).filter(v => v > 0);
    const candleHighs = candles.map(c => Number(c.high ?? c.h ?? 0)).filter(v => v > 0);
    const lo = Math.min(d.legs.longPut - 6, ...candleLows);
    const hi = Math.max(d.legs.longCall + 6, ...candleHighs);
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

    // ─── X-axis time labels (5 evenly spaced across candle area) ────
    const xAxisLabels = [];
    if (candles.length > 0) {
      const fmt = (ts) => {
        if (!ts) return '';
        try {
          // Tradier timesales returns "time" as ISO or "2026-05-19T13:45:00"
          const d = new Date(ts);
          return d.toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
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
    let nowMarker = null;
    if (d.spot != null && d.unrealized != null) {
      const cx = xPnl(d.unrealized);
      const cy = yPx(d.spot);
      const labelW = 158;
      const placeLeft = cx > overlayRight - labelW - 18;
      const labelX = placeLeft ? cx - labelW - 12 : cx + 12;
      nowMarker = {
        cx, cy,
        labelX,
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
      strikeLines, yTicks, xAxisLabels,
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
            <rect
              x={L.nowMarker.labelX} y={L.nowMarker.cy - 13}
              width={L.nowMarker.labelW} height="26" rx="4"
              fill="#fcd34d"
            />
            <text
              x={L.nowMarker.labelX + L.nowMarker.labelW / 2} y={L.nowMarker.cy + 4.5}
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
      <SummaryStrip d={d} />
      <EconomicsRow d={d} />
      <GreeksRow />
      <ChartCard d={d} theme={theme} botId={bot} />
    </div>
  );
}
