'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  BookOpen,
  Sun,
  Heart,
  RefreshCw,
  Clock,
  TrendingUp,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Quote,
  MessageCircle
} from 'lucide-react'

interface Scripture {
  reference: string
  text: string
  theme: string
}

interface NewsItem {
  headline: string
  summary: string
  category: string
  timestamp: string
  impact: string
}

interface Devotional {
  bible_study: string
  morning_prayer: string
  reflection_questions: string[]
  key_insight: string
  theme: string
}

interface DailyMannaData {
  devotional: Devotional
  scriptures: Scripture[]
  news: NewsItem[]
  date: string
  timestamp: string
  greeting: string
}

export default function DailyMannaPage() {
  const [data, setData] = useState<DailyMannaData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [expandedSections, setExpandedSections] = useState({
    news: true,
    scriptures: true,
    study: true,
    prayer: true,
    reflection: true
  })

  useEffect(() => {
    fetchDailyManna()
  }, [])

  const fetchDailyManna = async (forceRefresh = false) => {
    try {
      if (forceRefresh) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }
      setError(null)

      const response = await apiClient.getDailyManna(forceRefresh)

      if (response.data.success) {
        setData(response.data.data)
      } else {
        setError('Failed to load Daily Manna content')
      }
    } catch (err) {
      logger.error('Error fetching Daily Manna:', err)
      setError('Unable to connect to the server. Please try again.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'high': return 'text-danger'
      case 'medium': return 'text-warning'
      case 'low': return 'text-success'
      default: return 'text-text-secondary'
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navigation />
        <main className="pt-16 transition-all duration-300">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
              <div className="relative">
                <Sun className="w-16 h-16 text-amber-400 animate-pulse" />
                <Sparkles className="w-6 h-6 text-amber-300 absolute -top-1 -right-1 animate-bounce" />
              </div>
              <h2 className="text-xl font-semibold text-text-primary">Preparing Today&apos;s Manna...</h2>
              <p className="text-text-secondary text-center max-w-md">
                &ldquo;Give us this day our daily bread&rdquo; - Matthew 6:11
              </p>
              <div className="flex space-x-1 mt-4">
                <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-2 h-2 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="flex items-center justify-center space-x-3 mb-4">
              <Sun className="w-10 h-10 text-amber-400" />
              <h1 className="text-3xl font-bold text-text-primary">Daily Manna</h1>
              <BookOpen className="w-10 h-10 text-amber-400" />
            </div>
            <p className="text-lg text-text-secondary mb-2">
              {data?.date || 'Loading...'}
            </p>
            <p className="text-text-muted italic">
              {data?.greeting || 'Where faith meets finance'}
            </p>
            <button
              onClick={() => fetchDailyManna(true)}
              disabled={refreshing}
              className="mt-4 btn-secondary inline-flex items-center space-x-2"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span>{refreshing ? 'Refreshing...' : 'Refresh Content'}</span>
            </button>
          </div>

          {error && (
            <div className="bg-danger/10 border border-danger/30 rounded-lg p-4 mb-6">
              <div className="flex items-center space-x-2 text-danger">
                <AlertCircle className="w-5 h-5" />
                <span>{error}</span>
              </div>
            </div>
          )}

          {data && (
            <div className="space-y-6">
              {/* Theme Banner */}
              {data.devotional?.theme && (
                <div className="bg-gradient-to-r from-amber-500/20 via-amber-400/10 to-amber-500/20 border border-amber-500/30 rounded-lg p-4 text-center">
                  <div className="flex items-center justify-center space-x-2">
                    <Sparkles className="w-5 h-5 text-amber-400" />
                    <span className="text-lg font-semibold text-amber-400">Today&apos;s Theme: {data.devotional.theme}</span>
                    <Sparkles className="w-5 h-5 text-amber-400" />
                  </div>
                </div>
              )}

              {/* Key Insight */}
              {data.devotional?.key_insight && (
                <div className="bg-primary/10 border border-primary/30 rounded-lg p-4">
                  <div className="flex items-start space-x-3">
                    <Quote className="w-6 h-6 text-primary mt-1 flex-shrink-0" />
                    <p className="text-text-primary font-medium italic">
                      {data.devotional.key_insight}
                    </p>
                  </div>
                </div>
              )}

              {/* Today's Scriptures */}
              <div className="card">
                <button
                  onClick={() => toggleSection('scriptures')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <BookOpen className="w-6 h-6 text-amber-400" />
                    <span>Today&apos;s Scriptures</span>
                  </h2>
                  {expandedSections.scriptures ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.scriptures && (
                  <div className="space-y-4">
                    {data.scriptures?.map((scripture, index) => (
                      <div
                        key={index}
                        className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4"
                      >
                        <div className="flex items-start space-x-3">
                          <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                            <span className="text-amber-400 font-bold text-sm">{index + 1}</span>
                          </div>
                          <div>
                            <p className="font-semibold text-amber-400 mb-1">{scripture.reference}</p>
                            <p className="text-text-primary italic">&ldquo;{scripture.text}&rdquo;</p>
                            <p className="text-xs text-text-muted mt-2">Theme: {scripture.theme}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Market Context / Economic News */}
              <div className="card">
                <button
                  onClick={() => toggleSection('news')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <TrendingUp className="w-6 h-6 text-primary" />
                    <span>Today&apos;s Market Context</span>
                  </h2>
                  {expandedSections.news ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.news && (
                  <div className="space-y-3">
                    {data.news?.map((item, index) => (
                      <div
                        key={index}
                        className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center space-x-2 mb-1">
                              <span className="text-xs px-2 py-0.5 bg-primary/20 text-primary rounded">
                                {item.category}
                              </span>
                              <span className={`text-xs ${getImpactColor(item.impact)}`}>
                                {item.impact.toUpperCase()} IMPACT
                              </span>
                            </div>
                            <h3 className="font-medium text-text-primary mb-1">{item.headline}</h3>
                            <p className="text-sm text-text-secondary">{item.summary}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Bible Study */}
              <div className="card">
                <button
                  onClick={() => toggleSection('study')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <Sparkles className="w-6 h-6 text-amber-400" />
                    <span>Today&apos;s Bible Study</span>
                  </h2>
                  {expandedSections.study ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.study && (
                  <div className="prose prose-invert max-w-none">
                    <div className="text-text-primary whitespace-pre-wrap leading-relaxed">
                      {data.devotional?.bible_study}
                    </div>
                  </div>
                )}
              </div>

              {/* Morning Prayer */}
              <div className="card bg-gradient-to-br from-purple-900/20 to-indigo-900/20 border-purple-500/30">
                <button
                  onClick={() => toggleSection('prayer')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <Heart className="w-6 h-6 text-purple-400" />
                    <span>Morning Prayer</span>
                  </h2>
                  {expandedSections.prayer ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.prayer && (
                  <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6">
                    <p className="text-text-primary italic leading-relaxed text-center">
                      {data.devotional?.morning_prayer}
                    </p>
                    <p className="text-purple-400 text-center mt-4 font-semibold">Amen.</p>
                  </div>
                )}
              </div>

              {/* Reflection Questions */}
              <div className="card">
                <button
                  onClick={() => toggleSection('reflection')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <MessageCircle className="w-6 h-6 text-success" />
                    <span>Reflection Questions</span>
                  </h2>
                  {expandedSections.reflection ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.reflection && (
                  <div className="space-y-3">
                    {data.devotional?.reflection_questions?.map((question, index) => (
                      <div
                        key={index}
                        className="flex items-start space-x-3 p-3 bg-success/5 border border-success/20 rounded-lg"
                      >
                        <div className="w-6 h-6 rounded-full bg-success/20 flex items-center justify-center flex-shrink-0">
                          <span className="text-success font-bold text-sm">{index + 1}</span>
                        </div>
                        <p className="text-text-primary">{question}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="text-center py-6 border-t border-gray-800">
                <p className="text-text-muted text-sm">
                  <Clock className="w-4 h-4 inline mr-1" />
                  Generated at {new Date(data.timestamp).toLocaleTimeString()}
                </p>
                <p className="text-text-secondary mt-2 italic">
                  &ldquo;The Lord is my shepherd; I shall not want.&rdquo; - Psalm 23:1
                </p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
