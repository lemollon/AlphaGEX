'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

interface SidebarContextType {
  isPinned: boolean
  setIsPinned: (pinned: boolean) => void
  isHovered: boolean
  setIsHovered: (hovered: boolean) => void
  isExpanded: boolean
  sidebarWidth: number // in pixels
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined)

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [isPinned, setIsPinnedState] = useState(false)
  const [isHovered, setIsHovered] = useState(false)

  // Load pinned state from localStorage on mount
  useEffect(() => {
    const savedPinned = localStorage.getItem('sidebarPinned')
    if (savedPinned !== null) {
      setIsPinnedState(savedPinned === 'true')
    }
  }, [])

  // Save pinned state to localStorage
  const setIsPinned = (pinned: boolean) => {
    setIsPinnedState(pinned)
    localStorage.setItem('sidebarPinned', String(pinned))
  }

  // Sidebar is expanded when pinned OR hovered
  const isExpanded = isPinned || isHovered

  // Sidebar width in pixels: 64px collapsed, 256px expanded
  const sidebarWidth = isExpanded ? 256 : 64

  return (
    <SidebarContext.Provider
      value={{
        isPinned,
        setIsPinned,
        isHovered,
        setIsHovered,
        isExpanded,
        sidebarWidth,
      }}
    >
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  const context = useContext(SidebarContext)
  if (context === undefined) {
    throw new Error('useSidebar must be used within a SidebarProvider')
  }
  return context
}
