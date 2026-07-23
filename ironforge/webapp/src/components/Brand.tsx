/* Shared IronForge brand mark — the official IF logo (raster asset). */

export function IFMark({ className = 'h-8 w-auto' }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/ironforge-mark.png" alt="IronForge" className={className} />
}

/**
 * The one IronForge wordmark — [IF mark] IRONFORGE, IRON white + FORGE brand-orange
 * (#FD5301, matching the marketing accent), bold uppercase. This is the single source
 * of truth: every nav renders THIS so the logo can't drift between pages. Matches the
 * approved logo lockup exactly — do not reintroduce the amber-yellow FORGE or a second
 * mark image.
 */
export function Wordmark({ markClass = 'h-7 w-auto', textClass = 'text-xl' }: { markClass?: string; textClass?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <IFMark className={markClass} />
      <span className={`${textClass} font-bold uppercase tracking-tight`}>
        <span className="text-white">IRON</span>
        <span className="text-[#FD5301]">FORGE</span>
      </span>
    </div>
  )
}
