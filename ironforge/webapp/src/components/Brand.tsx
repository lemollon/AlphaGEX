/* Shared IronForge brand mark — the old "IF" raster logo, now RETIRED sitewide
 * (dev-handoff gap audit: "still the default logo on login, onboarding, legal
 * pages, ops tools, main signed-in nav, favicon, and OG image — only the
 * marketing homepage nav opted out"). `IFMark` is kept, unused, only so a
 * caller that still imports it does not 404 on a deleted asset; nothing in
 * this app renders it anymore. */

export function IFMark({ className = 'h-8 w-auto' }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/ironforge-mark.png" alt="IronForge" className={className} />
}

/**
 * The one IronForge wordmark — text-only, IRON white + FORGE brand-orange
 * (#EE5A24, matching the marketing accent), bold uppercase. This is the single
 * source of truth: every nav renders THIS so the logo can't drift between
 * pages. Matches the approved 10.4 logo lockup exactly — do not reintroduce the
 * amber-yellow FORGE or the retired mark image.
 *
 * `showMark` defaults to `false` now that the mark itself is retired sitewide
 * — every surface (marketing, signed-in, ops) renders the same text-only
 * lockup the marketing homepage nav already used. Passing `showMark={true}`
 * is still technically possible (nothing deletes the prop or the asset) but
 * no call site in this app does, and none should.
 */
export function Wordmark({
  markClass = 'h-7 w-auto',
  textClass = 'text-xl',
  showMark = false,
}: { markClass?: string; textClass?: string; showMark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      {showMark ? <IFMark className={markClass} /> : null}
      <span className={`${textClass} font-brand font-bold uppercase tracking-tight`}>
        <span className="text-white">IRON</span>
        <span className="text-amber-500">FORGE</span>
      </span>
    </div>
  )
}
