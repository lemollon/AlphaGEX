'use client'

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
  Database
} from 'lucide-react'
import { apiClient } from '@/lib/api'

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard, category: 'Main' },
  { href: '/gex', label: 'GEX Analysis', icon: TrendingUp, category: 'Analysis' },
  { href: '/gamma', label: 'Gamma Intelligence', icon: Zap, category: 'Analysis' },
  { href: '/gamma/0dte', label: '0DTE Tracker', icon: Clock, category: 'Analysis' },
  { href: '/psychology', label: 'Psychology Traps', icon: Brain, category: 'Analysis' },
  { href: '/psychology/performance', label: 'Psychology Performance', icon: BarChart3, category: 'Analysis' },
  { href: '/strategies', label: 'Strategy Optimizer', icon: TrendingUp, category: 'Trading' },
  { href: '/scanner', label: 'Scanner', icon: Search, category: 'Trading' },
  { href: '/setups', label: 'Trade Setups', icon: Target, category: 'Trading' },
  { href: '/position-sizing', label: 'Position Sizing', icon: Calculator, category: 'Trading' },
  { href: '/charts', label: 'Advanced Charts', icon: BarChart3, category: 'Analysis' },
  { href: '/backtesting', label: 'Backtesting', icon: TestTube, category: 'AI & Testing' },
  { href: '/trader', label: 'Autonomous Trader', icon: Bot, category: 'Automation' },
  { href: '/alerts', label: 'Alerts', icon: Bell, category: 'Automation' },
  { href: '/database', label: 'Database Admin', icon: Database, category: 'System' },
]

export default function Navigation() {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [spyPrice, setSpyPrice] = useState<number | null>(null)
  const [marketOpen, setMarketOpen] = useState(false)
  const [apiConnected, setApiConnected] = useState(true)

  // Fetch SPY price and market status - ONCE on mount only (no auto-refresh)
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const [gexRes, timeRes] = await Promise.all([
          apiClient.getGEX('SPY').catch(() => null),
          apiClient.time().catch(() => null)
        ])

        if (gexRes?.data?.data?.spot_price) {
          setSpyPrice(gexRes.data.data.spot_price)
          setApiConnected(true)
        } else {
          setApiConnected(false)
        }

        if (timeRes?.data?.market_open !== undefined) {
          setMarketOpen(timeRes.data.market_open)
        }
      } catch (error) {
        console.error('Error fetching market data:', error)
        setApiConnected(false)
      }
    }

    fetchMarketData()
    // No auto-refresh - protects API rate limit (20 calls/min shared across all users)
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
            <div className="hidden sm:flex items-center space-x-2 text-sm">
              <span className="text-text-secondary">SPY:</span>
              <span className="text-text-primary font-mono font-semibold">
                {spyPrice ? `$${spyPrice.toFixed(2)}` : (apiConnected ? '---' : 'Error')}
              </span>
              {spyPrice && <span className="text-success">▲</span>}
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
