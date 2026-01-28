'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { apiClient } from '@/lib/api'
import { useDailyManna, useDailyMannaComments } from '@/lib/hooks/useMarketData'
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
  MessageCircle,
  Share2,
  Printer,
  Archive,
  Send,
  ThumbsUp,
  CheckCircle,
  PenLine
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
  source?: string
  url?: string
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
  news_sources?: string[]
}

interface Comment {
  id: number
  user_name: string
  comment: string
  created_at: string
  likes: number
}

export default function DailyMannaPage() {
  const sidebarPadding = useSidebarPadding()
  // SWR hooks for data fetching with caching
  const { data: mannaResponse, error: mannaError, isLoading, mutate: refreshManna } = useDailyManna()
  const { data: commentsResponse, mutate: refreshComments } = useDailyMannaComments()

  // Extract data from SWR responses
  const data = mannaResponse?.success ? mannaResponse.data : null
  const comments = commentsResponse?.success ? (commentsResponse.data?.comments || []) : []
  const error = mannaError ? 'Unable to connect to the server. Please try again.' :
                (!mannaResponse?.success && mannaResponse ? 'Failed to load Daily Manna content' : null)

  const [refreshing, setRefreshing] = useState(false)
  const [expandedSections, setExpandedSections] = useState({
    news: true,
    scriptures: true,
    study: true,
    prayer: true,
    reflection: true,
    comments: false,
    myNotes: false
  })

  // Comments state
  const [newComment, setNewComment] = useState('')
  const [userName, setUserName] = useState('')
  const [submittingComment, setSubmittingComment] = useState(false)

  // Personal reflection state
  const [myReflection, setMyReflection] = useState('')
  const [savingReflection, setSavingReflection] = useState(false)
  const [reflectionSaved, setReflectionSaved] = useState(false)

  useEffect(() => {
    // Load saved user name from localStorage
    const savedName = localStorage.getItem('dailyMannaUserName')
    if (savedName) setUserName(savedName)
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      // Force refresh by making a direct API call with force_refresh=true
      const response = await apiClient.getDailyManna(true)
      if (response.data.success) {
        // Update the SWR cache with the new data
        refreshManna(response.data, false)
      }
    } catch (err) {
      logger.error('Error refreshing Daily Manna:', err)
    } finally {
      setRefreshing(false)
    }
  }

  const handleSubmitComment = async () => {
    if (!newComment.trim()) return

    setSubmittingComment(true)
    try {
      const name = userName.trim() || 'Anonymous'
      // Save user name for next time
      if (userName.trim()) {
        localStorage.setItem('dailyMannaUserName', userName.trim())
      }

      const response = await apiClient.addDailyMannaComment({
        user_name: name,
        comment: newComment.trim()
      })

      if (response.data.success) {
        setNewComment('')
        refreshComments() // Use SWR mutate instead of manual fetch
      }
    } catch (err) {
      logger.error('Error submitting comment:', err)
    } finally {
      setSubmittingComment(false)
    }
  }

  const handleLikeComment = async (commentId: number) => {
    try {
      await apiClient.likeDailyMannaComment(commentId)
      refreshComments() // Use SWR mutate instead of manual fetch
    } catch (err) {
      logger.error('Error liking comment:', err)
    }
  }

  const handleSaveReflection = async () => {
    if (!myReflection.trim()) return

    setSavingReflection(true)
    try {
      const response = await apiClient.saveDailyMannaReflection({
        reflection: myReflection.trim()
      })

      if (response.data.success) {
        setReflectionSaved(true)
        setTimeout(() => setReflectionSaved(false), 3000)
      }
    } catch (err) {
      logger.error('Error saving reflection:', err)
    } finally {
      setSavingReflection(false)
    }
  }

  const handleShare = async () => {
    if (!data) return

    const shareText = `Daily Manna - ${data.date}\n\n` +
      `Theme: ${data.devotional?.theme}\n\n` +
      `"${data.devotional?.key_insight}"\n\n` +
      `Scripture: ${data.scriptures?.[0]?.reference}\n` +
      `"${data.scriptures?.[0]?.text}"`

    if (navigator.share) {
      try {
        await navigator.share({
          title: 'Daily Manna Devotional',
          text: shareText
        })
      } catch (err) {
        // User cancelled or error
      }
    } else {
      // Fallback: copy to clipboard
      navigator.clipboard.writeText(shareText)
      alert('Devotional copied to clipboard!')
    }
  }

  const handlePrint = () => {
    window.print()
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

  const formatTime = (timestamp: string) => {
    try {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      }).format(new Date(timestamp))
    } catch {
      return timestamp
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen">
        <Navigation />
        <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
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
    <div className="min-h-screen print:bg-white">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="text-center mb-8 print:mb-4">
            <div className="flex items-center justify-center space-x-3 mb-4">
              <Sun className="w-10 h-10 text-amber-400" />
              <h1 className="text-3xl font-bold text-text-primary print:text-black">Daily Manna</h1>
              <BookOpen className="w-10 h-10 text-amber-400" />
            </div>
            <p className="text-lg text-text-secondary mb-2 print:text-gray-600">
              {data?.date || 'Loading...'}
            </p>
            <p className="text-text-muted italic print:text-gray-500">
              {data?.greeting || 'Where faith meets finance'}
            </p>

            {/* Action Buttons */}
            <div className="flex items-center justify-center gap-2 mt-4 print:hidden">
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="btn-secondary inline-flex items-center space-x-2"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
              </button>
              <button
                onClick={handleShare}
                className="btn-secondary inline-flex items-center space-x-2"
              >
                <Share2 className="w-4 h-4" />
                <span>Share</span>
              </button>
              <button
                onClick={handlePrint}
                className="btn-secondary inline-flex items-center space-x-2"
              >
                <Printer className="w-4 h-4" />
                <span>Print</span>
              </button>
              <a
                href="/daily-manna/archive"
                className="btn-secondary inline-flex items-center space-x-2"
              >
                <Archive className="w-4 h-4" />
                <span>Archive</span>
              </a>
            </div>
          </div>

          {error && (
            <div className="bg-danger/10 border border-danger/30 rounded-lg p-4 mb-6 print:hidden">
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
                  className="w-full flex items-center justify-between mb-4 print:pointer-events-none"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <BookOpen className="w-6 h-6 text-amber-400" />
                    <span>Today&apos;s Scriptures</span>
                  </h2>
                  <span className="print:hidden">
                    {expandedSections.scriptures ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </span>
                </button>

                {expandedSections.scriptures && (
                  <div className="space-y-4">
                    {data.scriptures?.map((scripture: Scripture, index: number) => (
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
                            <p className="text-text-primary italic print:text-black">&ldquo;{scripture.text}&rdquo;</p>
                            <p className="text-xs text-text-muted mt-2">Theme: {scripture.theme}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Today's Financial Headlines */}
              <div className="card print:break-before-page">
                <button
                  onClick={() => toggleSection('news')}
                  className="w-full flex items-center justify-between mb-4 print:pointer-events-none"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <TrendingUp className="w-6 h-6 text-primary" />
                    <span>Today&apos;s Financial Headlines</span>
                  </h2>
                  <span className="print:hidden">
                    {expandedSections.news ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </span>
                </button>

                {expandedSections.news && (
                  <>
                    {data.news_sources && data.news_sources.length > 0 && (
                      <div className="mb-4 text-xs text-text-muted">
                        Sources: {data.news_sources.join(' • ')}
                      </div>
                    )}
                    <div className="space-y-3">
                      {data.news?.map((item: NewsItem, index: number) => (
                        <div
                          key={index}
                          className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center flex-wrap gap-2 mb-2">
                                <span className="text-xs px-2 py-0.5 bg-primary/20 text-primary rounded">
                                  {item.category}
                                </span>
                                {item.source && (
                                  <span className="text-xs px-2 py-0.5 bg-gray-700 text-text-secondary rounded">
                                    {item.source}
                                  </span>
                                )}
                                <span className={`text-xs ${getImpactColor(item.impact)}`}>
                                  {item.impact?.toUpperCase()} IMPACT
                                </span>
                              </div>
                              {item.url ? (
                                <a
                                  href={item.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="font-medium text-text-primary hover:text-primary transition-colors block mb-1 print:text-black"
                                >
                                  {item.headline}
                                </a>
                              ) : (
                                <h3 className="font-medium text-text-primary mb-1 print:text-black">{item.headline}</h3>
                              )}
                              {item.summary && (
                                <p className="text-sm text-text-secondary print:text-gray-600">{item.summary}</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Bible Study */}
              <div className="card">
                <button
                  onClick={() => toggleSection('study')}
                  className="w-full flex items-center justify-between mb-4 print:pointer-events-none"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <Sparkles className="w-6 h-6 text-amber-400" />
                    <span>Today&apos;s Bible Study</span>
                  </h2>
                  <span className="print:hidden">
                    {expandedSections.study ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </span>
                </button>

                {expandedSections.study && (
                  <div className="prose prose-invert max-w-none print:prose-gray">
                    <div className="text-text-primary whitespace-pre-wrap leading-relaxed print:text-black">
                      {data.devotional?.bible_study}
                    </div>
                  </div>
                )}
              </div>

              {/* Morning Prayer */}
              <div className="card bg-gradient-to-br from-purple-900/20 to-indigo-900/20 border-purple-500/30 print:bg-gray-100">
                <button
                  onClick={() => toggleSection('prayer')}
                  className="w-full flex items-center justify-between mb-4 print:pointer-events-none"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <Heart className="w-6 h-6 text-purple-400" />
                    <span>Morning Prayer</span>
                  </h2>
                  <span className="print:hidden">
                    {expandedSections.prayer ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </span>
                </button>

                {expandedSections.prayer && (
                  <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 print:bg-gray-50">
                    <p className="text-text-primary italic leading-relaxed text-center print:text-black">
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
                  className="w-full flex items-center justify-between mb-4 print:pointer-events-none"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <MessageCircle className="w-6 h-6 text-success" />
                    <span>Reflection Questions</span>
                  </h2>
                  <span className="print:hidden">
                    {expandedSections.reflection ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </span>
                </button>

                {expandedSections.reflection && (
                  <div className="space-y-3">
                    {data.devotional?.reflection_questions?.map((question: string, index: number) => (
                      <div
                        key={index}
                        className="flex items-start space-x-3 p-3 bg-success/5 border border-success/20 rounded-lg"
                      >
                        <div className="w-6 h-6 rounded-full bg-success/20 flex items-center justify-center flex-shrink-0">
                          <span className="text-success font-bold text-sm">{index + 1}</span>
                        </div>
                        <p className="text-text-primary print:text-black">{question}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Personal Notes Section */}
              <div className="card print:hidden">
                <button
                  onClick={() => toggleSection('myNotes')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <PenLine className="w-6 h-6 text-blue-400" />
                    <span>My Reflection</span>
                    {reflectionSaved && (
                      <span className="text-sm text-success flex items-center">
                        <CheckCircle className="w-4 h-4 mr-1" /> Saved
                      </span>
                    )}
                  </h2>
                  {expandedSections.myNotes ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.myNotes && (
                  <div className="space-y-4">
                    <textarea
                      value={myReflection}
                      onChange={(e) => setMyReflection(e.target.value)}
                      placeholder="Write your personal thoughts and reflections on today's devotional..."
                      className="w-full h-32 px-4 py-3 bg-background-deep border border-gray-700 rounded-lg text-text-primary resize-none focus:outline-none focus:border-blue-500"
                    />
                    <div className="flex justify-between items-center">
                      <p className="text-xs text-text-muted">
                        Your reflections are saved and can be reviewed later
                      </p>
                      <button
                        onClick={handleSaveReflection}
                        disabled={savingReflection || !myReflection.trim()}
                        className="btn-primary disabled:opacity-50"
                      >
                        {savingReflection ? 'Saving...' : 'Save Reflection'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Community Comments Section */}
              <div className="card print:hidden">
                <button
                  onClick={() => toggleSection('comments')}
                  className="w-full flex items-center justify-between mb-4"
                >
                  <h2 className="text-xl font-semibold flex items-center space-x-2">
                    <MessageCircle className="w-6 h-6 text-cyan-400" />
                    <span>Community Discussion</span>
                    <span className="text-sm text-text-muted">({comments.length})</span>
                  </h2>
                  {expandedSections.comments ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                </button>

                {expandedSections.comments && (
                  <div className="space-y-4">
                    {/* Add Comment Form */}
                    <div className="bg-background-hover rounded-lg p-4">
                      <div className="flex gap-3 mb-3">
                        <input
                          type="text"
                          value={userName}
                          onChange={(e) => setUserName(e.target.value)}
                          placeholder="Your name"
                          className="flex-shrink-0 w-32 px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary text-sm focus:outline-none focus:border-cyan-500"
                        />
                        <input
                          type="text"
                          value={newComment}
                          onChange={(e) => setNewComment(e.target.value)}
                          placeholder="Share your thoughts on today's devotional..."
                          className="flex-1 px-3 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary text-sm focus:outline-none focus:border-cyan-500"
                          onKeyPress={(e) => e.key === 'Enter' && handleSubmitComment()}
                        />
                        <button
                          onClick={handleSubmitComment}
                          disabled={submittingComment || !newComment.trim()}
                          className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50 transition-colors"
                        >
                          <Send className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Comments List */}
                    {comments.length === 0 ? (
                      <div className="text-center py-8 text-text-muted">
                        <MessageCircle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                        <p>Be the first to share your thoughts!</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {comments.map((comment: Comment) => (
                          <div
                            key={comment.id}
                            className="bg-background-hover rounded-lg p-4"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 mb-1">
                                  <span className="font-medium text-cyan-400">{comment.user_name}</span>
                                  <span className="text-xs text-text-muted">
                                    {formatTime(comment.created_at)}
                                  </span>
                                </div>
                                <p className="text-text-primary text-sm">{comment.comment}</p>
                              </div>
                              <button
                                onClick={() => handleLikeComment(comment.id)}
                                className="flex items-center space-x-1 text-text-muted hover:text-pink-400 transition-colors"
                              >
                                <ThumbsUp className="w-4 h-4" />
                                {comment.likes > 0 && <span className="text-xs">{comment.likes}</span>}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="text-center py-6 border-t border-gray-800 print:border-gray-300">
                <p className="text-text-muted text-sm print:text-gray-500">
                  <Clock className="w-4 h-4 inline mr-1" />
                  Generated at {new Date(data.timestamp).toLocaleTimeString()}
                </p>
                <p className="text-text-secondary mt-2 italic print:text-gray-600">
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
