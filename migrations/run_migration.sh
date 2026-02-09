#!/bin/bash
# =============================================================================
# Run bot rename migration (idempotent - safe to run multiple times)
# =============================================================================
# Usage from Render shell:
#   curl -sL https://raw.githubusercontent.com/lemollon/AlphaGEX/claude/bot-name-mapping-Jdf6H/migrations/run_migration.sh | bash
# =============================================================================

export DB="postgresql://alphagex_user:ia5KWqhz4wfwsjiQxlPEGMfgftYT6Du1@dpg-d4132pje5dus738rkoug-a.oregon-postgres.render.com/alphagex"
export R="https://raw.githubusercontent.com/lemollon/AlphaGEX/claude/bot-name-mapping-Jdf6H"

echo "=== Downloading migration files ==="
curl -sL "$R/migrations/bot_rename_migration_v4_idempotent.sql" -o /tmp/migrate.sql
curl -sL "$R/migrations/post_migration_check.sql" -o /tmp/check.sql

echo "=== Files downloaded ==="
wc -l /tmp/migrate.sql /tmp/check.sql

echo ""
echo "=== Running idempotent migration v4 ==="
psql "$DB" -f /tmp/migrate.sql

echo ""
echo "=== Running post-migration check ==="
PAGER=cat psql "$DB" -f /tmp/check.sql

echo ""
echo "=== ALL DONE ==="
