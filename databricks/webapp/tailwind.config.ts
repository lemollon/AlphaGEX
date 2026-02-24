import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        flame: {
          DEFAULT: '#f59e0b',
          dark: '#d97706',
          glow: '#fbbf24',
        },
        spark: {
          DEFAULT: '#3b82f6',
          dark: '#2563eb',
        },
        forge: {
          bg: '#0c0a09',
          card: '#1c1917',
          border: '#292524',
          muted: '#78716c',
        },
      },
      backgroundImage: {
        'ember-glow': 'radial-gradient(ellipse at 50% 0%, rgba(245,158,11,0.08) 0%, transparent 60%)',
        'ember-subtle': 'radial-gradient(ellipse at 50% 100%, rgba(245,158,11,0.04) 0%, transparent 50%)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
export default config
