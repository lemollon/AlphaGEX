'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  TrendingUp,
  Zap,
  Bot,
  MessageSquare,
  Activity,
  Search,
  Target,
  Bell,
  Calculator,
  Menu,
  X,
  Clock,
  BarChart3,
  Brain,
  TestTube,
  TrendingDown,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Database,
  Settings,
  RotateCcw,
  Sword,
  Eye,
  FileText
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import BuildVersion from './BuildVersion'

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard, category: 'Main' },
  { href: '/gex', label: 'GEX Analysis', icon: TrendingUp, category: 'Analysis' },
  { href: '/gex/history', label: 'GEX History', icon: Activity, category: 'Analysis' },
  { href: '/gamma', label: 'Gamma Intelligence', icon: Zap, category: 'Analysis' },
  { href: '/psychology', label: 'Psychology Traps', icon: Brain, category: 'Analysis' },
  { href: '/scanner', label: 'Scanner', icon: Search, category: 'Trading' },
  { href: '/zero-dte-backtest', label: 'KRONOS (0DTE Condor)', icon: Clock, category: 'AI & Testing' },
  { href: '/oracle', label: 'Oracle AI', icon: Eye, category: 'AI & Testing' },
  { href: '/probability', label: 'Probability System', icon: Activity, category: 'AI & Testing' },
  { href: '/ares', label: 'ARES (SPX Iron Condor)', icon: Sword, category: 'Live Trading' },
  { href: '/apache', label: 'SAGE (Directional Spreads)', icon: Target, category: 'Live Trading' },
  { href: '/trader', label: 'PHOENIX (SPY 0DTE)', icon: Bot, category: 'Beta' },
  { href: '/wheel', label: 'HERMES (Manual Wheel)', icon: RotateCcw, category: 'Beta' },
  { href: '/spx-wheel', label: 'ATLAS (SPX Wheel)', icon: Target, category: 'Beta' },
  { href: '/spx', label: 'SPX Institutional', icon: TrendingUp, category: 'Beta' },
  { href: '/vix', label: 'VIX Dashboard', icon: Activity, category: 'Automation' },
  { href: '/volatility-comparison', label: 'Volatility Comparison', icon: TrendingDown, category: 'Automation' },
  { href: '/alerts', label: 'Alerts', icon: Bell, category: 'Automation' },
  { href: '/settings/system', label: 'System Settings', icon: Settings, category: 'System' },
  { href: '/settings/notifications', label: 'Notification Settings', icon: Bell, category: 'System' },
  { href: '/database', label: 'Database Admin', icon: Database, category: 'System' },
  { href: '/logs', label: 'Decision Logs', icon: FileText, category: 'System' },
]

export default function Navigation() {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [spyPrice, setSpyPrice] = useState<number | null>(null)
  const [vixPrice, setVixPrice] = useState<number | null>(null)
  const [marketOpen, setMarketOpen] = useState(false)
  const [apiConnected, setApiConnected] = useState(true)

  // Fetch SPY/VIX prices and market status with 5-minute auto-refresh
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const [gexRes, timeRes, vixRes] = await Promise.all([
          apiClient.getGEX('SPY').catch(() => null),
          apiClient.time().catch(() => null),
          apiClient.getVIXCurrent().catch(() => null)
        ])

        if (gexRes?.data?.data?.spot_price) {
          setSpyPrice(gexRes.data.data.spot_price)
          setApiConnected(true)
        } else {
          setApiConnected(false)
        }

        if (vixRes?.data?.data?.vix_spot) {
          setVixPrice(vixRes.data.data.vix_spot)
        }

        if (timeRes?.data?.market_open !== undefined) {
          setMarketOpen(timeRes.data.market_open)
        }
      } catch (error) {
        logger.error('Error fetching market data:', error)
        setApiConnected(false)
      }
    }

    fetchMarketData()

    // Auto-refresh every 5 minutes (300000ms)
    const interval = setInterval(fetchMarketData, 5 * 60 * 1000)

    return () => clearInterval(interval)
  }, [])

  // Group nav items by category
  const groupedItems = navItems.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = []
    }
    acc[item.category].push(item)
    return acc
  }, {} as Record<string, typeof navItems>)

  return (
    <>
      {/* Top Bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-background-card border-b border-gray-800 h-16">
        <div className="flex items-center justify-between h-full px-4">
          {/* Left: Menu Toggle + Logo */}
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover transition-colors"
              aria-label="Toggle sidebar"
            >
              <Menu className="w-6 h-6" />
            </button>

            <Link href="/" className="flex items-center space-x-2">
              <Activity className="w-8 h-8 text-primary" />
              <span className="text-xl font-bold text-text-primary">AlphaGEX</span>
            </Link>
          </div>

          {/* Right: Market Status */}
          <div className="flex items-center space-x-4">
            <div className="hidden sm:flex items-center space-x-4 text-sm">
              <div className="flex items-center space-x-2">
                <span className="text-text-secondary">SPY:</span>
                <span className="text-text-primary font-mono font-semibold">
                  {spyPrice ? `$${spyPrice.toFixed(2)}` : (apiConnected ? '---' : 'Error')}
                </span>
                {spyPrice && <span className="text-success">▲</span>}
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-text-secondary">VIX:</span>
                <span className={`font-mono font-semibold ${
                  vixPrice ? (vixPrice > 25 ? 'text-danger' : vixPrice > 18 ? 'text-warning' : 'text-success') : 'text-text-primary'
                }`}>
                  {vixPrice ? vixPrice.toFixed(2) : '---'}
                </span>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <div className={`w-2 h-2 rounded-full ${apiConnected ? (marketOpen ? 'bg-success' : 'bg-warning') : 'bg-danger'} ${apiConnected ? 'animate-pulse' : ''}`}></div>
              <span className="text-sm text-text-secondary hidden md:inline">
                {!apiConnected ? 'API Disconnected' : (marketOpen ? 'Market Open' : 'Market Closed')}
              </span>
            </div>
          </div>
        </div>
      </nav>

      {/* Left Sidebar */}
      <aside
        className={`
          fixed top-16 left-0 bottom-0 z-40 bg-background-card border-r border-gray-800
          transition-all duration-300 ease-in-out overflow-y-auto
          ${sidebarOpen ? 'w-64' : 'w-0'}
        `}
      >
        <div className={`${sidebarOpen ? 'opacity-100' : 'opacity-0'} transition-opacity duration-300 p-4 space-y-6`}>
          {Object.entries(groupedItems).map(([category, items]) => (
            <div key={category}>
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 px-3">
                {category}
              </h3>
              <div className="space-y-1">
                {items.map((item) => {
                  const Icon = item.icon
                  const isActive = pathname === item.href

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`
                        flex items-center space-x-3 px-3 py-2.5 rounded-lg font-medium transition-all text-sm
                        ${isActive
                          ? 'bg-primary text-white shadow-lg'
                          : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
                        }
                      `}
                    >
                      <Icon className="w-5 h-5 flex-shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}

          {/* Collapse Button */}
          <button
            onClick={() => setSidebarOpen(false)}
            className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover transition-all"
          >
            <ChevronLeft className="w-4 h-4" />
            <span className="text-sm">Collapse</span>
          </button>

          {/* Build Version - helps verify deployments */}
          <BuildVersion />
        </div>
      </aside>

      {/* Sidebar Overlay for Mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Expand Button (when sidebar is closed) */}
      {!sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed top-20 left-2 z-40 p-2 rounded-lg bg-background-card border border-gray-800 text-text-secondary hover:text-text-primary hover:bg-background-hover transition-all shadow-lg"
          aria-label="Open sidebar"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      )}
    </>
  )
}
