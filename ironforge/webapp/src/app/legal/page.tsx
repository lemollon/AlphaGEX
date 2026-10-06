import Link from 'next/link'
import LegalPage from '@/components/LegalPage'
import { LEGAL_DOCUMENTS } from '@/lib/enrollment/legal'

export const metadata = {
  title: 'Agreements & Disclosures — IronForge',
  description: 'Every document IronForge asks members to review and accept, with its current version.',
}

/**
 * Index of every versioned legal document (db-controls #203: Settings needs a
 * "brokerage, plan and agreements" link — brokerage and plan already have one each;
 * this was the missing third). LEGAL_DOCUMENTS (lib/enrollment/legal.ts) is the same
 * registry the enrollment Agreements step and the Review step's signer line read, so
 * this list can't drift from what a member actually accepted.
 */
export default function LegalIndexPage() {
  return (
    <LegalPage title="Agreements & Disclosures" updated="see each document below">
      <p>
        These are the documents IronForge asks members to review and accept. Accepting a new version of
        one never re-opens the others — each is versioned independently.
      </p>
      <ul className="space-y-3">
        {LEGAL_DOCUMENTS.map((d) => (
          <li key={d.code} className="flex items-baseline justify-between gap-4 border-b border-forge-border pb-3">
            <Link href={d.contentUri} className="text-gray-100 hover:text-amber-500 transition-colors">
              {d.title}
            </Link>
            <span className="shrink-0 font-mono text-xs text-forge-muted">v{d.version}</span>
          </li>
        ))}
      </ul>
    </LegalPage>
  )
}
