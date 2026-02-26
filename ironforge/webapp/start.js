// Force 0.0.0.0 binding before Next.js reads HOSTNAME.
// Kubernetes overrides the HOSTNAME env var with the pod name,
// which causes the standalone server to bind to an unreachable address.
process.env.HOSTNAME = '0.0.0.0';
require('./.next/standalone/server.js');
