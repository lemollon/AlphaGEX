#!/bin/bash
# Run bot rename migration v2
export DATABASE_URL="postgresql://alphagex_user:ia5KWqhz4wfwsjiQxlPEGMfgftYT6Du1@dpg-d4132pje5dus738rkoug-a.oregon-postgres.render.com/alphagex"

echo "=== Running bot_rename_migration_v2.sql ==="
psql "$DATABASE_URL" -f migrations/bot_rename_migration_v2.sql

echo ""
echo "=== Running post_migration_check.sql ==="
psql "$DATABASE_URL" -f migrations/post_migration_check.sql
