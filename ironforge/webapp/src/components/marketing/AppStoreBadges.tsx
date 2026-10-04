/**
 * Apple/Google badges. Placeholder search-listing URLs, matching the design
 * spec verbatim — swap for the real listing links once the apps are live.
 */
const STORE_LINKS = {
  apple: 'https://apps.apple.com/us/search?term=IronForge',
  google: 'https://play.google.com/store/search?q=IronForge&c=apps',
}

export default function AppStoreBadges({ className }: { className?: string }) {
  return (
    <div className={`stores${className ? ` ${className}` : ''}`}>
      <a className="store" href={STORE_LINKS.apple} target="_blank" rel="noopener noreferrer">
        <svg>
          <use href="#i-apple" />
        </svg>
        <span>
          <small>Download on the</small>
          <b>App Store</b>
        </span>
      </a>
      <a className="store" href={STORE_LINKS.google} target="_blank" rel="noopener noreferrer">
        <svg>
          <use href="#i-play" />
        </svg>
        <span>
          <small>Get it on</small>
          <b>Google Play</b>
        </span>
      </a>
    </div>
  )
}
