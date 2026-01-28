'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import Link from 'next/link'
import { apiClient } from '@/lib/api'
import {
  BookOpen,
  Calendar,
  ChevronLeft,
  Clock,
  Sparkles,
  ArrowLeft,
  FileText
} from 'lucide-react'

interface ArchiveItem {
  date: string
  theme: string
  key_insight: string
  scriptures: string[]
  news_count: number
  archived_at: string
}

export default function DailyMannaArchivePage() {
  const sidebarPadding = useSidebarPadding()
  const [archive, setArchive] = useState<ArchiveItem[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    fetchArchive()
  }, [])

  const fetchArchive = async () => {
    try {
      setLoading(true)
      const response = await apiClient.getDailyMannaArchive(30)
      if (response.data.success) {
        setArchive(response.data.data.archive || [])
        setTotal(response.data.data.total || 0)
      }
    } catch (err) {
      console.error('Error fetching archive:', err)
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr)
      return new Intl.DateTimeFormat('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      }).format(date)
    } catch {
      return dateStr
    }
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="mb-8">
            <Link
              href="/daily-manna"
              className="inline-flex items-center text-text-secondary hover:text-primary transition-colors mb-4"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Today&apos;s Manna
            </Link>

            <div className="flex items-center space-x-3">
              <Calendar className="w-10 h-10 text-amber-400" />
              <div>
                <h1 className="text-3xl font-bold text-text-primary">Daily Manna Archive</h1>
                <p className="text-text-secondary">
                  {total} devotionals saved • Review past reflections
                </p>
              </div>
            </div>
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-16">
              <BookOpen className="w-12 h-12 text-amber-400 animate-pulse mb-4" />
              <p className="text-text-secondary">Loading archive...</p>
            </div>
          ) : archive.length === 0 ? (
            <div className="card text-center py-16">
              <FileText className="w-16 h-16 text-text-muted mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-text-primary mb-2">No Archive Yet</h2>
              <p className="text-text-secondary mb-4">
                Devotionals will be saved here as you view them each day.
              </p>
              <Link
                href="/daily-manna"
                className="btn-primary inline-flex items-center"
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Get Today&apos;s Manna
              </Link>
            </div>
          ) : (
            <div className="space-y-4">
              {archive.map((item) => (
                <Link
                  key={item.date}
                  href={`/daily-manna?date=${item.date}`}
                  className="card block hover:border-amber-500/50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <Calendar className="w-5 h-5 text-amber-400" />
                        <span className="font-semibold text-text-primary">
                          {formatDate(item.date)}
                        </span>
                      </div>

                      {item.theme && (
                        <div className="flex items-center space-x-2 mb-2">
                          <Sparkles className="w-4 h-4 text-amber-400" />
                          <span className="text-amber-400 font-medium">{item.theme}</span>
                        </div>
                      )}

                      {item.key_insight && (
                        <p className="text-text-secondary text-sm italic mb-2">
                          &ldquo;{item.key_insight}&rdquo;
                        </p>
                      )}

                      <div className="flex items-center space-x-4 text-xs text-text-muted">
                        {item.scriptures && item.scriptures.length > 0 && (
                          <span>
                            <BookOpen className="w-3 h-3 inline mr-1" />
                            {item.scriptures.join(', ')}
                          </span>
                        )}
                        {item.news_count > 0 && (
                          <span>{item.news_count} headlines</span>
                        )}
                      </div>
                    </div>

                    <ChevronLeft className="w-5 h-5 text-text-muted rotate-180" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
