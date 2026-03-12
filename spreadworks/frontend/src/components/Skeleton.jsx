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
        background: 'linear-gradient(90deg, rgba(30, 30, 70, 0.3) 0%, rgba(30, 30, 70, 0.5) 50%, rgba(30, 30, 70, 0.3) 100%)',
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
  background: 'rgba(13, 13, 35, 0.6)',
  border: '1px solid rgba(30, 30, 70, 0.4)',
  borderRadius: 'var(--radius-md)',
  display: 'flex',
  flexDirection: 'column',
  gap: 5,
};

const barStyle = {
  display: 'flex',
  gap: 2,
  padding: '6px 10px',
  background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)',
  borderTop: '1px solid var(--border-subtle)',
  fontFamily: 'var(--font-ui)',
};

export function MetricsBarSkeleton() {
  const cells = (count, labelW = 50, valW = 60, valH = 14) =>
    Array.from({ length: count }, (_, i) => (
      <div key={i} style={cellStyle}>
        <Shimmer width={labelW} height={8} />
        <Shimmer width={valW} height={valH} />
      </div>
    ));

  return (
    <div>
      <div style={barStyle}>{cells(6, 55, 65, 14)}</div>
      <div style={{ ...barStyle, borderTop: 'none' }}>
        {cells(4, 40, 55, 13)}
        <div style={{ ...cellStyle, flex: 2, opacity: 0 }} />
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
      background: 'rgba(5, 5, 16, 0.8)',
      backdropFilter: 'blur(4px)',
      zIndex: 5,
      fontFamily: 'var(--font-ui)',
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 14,
        padding: '24px 32px',
        background: 'rgba(13, 13, 35, 0.7)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid rgba(30, 30, 70, 0.4)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
      }}>
        <div style={{
          width: 32,
          height: 32,
          border: '2px solid rgba(30, 30, 70, 0.5)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'sw-spin 0.8s linear infinite',
        }} />
        <span style={{ color: 'var(--text-secondary)', fontSize: 12, fontWeight: 600 }}>
          Calculating...
        </span>
      </div>
    </div>
  );
}
