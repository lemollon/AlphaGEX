'use client'

import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, HistogramData } from 'lightweight-charts'

interface GEXLevel {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
}

interface GEXProfileChartProps {
  data: GEXLevel[]
  spotPrice?: number
  height?: number
}

export default function GEXProfileChart({
  data,
  spotPrice,
  height = 400
}: GEXProfileChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0a0e1a' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1a1f2e' },
        horzLines: { color: '#1a1f2e' },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      rightPriceScale: {
        borderColor: '#2a2f3e',
      },
      timeScale: {
        visible: false,
      },
      crosshair: {
        mode: 1,
      },
    })

    chartRef.current = chart

    // Prepare histogram data for total GEX
    const histogramData: HistogramData[] = data.map((level, index) => ({
      time: index as any,
      value: level.total_gex,
      color: level.total_gex > 0 ? '#10b981' : '#ef4444',
    }))

    // Add histogram series
    const histogramSeries = chart.addHistogramSeries({
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '',
    })

    histogramSeries.setData(histogramData)

    // Add price markers for spot price and key levels
    if (spotPrice) {
      const spotIndex = data.findIndex(level => level.strike >= spotPrice)
      if (spotIndex !== -1) {
        histogramSeries.setMarkers([
          {
            time: spotIndex as any,
            position: 'inBar',
            color: '#3b82f6',
            shape: 'arrowDown',
            text: 'Spot',
          },
        ])
      }
    }

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      if (chart) {
        chart.remove()
      }
    }
  }, [data, spotPrice, height])

  // Render custom bar chart if lightweight-charts histogram doesn't work well
  if (!data || data.length === 0) {
    return (
      <div
        className="w-full bg-background-deep rounded-lg flex items-center justify-center"
        style={{ height: `${height}px` }}
      >
        <p className="text-text-muted">No GEX data available</p>
      </div>
    )
  }

  return (
    <div
      ref={chartContainerRef}
      className="w-full rounded-lg overflow-hidden"
      style={{ height: `${height}px` }}
    />
  )
}
