/* Shared IronForge brand mark — angular blade "F" + slab-serif "I". */

export function IFMark({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} role="img" aria-label="IronForge">
      <defs>
        <linearGradient id="brand-f" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FB7A3D" />
          <stop offset="0.5" stopColor="#E8531F" />
          <stop offset="1" stopColor="#C2410C" />
        </linearGradient>
        <linearGradient id="brand-i" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.55" stopColor="#F5F5F4" />
          <stop offset="1" stopColor="#D6D3D1" />
        </linearGradient>
      </defs>
      <g fill="#7C2D0E" transform="translate(3.5,4)">
        <polygon points="54,28 76,28 76,92 54,92" />
        <polygon points="54,28 102,28 90,48 54,48" />
        <polygon points="54,56 88,56 76,74 54,74" />
      </g>
      <g fill="url(#brand-i)">
        <rect x="26" y="36" width="20" height="56" />
        <rect x="18" y="36" width="36" height="12" />
        <rect x="18" y="80" width="36" height="12" />
      </g>
      <g fill="url(#brand-f)">
        <polygon points="54,28 76,28 76,92 54,92" />
        <polygon points="54,28 102,28 90,48 54,48" />
        <polygon points="54,56 88,56 76,74 54,74" />
      </g>
      <polygon points="54,28 102,28 98,34 54,34" fill="#FB8B53" opacity="0.7" />
    </svg>
  )
}

export function Wordmark({ markClass = 'h-8 w-8', textClass = 'text-xl' }: { markClass?: string; textClass?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <IFMark className={markClass} />
      <span className={`${textClass} font-bold tracking-tight`}>
        <span className="text-white">IRON</span>
        <span className="text-amber-500">FORGE</span>
      </span>
    </div>
  )
}
