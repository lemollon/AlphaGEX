/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      { source: '/landing', destination: '/landing/index.html' },
      { source: '/landing/', destination: '/landing/index.html' },
    ]
  },
}

module.exports = nextConfig
