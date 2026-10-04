/**
 * Shared `<symbol>` defs for the 10.4 marketing design, rendered once by
 * `MarketingShell` and referenced everywhere else as `<svg><use href="#i-x"/></svg>`
 * — same pattern the source design HTML uses. Paths copied verbatim from
 * `IronForge_WebDesign_10.4.html`.
 */
export default function MarketingIcons() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <defs>
        <symbol id="i-check" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={2.2}
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M5 12.5l4.2 4.2L19 7"
          />
        </symbol>
        <symbol id="i-x" viewBox="0 0 24 24">
          <path fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" d="M7 7l10 10M17 7L7 17" />
        </symbol>
        <symbol id="i-sun" viewBox="0 0 24 24">
          <circle cx={12} cy={12} r={4.2} fill="none" stroke="currentColor" strokeWidth={1.8} />
          <path
            d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
          />
        </symbol>
        <symbol id="i-moon" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinejoin="round"
            d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"
          />
        </symbol>
        <symbol id="i-menu" viewBox="0 0 24 24">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
        </symbol>
        <symbol id="i-lock" viewBox="0 0 24 24">
          <rect x={5} y={10.5} width={14} height={10} rx={3} fill="none" stroke="currentColor" strokeWidth={1.8} />
          <path d="M8.5 10.5V8a3.5 3.5 0 017 0v2.5" fill="none" stroke="currentColor" strokeWidth={1.8} />
        </symbol>
        <symbol id="i-shield" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinejoin="round"
            d="M12 3l7.5 3v5.5c0 4.6-3.1 8.3-7.5 9.5-4.4-1.2-7.5-4.9-7.5-9.5V6L12 3z"
          />
        </symbol>
        <symbol id="i-pause" viewBox="0 0 24 24">
          <circle cx={12} cy={12} r={8.5} fill="none" stroke="currentColor" strokeWidth={1.8} />
          <path d="M10 9v6M14 9v6" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
        </symbol>
        <symbol id="i-link" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"
          />
        </symbol>
        <symbol id="i-steps" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinejoin="round"
            strokeLinecap="round"
            d="M3.5 19.5h5v-5h5v-5h5v-5"
          />
        </symbol>
        <symbol id="i-drop" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinejoin="round"
            d="M12 3.5s6 6.4 6 10.5a6 6 0 01-12 0c0-4.1 6-10.5 6-10.5z"
          />
        </symbol>
        <symbol id="i-eye" viewBox="0 0 24 24">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"
          />
          <circle cx={12} cy={12} r={3} fill="none" stroke="currentColor" strokeWidth={1.8} />
        </symbol>
        <symbol id="i-apple" viewBox="0 0 24 24">
          <path
            fill="currentColor"
            d="M16.4 12.6c0-2.4 2-3.5 2-3.6-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9-.7 0-1.8-.8-3-.8-1.5 0-3 .9-3.8 2.3-1.6 2.8-.4 7 1.2 9.3.8 1.1 1.7 2.4 2.9 2.3 1.2 0 1.6-.7 3-.7s1.8.7 3 .7c1.3 0 2.1-1.1 2.8-2.3.9-1.3 1.3-2.6 1.3-2.6s-2.5-1-2.5-3.7zM14.1 5.6c.6-.8 1.1-1.9 1-3-.9 0-2.1.6-2.7 1.4-.6.7-1.1 1.8-1 2.9 1 .1 2.1-.5 2.7-1.3z"
          />
        </symbol>
        <symbol id="i-play" viewBox="0 0 24 24">
          <path fill="#34a853" d="M4 3.2l10.2 10.3L4 23.7c-.4-.2-.6-.6-.6-1.1V4.3c0-.5.2-.9.6-1.1z" />
          <path fill="#fbbc04" d="M17.6 10l-3.4 3.5 3.4 3.4 3.9-2.2c1.1-.6 1.1-1.7 0-2.4z" />
          <path fill="#ea4335" d="M14.2 13.5L4 23.7c.4.2.9.2 1.4-.1l12.2-6.7z" />
          <path fill="#4285f4" d="M17.6 10L5.4 3.3C4.9 3 4.4 3 4 3.2l10.2 10.3z" />
        </symbol>
      </defs>
    </svg>
  )
}
