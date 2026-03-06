-- =============================================================================
-- IronForge Databricks SQL Table Setup
-- =============================================================================
-- Converts all PostgreSQL DDL from the Render version to Databricks SQL dialect.
--
-- Key differences from PostgreSQL:
--   - TIMESTAMPTZ → TIMESTAMP
--   - TEXT → STRING
--   - NUMERIC(p,s) → DECIMAL(p,s)
--   - SERIAL / GENERATED ALWAYS AS IDENTITY → BIGINT GENERATED ALWAYS AS IDENTITY
--   - No DEFAULT on columns in Delta Lake (handled in application layer)
--   - ON CONFLICT → MERGE INTO (handled in application layer)
--   - No UNIQUE constraints (disabled by default; enforced via MERGE INTO in app layer)
--   - No CREATE INDEX → use OPTIMIZE + ZORDER
--
-- Usage: Run this notebook once in your Databricks workspace to create all tables.
-- =============================================================================

-- Create catalog and schema
CREATE CATALOG IF NOT EXISTS alpha_prime;
USE CATALOG alpha_prime;
CREATE SCHEMA IF NOT EXISTS ironforge;
USE SCHEMA ironforge;

-- =============================================================================
-- Shared Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS bot_heartbeats (
  bot_name STRING NOT NULL,
  last_heartbeat TIMESTAMP,
  status STRING,
  scan_count BIGINT,
  details STRING,
  CONSTRAINT bot_heartbeats_pk PRIMARY KEY (bot_name)
);

-- =============================================================================
-- FLAME Bot Tables (2DTE Iron Condor)
-- =============================================================================

CREATE TABLE IF NOT EXISTS flame_paper_account (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  starting_capital DECIMAL(12,2) NOT NULL,
  current_balance DECIMAL(12,2) NOT NULL,
  cumulative_pnl DECIMAL(12,2),
  total_trades INT,
  collateral_in_use DECIMAL(12,2),
  buying_power DECIMAL(12,2) NOT NULL,
  high_water_mark DECIMAL(12,2) NOT NULL,
  max_drawdown DECIMAL(12,2),
  is_active BOOLEAN,
  dte_mode STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT flame_paper_account_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_positions (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  position_id STRING NOT NULL,
  ticker STRING NOT NULL,
  expiration DATE NOT NULL,
  put_short_strike DECIMAL(10,2) NOT NULL,
  put_long_strike DECIMAL(10,2) NOT NULL,
  put_credit DECIMAL(10,4) NOT NULL,
  call_short_strike DECIMAL(10,2) NOT NULL,
  call_long_strike DECIMAL(10,2) NOT NULL,
  call_credit DECIMAL(10,4) NOT NULL,
  contracts INT NOT NULL,
  spread_width DECIMAL(10,2) NOT NULL,
  total_credit DECIMAL(10,4) NOT NULL,
  max_loss DECIMAL(10,2) NOT NULL,
  max_profit DECIMAL(10,2) NOT NULL,
  collateral_required DECIMAL(10,2),
  underlying_at_entry DECIMAL(10,2) NOT NULL,
  vix_at_entry DECIMAL(6,2),
  expected_move DECIMAL(10,2),
  call_wall DECIMAL(10,2),
  put_wall DECIMAL(10,2),
  gex_regime STRING,
  flip_point DECIMAL(10,2),
  net_gex DECIMAL(15,2),
  oracle_confidence DECIMAL(5,4),
  oracle_win_probability DECIMAL(8,4),
  oracle_advice STRING,
  oracle_reasoning STRING,
  oracle_top_factors STRING,
  oracle_use_gex_walls BOOLEAN,
  wings_adjusted BOOLEAN,
  original_put_width DECIMAL(10,2),
  original_call_width DECIMAL(10,2),
  put_order_id STRING,
  call_order_id STRING,
  sandbox_order_id STRING,
  status STRING NOT NULL,
  open_time TIMESTAMP NOT NULL,
  open_date DATE,
  close_time TIMESTAMP,
  close_price DECIMAL(10,4),
  close_reason STRING,
  realized_pnl DECIMAL(10,2),
  dte_mode STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT flame_positions_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_signals (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  signal_time TIMESTAMP,
  spot_price DECIMAL(10,2),
  vix DECIMAL(6,2),
  expected_move DECIMAL(10,2),
  call_wall DECIMAL(10,2),
  put_wall DECIMAL(10,2),
  gex_regime STRING,
  put_short DECIMAL(10,2),
  put_long DECIMAL(10,2),
  call_short DECIMAL(10,2),
  call_long DECIMAL(10,2),
  total_credit DECIMAL(10,4),
  confidence DECIMAL(5,4),
  was_executed BOOLEAN,
  skip_reason STRING,
  reasoning STRING,
  wings_adjusted BOOLEAN,
  dte_mode STRING,
  CONSTRAINT flame_signals_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_equity_snapshots (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  snapshot_time TIMESTAMP,
  balance DECIMAL(12,2) NOT NULL,
  unrealized_pnl DECIMAL(12,2),
  realized_pnl DECIMAL(12,2),
  open_positions INT,
  note STRING,
  dte_mode STRING,
  created_at TIMESTAMP,
  CONSTRAINT flame_equity_snapshots_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  log_time TIMESTAMP,
  level STRING,
  message STRING,
  details STRING,
  dte_mode STRING,
  CONSTRAINT flame_logs_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_daily_perf (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date DATE NOT NULL,
  trades_executed INT,
  positions_closed INT,
  realized_pnl DECIMAL(10,2),
  updated_at TIMESTAMP,
  CONSTRAINT flame_daily_perf_pk PRIMARY KEY (id)
  -- Uniqueness on trade_date enforced via MERGE INTO in application layer
);

CREATE TABLE IF NOT EXISTS flame_pdt_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date DATE NOT NULL,
  symbol STRING NOT NULL,
  position_id STRING NOT NULL,
  opened_at TIMESTAMP NOT NULL,
  closed_at TIMESTAMP,
  is_day_trade BOOLEAN,
  contracts INT NOT NULL,
  entry_credit DECIMAL(10,4),
  exit_cost DECIMAL(10,4),
  pnl DECIMAL(10,2),
  close_reason STRING,
  dte_mode STRING,
  created_at TIMESTAMP,
  CONSTRAINT flame_pdt_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_pdt_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name STRING NOT NULL,
  pdt_enabled BOOLEAN,
  day_trade_count INT,
  max_day_trades INT,
  window_days INT,
  max_trades_per_day INT,
  last_reset_at TIMESTAMP,
  last_reset_by STRING,
  updated_at TIMESTAMP,
  created_at TIMESTAMP,
  CONSTRAINT flame_pdt_config_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_pdt_audit_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name STRING NOT NULL,
  action STRING NOT NULL,
  old_value STRING,
  new_value STRING,
  reason STRING,
  performed_by STRING,
  created_at TIMESTAMP,
  CONSTRAINT flame_pdt_audit_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS flame_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  dte_mode STRING NOT NULL,
  sd_multiplier DECIMAL(5,2),
  spread_width DECIMAL(5,2),
  min_credit DECIMAL(5,4),
  profit_target_pct DECIMAL(5,2),
  stop_loss_pct DECIMAL(5,2),
  vix_skip DECIMAL(5,2),
  max_contracts INT,
  max_trades_per_day INT,
  buying_power_usage_pct DECIMAL(5,4),
  risk_per_trade_pct DECIMAL(5,4),
  min_win_probability DECIMAL(5,4),
  entry_start STRING,
  entry_end STRING,
  eod_cutoff_et STRING,
  pdt_max_day_trades INT,
  starting_capital DECIMAL(12,2),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT flame_config_pk PRIMARY KEY (id)
  -- Uniqueness on dte_mode enforced via MERGE INTO in application layer
);

-- =============================================================================
-- SPARK Bot Tables (1DTE Iron Condor)
-- Identical schema to FLAME, different prefix.
-- =============================================================================

CREATE TABLE IF NOT EXISTS spark_paper_account (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  starting_capital DECIMAL(12,2) NOT NULL,
  current_balance DECIMAL(12,2) NOT NULL,
  cumulative_pnl DECIMAL(12,2),
  total_trades INT,
  collateral_in_use DECIMAL(12,2),
  buying_power DECIMAL(12,2) NOT NULL,
  high_water_mark DECIMAL(12,2) NOT NULL,
  max_drawdown DECIMAL(12,2),
  is_active BOOLEAN,
  dte_mode STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT spark_paper_account_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_positions (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  position_id STRING NOT NULL,
  ticker STRING NOT NULL,
  expiration DATE NOT NULL,
  put_short_strike DECIMAL(10,2) NOT NULL,
  put_long_strike DECIMAL(10,2) NOT NULL,
  put_credit DECIMAL(10,4) NOT NULL,
  call_short_strike DECIMAL(10,2) NOT NULL,
  call_long_strike DECIMAL(10,2) NOT NULL,
  call_credit DECIMAL(10,4) NOT NULL,
  contracts INT NOT NULL,
  spread_width DECIMAL(10,2) NOT NULL,
  total_credit DECIMAL(10,4) NOT NULL,
  max_loss DECIMAL(10,2) NOT NULL,
  max_profit DECIMAL(10,2) NOT NULL,
  collateral_required DECIMAL(10,2),
  underlying_at_entry DECIMAL(10,2) NOT NULL,
  vix_at_entry DECIMAL(6,2),
  expected_move DECIMAL(10,2),
  call_wall DECIMAL(10,2),
  put_wall DECIMAL(10,2),
  gex_regime STRING,
  flip_point DECIMAL(10,2),
  net_gex DECIMAL(15,2),
  oracle_confidence DECIMAL(5,4),
  oracle_win_probability DECIMAL(8,4),
  oracle_advice STRING,
  oracle_reasoning STRING,
  oracle_top_factors STRING,
  oracle_use_gex_walls BOOLEAN,
  wings_adjusted BOOLEAN,
  original_put_width DECIMAL(10,2),
  original_call_width DECIMAL(10,2),
  put_order_id STRING,
  call_order_id STRING,
  sandbox_order_id STRING,
  status STRING NOT NULL,
  open_time TIMESTAMP NOT NULL,
  open_date DATE,
  close_time TIMESTAMP,
  close_price DECIMAL(10,4),
  close_reason STRING,
  realized_pnl DECIMAL(10,2),
  dte_mode STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT spark_positions_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_signals (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  signal_time TIMESTAMP,
  spot_price DECIMAL(10,2),
  vix DECIMAL(6,2),
  expected_move DECIMAL(10,2),
  call_wall DECIMAL(10,2),
  put_wall DECIMAL(10,2),
  gex_regime STRING,
  put_short DECIMAL(10,2),
  put_long DECIMAL(10,2),
  call_short DECIMAL(10,2),
  call_long DECIMAL(10,2),
  total_credit DECIMAL(10,4),
  confidence DECIMAL(5,4),
  was_executed BOOLEAN,
  skip_reason STRING,
  reasoning STRING,
  wings_adjusted BOOLEAN,
  dte_mode STRING,
  CONSTRAINT spark_signals_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_equity_snapshots (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  snapshot_time TIMESTAMP,
  balance DECIMAL(12,2) NOT NULL,
  unrealized_pnl DECIMAL(12,2),
  realized_pnl DECIMAL(12,2),
  open_positions INT,
  note STRING,
  dte_mode STRING,
  created_at TIMESTAMP,
  CONSTRAINT spark_equity_snapshots_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  log_time TIMESTAMP,
  level STRING,
  message STRING,
  details STRING,
  dte_mode STRING,
  CONSTRAINT spark_logs_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_daily_perf (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date DATE NOT NULL,
  trades_executed INT,
  positions_closed INT,
  realized_pnl DECIMAL(10,2),
  updated_at TIMESTAMP,
  CONSTRAINT spark_daily_perf_pk PRIMARY KEY (id)
  -- Uniqueness on trade_date enforced via MERGE INTO in application layer
);

CREATE TABLE IF NOT EXISTS spark_pdt_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  trade_date DATE NOT NULL,
  symbol STRING NOT NULL,
  position_id STRING NOT NULL,
  opened_at TIMESTAMP NOT NULL,
  closed_at TIMESTAMP,
  is_day_trade BOOLEAN,
  contracts INT NOT NULL,
  entry_credit DECIMAL(10,4),
  exit_cost DECIMAL(10,4),
  pnl DECIMAL(10,2),
  close_reason STRING,
  dte_mode STRING,
  created_at TIMESTAMP,
  CONSTRAINT spark_pdt_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_pdt_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name STRING NOT NULL,
  pdt_enabled BOOLEAN,
  day_trade_count INT,
  max_day_trades INT,
  window_days INT,
  max_trades_per_day INT,
  last_reset_at TIMESTAMP,
  last_reset_by STRING,
  updated_at TIMESTAMP,
  created_at TIMESTAMP,
  CONSTRAINT spark_pdt_config_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_pdt_audit_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  bot_name STRING NOT NULL,
  action STRING NOT NULL,
  old_value STRING,
  new_value STRING,
  reason STRING,
  performed_by STRING,
  created_at TIMESTAMP,
  CONSTRAINT spark_pdt_audit_log_pk PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS spark_config (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  dte_mode STRING NOT NULL,
  sd_multiplier DECIMAL(5,2),
  spread_width DECIMAL(5,2),
  min_credit DECIMAL(5,4),
  profit_target_pct DECIMAL(5,2),
  stop_loss_pct DECIMAL(5,2),
  vix_skip DECIMAL(5,2),
  max_contracts INT,
  max_trades_per_day INT,
  buying_power_usage_pct DECIMAL(5,4),
  risk_per_trade_pct DECIMAL(5,4),
  min_win_probability DECIMAL(5,4),
  entry_start STRING,
  entry_end STRING,
  eod_cutoff_et STRING,
  pdt_max_day_trades INT,
  starting_capital DECIMAL(12,2),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  CONSTRAINT spark_config_pk PRIMARY KEY (id)
  -- Uniqueness on dte_mode enforced via MERGE INTO in application layer
);

-- =============================================================================
-- Seed Paper Accounts (starting capital $10,000 per bot)
-- =============================================================================

MERGE INTO flame_paper_account AS t
USING (SELECT '2DTE' AS dte_mode) AS s
ON t.dte_mode = s.dte_mode AND t.is_active = TRUE
WHEN NOT MATCHED THEN INSERT (
  starting_capital, current_balance, cumulative_pnl, total_trades,
  collateral_in_use, buying_power, high_water_mark, max_drawdown,
  is_active, dte_mode, created_at, updated_at
) VALUES (
  10000, 10000, 0, 0, 0, 10000, 10000, 0,
  TRUE, '2DTE', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO spark_paper_account AS t
USING (SELECT '1DTE' AS dte_mode) AS s
ON t.dte_mode = s.dte_mode AND t.is_active = TRUE
WHEN NOT MATCHED THEN INSERT (
  starting_capital, current_balance, cumulative_pnl, total_trades,
  collateral_in_use, buying_power, high_water_mark, max_drawdown,
  is_active, dte_mode, created_at, updated_at
) VALUES (
  10000, 10000, 0, 0, 0, 10000, 10000, 0,
  TRUE, '1DTE', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

-- =============================================================================
-- Seed PDT Config (one row per bot)
-- =============================================================================

MERGE INTO flame_pdt_config AS t
USING (SELECT 'FLAME' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'FLAME', TRUE, 0, 3, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

MERGE INTO spark_pdt_config AS t
USING (SELECT 'SPARK' AS bot_name) AS s
ON t.bot_name = s.bot_name
WHEN NOT MATCHED THEN INSERT (
  bot_name, pdt_enabled, day_trade_count, max_day_trades,
  window_days, max_trades_per_day, created_at, updated_at
) VALUES (
  'SPARK', TRUE, 0, 3, 5, 1,
  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
);

-- =============================================================================
-- Optimize tables for common query patterns
-- Run these AFTER data has been inserted (not on empty tables).
-- =============================================================================
-- OPTIMIZE flame_positions ZORDER BY (status, dte_mode, open_time);
-- OPTIMIZE spark_positions ZORDER BY (status, dte_mode, open_time);
-- OPTIMIZE flame_equity_snapshots ZORDER BY (dte_mode, snapshot_time);
-- OPTIMIZE spark_equity_snapshots ZORDER BY (dte_mode, snapshot_time);
-- OPTIMIZE flame_logs ZORDER BY (dte_mode, log_time);
-- OPTIMIZE spark_logs ZORDER BY (dte_mode, log_time);
