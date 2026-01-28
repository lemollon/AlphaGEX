'use client'

import { ReactNode } from 'react'
import Navigation from './Navigation'
import { useSidebar } from '@/contexts/SidebarContext'

interface PageLayoutProps {
  children: ReactNode
  /** Additional classes to apply to the main content area */
  className?: string
  /** Whether to apply max-width constraint (default: true) */
  constrained?: boolean
  /** Custom max-width class (default: max-w-7xl) */
  maxWidth?: string
}

/**
 * PageLayout - Consistent page wrapper that handles sidebar offset
 *
 * This component ensures all pages properly account for the sidebar width,
 * preventing content from being cut off or overlapped by the navigation.
 *
 * Usage:
 * ```tsx
 * export default function MyPage() {
 *   return (
 *     <PageLayout>
 *       <h1>My Page Content</h1>
 *     </PageLayout>
 *   )
 * }
 * ```
 */
export default function PageLayout({
  children,
  className = '',
  constrained = true,
  maxWidth = 'max-w-7xl'
}: PageLayoutProps) {
  const { isExpanded } = useSidebar()

  return (
    <>
      <Navigation />
      <main
        className={`
          min-h-screen pt-24 pb-8 px-4 sm:px-6 lg:px-8
          transition-all duration-300 ease-in-out
          ${isExpanded ? 'lg:pl-72' : 'lg:pl-24'}
          ${className}
        `}
      >
        {constrained ? (
          <div className={`${maxWidth} mx-auto`}>
            {children}
          </div>
        ) : (
          children
        )}
      </main>
    </>
  )
}

/**
 * PageLayoutUnconstrained - For pages that need full-width content
 *
 * Same as PageLayout but without the max-width constraint.
 */
export function PageLayoutUnconstrained({
  children,
  className = ''
}: Omit<PageLayoutProps, 'constrained' | 'maxWidth'>) {
  return (
    <PageLayout className={className} constrained={false}>
      {children}
    </PageLayout>
  )
}
