import { redirect } from 'next/navigation'

// Consolidated into /perpetuals-crypto (coin view). Preserve ?coin= so
// bookmarked/linked per-coin URLs still land on the right bot.
export default function Page({
  searchParams,
}: {
  searchParams: { [key: string]: string | string[] | undefined }
}) {
  const coin = typeof searchParams?.coin === 'string' ? searchParams.coin : undefined
  redirect(coin ? `/perpetuals-crypto?coin=${coin}` : '/perpetuals-crypto')
}
