import fs from 'fs'
import path from 'path'

export const metadata = {
  title: 'IronForge · Credit where credit\'s due.',
  description:
    'Three iron condor bots, paper-traded against real Tradier data. Every fill, every cycle, in real time.',
}

function loadLandingBody(): string {
  const file = path.join(process.cwd(), 'public', 'landing', '2.html')
  const html = fs.readFileSync(file, 'utf-8')
  const inside = html.match(/<body[^>]*>([\s\S]*)<\/body>/)?.[1] ?? ''
  return inside.replace(/<div class="demo-bar"[\s\S]*?<\/div>\s*/, '')
}

export default function Home() {
  const body = loadLandingBody()
  return (
    <>
      <link rel="stylesheet" href="/landing/styles.css" />
      <a
        href="/dashboard"
        style={{
          position: 'fixed',
          top: 16,
          right: 20,
          zIndex: 9999,
          padding: '8px 16px',
          background: 'rgba(10,3,1,0.92)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(251,191,36,0.4)',
          borderRadius: 6,
          color: '#fbbf24',
          fontFamily: 'Inter, sans-serif',
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          textDecoration: 'none',
        }}
      >
        Dashboard →
      </a>
      <div dangerouslySetInnerHTML={{ __html: body }} />
    </>
  )
}
