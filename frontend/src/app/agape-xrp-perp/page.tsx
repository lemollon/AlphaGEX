import { redirect } from 'next/navigation'

// Consolidated into /agape-perps
export default function Page() {
  redirect('/agape-perps?coin=xrp')
}
