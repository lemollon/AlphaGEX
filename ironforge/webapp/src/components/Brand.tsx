/* Shared IronForge brand mark — the official IF logo (raster asset). */

export function IFMark({ className = 'h-8 w-auto' }: { className?: string }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/ironforge-mark.png" alt="IronForge" className={className} />
}

export function Wordmark({ markClass = 'h-7 w-auto', textClass = 'text-xl' }: { markClass?: string; textClass?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <IFMark className={markClass} />
      <span className={`${textClass} font-bold tracking-tight`}>
        <span className="text-white">IRON</span>
        <span className="text-amber-500">FORGE</span>
      </span>
    </div>
  )
}
