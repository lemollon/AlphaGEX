/**
 * Full disclosure. Sits immediately below the trade log and is never hidden
 * behind a tooltip or a disclosure widget.
 */
export default function LedgerDisclosure() {
  return (
    <section aria-label="Disclosure" className="mt-10 border-t border-white/10 pt-6">
      <p className="mx-auto max-w-3xl text-center text-xs leading-relaxed text-gray-400">
        Paper-trade results are simulated using live market data and do not reflect actual brokerage
        execution, liquidity, slippage, or individual account performance.
      </p>
      <p
        id="ledger-fee-note"
        className="mx-auto mt-3 max-w-3xl text-center text-xs leading-relaxed text-gray-400"
      >
        <span aria-hidden="true">*</span> Results are shown before commissions and exchange fees.
        IronForge does not record per-trade commission data, so any fee figure here would be an
        estimate rather than a record — the basis is stated plainly instead. Every figure is
        normalised to one modelled contract, so results are comparable across trades of different
        size and will not correspond to any single account statement. Past results, simulated or
        otherwise, do not predict future performance.
      </p>
    </section>
  )
}
