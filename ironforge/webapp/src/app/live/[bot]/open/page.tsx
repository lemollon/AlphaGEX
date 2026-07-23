import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getBotPlan } from '@/lib/billing/plans'
import OpenAccountClient from './OpenAccountClient'

export const dynamic = 'force-dynamic'

export function generateMetadata({ params }: { params: { bot: string } }): Metadata {
  const plan = getBotPlan(params.bot)
  const name = plan?.name ?? 'Bot'
  return {
    title: `Open ${name} Account — IronForge`,
    description: `Set up a dedicated ${name} account for automated trading.`,
  }
}

export default function OpenAccountPage({ params }: { params: { bot: string } }) {
  const plan = getBotPlan(params.bot)
  if (!plan) notFound()
  return <OpenAccountClient bot={plan.slug} />
}
