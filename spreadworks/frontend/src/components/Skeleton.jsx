/**
 * Shimmer / skeleton bar used as a loading placeholder.
 */

export function Shimmer({ width = 60, height = 14, style: extra }) {
  return (
    <span
      className="inline-block rounded-md animate-shimmer"
      style={{
        width,
        height,
        background: 'linear-gradient(90deg, rgba(30, 30, 70, 0.3) 0%, rgba(30, 30, 70, 0.5) 50%, rgba(30, 30, 70, 0.3) 100%)',
        ...extra,
      }}
    />
  );
}

/**
 * Full-row skeleton for MetricsBar (2 rows of shimmer cells).
 */
export function MetricsBarSkeleton() {
  const cells = (count, labelW = 50, valW = 60, valH = 14) =>
    Array.from({ length: count }, (_, i) => (
      <div key={i} className="flex-1 flex flex-col gap-1.5 px-3.5 py-2.5 rounded-md border border-white/5 bg-bg-card">
        <Shimmer width={labelW} height={8} />
        <Shimmer width={valW} height={valH} />
      </div>
    ));

  return (
    <div>
      <div className="flex gap-0.5 px-2.5 py-1.5 border-t border-white/5 bg-bg-base font-[var(--font-ui)]">
        {cells(6, 55, 65, 14)}
      </div>
      <div className="flex gap-0.5 px-2.5 py-1.5 bg-bg-base font-[var(--font-ui)]">
        {cells(4, 40, 55, 13)}
        <div className="flex-[2] opacity-0" />
      </div>
    </div>
  );
}

/**
 * Overlay skeleton for the chart/table area while calculating.
 */
export function CalcOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center z-5"
      style={{ background: 'rgba(7, 9, 15, 0.85)' }}>
      <div className="flex flex-col items-center gap-3.5 px-8 py-6 rounded-md border border-white/5 bg-bg-card">
        <div className="w-8 h-8 rounded-full border-2 border-border-subtle border-t-accent animate-spin-fast" />
        <span className="text-text-secondary text-xs font-semibold">Calculating...</span>
      </div>
    </div>
  );
}
