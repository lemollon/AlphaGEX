// SpreadWorks bot API helpers. Returns parsed JSON or throws on non-2xx.

const API_BASE = import.meta.env.VITE_API_URL || '';

async function _get(path) {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function _post(path, body) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const botApi = {
  listAll:        ()         => _get(`/api/spreadworks/bots`),
  status:         (b)        => _get(`/api/spreadworks/bots/${b}/status`),
  positions:      (b)        => _get(`/api/spreadworks/bots/${b}/positions`),
  positionMonitor:(b)        => _get(`/api/spreadworks/bots/${b}/position-monitor`),
  equityCurve:    (b)        => _get(`/api/spreadworks/bots/${b}/equity-curve`),
  equityIntraday: (b)        => _get(`/api/spreadworks/bots/${b}/equity-curve/intraday`),
  trades:         (b, limit=100) => _get(`/api/spreadworks/bots/${b}/trades?limit=${limit}`),
  performance:    (b)        => _get(`/api/spreadworks/bots/${b}/performance`),
  dailyPerf:      (b)        => _get(`/api/spreadworks/bots/${b}/daily-perf`),
  config:         (b)        => _get(`/api/spreadworks/bots/${b}/config`),
  saveConfig:     (b, body)  => _post(`/api/spreadworks/bots/${b}/config`, body),
  toggle:         (b)        => _post(`/api/spreadworks/bots/${b}/toggle`),
  forceTrade:     (b)        => _post(`/api/spreadworks/bots/${b}/force-trade`),
  forceClose:     (b, pid)   => _post(`/api/spreadworks/bots/${b}/force-close?position_id=${encodeURIComponent(pid)}`),
  scanActivity:   (b, limit=200) => _get(`/api/spreadworks/bots/${b}/scan-activity?limit=${limit}`),
};
