'use client'

import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import { Sun, BookOpen, TrendingUp, Heart, MessageCircle, Sparkles } from 'lucide-react'

// Skeleton component for shimmer effect
function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-gray-700/50 rounded ${className}`} />
  )
}

export default function DailyMannaLoading() {
  const sidebarPadding = useSidebarPadding()

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className={`pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="flex items-center justify-center space-x-3 mb-4">
              <Sun className="w-10 h-10 text-amber-400" />
              <h1 className="text-3xl font-bold text-text-primary">Daily Manna</h1>
              <BookOpen className="w-10 h-10 text-amber-400" />
            </div>
            <Skeleton className="h-6 w-48 mx-auto mb-2" />
            <p className="text-text-muted italic">Where faith meets finance</p>

            {/* Action Buttons skeleton */}
            <div className="flex items-center justify-center gap-2 mt-4">
              <Skeleton className="h-10 w-24" />
              <Skeleton className="h-10 w-20" />
              <Skeleton className="h-10 w-20" />
              <Skeleton className="h-10 w-24" />
            </div>
          </div>

          <div className="space-y-6">
            {/* Theme Banner skeleton */}
            <div className="bg-gradient-to-r from-amber-500/20 via-amber-400/10 to-amber-500/20 border border-amber-500/30 rounded-lg p-4 text-center">
              <div className="flex items-center justify-center space-x-2">
                <Sparkles className="w-5 h-5 text-amber-400" />
                <Skeleton className="h-6 w-64" />
                <Sparkles className="w-5 h-5 text-amber-400" />
              </div>
            </div>

            {/* Key Insight skeleton */}
            <div className="bg-primary/10 border border-primary/30 rounded-lg p-4">
              <div className="flex items-start space-x-3">
                <Skeleton className="w-6 h-6 flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              </div>
            </div>

            {/* Scriptures skeleton */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <BookOpen className="w-6 h-6 text-amber-400" />
                <h2 className="text-xl font-semibold">Today's Scriptures</h2>
              </div>
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4">
                    <div className="flex items-start space-x-3">
                      <Skeleton className="w-8 h-8 rounded-full flex-shrink-0" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-5/6" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Financial Headlines skeleton */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <TrendingUp className="w-6 h-6 text-primary" />
                <h2 className="text-xl font-semibold">Today's Financial Headlines</h2>
              </div>
              <Skeleton className="h-4 w-48 mb-4" />
              <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-background-hover rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Skeleton className="h-5 w-24" />
                      <Skeleton className="h-5 w-20" />
                      <Skeleton className="h-5 w-28" />
                    </div>
                    <Skeleton className="h-5 w-full mb-2" />
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-4/5" />
                  </div>
                ))}
              </div>
            </div>

            {/* Bible Study skeleton */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <Sparkles className="w-6 h-6 text-amber-400" />
                <h2 className="text-xl font-semibold">Today's Bible Study</h2>
              </div>
              <div className="space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
              </div>
            </div>

            {/* Morning Prayer skeleton */}
            <div className="card bg-gradient-to-br from-purple-900/20 to-indigo-900/20 border-purple-500/30">
              <div className="flex items-center space-x-2 mb-4">
                <Heart className="w-6 h-6 text-purple-400" />
                <h2 className="text-xl font-semibold">Morning Prayer</h2>
              </div>
              <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6">
                <div className="space-y-3">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-11/12" />
                  <Skeleton className="h-4 w-3/4 mx-auto" />
                </div>
                <Skeleton className="h-5 w-16 mx-auto mt-4" />
              </div>
            </div>

            {/* Reflection Questions skeleton */}
            <div className="card">
              <div className="flex items-center space-x-2 mb-4">
                <MessageCircle className="w-6 h-6 text-success" />
                <h2 className="text-xl font-semibold">Reflection Questions</h2>
              </div>
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-start space-x-3 p-3 bg-success/5 border border-success/20 rounded-lg">
                    <Skeleton className="w-6 h-6 rounded-full flex-shrink-0" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-4 w-4/5" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
