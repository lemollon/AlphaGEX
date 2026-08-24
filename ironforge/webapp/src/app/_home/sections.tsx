import Link from 'next/link'
import { IFMark } from '@/components/Brand'
import { MARKETING_TIERS } from '@/lib/billing/plans'
import { ShieldIcon, PeopleIcon, CheckIcon } from './icons'

/* ─────────────────────────────────────────────────────────────────────────────
 * MEMBERSHIP TIERS.
 *
 * This file used to hold the whole previous homepage — a hero with a live
 * dashboard preview, a three-card feature section, and a closing CTA banner.
 * The homepage now renders the approved marketing design from `marketing.tsx`,
 * which has no membership section, so everything except the two tier cards was
 * deleted rather than left sitting here: a second, unreachable homepage in the
 * tree is how a change lands on the design nobody is looking at.
 * `DashboardPreview.tsx` went with it (it had no other caller). Both are in git
 * history if the old layout is ever wanted back.
 *
 * What remains is rendered by exactly one route, /pricing.
 * ──────────────────────────────────────────────────────────────────────────── */

/* Row-major order so the rendered 2-col grid reads column-wise like the mock:
 * col 1 = AI briefings / commentary / discussions, col 2 = education / reviews / access. */
const COMMUNITY_FEATURES = [
  'AI market briefings',
  'Educational content',
  'Daily market commentary',
  'Trade reviews',
  'Member discussions',
  'Community access',
]

const AUTOMATE_FEATURES = [
  'Automated execution',
  'Real-time monitoring',
  'Risk-managed strategy',
  'Trade history',
  'Connected brokerage',
  'Performance dashboard',
]

function FeatureChecklist({ items }: { items: string[] }) {
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-2.5">
      {items.map((f) => (
        <li key={f} className="flex items-center gap-2">
          <CheckIcon className="h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span className="text-xs text-gray-200 md:text-[13px]">{f}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * The paid tier card.
 *
 * The tier NAME and PRICE are read from MARKETING_TIERS, never written here.
 * plans.ts is the single source; the Terms of Service billing paragraph and the
 * support knowledge base read the same fields. A price typed into a component is
 * how the retired /pricing page and the homepage came to disagree.
 */
export function ForgeStarterCard() {
  return (
    /* Green border, matching the trial badge and the trial CTA — the design uses green
       for "start free" throughout and reserves brand orange for paid actions like Join
       Community. h-full so it matches the Community card's height in the grid. */
    <div className="relative flex h-full flex-col rounded-2xl border border-emerald-500/50 bg-[#0A0B0C] p-6 md:p-7">
      <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-emerald-500/50 bg-emerald-950 px-4 py-1 text-[11px] font-bold tracking-wide text-emerald-400">
        5 TRADING DAY FREE TRIAL
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
          <ShieldIcon className="h-12 w-12 text-amber-500" />
          <IFMark className="absolute h-5 w-auto" />
        </div>
        <div>
          <h3 className="text-[22px] font-bold text-white">
            {MARKETING_TIERS.starter.name.split(' ')[0]}{' '}
            <span className="text-amber-500">
              {MARKETING_TIERS.starter.name.split(' ').slice(1).join(' ')}
            </span>
          </h3>
          <p className="mt-0.5 text-sm text-gray-400">Everything in Forge Community, plus:</p>
        </div>
      </div>

      <div className="mt-6">
        <FeatureChecklist items={AUTOMATE_FEATURES} />
      </div>

      <div className="mt-auto border-t border-white/10 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="text-white">
            <span className="text-[30px] font-extrabold">${MARKETING_TIERS.starter.priceMonthly}</span>
            <span className="ml-1 text-sm text-gray-400">/month</span>
          </div>
          <Link
            href="/signup?plan=automate&source=pricing&placement=tier_card"
            className="whitespace-nowrap rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-400 md:px-7 md:text-[15px]"
          >
            Start 5-Day Free Trial
          </Link>
        </div>
        <p className="mt-3 text-xs text-gray-500">No long-term commitment. Cancel anytime.</p>
      </div>
    </div>
  )
}

export function MembershipSection() {
  return (
    /* The `memberships` id is kept even though /pricing owns this section again:
       external links and old bookmarks to `#memberships` still exist, and an
       anchor that resolves costs nothing. */
    <section id="memberships" className="mx-auto max-w-[1200px] px-5 pb-16 md:px-8">
      <h2 className="text-center text-[26px] font-bold tracking-tight text-white md:text-[28px]">
        Choose Your Membership
      </h2>

      {/* Two tiers side by side — the comparison IS the section. `items-stretch` keeps
          both cards the same height whichever has more copy, and the paid card carries a
          `mt-4 md:mt-0` so its floating trial badge is never clipped when the grid
          collapses to one column on mobile. */}
      <div className="mx-auto mt-10 grid max-w-[1000px] grid-cols-1 items-stretch gap-6 md:grid-cols-2">
        {/* Forge Community */}
        <div className="flex flex-col rounded-2xl border border-white/10 bg-[#0A0B0C] p-6 md:p-7">
          {/* Header structure mirrors ForgeStarterCard exactly (UAT-001): same 12×12
              icon box, same title/sub-line stack, so the checklists start on the same
              baseline in both cards. */}
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center">
              <PeopleIcon className="h-11 w-11 text-amber-500" />
            </div>
            <div>
              <h3 className="text-[22px] font-bold text-white">
                {MARKETING_TIERS.community.name.split(' ')[0]}{' '}
                <span className="text-amber-500">
                  {MARKETING_TIERS.community.name.split(' ').slice(1).join(' ')}
                </span>
              </h3>
              <p className="mt-0.5 text-sm text-gray-400">The foundation.</p>
            </div>
          </div>

          <div className="mt-6">
            <FeatureChecklist items={COMMUNITY_FEATURES} />
          </div>

          {/* Bottom block mirrors ForgeStarterCard: mt-auto pins it, and the matching
              caption line keeps both tiers' price/CTA rows on the SAME baseline —
              without it Community's price sat lower than Automate's (UAT-001). */}
          <div className="mt-auto border-t border-white/10 pt-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="text-white">
                <span className="text-[30px] font-extrabold">${MARKETING_TIERS.community.priceMonthly}</span>
                <span className="ml-1 text-sm text-gray-400">/month</span>
              </div>
              <Link
                href="/signup?plan=community&source=pricing&placement=tier_card"
                className="whitespace-nowrap rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-400 md:px-7 md:text-[15px]"
              >
                Join Community
              </Link>
            </div>
            <p className="mt-3 text-xs text-gray-500">Cancel anytime.</p>
          </div>
        </div>

        {/* The paid tier, promoted: green border + trial badge, as in the design. */}
        <div className="mt-4 md:mt-0">
          <ForgeStarterCard />
        </div>
      </div>
    </section>
  )
}
