/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
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
