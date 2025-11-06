'use client'

import { useEffect } from 'react'
import { AlertTriangle, RefreshCcw, Home } from 'lucide-react'
import Link from 'next/link'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Log error to console for debugging
    console.error('Application Error:', {
      message: error.message,
      digest: error.digest,
      stack: error.stack,
      timestamp: new Date().toISOString()
    })
  }, [error])

  return (
    <div className="min-h-screen bg-background-deep flex items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center">
        {/* Error Icon */}
        <div className="mb-8">
          <div className="inline-block p-6 bg-danger/10 rounded-full mb-4">
            <AlertTriangle className="w-16 h-16 text-danger" />
          </div>
          <h1 className="text-3xl font-bold text-text-primary mb-2">
            Something Went Wrong
          </h1>
          <p className="text-text-secondary text-lg">
            We encountered an unexpected error. Don't worry, we're working on it.
          </p>
        </div>

        {/* Error Details (only in development) */}
        {process.env.NODE_ENV === 'development' && (
          <div className="card mb-8 text-left">
            <h3 className="text-lg font-semibold mb-4 text-danger">Error Details</h3>
            <div className="bg-background-deep rounded-lg p-4 overflow-auto">
              <pre className="text-xs text-text-muted font-mono whitespace-pre-wrap">
                {error.message}
              </pre>
              {error.digest && (
                <div className="mt-2 text-xs text-text-muted">
                  Digest: {error.digest}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
          <button
            onClick={reset}
            className="btn-primary inline-flex items-center justify-center space-x-2 px-6 py-3"
          >
            <RefreshCcw className="w-5 h-5" />
            <span>Try Again</span>
          </button>
          <Link
            href="/"
            className="btn-secondary inline-flex items-center justify-center space-x-2 px-6 py-3"
          >
            <Home className="w-5 h-5" />
            <span>Go to Dashboard</span>
          </Link>
        </div>

        {/* Troubleshooting Tips */}
        <div className="card max-w-md mx-auto">
          <h3 className="text-lg font-semibold mb-4">Troubleshooting Tips</h3>
          <div className="space-y-3 text-left text-sm">
            <div className="flex items-start space-x-3">
              <span className="text-primary">•</span>
              <div>
                <div className="font-medium">Refresh the page</div>
                <div className="text-text-muted">Sometimes a simple refresh fixes the issue</div>
              </div>
            </div>
            <div className="flex items-start space-x-3">
              <span className="text-primary">•</span>
              <div>
                <div className="font-medium">Check your connection</div>
                <div className="text-text-muted">Make sure you're connected to the internet</div>
              </div>
            </div>
            <div className="flex items-start space-x-3">
              <span className="text-primary">•</span>
              <div>
                <div className="font-medium">Clear browser cache</div>
                <div className="text-text-muted">Old cached data might cause issues</div>
              </div>
            </div>
            <div className="flex items-start space-x-3">
              <span className="text-primary">•</span>
              <div>
                <div className="font-medium">Backend service</div>
                <div className="text-text-muted">Ensure the API server is running</div>
              </div>
            </div>
          </div>
        </div>

        {/* Contact Support */}
        <div className="mt-8 text-sm text-text-muted">
          <p>
            If the problem persists, check the browser console for more details or
            contact support with error ID: <span className="font-mono">{error.digest || 'N/A'}</span>
          </p>
        </div>
      </div>
    </div>
  )
}
