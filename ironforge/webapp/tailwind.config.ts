import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        // --font-sans / --font-display are injected by next/font in app/layout.tsx
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        display: ['var(--font-display)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Brand re-hue: the accent rides on Tailwind's built-in `amber-*` classes
        // (414 usages), so overriding the `amber` scale re-skins the whole site to
        // the orange-red brand in one place. Anchored on the mockup CTA (#E8531F).
        amber: {
          50: '#FFF3ED',
          100: '#FFE3D3',
          200: '#FFC4A5',
          300: '#FB9B6B',
          400: '#F5743C',
          500: '#EE5A24',
          600: '#E8531F',
          700: '#B83C12',
          800: '#92300E',
          900: '#5C1E08',
        },
        flame: {
          DEFAULT: '#E8531F',
          dark: '#C2410C',
          glow: '#FB7A3D',
        },
        spark: {
          DEFAULT: '#3b82f6',
          dark: '#2563eb',
        },
        forge: {
          bg: '#0B0B0D',
          card: '#16161A',
          border: '#262629',
          muted: '#78716c',
        },
      },
      backgroundImage: {
        'ember-glow': 'radial-gradient(ellipse at 50% 0%, rgba(232,83,31,0.08) 0%, transparent 60%)',
        'ember-subtle': 'radial-gradient(ellipse at 50% 100%, rgba(232,83,31,0.04) 0%, transparent 50%)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
export default config
