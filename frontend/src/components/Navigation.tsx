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
  Brain
} from 'lucide-react'
import { apiClient } from '@/lib/api'

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/gex', label: 'GEX Analysis', icon: TrendingUp },
  { href: '/gamma', label: 'Gamma Intelligence', icon: Zap },
  { href: '/gamma/0dte', label: '0DTE Tracker', icon: Clock },
  { href: '/psychology', label: 'Psychology Traps', icon: Brain },
  { href: '/strategies', label: 'Strategy Optimizer', icon: BarChart3 },
  { href: '/scanner', label: 'Scanner', icon: Search },
  { href: '/setups', label: 'Trade Setups', icon: Target },
  { href: '/alerts', label: 'Alerts', icon: Bell },
  { href: '/position-sizing', label: 'Position Sizing', icon: Calculator },
  { href: '/ai', label: 'AI Copilot', icon: MessageSquare },
  { href: '/trader', label: 'Autonomous Trader', icon: Bot },
]

export default function Navigation() {
  const pathname = usePathname()
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

  return (
    <nav className="bg-background-card border-b border-gray-800">
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          {/* Logo */}
          <div className="flex items-center space-x-2 flex-shrink-0">
            <Link href="/" className="flex items-center space-x-2">
              <Activity className="w-8 h-8 text-primary" />
              <span className="text-xl font-bold text-text-primary">AlphaGEX</span>
            </Link>
          </div>

          {/* Navigation Tabs */}
          <div className="hidden md:flex items-center justify-evenly flex-1 gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = pathname === item.href

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`
                    flex items-center justify-center space-x-1.5 px-3 py-2 rounded-lg font-medium transition-all text-sm flex-1 min-w-0
                    ${isActive
                      ? 'bg-primary text-white'
                      : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
                    }
                  `}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="whitespace-nowrap hidden lg:inline">{item.label}</span>
                </Link>
              )
            })}
          </div>

          {/* Mobile menu button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover flex-shrink-0"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>

          {/* Market Status */}
          <div className="hidden md:flex items-center space-x-4 flex-shrink-0">
            <div className="hidden xl:flex items-center space-x-2 text-sm">
              <span className="text-text-secondary">SPY:</span>
              <span className="text-text-primary font-mono font-semibold">
                {spyPrice ? `$${spyPrice.toFixed(2)}` : (apiConnected ? '---' : 'Error')}
              </span>
              {spyPrice && <span className="text-success">▲</span>}
            </div>
            <div className="flex items-center space-x-2">
              <div className={`w-2 h-2 rounded-full ${apiConnected ? (marketOpen ? 'bg-success' : 'bg-warning') : 'bg-danger'} ${apiConnected ? 'animate-pulse' : ''}`}></div>
              <span className="text-sm text-text-secondary hidden lg:inline">
                {!apiConnected ? 'API Disconnected' : (marketOpen ? 'Market Open' : 'Market Closed')}
              </span>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden py-4 border-t border-gray-800">
            <div className="flex flex-col space-y-2">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = pathname === item.href

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`
                      flex items-center space-x-3 px-4 py-3 rounded-lg font-medium transition-all
                      ${isActive
                        ? 'bg-primary text-white'
                        : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
                      }
                    `}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{item.label}</span>
                  </Link>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}
