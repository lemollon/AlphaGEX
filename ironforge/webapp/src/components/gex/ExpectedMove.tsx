'use client'

interface Props {
  price: number
  expectedMove: number | null
  upper1sd: number | null
  lower1sd: number | null
}

/** Compact line showing the 0DTE daily expected move and the ±1σ price range. */
export default function ExpectedMove({ price, expectedMove, upper1sd, lower1sd }: Props) {
  if (!expectedMove || expectedMove <= 0 || !price) {
    return <p className="text-xs text-gray-500">Expected move unavailable.</p>
  }
  const pct = (expectedMove / price) * 100
  return (
    <p className="text-xs text-gray-400">
      <span className="text-gray-500 uppercase tracking-wide text-[10px]">Daily Expected Move</span>{' '}
      <span className="text-amber-300 font-semibold">±${expectedMove.toFixed(2)}</span>
      <span className="text-gray-500"> (±{pct.toFixed(2)}%)</span>
      {lower1sd != null && upper1sd != null && (
        <>
          {'  ·  '}
          <span className="text-gray-500 uppercase tracking-wide text-[10px]">±1σ</span>{' '}
          <span className="text-gray-200 font-mono">${lower1sd.toFixed(2)} – ${upper1sd.toFixed(2)}</span>
        </>
      )}
    </p>
  )
}
