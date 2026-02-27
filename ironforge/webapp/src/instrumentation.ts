/**
 * Next.js Instrumentation — starts the IronForge scan loop on server boot.
 *
 * This file is automatically loaded by Next.js when the server starts.
 * It only runs server-side (not in the browser or during build).
 *
 * @see https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
  // Only run on the server, not during build or in edge runtime
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const { startScanner } = await import('./lib/scanner')
    startScanner()
  }
}
