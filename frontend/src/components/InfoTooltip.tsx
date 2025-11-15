'use client'

import { HelpCircle } from 'lucide-react'
import { useState } from 'react'

interface InfoTooltipProps {
  content: string
  className?: string
}

export default function InfoTooltip({ content, className = '' }: InfoTooltipProps) {
  const [isVisible, setIsVisible] = useState(false)

  return (
    <div className="relative inline-block">
      <button
        className={`text-gray-400 hover:text-gray-300 transition-colors ${className}`}
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        onClick={(e) => {
          e.preventDefault()
          setIsVisible(!isVisible)
        }}
      >
        <HelpCircle className="w-4 h-4" />
      </button>

      {isVisible && (
        <div className="absolute z-50 w-64 p-3 bg-gray-800 border border-gray-700 rounded-lg shadow-xl text-sm text-gray-200 bottom-full left-1/2 transform -translate-x-1/2 mb-2">
          <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
            <div className="border-8 border-transparent border-t-gray-800" />
          </div>
          {content}
        </div>
      )}
    </div>
  )
}
