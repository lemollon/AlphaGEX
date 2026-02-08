'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, useMemo, useCallback } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  TrendingUp,
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
  FileText,
  Sun,
  BookOpen,
  Pin,
  PinOff,
  Flame,
  Shield,
  Zap,
  Globe
} from 'lucide-react'
import { apiClient } from '@/lib/api'
import BuildVersion from './BuildVersion'
import { CrossButton, DedicationModal, StewardshipTagline, StewardshipBanner } from './StewardshipBanner'
import { useSidebar } from '@/contexts/SidebarContext'
import { BOT_DISPLAY_NAMES, ADVISOR_DISPLAY_NAMES } from '@/lib/botDisplayNames'

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, category: 'Main' },
  { href: '/daily-manna', label: 'Daily Manna', icon: BookOpen, category: 'Main' },
  { href: '/gex', label: 'GEX Analysis', icon: TrendingUp, category: 'Analysis' },
  { href: '/gex/history', label: 'GEX History', icon: Activity, category: 'Analysis' },
  { href: '/watchtower', label: `${ADVISOR_DISPLAY_NAMES.WATCHTOWER} (0DTE Gamma)`, icon: Eye, category: 'Analysis' },
  { href: '/gex-charts', label: 'GEX Charts (TV Style)', icon: BarChart3, category: 'Analysis' },
  { href: '/glory', label: `${ADVISOR_DISPLAY_NAMES.GLORY} (Weekly Gamma)`, icon: Sparkles, category: 'Analysis' },
  { href: '/discernment', label: `${ADVISOR_DISPLAY_NAMES.DISCERNMENT} (ML Scanner)`, icon: Sun, category: 'Trading' },
  { href: '/zero-dte-backtest', label: `${ADVISOR_DISPLAY_NAMES.CHRONICLES} (0DTE Condor)`, icon: Clock, category: 'AI & Testing' },
  { href: '/wisdom', label: `${ADVISOR_DISPLAY_NAMES.WISDOM} (ML Advisor)`, icon: Brain, category: 'AI & Testing' },
  { href: '/gex-ml', label: `${ADVISOR_DISPLAY_NAMES.STARS} (GEX ML)`, icon: Brain, category: 'AI & Testing' },
  { href: '/prophet', label: `${ADVISOR_DISPLAY_NAMES.PROPHET} (AI Advisor)`, icon: Eye, category: 'AI & Testing' },
  { href: '/quant', label: 'QUANT (ML Models)', icon: Calculator, category: 'AI & Testing' },
  { href: '/proverbs', label: `${ADVISOR_DISPLAY_NAMES.PROVERBS} (Feedback Loop)`, icon: BookOpen, category: 'AI & Testing' },
  { href: '/math-optimizer', label: 'Math Optimizer', icon: Brain, category: 'AI & Testing' },
  { href: '/live-trading', label: 'Live Trading', icon: LayoutDashboard, category: 'Live Trading' },
  { href: '/jubilee', label: `${BOT_DISPLAY_NAMES.JUBILEE} (Box Spread + IC)`, icon: Flame, category: 'Live Trading' },
  { href: '/fortress', label: `${BOT_DISPLAY_NAMES.FORTRESS} (SPY Iron Condor)`, icon: Sword, category: 'Live Trading' },
  { href: '/solomon', label: `${BOT_DISPLAY_NAMES.SOLOMON} (Directional Spreads)`, icon: Target, category: 'Live Trading' },
  { href: '/gideon', label: `${BOT_DISPLAY_NAMES.GIDEON} (Aggressive Directional)`, icon: Flame, category: 'Live Trading' },
  { href: '/anchor', label: `${BOT_DISPLAY_NAMES.ANCHOR} (SPX Iron Condor)`, icon: Shield, category: 'Live Trading' },
  { href: '/samson', label: `${BOT_DISPLAY_NAMES.SAMSON} (Aggressive SPX IC)`, icon: Zap, category: 'Live Trading' },
  { href: '/valor', label: `${BOT_DISPLAY_NAMES.VALOR} (MES Futures)`, icon: Activity, category: 'Live Trading' },
  { href: '/agape', label: `${BOT_DISPLAY_NAMES.AGAPE} (ETH Futures)`, icon: TrendingUp, category: 'Live Trading' },
  { href: '/agape-spot', label: `${BOT_DISPLAY_NAMES.AGAPE_SPOT} (Crypto Spot 24/7)`, icon: Globe, category: 'Live Trading' },
  { href: '/vix', label: 'VIX Dashboard', icon: Activity, category: 'Volatility' },
  { href: '/volatility-comparison', label: 'Volatility Comparison', icon: TrendingDown, category: 'Volatility' },
  { href: '/alerts', label: 'Alerts', icon: Bell, category: 'Volatility' },
  { href: '/trader', label: `${BOT_DISPLAY_NAMES.LAZARUS} (SPY 0DTE)`, icon: Bot, category: 'Beta' },
  { href: '/wheel', label: `${BOT_DISPLAY_NAMES.SHEPHERD} (Manual Wheel)`, icon: RotateCcw, category: 'Beta' },
  { href: '/spx-wheel', label: `${BOT_DISPLAY_NAMES.CORNERSTONE} (SPX Wheel)`, icon: Target, category: 'Beta' },
  { href: '/spx', label: 'SPX Institutional', icon: TrendingUp, category: 'Beta' },
  { href: '/counselor-commands', label: `${ADVISOR_DISPLAY_NAMES.COUNSELOR} Commands`, icon: MessageSquare, category: 'System' },
  { href: '/settings/system', label: 'System Settings', icon: Settings, category: 'System' },
  { href: '/settings/notifications', label: 'Notification Settings', icon: Bell, category: 'System' },
  { href: '/database', label: 'Database Admin', icon: Database, category: 'System' },
  { href: '/logs', label: 'Decision Logs', icon: FileText, category: 'System' },
  { href: '/data-transparency', label: 'Data Transparency', icon: Eye, category: 'System' },
  { href: '/system/processes', label: 'System Processes', icon: Activity, category: 'System' },
  { href: '/covenant', label: `${ADVISOR_DISPLAY_NAMES.COVENANT} (Neural Network)`, icon: Sparkles, category: 'Main' },
  { href: '/feature-docs', label: 'Feature Docs', icon: Calculator, category: 'System' },
]

export default function Navigation() {
  const pathname = usePathname()
  // Use shared sidebar context for state
  const { isPinned, setIsPinned, isHovered, setIsHovered, isExpanded } = useSidebar()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [spyPrice, setSpyPrice] = useState<number | null>(null)
  const [vixPrice, setVixPrice] = useState<number | null>(null)
  const [marketOpen, setMarketOpen] = useState(false)
  const [apiConnected, setApiConnected] = useState(true)
  const [dedicationModalOpen, setDedicationModalOpen] = useState(false)

  // Toggle pin state (localStorage is handled by SidebarContext)
  const togglePin = () => {
    setIsPinned(!isPinned)
  }

  // Fetch SPY/VIX prices and market status with 30-second auto-refresh during market hours
  useEffect(() => {
    const fetchMarketData = async () => {
      try {
        const [gexRes, timeRes, vixRes] = await Promise.all([
          apiClient.getGEX('SPY').catch((err) => {
            logger.debug('GEX fetch failed:', err)
            return null
          }),
          apiClient.time().catch((err) => {
            logger.debug('Time fetch failed:', err)
            return null
          }),
          apiClient.getVIXCurrent().catch((err) => {
            logger.debug('VIX fetch failed:', err)
            return null
          })
        ])

        // Update market status first
        if (timeRes?.data?.market_open !== undefined) {
          setMarketOpen(timeRes.data.market_open)
        }

        if (gexRes?.data?.data?.spot_price) {
          setSpyPrice(gexRes.data.data.spot_price)
          setApiConnected(true)
        } else if (gexRes?.data?.spot_price) {
          // Handle case where data is not nested
          setSpyPrice(gexRes.data.spot_price)
          setApiConnected(true)
        } else {
          setApiConnected(false)
        }

        if (vixRes?.data?.data?.vix_spot) {
          setVixPrice(vixRes.data.data.vix_spot)
        } else if (vixRes?.data?.vix_spot) {
          // Handle case where data is not nested
          setVixPrice(vixRes.data.vix_spot)
        }
      } catch (error) {
        logger.error('Error fetching market data:', error)
        setApiConnected(false)
      }
    }

    fetchMarketData()

    // Auto-refresh every 30 seconds for real-time market data
    // (Backend caches for 60 seconds, so 30s ensures fresh data without hammering API)
    const interval = setInterval(fetchMarketData, 30 * 1000)

    return () => clearInterval(interval)
  }, [])

  // PERFORMANCE FIX: Memoize grouped nav items (navItems is static, no need to recalculate)
  const groupedItems = useMemo(() => {
    return navItems.reduce((acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = []
      }
      acc[item.category].push(item)
      return acc
    }, {} as Record<string, typeof navItems>)
  }, [])  // Empty deps since navItems is static

  return (
    <>
      {/* Top Bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-background-card border-b border-gray-800 h-16">
        <div className="flex items-center justify-between h-full px-4">
          {/* Left: Menu Toggle (mobile) + Logo */}
          <div className="flex items-center space-x-4">
            {/* Mobile menu button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-background-hover transition-colors"
              aria-label="Toggle mobile menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>

            <div className="flex items-center space-x-3">
              <Link href="/dashboard" className="flex items-center space-x-2">
                <Activity className="w-8 h-8 text-primary" />
                <div className="flex flex-col">
                  <span className="text-xl font-bold text-text-primary leading-tight">AlphaGEX</span>
                  <StewardshipTagline />
                </div>
              </Link>
              <div className="hidden sm:block border-l border-gray-700 h-8 mx-1" />
              <CrossButton onClick={() => setDedicationModalOpen(true)} />
            </div>
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

      {/* Gold Scripture Banner */}
      <div className="fixed top-16 left-0 right-0 z-40">
        <StewardshipBanner />
      </div>

      {/* Dedication Modal */}
      <DedicationModal
        isOpen={dedicationModalOpen}
        onClose={() => setDedicationModalOpen(false)}
      />

      {/* Desktop Sidebar - Hover to Expand */}
      <aside
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`
          hidden lg:block fixed top-16 left-0 bottom-0 z-40
          bg-background-card border-r border-gray-800
          transition-all duration-300 ease-in-out overflow-hidden
          ${isExpanded ? 'w-64' : 'w-16'}
        `}
      >
        <div className="h-full flex flex-col">
          {/* Navigation Items */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden py-4">
            {Object.entries(groupedItems).map(([category, items]) => (
              <div key={category} className="mb-4">
                {/* Category Label - only show when expanded */}
                <div className={`
                  px-4 mb-2 transition-opacity duration-200
                  ${isExpanded ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden'}
                `}>
                  <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    {category}
                  </h3>
                </div>

                <div className="space-y-1 px-2">
                  {items.map((item) => {
                    const Icon = item.icon
                    const isActive = pathname === item.href

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        title={!isExpanded ? item.label : undefined}
                        className={`
                          flex items-center rounded-lg font-medium transition-all text-sm
                          ${isExpanded ? 'px-3 py-2.5 space-x-3' : 'px-3 py-2.5 justify-center'}
                          ${isActive
                            ? 'bg-primary text-white shadow-lg'
                            : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
                          }
                        `}
                      >
                        <Icon className="w-5 h-5 flex-shrink-0" />
                        <span className={`
                          truncate whitespace-nowrap transition-all duration-200
                          ${isExpanded ? 'opacity-100 w-auto' : 'opacity-0 w-0 overflow-hidden'}
                        `}>
                          {item.label}
                        </span>
                      </Link>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Bottom Section: Pin Button + Build Version */}
          <div className="border-t border-gray-800 p-2">
            {/* Pin/Unpin Button */}
            <button
              onClick={togglePin}
              title={isPinned ? 'Unpin sidebar' : 'Pin sidebar open'}
              className={`
                w-full flex items-center rounded-lg text-text-secondary
                hover:text-text-primary hover:bg-background-hover transition-all
                ${isExpanded ? 'px-3 py-2 space-x-3' : 'px-3 py-2 justify-center'}
              `}
            >
              {isPinned ? (
                <PinOff className="w-5 h-5 flex-shrink-0" />
              ) : (
                <Pin className="w-5 h-5 flex-shrink-0" />
              )}
              <span className={`
                text-sm whitespace-nowrap transition-all duration-200
                ${isExpanded ? 'opacity-100 w-auto' : 'opacity-0 w-0 overflow-hidden'}
              `}>
                {isPinned ? 'Unpin Sidebar' : 'Pin Sidebar'}
              </span>
            </button>

            {/* Build Version - only show when expanded */}
            <div className={`
              transition-all duration-200 overflow-hidden
              ${isExpanded ? 'opacity-100 max-h-20' : 'opacity-0 max-h-0'}
            `}>
              <BuildVersion />
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <aside
        className={`
          lg:hidden fixed top-16 left-0 bottom-0 z-50
          bg-background-card border-r border-gray-800
          transition-transform duration-300 ease-in-out
          w-64 overflow-y-auto
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <div className="p-4 space-y-6">
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
                      onClick={() => setMobileMenuOpen(false)}
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

          {/* Build Version */}
          <BuildVersion />
        </div>
      </aside>
    </>
  )
}
