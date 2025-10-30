'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  TrendingUp,
  Zap,
  Bot,
  MessageSquare,
  MoreHorizontal,
  Activity
} from 'lucide-react'

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/gex', label: 'GEX Analysis', icon: TrendingUp },
  { href: '/gamma', label: 'Gamma Intelligence', icon: Zap },
  { href: '/ai', label: 'AI Copilot', icon: MessageSquare },
  { href: '/trader', label: 'Autonomous Trader', icon: Bot },
]

export default function Navigation() {
  const pathname = usePathname()

  return (
    <nav className="bg-background-card border-b border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center space-x-2">
            <Activity className="w-8 h-8 text-primary" />
            <span className="text-xl font-bold text-text-primary">AlphaGEX</span>
          </div>

          {/* Navigation Tabs */}
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = pathname === item.href

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`
                    flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all
                    ${isActive
                      ? 'bg-primary text-white'
                      : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
                    }
                  `}
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </Link>
              )
            })}

            {/* More Menu */}
            <button className="flex items-center space-x-2 px-4 py-2 rounded-lg font-medium text-text-secondary hover:text-text-primary hover:bg-background-hover transition-all">
              <MoreHorizontal className="w-4 h-4" />
              <span>More</span>
            </button>
          </div>

          {/* Market Status */}
          <div className="flex items-center space-x-4">
            <div className="hidden lg:flex items-center space-x-2 text-sm">
              <span className="text-text-secondary">SPY:</span>
              <span className="text-text-primary font-mono font-semibold">$580.25</span>
              <span className="text-success">▲</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
              <span className="text-sm text-text-secondary hidden sm:inline">Market Open</span>
            </div>
          </div>
        </div>
      </div>
    </nav>
  )
}
