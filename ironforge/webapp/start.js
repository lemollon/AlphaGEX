// Force 0.0.0.0 binding before Next.js reads HOSTNAME.
// Kubernetes overrides the HOSTNAME env var with the pod name,
// which causes the standalone server to bind to an unreachable address.
process.env.HOSTNAME = '0.0.0.0';
require('./.next/standalone/server.js');

// Self-warmup: the scanner starts lazily on the first DB connection
// (db.ts ensureTables). On a service with no inbound traffic right after a
// deploy, that first connection never happens and the scanner stays dead —
// on 2026-07-28 four back-to-back deploys left the real-money scanner
// silent for 86 minutes of market hours. Ping our own /api/health (which
// touches the DB) until it answers, so every fresh instance wakes the
// scanner without depending on outside traffic. SCANNER_ENABLED still
// gates whether scanning actually starts; this only triggers table init.
const WARMUP_PORT = process.env.PORT || 3000;
const WARMUP_MAX_ATTEMPTS = 30;
let warmupAttempts = 0;
function warmup() {
  warmupAttempts += 1;
  fetch(`http://127.0.0.1:${WARMUP_PORT}/api/health`)
    .then((res) => {
      console.log(`[warmup] /api/health → ${res.status} (attempt ${warmupAttempts})`);
    })
    .catch((err) => {
      if (warmupAttempts < WARMUP_MAX_ATTEMPTS) {
        setTimeout(warmup, 10_000);
      } else {
        console.warn(`[warmup] gave up after ${warmupAttempts} attempts: ${err.message}`);
      }
    });
}
setTimeout(warmup, 5_000);
