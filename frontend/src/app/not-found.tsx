'use client'

import { logger } from '@/lib/logger'

import Link from 'next/link'
import { useEffect } from 'react'
import { Home, ArrowLeft, Search } from 'lucide-react'

export default function NotFound() {
  useEffect(() => {
    // Log 404 errors for debugging
    logger.error('404 Page Not Found:', {
      url: window.location.href,
      timestamp: new Date().toISOString(),
      referrer: document.referrer
    })
  }, [])

  return (
    <div className="min-h-screen bg-background-deep flex items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center">
        {/* Error Code */}
        <div className="mb-8">
          <h1 className="text-9xl font-bold text-primary mb-4">404</h1>
          <div className="text-3xl font-semibold text-text-primary mb-2">
            Page Not Found
          </div>
          <p className="text-text-secondary text-lg">
            The page you're looking for doesn't exist or has been moved.
          </p>
        </div>

        {/* Illustration */}
        <div className="mb-8">
          <div className="inline-block p-6 bg-background-hover rounded-full">
            <Search className="w-16 h-16 text-text-muted" />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
          <Link
            href="/"
            className="btn-primary inline-flex items-center justify-center space-x-2 px-6 py-3"
          >
            <Home className="w-5 h-5" />
            <span>Go to Dashboard</span>
          </Link>
          <button
            onClick={() => window.history.back()}
            className="btn-secondary inline-flex items-center justify-center space-x-2 px-6 py-3"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Go Back</span>
          </button>
        </div>

        {/* Quick Links */}
        <div className="card max-w-md mx-auto">
          <h3 className="text-lg font-semibold mb-4">Quick Links</h3>
          <div className="space-y-2 text-left">
            <Link
              href="/"
              className="block px-4 py-2 rounded-lg hover:bg-background-hover transition-colors"
            >
              <div className="flex items-center space-x-3">
                <span className="text-2xl">🏠</span>
                <div>
                  <div className="font-medium">Dashboard</div>
                  <div className="text-sm text-text-muted">Main overview and positions</div>
                </div>
              </div>
            </Link>
            <Link
              href="/scanner"
              className="block px-4 py-2 rounded-lg hover:bg-background-hover transition-colors"
            >
              <div className="flex items-center space-x-3">
                <span className="text-2xl">🔍</span>
                <div>
                  <div className="font-medium">Market Scanner</div>
                  <div className="text-sm text-text-muted">Find trading opportunities</div>
                </div>
              </div>
            </Link>
            <Link
              href="/gex"
              className="block px-4 py-2 rounded-lg hover:bg-background-hover transition-colors"
            >
              <div className="flex items-center space-x-3">
                <span className="text-2xl">📊</span>
                <div>
                  <div className="font-medium">GEX Analysis</div>
                  <div className="text-sm text-text-muted">Gamma exposure insights</div>
                </div>
              </div>
            </Link>
            <Link
              href="/ai-copilot"
              className="block px-4 py-2 rounded-lg hover:bg-background-hover transition-colors"
            >
              <div className="flex items-center space-x-3">
                <span className="text-2xl">🤖</span>
                <div>
                  <div className="font-medium">AI Copilot</div>
                  <div className="text-sm text-text-muted">Ask trading questions</div>
                </div>
              </div>
            </Link>
          </div>
        </div>

        {/* Debug Info (only in development) */}
        {process.env.NODE_ENV === 'development' && (
          <div className="mt-8 p-4 bg-background-hover rounded-lg text-left">
            <div className="text-xs text-text-muted font-mono">
              <div>URL: {typeof window !== 'undefined' ? window.location.href : 'N/A'}</div>
              <div>Time: {new Date().toISOString()}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
