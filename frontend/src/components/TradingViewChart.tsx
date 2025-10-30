'use client'

import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, LineData, CandlestickData } from 'lightweight-charts'

interface TradingViewChartProps {
  data: Array<LineData | CandlestickData>
  type?: 'line' | 'candlestick' | 'area'
  height?: number
  colors?: {
    upColor?: string
    downColor?: string
    lineColor?: string
    areaTopColor?: string
    areaBottomColor?: string
  }
}

export default function TradingViewChart({
  data,
  type = 'line',
  height = 400,
  colors = {}
}: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line' | 'Candlestick' | 'Area'> | null>(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

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
      timeScale: {
        borderColor: '#2a2f3e',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#2a2f3e',
      },
      crosshair: {
        mode: 1,
      },
    })

    chartRef.current = chart

    // Create series based on type
    let series: ISeriesApi<'Line' | 'Candlestick' | 'Area'>

    if (type === 'candlestick') {
      series = chart.addCandlestickSeries({
        upColor: colors.upColor || '#10b981',
        downColor: colors.downColor || '#ef4444',
        borderUpColor: colors.upColor || '#10b981',
        borderDownColor: colors.downColor || '#ef4444',
        wickUpColor: colors.upColor || '#10b981',
        wickDownColor: colors.downColor || '#ef4444',
      })
    } else if (type === 'area') {
      series = chart.addAreaSeries({
        lineColor: colors.lineColor || '#3b82f6',
        topColor: colors.areaTopColor || 'rgba(59, 130, 246, 0.4)',
        bottomColor: colors.areaBottomColor || 'rgba(59, 130, 246, 0.0)',
        lineWidth: 2,
      })
    } else {
      series = chart.addLineSeries({
        color: colors.lineColor || '#3b82f6',
        lineWidth: 2,
      })
    }

    seriesRef.current = series

    // Set data
    if (data && data.length > 0) {
      series.setData(data as any)
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
  }, [])

  // Update data when it changes
  useEffect(() => {
    if (seriesRef.current && data && data.length > 0) {
      seriesRef.current.setData(data as any)
    }
  }, [data])

  return (
    <div
      ref={chartContainerRef}
      className="w-full rounded-lg overflow-hidden"
      style={{ height: `${height}px` }}
    />
  )
}
