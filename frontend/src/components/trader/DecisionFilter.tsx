'use client'

import { useState } from 'react'
import { Search, Filter, X, Calendar, ChevronDown } from 'lucide-react'

type DecisionType = 'all' | 'entry' | 'exit' | 'skip' | 'error'
type SignalSource = 'all' | 'ml' | 'oracle' | 'override' | 'config'

interface DecisionFilterProps {
  onFilterChange: (filters: DecisionFilters) => void
  decisionCounts?: {
    entry: number
    exit: number
    skip: number
    error: number
  }
}

export interface DecisionFilters {
  search: string
  decisionType: DecisionType
  signalSource: SignalSource
  dateRange: 'today' | 'week' | 'month' | 'all'
  showOverridesOnly: boolean
}

const defaultFilters: DecisionFilters = {
  search: '',
  decisionType: 'all',
  signalSource: 'all',
  dateRange: 'today',
  showOverridesOnly: false
}

export default function DecisionFilter({ onFilterChange, decisionCounts }: DecisionFilterProps) {
  const [filters, setFilters] = useState<DecisionFilters>(defaultFilters)
  const [isExpanded, setIsExpanded] = useState(false)

  const updateFilters = (updates: Partial<DecisionFilters>) => {
    const newFilters = { ...filters, ...updates }
    setFilters(newFilters)
    onFilterChange(newFilters)
  }

  const resetFilters = () => {
    setFilters(defaultFilters)
    onFilterChange(defaultFilters)
  }

  const hasActiveFilters =
    filters.search !== '' ||
    filters.decisionType !== 'all' ||
    filters.signalSource !== 'all' ||
    filters.dateRange !== 'today' ||
    filters.showOverridesOnly

  const decisionTypes: { value: DecisionType; label: string; count?: number }[] = [
    { value: 'all', label: 'All' },
    { value: 'entry', label: 'Entry', count: decisionCounts?.entry },
    { value: 'exit', label: 'Exit', count: decisionCounts?.exit },
    { value: 'skip', label: 'Skip', count: decisionCounts?.skip },
    { value: 'error', label: 'Error', count: decisionCounts?.error }
  ]

  const signalSources: { value: SignalSource; label: string }[] = [
    { value: 'all', label: 'All Sources' },
    { value: 'ml', label: 'ML' },
    { value: 'oracle', label: 'Oracle' },
    { value: 'override', label: 'Overrides' },
    { value: 'config', label: 'Config' }
  ]

  const dateRanges: { value: 'today' | 'week' | 'month' | 'all'; label: string }[] = [
    { value: 'today', label: 'Today' },
    { value: 'week', label: 'This Week' },
    { value: 'month', label: 'This Month' },
    { value: 'all', label: 'All Time' }
  ]

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Search Bar */}
      <div className="p-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search decisions..."
              value={filters.search}
              onChange={(e) => updateFilters({ search: e.target.value })}
              className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            {filters.search && (
              <button
                onClick={() => updateFilters({ search: '' })}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                <X className="w-4 h-4 text-gray-500 hover:text-white" />
              </button>
            )}
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={`p-2 rounded-lg border transition-colors ${
              hasActiveFilters
                ? 'bg-blue-500/20 border-blue-500/50 text-blue-400'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white'
            }`}
          >
            <Filter className="w-4 h-4" />
          </button>
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="p-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:text-white"
              title="Reset filters"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Decision Type Tabs */}
      <div className="px-3 py-2 border-b border-gray-700 flex gap-1 overflow-x-auto">
        {decisionTypes.map((type) => (
          <button
            key={type.value}
            onClick={() => updateFilters({ decisionType: type.value })}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
              filters.decisionType === type.value
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                : 'bg-gray-800 text-gray-400 hover:text-white border border-transparent'
            }`}
          >
            {type.label}
            {type.count !== undefined && type.count > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
                {type.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Expanded Filters */}
      {isExpanded && (
        <div className="p-3 space-y-3">
          {/* Signal Source */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Signal Source</label>
            <div className="flex flex-wrap gap-1">
              {signalSources.map((source) => (
                <button
                  key={source.value}
                  onClick={() => updateFilters({ signalSource: source.value })}
                  className={`px-2 py-1 rounded text-xs transition-colors ${
                    filters.signalSource === source.value
                      ? source.value === 'override'
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50'
                        : 'bg-purple-500/20 text-purple-400 border border-purple-500/50'
                      : 'bg-gray-800 text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  {source.label}
                </button>
              ))}
            </div>
          </div>

          {/* Date Range */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Time Period</label>
            <div className="flex flex-wrap gap-1">
              {dateRanges.map((range) => (
                <button
                  key={range.value}
                  onClick={() => updateFilters({ dateRange: range.value })}
                  className={`px-2 py-1 rounded text-xs flex items-center gap-1 transition-colors ${
                    filters.dateRange === range.value
                      ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                      : 'bg-gray-800 text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  <Calendar className="w-3 h-3" />
                  {range.label}
                </button>
              ))}
            </div>
          </div>

          {/* Override Toggle */}
          <div className="flex items-center justify-between pt-2 border-t border-gray-700">
            <span className="text-xs text-gray-400">Show overrides only</span>
            <button
              onClick={() => updateFilters({ showOverridesOnly: !filters.showOverridesOnly })}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                filters.showOverridesOnly ? 'bg-amber-500' : 'bg-gray-700'
              }`}
            >
              <span
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  filters.showOverridesOnly ? 'translate-x-5' : 'translate-x-0.5'
                }`}
              ></span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
