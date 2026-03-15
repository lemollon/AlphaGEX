import { useMemo } from 'react';
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);

/**
 * Plotly-based candlestick chart with GEX overlay — matches AlphaGEX GEX Profile.
 *
 * Features:
 *   - 5-min OHLC candlesticks (from intraday-bars)
 *   - Per-strike GEX bars on the right side (horizontal rectangles)
 *   - Reference lines: flip point (yellow), call wall (cyan), put wall (purple)
 *   - ±1σ expected move band (orange)
 *   - Strategy strike overlay lines (green = long, red = short)
 *   - Current price badge
 *
 * Props:
 *   intradayBars  — Array of { time, open, high, low, close, volume }
 *   sortedStrikes — Array of { strike, net_gamma, abs_net_gamma }
 *   levels        — { gex_flip, call_wall, put_wall, upper_1sd, lower_1sd, expected_move }
 *   strikes       — Strategy strikes { longPutStrike, shortPutStrike, shortCallStrike, longCallStrike }
 *   spotPrice     — Current spot price
 *   height        — Chart height in pixels
 *   sessionDate   — Session date label
 *   yRangeOut     — Callback to pass computed [yMin, yMax] to parent for PayoffPanel sync
 */

function toCentralPlotly(iso) {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (t) => parts.find(p => p.type === t)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`;
}

function formatGex(num, decimals = 1) {
  const abs = Math.abs(num);
  if (abs >= 1e9) return `${(num / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `${(num / 1e6).toFixed(decimals)}M`;
  if (abs >= 1e3) return `${(num / 1e3).toFixed(decimals)}K`;
  return num.toFixed(decimals);
}

export default function CandleChart({
  intradayBars = [],
  sortedStrikes = [],
  levels,
  strikes,
  spotPrice,
  height = 500,
  sessionDate,
  yRangeOut,
}) {
  const plotData = useMemo(() => {
    const hasBars = intradayBars.length > 0;

    // Candlestick data
    const candleTimes = hasBars ? intradayBars.map(b => toCentralPlotly(b.time)) : [];
    const priceValues = hasBars
      ? [...intradayBars.map(b => b.high), ...intradayBars.map(b => b.low)]
      : spotPrice ? [spotPrice] : [];

    const priceMin = priceValues.length > 0 ? Math.min(...priceValues) : 0;
    const priceMax = priceValues.length > 0 ? Math.max(...priceValues) : 0;
    const priceRange = priceMax - priceMin || 1;

    // Filter strikes to visible price range
    const visibleStrikes = sortedStrikes.filter(ss =>
      ss.strike >= priceMin - priceRange * 1.5 && ss.strike <= priceMax + priceRange * 1.5
    );

    const maxGamma = visibleStrikes.length > 0
      ? Math.max(...visibleStrikes.map(ss => ss.abs_net_gamma), 0.001) : 1;

    // Layout: candles [0 – 0.78] | gap | GEX bars [0.82 – 0.98] | price axis in r margin
    const barLeft = 0.82;
    const barRight = 0.98;
    const barMaxWidth = barRight - barLeft;
    const strikeSpacing = visibleStrikes.length > 1
      ? Math.abs(visibleStrikes[0].strike - visibleStrikes[1].strike) * 0.35 : 0.5;

    // GEX bar shapes
    const gexShapes = visibleStrikes.map(ss => {
      const pct = (ss.abs_net_gamma / maxGamma) * barMaxWidth;
      const color = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)';
      const borderColor = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)';
      return {
        type: 'rect', xref: 'paper', yref: 'y',
        x0: barRight, x1: barRight - pct,
        y0: ss.strike - strikeSpacing, y1: ss.strike + strikeSpacing,
        fillcolor: color, line: { color: borderColor, width: 1 }, layer: 'above',
      };
    });

    // GEX value annotations
    const gexAnnotations = visibleStrikes
      .filter(ss => ss.abs_net_gamma / maxGamma > 0.15)
      .map(ss => ({
        xref: 'paper', yref: 'y',
        x: barRight - (ss.abs_net_gamma / maxGamma) * barMaxWidth - 0.005,
        y: ss.strike,
        text: `${formatGex(ss.net_gamma)} [$${ss.strike}]`,
        showarrow: false,
        font: { color: ss.net_gamma >= 0 ? '#22c55e' : '#ef4444', size: 9, family: 'monospace' },
        xanchor: 'right', yanchor: 'middle',
      }));

    // Reference lines
    const refLines = [];
    const flip = levels?.gex_flip;
    const cw = levels?.call_wall;
    const pw = levels?.put_wall;
    const upper_1sd = levels?.upper_1sd;
    const lower_1sd = levels?.lower_1sd;
    const expected_move = levels?.expected_move;

    if (flip) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: flip, y1: flip, line: { color: '#eab308', width: 2.5, dash: 'dash' } });
    if (cw) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: cw, y1: cw, line: { color: '#06b6d4', width: 2.5, dash: 'dot' } });
    if (pw) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: pw, y1: pw, line: { color: '#a855f7', width: 2.5, dash: 'dot' } });
    if (upper_1sd) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: upper_1sd, y1: upper_1sd, line: { color: '#f97316', width: 1.5, dash: 'dashdot' } });
    if (lower_1sd) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: lower_1sd, y1: lower_1sd, line: { color: '#f97316', width: 1.5, dash: 'dashdot' } });
    if (upper_1sd && lower_1sd) refLines.push({
      type: 'rect', xref: 'paper', yref: 'y',
      x0: 0, x1: 1, y0: lower_1sd, y1: upper_1sd,
      fillcolor: 'rgba(249,115,22,0.06)', line: { width: 0 }, layer: 'below',
    });

    // Strategy strike lines (from spread builder)
    const strategyLines = [];
    if (strikes) {
      const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter(Boolean).map(Number);
      const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter(Boolean).map(Number);
      longPrices.forEach(p => {
        if (!isNaN(p)) strategyLines.push({
          type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: p, y1: p,
          line: { color: '#22c55e', width: 1.5, dash: 'dash' },
        });
      });
      shortPrices.forEach(p => {
        if (!isNaN(p)) strategyLines.push({
          type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: p, y1: p,
          line: { color: '#ef4444', width: 1.5, dash: 'dash' },
        });
      });
    }

    // Compute Y range
    const yPoints = [...priceValues];
    if (flip) yPoints.push(flip);
    if (cw) yPoints.push(cw);
    if (pw) yPoints.push(pw);
    if (upper_1sd) yPoints.push(upper_1sd);
    if (lower_1sd) yPoints.push(lower_1sd);
    // Include strategy strikes
    if (strikes) {
      [strikes.longPutStrike, strikes.shortPutStrike, strikes.shortCallStrike, strikes.longCallStrike]
        .filter(Boolean).map(Number).filter(n => !isNaN(n)).forEach(n => yPoints.push(n));
    }
    const yMin = yPoints.length > 0 ? Math.min(...yPoints) : 0;
    const yMax = yPoints.length > 0 ? Math.max(...yPoints) : 0;
    const yPad = (yMax - yMin) * 0.15 || 4;
    const yRange = [yMin - yPad, yMax + yPad];

    // Reference level annotations
    const refAnnotations = [];
    if (flip) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: flip, text: `FLIP $${flip.toFixed(0)}`, showarrow: false, font: { color: '#eab308', size: 10 }, xanchor: 'left', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (cw) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: cw, text: `CALL WALL $${cw.toFixed(0)}`, showarrow: false, font: { color: '#06b6d4', size: 10 }, xanchor: 'left', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (pw) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: pw, text: `PUT WALL $${pw.toFixed(0)}`, showarrow: false, font: { color: '#a855f7', size: 10 }, xanchor: 'left', yanchor: 'top', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (upper_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.77, y: upper_1sd, text: `+1σ $${upper_1sd.toFixed(0)}${expected_move ? ` (EM $${expected_move.toFixed(1)})` : ''}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (lower_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.77, y: lower_1sd, text: `-1σ $${lower_1sd.toFixed(0)}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'top', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });

    // Strategy strike annotations
    const strikeAnnotations = [];
    if (strikes) {
      const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter(Boolean).map(Number);
      const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter(Boolean).map(Number);
      longPrices.forEach(p => {
        if (!isNaN(p)) strikeAnnotations.push({
          xref: 'paper', yref: 'y', x: 0.77, y: p,
          text: `Long $${p}`, showarrow: false,
          font: { color: '#22c55e', size: 9 }, xanchor: 'right', yanchor: 'bottom',
          bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
        });
      });
      shortPrices.forEach(p => {
        if (!isNaN(p)) strikeAnnotations.push({
          xref: 'paper', yref: 'y', x: 0.77, y: p,
          text: `Short $${p}`, showarrow: false,
          font: { color: '#ef4444', size: 9 }, xanchor: 'right', yanchor: 'top',
          bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
        });
      });
    }

    // Candlestick trace
    const traces = [];
    if (hasBars) {
      traces.push({
        x: candleTimes,
        open: intradayBars.map(b => b.open),
        high: intradayBars.map(b => b.high),
        low: intradayBars.map(b => b.low),
        close: intradayBars.map(b => b.close),
        type: 'candlestick',
        increasing: { line: { color: '#22c55e' }, fillcolor: 'rgba(34,197,94,0.3)' },
        decreasing: { line: { color: '#ef4444' }, fillcolor: 'rgba(239,68,68,0.8)' },
        name: 'Price',
        hoverinfo: 'x+text',
        text: intradayBars.map(b =>
          `O:${b.open.toFixed(2)} H:${b.high.toFixed(2)} L:${b.low.toFixed(2)} C:${b.close.toFixed(2)}<br>Vol:${(b.volume || 0).toLocaleString()}`
        ),
      });
    } else if (spotPrice) {
      // Fallback: single price marker
      traces.push({
        x: [new Date().toISOString()],
        y: [spotPrice],
        type: 'scatter',
        mode: 'markers',
        marker: { color: '#448aff', size: 8 },
        name: 'Spot',
      });
    }

    return {
      traces,
      shapes: [...gexShapes, ...refLines, ...strategyLines],
      annotations: [...gexAnnotations, ...refAnnotations, ...strikeAnnotations],
      yRange,
      hasBars,
    };
  }, [intradayBars, sortedStrikes, levels, strikes, spotPrice]);

  // Sync yRange to parent for PayoffPanel alignment
  useMemo(() => {
    if (yRangeOut && plotData.yRange) {
      yRangeOut(plotData.yRange);
    }
  }, [plotData.yRange, yRangeOut]);

  if (!plotData.hasBars && !spotPrice) {
    return (
      <div className="flex-[3] flex flex-col items-center justify-center text-text-muted font-[var(--font-mono)] text-xs bg-bg-base gap-1.5">
        <span>No candle data available</span>
        <span className="text-[10px] text-text-muted/60">
          Data loads from AlphaGEX — check connection during market hours.
        </span>
      </div>
    );
  }

  return (
    <div className="flex-[3] overflow-hidden bg-bg-base">
      <Plot
        data={plotData.traces}
        layout={{
          height,
          paper_bgcolor: '#0a0a14',
          plot_bgcolor: '#0f0f1e',
          font: { color: '#9ca3af', family: 'Inter, Arial, sans-serif', size: 11 },
          xaxis: {
            type: 'date',
            gridcolor: '#1a1a2e',
            showgrid: true,
            rangeslider: { visible: false },
            hoverformat: '%I:%M %p CT',
            tickformat: '%I:%M %p',
            domain: [0, 0.78],
          },
          yaxis: {
            gridcolor: '#1a1a2e',
            showgrid: true,
            side: 'right',
            tickformat: '$,.0f',
            range: plotData.yRange,
            autorange: false,
          },
          shapes: plotData.shapes,
          annotations: plotData.annotations,
          margin: { t: 10, b: 40, l: 10, r: 70 },
          hovermode: 'x unified',
          showlegend: false,
          transition: { duration: 300, easing: 'cubic-in-out' },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
}
