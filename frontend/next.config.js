/** @type {import('next').NextConfig} */

// Generate build ID at build time
const buildId = new Date().toISOString().slice(0, 16).replace('T', ' ')
const gitCommit = process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) || 'local'

const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: '/jubilee-box',
        destination: '/jubilee',
        permanent: true,
      },
      {
        source: '/counselor',
        destination: '/counselor-commands',
        permanent: true,
      },
      {
        source: '/ai',
        destination: '/ai-copilot',
        permanent: true,
      },
      {
        source: '/autonomous',
        destination: '/trader',
        permanent: true,
      },
    ]
  },
  env: {
    // No localhost fallbacks - these MUST be set in production
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
    // Build version tracking - baked in at build time
    NEXT_PUBLIC_BUILD_TIME: buildId,
    NEXT_PUBLIC_BUILD_COMMIT: gitCommit,
  },
  async headers() {
    return [
      {
        // Apply security headers to all routes
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin'
          },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://s3.tradingview.com https://vercel.live",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https: blob:",
              "font-src 'self' data:",
              `connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ${process.env.NEXT_PUBLIC_API_URL || ''} ${process.env.NEXT_PUBLIC_WS_URL || ''} wss: ws: https:`,
              "frame-src 'self' https://s3.tradingview.com https://vercel.live",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "frame-ancestors 'self'",
            ].join('; ')
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()'
          }
        ]
      }
    ]
  }
}

module.exports = nextConfig
