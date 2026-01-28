'use client'

import { useSidebar } from '@/contexts/SidebarContext'

/**
 * Hook that returns the appropriate padding class for main content
 * based on the current sidebar state.
 *
 * Usage:
 * ```tsx
 * const sidebarPadding = useSidebarPadding()
 * return <main className={`pt-24 ${sidebarPadding}`}>...</main>
 * ```
 *
 * Returns:
 * - 'lg:pl-72' when sidebar is expanded (256px + 32px gap = 288px ≈ 18rem = pl-72)
 * - 'lg:pl-24' when sidebar is collapsed (64px + 32px gap = 96px = 6rem = pl-24)
 */
export function useSidebarPadding(): string {
  const { isExpanded } = useSidebar()
  return isExpanded ? 'lg:pl-72' : 'lg:pl-24'
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
