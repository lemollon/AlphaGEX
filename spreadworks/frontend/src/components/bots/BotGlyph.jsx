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

  if (kind === 'droplet') {
    // SPLASH = a falling drop over its ripple — the small-account bot.
    return (
      <svg {...common}>
        <path d="M12 3.5 C 9.5 7.5, 7.5 10, 7.5 12.5 a 4.5 4.5 0 0 0 9 0 C 16.5 10, 14.5 7.5, 12 3.5 Z" />
        <path d="M4 20.5 q 2 -1.6 4 0 t 4 0 t 4 0 t 4 0" />
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

  if (kind === 'stream') {
    // RIVER = a meandering river winding down between its banks. Distinct from
    // FLOW's converging horizontal current and TIDE's stacked sine waves.
    return (
      <svg {...common}>
        <path d="M12 3c-3 2-3 4 0 6s3 4 0 6 3 4 0 6" />
        <path d="M6 4c-1.5 3-1.5 6 0 9" opacity="0.5" />
        <path d="M18 5c1.5 3 1.5 6 0 9" opacity="0.5" />
      </svg>
    );
  }

  if (kind === 'sprout') {
    // MEADOW = a seedling sprouting two leaves from the ground. Reads as
    // growth/meadow — distinct from the water/wind glyphs of the siblings.
    return (
      <svg {...common}>
        <line x1="12" y1="21" x2="12" y2="11" />
        <path d="M12 13c0-3-2.2-5.2-5.5-5.2C6.5 11 8.7 13 12 13z" fill="currentColor" fillOpacity="0.2" />
        <path d="M12 11c0-3.4 2.4-5.8 6-5.8C18 8.6 15.6 11 12 11z" fill="currentColor" fillOpacity="0.2" />
        <path d="M5 21h14" />
      </svg>
    );
  }

  return null;
}
