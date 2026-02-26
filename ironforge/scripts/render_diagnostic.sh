#!/bin/bash
# =============================================================
#  IronForge Render Shell Diagnostic
#  Uses Node.js + pg (already installed in webapp's node_modules).
#  No Python, no venv, no pip install.
#
#  Usage (from Render shell):
#    bash ~/project/src/ironforge/scripts/render_diagnostic.sh
# =============================================================

WEBAPP_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")/webapp"

# Fallback for Render paths
if [ ! -d "$WEBAPP_DIR/node_modules" ]; then
  WEBAPP_DIR="/opt/render/project/src/ironforge/webapp"
fi
if [ ! -d "$WEBAPP_DIR/node_modules" ]; then
  WEBAPP_DIR="$HOME/project/src/ironforge/webapp"
fi

if [ ! -d "$WEBAPP_DIR/node_modules" ]; then
  echo "ERROR: Cannot find webapp/node_modules at any known path."
  echo "  Tried: $(dirname "$(dirname "$0")")/webapp, /opt/render/project/src/ironforge/webapp, ~/project/src/ironforge/webapp"
  echo ""
  echo "  Run from the webapp directory instead:"
  echo "    cd ~/project/src/ironforge/webapp && node scripts/diag.js"
  exit 1
fi

cd "$WEBAPP_DIR"
node scripts/diag.js
