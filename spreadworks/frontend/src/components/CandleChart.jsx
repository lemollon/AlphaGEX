import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';

export default function CandleChart({ candles, gexData, height = 320 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: { background: { color: '#1e293b' }, textColor: '#94a3b8' },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      crosshair: { mode: 0 },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    const volumeSeries = chart.addHistogramSeries({
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    if (candles && candles.length > 0) {
      const candleData = candles
        .filter((c) => c.time && c.open != null)
        .map((c) => ({
          time: Math.floor(new Date(c.time).getTime() / 1000),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));

      const volData = candles
        .filter((c) => c.time && c.volume != null)
        .map((c) => ({
          time: Math.floor(new Date(c.time).getTime() / 1000),
          value: c.volume,
          color: c.close >= c.open ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)',
        }));

      if (candleData.length > 0) {
        candleSeries.setData(candleData);
        volumeSeries.setData(volData);

        // Add GEX level lines
        if (gexData) {
          const lines = [];
          if (gexData.flip_point) {
            lines.push({
              price: gexData.flip_point,
              color: '#facc15',
              lineWidth: 1,
              lineStyle: 2,
              title: 'Flip',
            });
          }
          if (gexData.call_wall) {
            lines.push({
              price: gexData.call_wall,
              color: '#22c55e',
              lineWidth: 1,
              lineStyle: 2,
              title: 'Call Wall',
            });
          }
          if (gexData.put_wall) {
            lines.push({
              price: gexData.put_wall,
              color: '#ef4444',
              lineWidth: 1,
              lineStyle: 2,
              title: 'Put Wall',
            });
          }
          lines.forEach((l) => candleSeries.createPriceLine(l));
        }

        chart.timeScale().fitContent();
      }
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, gexData, height]);

  return <div ref={containerRef} style={{ width: '100%' }} />;
}
