/**
 * Shimmer / skeleton bar used as a loading placeholder.
 * Renders a pulsing rectangle at the given width × height.
 */
const font = "'Courier New', monospace";

const keyframes = `
@keyframes sw-shimmer {
  0%   { opacity: 0.25; }
  50%  { opacity: 0.45; }
  100% { opacity: 0.25; }
}
`;

let injected = false;
function injectKeyframes() {
  if (injected) return;
  injected = true;
  const style = document.createElement('style');
  style.textContent = keyframes;
  document.head.appendChild(style);
}

export function Shimmer({ width = 60, height = 14, style: extra }) {
  injectKeyframes();
  return (
    <span
      style={{
        display: 'inline-block',
        width,
        height,
        borderRadius: 3,
        background: '#1a1a2e',
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
  padding: '8px 12px',
  borderRight: '1px solid #1a1a2e',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
};

const barStyle = {
  display: 'flex',
  background: 'var(--bg-surface)',
  borderTop: '1px solid #1a1a2e',
  fontFamily: font,
};

export function MetricsBarSkeleton() {
  injectKeyframes();
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
  injectKeyframes();
  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(8, 8, 16, 0.7)',
      zIndex: 5,
      fontFamily: font,
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
      }}>
        <div style={{
          width: 24,
          height: 24,
          border: '2px solid #1a1a2e',
          borderTopColor: '#448aff',
          borderRadius: '50%',
          animation: 'sw-spin 0.8s linear infinite',
        }} />
        <span style={{ color: '#555', fontSize: 11 }}>Calculating...</span>
        <style>{`@keyframes sw-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
