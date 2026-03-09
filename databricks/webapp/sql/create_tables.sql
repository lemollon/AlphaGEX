-- =============================================================================
-- IronForge: Additional Delta Lake Tables
-- PDT Config, PDT Audit Log, Sandbox Accounts
-- =============================================================================
-- Run this in Databricks SQL editor. All CREATE TABLE use IF NOT EXISTS.
-- Table naming follows existing convention: alpha_prime.ironforge.{table_name}
-- =============================================================================

USE CATALOG alpha_prime;
USE SCHEMA ironforge;

-- =============================================================================
-- PDT Config — per-bot PDT enforcement state
-- =============================================================================

CREATE TABLE IF NOT EXISTS ironforge_pdt_config (
  bot_name STRING NOT NULL,
  pdt_enabled BOOLEAN,
  day_trade_count INT,
  max_day_trades INT,
  window_days INT,
  max_trades_per_day INT,
  last_reset_at TIMESTAMP,
  last_reset_by STRING,
  updated_at TIMESTAMP,
  created_at TIMESTAMP
) USING DELTA;

-- =============================================================================
-- PDT Audit Log — tracks all PDT state changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS ironforge_pdt_log (
  log_id STRING NOT NULL,
  bot_name STRING NOT NULL,
  action STRING NOT NULL,
  old_value STRING,
  new_value STRING,
  reason STRING,
  performed_by STRING,
  created_at TIMESTAMP
) USING DELTA;

-- =============================================================================
-- Sandbox Accounts — Tradier sandbox accounts for order mirroring
-- =============================================================================

CREATE TABLE IF NOT EXISTS ironforge_sandbox_accounts (
  account_id STRING NOT NULL,
  api_key STRING NOT NULL,
  owner_name STRING NOT NULL,
  bot_name STRING NOT NULL,
  is_active BOOLEAN,
  notes STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
) USING DELTA;

-- =============================================================================
-- Seed PDT Config
-- =============================================================================

MERGE INTO ironforge_pdt_config AS t
USING (SELECT 'FLAME' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'FLAME', true, 0, 3, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO ironforge_pdt_config AS t
USING (SELECT 'SPARK' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'SPARK', true, 0, 3, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

-- =============================================================================
-- Seed Sandbox Accounts (existing accounts from scanner Cell 1)
-- =============================================================================

MERGE INTO ironforge_sandbox_accounts AS t
USING (SELECT 'VA39284047' AS account_id) AS s
ON t.account_id = s.account_id
WHEN NOT MATCHED THEN INSERT (
  account_id, api_key, owner_name, bot_name, is_active, notes, created_at, updated_at
) VALUES (
  'VA39284047', 'iPidGGnYrhzjp6vGBBQw8HyqF0xj', 'User', 'BOTH', true,
  'Primary sandbox', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO ironforge_sandbox_accounts AS t
USING (SELECT 'VA55391129' AS account_id) AS s
ON t.account_id = s.account_id
WHEN NOT MATCHED THEN INSERT (
  account_id, api_key, owner_name, bot_name, is_active, notes, created_at, updated_at
) VALUES (
  'VA55391129', 'AGoNTv6o6GKMKT8uc7ooVNOct0e0', 'Matt', 'FLAME', true,
  NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO ironforge_sandbox_accounts AS t
USING (SELECT 'VA59240884' AS account_id) AS s
ON t.account_id = s.account_id
WHEN NOT MATCHED THEN INSERT (
  account_id, api_key, owner_name, bot_name, is_active, notes, created_at, updated_at
) VALUES (
  'VA59240884', 'AcDucIMyjeNgFh60LWOb0F5fhXHh', 'Logan', 'FLAME', true,
  NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);
