/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [{ source: '/forge', destination: '/forge.html' }]
  },
}

module.exports = nextConfig
