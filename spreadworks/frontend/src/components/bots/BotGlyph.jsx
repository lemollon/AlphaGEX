// Custom inline SVG glyphs for each bot identity. Lifted from the
// SpreadWorks Design System handoff (design_handoff_bots/bots-chrome.jsx
// → BotIcon). Drawn larger and with more presence than Lucide defaults so
// they read at both 18px (nav pill) and 32px (nameplate).

export default function BotGlyph({ kind, size = 18, strokeWidth = 1.6, className = '', style }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    className,
    style,
  };

  if (kind === 'snowflake') {
    return (
      <svg {...common}>
        <line x1="12" y1="3" x2="12" y2="21" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="5.6" y1="5.6" x2="18.4" y2="18.4" />
        <line x1="18.4" y1="5.6" x2="5.6" y2="18.4" />
        <polyline points="9 4 12 7 15 4" />
        <polyline points="9 20 12 17 15 20" />
        <polyline points="4 9 7 12 4 15" />
        <polyline points="20 9 17 12 20 15" />
      </svg>
    );
  }

  if (kind === 'wave') {
    return (
      <svg {...common}>
        <path d="M2 8c2.5-4 5-4 7.5 0S15 12 17.5 8 22 4 22 4" />
        <path d="M2 14c2.5-4 5-4 7.5 0S15 18 17.5 14 22 10 22 10" />
        <path d="M2 20c2.5-4 5-4 7.5 0S15 24 17.5 20" />
      </svg>
    );
  }

  if (kind === 'compass') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <polygon
          points="15.5 8.5 13.5 13.5 8.5 15.5 10.5 10.5 15.5 8.5"
          fill="currentColor"
          fillOpacity="0.25"
        />
      </svg>
    );
  }

  if (kind === 'river') {
    // Two converging streamlines for FLOW — distinct from "wave" (TIDE)
    // which uses 3 horizontal sine waves. River reads as directional
    // current.
    return (
      <svg {...common}>
        <path d="M3 7c4 0 5 4 9 4s5-4 9-4" />
        <path d="M3 13c4 0 5 4 9 4s5-4 9-4" />
        <circle cx="7" cy="7" r="0.7" fill="currentColor" />
        <circle cx="17" cy="17" r="0.7" fill="currentColor" />
      </svg>
    );
  }

  return null;
}
