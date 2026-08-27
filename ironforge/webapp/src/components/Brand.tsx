/* Shared IronForge brand mark — the official IF logo (raster asset). */

export function IFMark({ className = 'h-8 w-auto' }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/ironforge-mark.png" alt="IronForge" className={className} />
}

/**
 * The one IronForge wordmark — [IF mark] IRONFORGE, IRON white + FORGE brand-orange
 * (#EE5A24, matching the marketing accent), bold uppercase. This is the single source
 * of truth: every nav renders THIS so the logo can't drift between pages. Matches the
 * approved logo lockup exactly — do not reintroduce the amber-yellow FORGE or a second
 * mark image.
 *
 * `showMark={false}` renders the wordmark alone. The public marketing masthead
 * uses it because the approved homepage mock draws "IRONFORGE" with no mark;
 * every signed-in surface keeps the full lockup.
 */
export function Wordmark({
  markClass = 'h-7 w-auto',
  textClass = 'text-xl',
  showMark = true,
}: { markClass?: string; textClass?: string; showMark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      {showMark ? <IFMark className={markClass} /> : null}
      <span className={`${textClass} font-bold uppercase tracking-tight`}>
        <span className="text-white">IRON</span>
        <span className="text-amber-500">FORGE</span>
      </span>
    </div>
  )
}
