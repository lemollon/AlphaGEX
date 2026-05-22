'use client'

import { useState, useRef, useEffect } from 'react'

interface InfoTipProps {
  text: string
}

export default function InfoTip({ text }: InfoTipProps) {
  const [open, setOpen] = useState(false)
  const [above, setAbove] = useState(false)
  const [alignRight, setAlignRight] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open || !ref.current || !tooltipRef.current) return
    const anchor = ref.current.getBoundingClientRect()
    const tip = tooltipRef.current.getBoundingClientRect()
    // Flip above if not enough space below
    setAbove(anchor.bottom + tip.height + 8 > window.innerHeight)
    // Align right if tooltip would clip the right edge
    setAlignRight(anchor.left + tip.width + 8 > window.innerWidth)
  }, [open])

  return (
    <span
      ref={ref}
      className="relative inline-flex items-center ml-1 align-middle"
      tabIndex={0}
      role="button"
      aria-label="More information"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {/* Info glyph — "i" in a circle */}
      <svg
        width="13"
        height="13"
        viewBox="0 0 13 13"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="text-forge-muted hover:text-amber-400 focus:text-amber-400 transition-colors cursor-help"
        aria-hidden="true"
      >
        <circle cx="6.5" cy="6.5" r="5.75" stroke="currentColor" strokeWidth="1.2" />
        {/* dot */}
        <circle cx="6.5" cy="4" r="0.7" fill="currentColor" />
        {/* stem */}
        <path d="M6.5 5.8v3.4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>

      {/* Tooltip popover */}
      {open && (
        <div
          ref={tooltipRef}
          role="tooltip"
          className={`
            absolute z-50 max-w-[260px] w-max
            rounded-lg border border-forge-border bg-[#1c1917] shadow-xl
            px-3 py-2 text-xs text-gray-300 leading-relaxed
            pointer-events-none
            ${above ? 'bottom-full mb-2' : 'top-full mt-2'}
            ${alignRight ? 'right-0' : 'left-0'}
          `}
          style={{ minWidth: '180px' }}
        >
          {text}
          {/* Small arrow caret */}
          <span
            className={`
              absolute left-3 border-4 border-transparent
              ${above
                ? 'top-full border-t-[#292524]'
                : 'bottom-full border-b-[#292524]'}
            `}
          />
        </div>
      )}
    </span>
  )
}
