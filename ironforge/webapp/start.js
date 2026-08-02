// Sandbox safety gate. No-op unless IRONFORGE_ENV=sandbox, in which case it
// proves this service cannot reach real money (prod broker keys, live Stripe,
// the scanner, the production databases) and exits non-zero if it can. Runs
// BEFORE the server is loaded so a misconfigured sandbox never serves traffic.
//
// This is also the boot path of the LIVE services, so a failure to load the
// guard must never be what stops the real-money scanner from starting: on
// production we log and continue, on sandbox we fail closed.
try {
  require('./scripts/sandbox-guard.js').enforceSandboxGuard();
} catch (err) {
  if (String(process.env.IRONFORGE_ENV || '').trim().toLowerCase() === 'sandbox') {
    console.error(`[sandbox-guard] could not load the guard: ${err.message}`);
    console.error('[sandbox-guard] refusing to start an unverified sandbox.');
    process.exit(1);
  }
  console.warn(`[sandbox-guard] skipped (not sandbox): ${err.message}`);
}

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
