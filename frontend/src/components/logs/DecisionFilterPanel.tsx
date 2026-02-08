'use client'

import React, { useState } from 'react'
import { Search, Filter, Calendar, Bot, TrendingUp, TrendingDown, Clock, X, Download } from 'lucide-react'

interface FilterState {
  bot: string
  decisionType: string
  outcome: string
  startDate: string
  endDate: string
  search: string
  confidenceLevel: string
}

interface DecisionFilterPanelProps {
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  onExport: (format: 'csv' | 'json' | 'excel') => void
  isExporting?: boolean
  className?: string
}

const BOTS = [
  { id: 'all', name: 'All Bots' },
  { id: 'FORTRESS', name: 'FORTRESS', color: 'text-red-400' },
  { id: 'SOLOMON', name: 'SOLOMON', color: 'text-pink-400' },
  { id: 'CORNERSTONE', name: 'CORNERSTONE', color: 'text-blue-400' },
  { id: 'ANCHOR', name: 'ANCHOR', color: 'text-cyan-400' },
  { id: 'LAZARUS', name: 'LAZARUS', color: 'text-orange-400' },
  { id: 'SHEPHERD', name: 'SHEPHERD', color: 'text-green-400' },
  { id: 'ORACLE', name: 'ORACLE', color: 'text-purple-400' },
]

const DECISION_TYPES = [
  { id: 'all', name: 'All Types' },
  { id: 'ENTRY', name: 'Entry' },
  { id: 'EXIT', name: 'Exit' },
  { id: 'SKIP', name: 'Skip' },
  { id: 'ADJUSTMENT', name: 'Adjustment' },
]

const OUTCOMES = [
  { id: 'all', name: 'All Outcomes' },
  { id: 'profit', name: 'Profitable', icon: TrendingUp, color: 'text-green-400' },
  { id: 'loss', name: 'Loss', icon: TrendingDown, color: 'text-red-400' },
  { id: 'pending', name: 'Pending', icon: Clock, color: 'text-yellow-400' },
]

const CONFIDENCE_LEVELS = [
  { id: 'all', name: 'All Confidence' },
  { id: 'HIGH', name: 'High' },
  { id: 'MEDIUM', name: 'Medium' },
  { id: 'LOW', name: 'Low' },
]

export default function DecisionFilterPanel({
  filters,
  onFiltersChange,
  onExport,
  isExporting = false,
  className = ''
}: DecisionFilterPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const updateFilter = (key: keyof FilterState, value: string) => {
    onFiltersChange({ ...filters, [key]: value })
  }

  const clearFilters = () => {
    onFiltersChange({
      bot: 'all',
      decisionType: 'all',
      outcome: 'all',
      startDate: '',
      endDate: '',
      search: '',
      confidenceLevel: 'all'
    })
  }

  const hasActiveFilters =
    filters.bot !== 'all' ||
    filters.decisionType !== 'all' ||
    filters.outcome !== 'all' ||
    filters.startDate ||
    filters.endDate ||
    filters.search ||
    filters.confidenceLevel !== 'all'

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
      {/* Quick Filters Bar */}
      <div className="p-4 flex flex-wrap items-center gap-4">
        {/* Search */}
        <div className="flex-1 min-w-[200px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search reasoning, notes..."
              value={filters.search}
              onChange={(e) => updateFilter('search', e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Bot Filter */}
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-gray-400" />
          <select
            value={filters.bot}
            onChange={(e) => updateFilter('bot', e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          >
            {BOTS.map(bot => (
              <option key={bot.id} value={bot.id}>{bot.name}</option>
            ))}
          </select>
        </div>

        {/* Date Range */}
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-400" />
          <input
            type="date"
            value={filters.startDate}
            onChange={(e) => updateFilter('startDate', e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          />
          <span className="text-gray-500">to</span>
          <input
            type="date"
            value={filters.endDate}
            onChange={(e) => updateFilter('endDate', e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* More Filters Toggle */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`flex items-center gap-2 px-3 py-2 rounded text-sm ${
            isExpanded || hasActiveFilters
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          <Filter className="w-4 h-4" />
          <span>{isExpanded ? 'Hide Filters' : 'More Filters'}</span>
          {hasActiveFilters && !isExpanded && (
            <span className="w-2 h-2 bg-blue-400 rounded-full" />
          )}
        </button>

        {/* Export Buttons */}
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={() => onExport('csv')}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-medium disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            CSV
          </button>
          <button
            onClick={() => onExport('json')}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            JSON
          </button>
          <button
            onClick={() => onExport('excel')}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded text-sm font-medium disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Excel
          </button>
        </div>
      </div>

      {/* Expanded Filters */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-700 pt-4">
          <div className="flex flex-wrap items-center gap-6">
            {/* Decision Type */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">Decision Type:</span>
              <div className="flex gap-1">
                {DECISION_TYPES.map(type => (
                  <button
                    key={type.id}
                    onClick={() => updateFilter('decisionType', type.id)}
                    className={`px-3 py-1 rounded text-sm ${
                      filters.decisionType === type.id
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {type.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Outcome */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">Outcome:</span>
              <div className="flex gap-1">
                {OUTCOMES.map(outcome => (
                  <button
                    key={outcome.id}
                    onClick={() => updateFilter('outcome', outcome.id)}
                    className={`px-3 py-1 rounded text-sm flex items-center gap-1 ${
                      filters.outcome === outcome.id
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {outcome.icon && <outcome.icon className={`w-3 h-3 ${outcome.color}`} />}
                    {outcome.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Confidence Level */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">AI Confidence:</span>
              <select
                value={filters.confidenceLevel}
                onChange={(e) => updateFilter('confidenceLevel', e.target.value)}
                className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {CONFIDENCE_LEVELS.map(level => (
                  <option key={level.id} value={level.id}>{level.name}</option>
                ))}
              </select>
            </div>

            {/* Clear Filters */}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="flex items-center gap-1 px-3 py-1 text-sm text-red-400 hover:text-red-300"
              >
                <X className="w-4 h-4" />
                Clear all filters
              </button>
            )}
          </div>
        </div>
      )}

      {/* Active Filters Summary */}
      {hasActiveFilters && !isExpanded && (
        <div className="px-4 pb-3 flex flex-wrap gap-2">
          {filters.bot !== 'all' && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-900/30 text-blue-300 rounded text-xs">
              Bot: {filters.bot}
              <button onClick={() => updateFilter('bot', 'all')} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
          {filters.decisionType !== 'all' && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-purple-900/30 text-purple-300 rounded text-xs">
              Type: {filters.decisionType}
              <button onClick={() => updateFilter('decisionType', 'all')} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
          {filters.outcome !== 'all' && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/30 text-green-300 rounded text-xs">
              Outcome: {filters.outcome}
              <button onClick={() => updateFilter('outcome', 'all')} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
          {(filters.startDate || filters.endDate) && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-900/30 text-yellow-300 rounded text-xs">
              Date: {filters.startDate || '...'} to {filters.endDate || '...'}
              <button onClick={() => { updateFilter('startDate', ''); updateFilter('endDate', ''); }} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
          {filters.search && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-700 text-gray-300 rounded text-xs">
              Search: &quot;{filters.search.substring(0, 20)}...&quot;
              <button onClick={() => updateFilter('search', '')} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
