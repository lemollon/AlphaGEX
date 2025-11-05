'use client'

import { useEffect, useRef, memo } from 'react'

interface TradingViewWidgetProps {
  symbol?: string
  interval?: string
  theme?: 'light' | 'dark'
  height?: number
  width?: string | number
  autosize?: boolean
}

function TradingViewWidget({
  symbol = 'SPY',
  interval = 'D',
  theme = 'dark',
  height = 400,
  width = '100%',
  autosize = true
}: TradingViewWidgetProps) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return

    // Clear previous widget
    container.current.innerHTML = ''

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: autosize,
      symbol: `${symbol}`,
      interval: interval,
      timezone: 'America/New_York',
      theme: theme,
      style: '1',
      locale: 'en',
      backgroundColor: theme === 'dark' ? 'rgba(10, 14, 26, 1)' : 'rgba(255, 255, 255, 1)',
      gridColor: theme === 'dark' ? 'rgba(26, 31, 46, 0.6)' : 'rgba(240, 243, 250, 0.6)',
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      height: autosize ? '100%' : height,
      width: autosize ? '100%' : width,
      withdateranges: true,
      allow_symbol_change: false,
      details: false,
      hotlist: false,
      calendar: false,
      studies: [
        'STD;SMA'
      ],
      support_host: 'https://www.tradingview.com'
    })

    container.current.appendChild(script)

    return () => {
      if (container.current) {
        container.current.innerHTML = ''
      }
    }
  }, [symbol, interval, theme, height, width, autosize])

  return (
    <div className="tradingview-widget-container" ref={container} style={{ height: `${height}px`, width: '100%' }}>
      <div className="tradingview-widget-container__widget" style={{ height: 'calc(100% - 32px)', width: '100%' }}></div>
      <div className="tradingview-widget-copyright">
        <a href={`https://www.tradingview.com/symbols/${symbol}/`} rel="noopener nofollow" target="_blank">
          <span className="text-xs text-text-muted">Track {symbol} on TradingView</span>
        </a>
      </div>
    </div>
  )
}

export default memo(TradingViewWidget)
