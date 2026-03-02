// Patch Next.js standalone server.js to bind to 0.0.0.0.
// Kubernetes sets HOSTNAME to the pod name, which causes the server
// to bind to an unreachable address. This replaces the env var lookup
// with a hardcoded '0.0.0.0'.
const fs = require('fs');
const path = require('path');
const serverJs = path.join(__dirname, '..', '.next', 'standalone', 'server.js');
let content = fs.readFileSync(serverJs, 'utf8');
const original = content;
content = content.replace(
  "const hostname = process.env.HOSTNAME || '0.0.0.0'",
  "const hostname = '0.0.0.0'"
);
if (content === original) {
  console.warn('WARNING: hostname pattern not found in server.js — no patch applied');
  process.exit(1);
} else {
  fs.writeFileSync(serverJs, content);
  console.log('Patched server.js: hostname hardcoded to 0.0.0.0');
}
