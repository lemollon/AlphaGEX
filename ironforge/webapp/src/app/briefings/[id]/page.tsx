'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useParams } from 'next/navigation'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingDetail() {
  const params = useParams<{ id: string }>()
  const id = decodeURIComponent(params.id as string)
  const { data, isLoading } = useSWR<{ brief: BriefRow }>(`/api/briefings/${encodeURIComponent(id)}`, fetcher)
  if (isLoading) return <div className="max-w-4xl mx-auto px-4 py-6 text-gray-400">Loading…</div>
  if (!data?.brief) return <div className="max-w-4xl mx-auto px-4 py-6 text-red-400">Brief not found.</div>
  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-4">
      <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back to briefings</Link>
      <BriefingCard brief={data.brief} />
    </div>
  )
}
