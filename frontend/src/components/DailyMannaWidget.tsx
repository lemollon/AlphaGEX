'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { apiClient } from '@/lib/api'
import { BookOpen, Sparkles, ArrowRight } from 'lucide-react'

interface WidgetData {
  date: string
  theme: string
  key_insight: string
  scripture: string
  has_content: boolean
}

export default function DailyMannaWidget() {
  const [data, setData] = useState<WidgetData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWidget()
  }, [])

  const fetchWidget = async () => {
    try {
      const response = await apiClient.getDailyMannaWidget()
      if (response.data.success) {
        setData(response.data.data)
      }
    } catch (err) {
      // Silently fail - widget is optional
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="card bg-gradient-to-r from-amber-500/10 to-orange-500/5 border-amber-500/30 animate-pulse">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <BookOpen className="w-6 h-6 text-amber-400" />
            <div className="h-5 bg-amber-500/20 rounded w-32"></div>
          </div>
        </div>
      </div>
    )
  }

  if (!data) return null

  return (
    <Link href="/daily-manna" className="block">
      <div className="card bg-gradient-to-r from-amber-500/10 via-amber-400/5 to-orange-500/10 border-amber-500/30 hover:border-amber-400/50 transition-all group">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center space-x-2 mb-2">
              <BookOpen className="w-5 h-5 text-amber-400" />
              <span className="font-semibold text-amber-400">Daily Manna</span>
              {data.theme && (
                <>
                  <span className="text-text-muted">•</span>
                  <span className="text-sm text-text-secondary flex items-center">
                    <Sparkles className="w-3 h-3 mr-1 text-amber-400" />
                    {data.theme}
                  </span>
                </>
              )}
            </div>

            {data.key_insight && (
              <p className="text-text-primary text-sm italic leading-relaxed">
                &ldquo;{data.key_insight}&rdquo;
              </p>
            )}

            {data.scripture && (
              <p className="text-xs text-text-muted mt-2">
                {data.scripture}
              </p>
            )}
          </div>

          <div className="flex items-center text-amber-400 group-hover:translate-x-1 transition-transform">
            <ArrowRight className="w-5 h-5" />
          </div>
        </div>
      </div>
    </Link>
  )
}
