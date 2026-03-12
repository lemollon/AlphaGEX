-- =============================================================================
-- IronForge PDT Tables — Databricks SQL
-- =============================================================================
-- Creates the SHARED ironforge_pdt_config table (missing from 01_setup_tables.sql)
-- and re-creates per-bot pdt_log + pdt_audit_log with IF NOT EXISTS safety.
--
-- Paste this entire file into Databricks SQL Editor and run.
-- Safe to re-run — all CREATE TABLE use IF NOT EXISTS, all seeds use MERGE.
-- =============================================================================

USE CATALOG alpha_prime;
USE SCHEMA ironforge;

-- =============================================================================
-- 1. SHARED TABLE: ironforge_pdt_config
--    This is the table the webapp reads/writes via sharedTable('ironforge_pdt_config')
--    → alpha_prime.ironforge.ironforge_pdt_config
-- =============================================================================

CREATE TABLE IF NOT EXISTS ironforge_pdt_config (
  id                BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name          STRING NOT NULL,
  pdt_enabled       BOOLEAN,
  day_trade_count   INT,
  max_day_trades    INT,
  window_days       INT,
  max_trades_per_day INT,
  last_reset_at     TIMESTAMP,
  last_reset_by     STRING,
  updated_at        TIMESTAMP,
  created_at        TIMESTAMP,
  CONSTRAINT ironforge_pdt_config_pk PRIMARY KEY (id)
);

-- =============================================================================
-- 2. PER-BOT TABLES: {bot}_pdt_log
--    Written by the scanner. Read by the webapp.
--    botTable(bot, 'pdt_log') → alpha_prime.ironforge.{bot}_pdt_log
--
--    Columns queried by pdt/route.ts:
--      SELECT: trade_date, position_id, is_day_trade, dte_mode, created_at, opened_at
--      UPDATE: is_day_trade
--      WHERE:  is_day_trade, dte_mode, trade_date, created_at
-- =============================================================================

CREATE TABLE IF NOT EXISTS flame_pdt_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date    DATE NOT NULL,
  symbol        STRING NOT NULL,
  position_id   STRING NOT NULL,
  opened_at     TIMESTAMP NOT NULL,
  closed_at     TIMESTAMP,
  is_day_trade  BOOLEAN,
  contracts     INT NOT NULL,
  entry_credit  DECIMAL(10,4),
  exit_cost     DECIMAL(10,4),
  pnl           DECIMAL(10,2),
  close_reason  STRING,
  dte_mode      STRING,
  created_at    TIMESTAMP,
  CONSTRAINT flame_pdt_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_pdt_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date    DATE NOT NULL,
  symbol        STRING NOT NULL,
  position_id   STRING NOT NULL,
  opened_at     TIMESTAMP NOT NULL,
  closed_at     TIMESTAMP,
  is_day_trade  BOOLEAN,
  contracts     INT NOT NULL,
  entry_credit  DECIMAL(10,4),
  exit_cost     DECIMAL(10,4),
  pnl           DECIMAL(10,2),
  close_reason  STRING,
  dte_mode      STRING,
  created_at    TIMESTAMP,
  CONSTRAINT spark_pdt_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS inferno_pdt_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date    DATE NOT NULL,
  symbol        STRING NOT NULL,
  position_id   STRING NOT NULL,
  opened_at     TIMESTAMP NOT NULL,
  closed_at     TIMESTAMP,
  is_day_trade  BOOLEAN,
  contracts     INT NOT NULL,
  entry_credit  DECIMAL(10,4),
  exit_cost     DECIMAL(10,4),
  pnl           DECIMAL(10,2),
  close_reason  STRING,
  dte_mode      STRING,
  created_at    TIMESTAMP,
  CONSTRAINT inferno_pdt_log_pk PRIMARY KEY (id)
);

-- =============================================================================
-- 3. PER-BOT TABLES: {bot}_pdt_audit_log
--    Written by the webapp (toggle/reset actions). Read by pdt/audit/route.ts.
--    botTable(bot, 'pdt_audit_log') → alpha_prime.ironforge.{bot}_pdt_audit_log
--
--    Columns used by both pdt/route.ts and pdt/audit/route.ts:
--      INSERT: bot_name, action, old_value, new_value, reason, performed_by, created_at
--      SELECT: action, old_value, new_value, reason, performed_by, created_at
--      WHERE:  bot_name
-- =============================================================================

CREATE TABLE IF NOT EXISTS flame_pdt_audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name      STRING NOT NULL,
  action        STRING NOT NULL,
  old_value     STRING,
  new_value     STRING,
  reason        STRING,
  performed_by  STRING,
  created_at    TIMESTAMP,
  CONSTRAINT flame_pdt_audit_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_pdt_audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name      STRING NOT NULL,
  action        STRING NOT NULL,
  old_value     STRING,
  new_value     STRING,
  reason        STRING,
  performed_by  STRING,
  created_at    TIMESTAMP,
  CONSTRAINT spark_pdt_audit_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS inferno_pdt_audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name      STRING NOT NULL,
  action        STRING NOT NULL,
  old_value     STRING,
  new_value     STRING,
  reason        STRING,
  performed_by  STRING,
  created_at    TIMESTAMP,
  CONSTRAINT inferno_pdt_audit_log_pk PRIMARY KEY (id)
);

-- =============================================================================
-- 4. SEED: ironforge_pdt_config — one row per bot
--    FLAME/SPARK: max 1 trade/day, 4 day trades / 5 rolling biz days
--    INFERNO:     max 3 trades/day (FORTRESS-style), same PDT window
-- =============================================================================

MERGE INTO ironforge_pdt_config AS t
USING (SELECT 'FLAME' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'FLAME', TRUE, 0, 4, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO ironforge_pdt_config AS t
USING (SELECT 'SPARK' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'SPARK', TRUE, 0, 4, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO ironforge_pdt_config AS t
USING (SELECT 'INFERNO' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'INFERNO', TRUE, 0, 4, 5, 3,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

-- =============================================================================
-- 5. VERIFY: Quick sanity check after running
-- =============================================================================

SELECT 'ironforge_pdt_config' AS table_name, COUNT(*) AS rows FROM ironforge_pdt_config
UNION ALL
SELECT 'flame_pdt_log', COUNT(*) FROM flame_pdt_log
UNION ALL
SELECT 'spark_pdt_log', COUNT(*) FROM spark_pdt_log
UNION ALL
SELECT 'inferno_pdt_log', COUNT(*) FROM inferno_pdt_log
UNION ALL
SELECT 'flame_pdt_audit_log', COUNT(*) FROM flame_pdt_audit_log
UNION ALL
SELECT 'spark_pdt_audit_log', COUNT(*) FROM spark_pdt_audit_log
UNION ALL
SELECT 'inferno_pdt_audit_log', COUNT(*) FROM inferno_pdt_audit_log;
