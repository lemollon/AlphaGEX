/**
 * Fixed ribbon marking a page as the sandbox.
 *
 * The sandbox is seeded with fabricated subscriptions, trials and open positions
 * (webapp/scripts/seed-sandbox.js). Those numbers render in the same components
 * as real ones, so a screenshot of a sandbox /live is indistinguishable from a
 * real customer's account unless the page says otherwise. It says otherwise.
 *
 * Server-rendered from the IRONFORGE_ENV flag by the root layout — never a client
 * check, so it cannot be toggled off from the browser.
 */
import { SANDBOX_BANNER_TEXT } from '@/lib/sandbox'

export default function SandboxBanner({ enabled }: { enabled: boolean }) {
  if (!enabled) return null
  return (
    <div
      role="status"
      aria-label="Sandbox environment"
      className="fixed bottom-0 inset-x-0 z-[9999] pointer-events-none
                 bg-amber-500 text-black text-center
                 text-[11px] font-semibold uppercase tracking-widest
                 py-1 px-3 shadow-[0_-2px_8px_rgba(0,0,0,0.35)]"
    >
      {SANDBOX_BANNER_TEXT}
    </div>
  )
}
