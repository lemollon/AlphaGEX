-- ============================================================
-- Migration 011: Update SOLOMON config to Apache backtest parameters
-- Date: 2025-01-09
--
-- This migration updates SOLOMON to use the profitable parameters
-- discovered in the Apache GEX directional backtest.
-- ============================================================

-- Strategy params
INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'wall_filter_pct', '1.0')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '1.0', updated_at = NOW();

INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'min_rr_ratio', '1.5')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '1.5', updated_at = NOW();

-- Win probability thresholds (MUST be above 50% for positive expectancy)
INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'min_win_probability', '0.55')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '0.55', updated_at = NOW();

INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'min_confidence', '0.55')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '0.55', updated_at = NOW();

-- VIX filter (Apache backtest optimal range: 15-25)
INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'min_vix', '15.0')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '15.0', updated_at = NOW();

INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'max_vix', '25.0')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '25.0', updated_at = NOW();

-- GEX ratio asymmetry (need strong signal: >1.5 bearish, <0.67 bullish)
INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'min_gex_ratio_bearish', '1.5')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '1.5', updated_at = NOW();

INSERT INTO autonomous_config (bot_name, config_key, config_value)
VALUES ('SOLOMON', 'max_gex_ratio_bullish', '0.67')
ON CONFLICT (bot_name, config_key) DO UPDATE SET config_value = '0.67', updated_at = NOW();
