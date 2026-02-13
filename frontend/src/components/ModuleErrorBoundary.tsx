'use client'

import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: React.ReactNode
  moduleName: string
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * Error boundary that wraps individual Watchtower modules.
 * If one module crashes, the rest of the page continues to work.
 */
export default class ModuleErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error(`[WATCHTOWER] ${this.props.moduleName} crashed:`, error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span className="text-sm font-medium text-rose-300">{this.props.moduleName} Error</span>
          </div>
          <p className="text-xs text-rose-400/70 mb-3">
            This module encountered an error and was isolated to prevent affecting other modules.
          </p>
          <button
            onClick={this.handleRetry}
            className="text-xs text-rose-300 hover:text-rose-200 flex items-center gap-1 px-2 py-1 bg-rose-500/10 rounded hover:bg-rose-500/20 transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
