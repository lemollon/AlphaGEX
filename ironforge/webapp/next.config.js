/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    // ironforge/shared (the #225 shared API types module) lives one level above
    // this project's root. Next refuses to resolve imports outside its root
    // directory by default — this is the documented opt-out.
    externalDir: true,
  },
  async headers() {
    return [
      {
        /**
         * apple-app-site-association has NO file extension, so Next's static handler
         * cannot infer a mime type and serves it as application/octet-stream. Apple's
         * CDN fetcher requires application/json, and a wrong content type fails the
         * association silently — iOS then CACHES the failure, so Universal Links stay
         * broken on a device even after the file is corrected. Force the type here.
         */
        source: '/.well-known/apple-app-site-association',
        headers: [{ key: 'Content-Type', value: 'application/json' }],
      },
    ]
  },
}

module.exports = nextConfig
