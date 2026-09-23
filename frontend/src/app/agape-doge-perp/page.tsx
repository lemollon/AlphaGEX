import { redirect } from 'next/navigation'

// Consolidated into /perpetuals-crypto
export default function Page() {
  redirect('/perpetuals-crypto?coin=doge')
}
