'use client'

import { useSidebar } from '@/contexts/SidebarContext'

/**
 * Hook that returns the appropriate padding class for main content
 * based on the current sidebar state.
 *
 * The persistent left rail has been removed site-wide (navigation now lives
 * in the top bar), so there's nothing left to reserve space for. Always
 * returns an empty string.
 *
 * Usage:
 * ```tsx
 * const sidebarPadding = useSidebarPadding()
 * return <main className={`pt-24 ${sidebarPadding}`}>...</main>
 * ```
 */
export function useSidebarPadding(): string {
  return ''
}

/**
 * Hook that returns both the padding class and the sidebar state
 * for components that need more control.
 */
export function useSidebarLayout() {
  const { isExpanded, isPinned, isHovered, sidebarWidth } = useSidebar()

  return {
    isExpanded,
    isPinned,
    isHovered,
    sidebarWidth,
    paddingClass: isExpanded ? 'lg:pl-72' : 'lg:pl-24',
    // For inline styles if needed
    paddingStyle: { paddingLeft: `${sidebarWidth + 32}px` } as const,
  }
}
