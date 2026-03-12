/**
 * Shimmer / skeleton bar used as a loading placeholder.
 */

export function Shimmer({ width = 60, height = 14, style: extra }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width,
        height,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--border-subtle)',
        animation: 'sw-shimmer 1.2s ease-in-out infinite',
        ...extra,
      }}
    />
  );
}

/**
 * Full-row skeleton for MetricsBar (2 rows of shimmer cells).
 */
const cellStyle = {
  flex: 1,
  padding: '10px 14px',
  borderRight: '1px solid var(--border-subtle)',
  display: 'flex',
  flexDirection: 'column',
  gap: 5,
};

const barStyle = {
  display: 'flex',
  background: 'var(--bg-surface)',
  borderTop: '1px solid var(--border-subtle)',
  fontFamily: 'var(--font-ui)',
};

export function MetricsBarSkeleton() {
  const cells = (count, labelW = 50, valW = 60, valH = 14) =>
    Array.from({ length: count }, (_, i) => (
      <div key={i} style={{ ...cellStyle, ...(i === count - 1 ? { borderRight: 'none' } : {}) }}>
        <Shimmer width={labelW} height={8} />
        <Shimmer width={valW} height={valH} />
      </div>
    ));

  return (
    <div>
      <div style={barStyle}>{cells(6, 55, 65, 14)}</div>
      <div style={{ ...barStyle, borderTop: 'none' }}>
        {cells(4, 40, 55, 13)}
        <div style={{ ...cellStyle, flex: 2, borderRight: 'none' }} />
      </div>
    </div>
  );
}

/**
 * Overlay skeleton for the chart/table area while calculating.
 */
export function CalcOverlay() {
  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(6, 6, 14, 0.75)',
      backdropFilter: 'blur(2px)',
      zIndex: 5,
      fontFamily: 'var(--font-ui)',
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
      }}>
        <div style={{
          width: 28,
          height: 28,
          border: '2px solid var(--border-subtle)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'sw-spin 0.8s linear infinite',
        }} />
        <span style={{ color: 'var(--text-tertiary)', fontSize: 12, fontWeight: 500 }}>
          Calculating...
        </span>
      </div>
    </div>
  );
}
