-- Migration 029: GOLIATH material-news flag table
--
-- Per master spec section 4 trigger 6 + Leron Q5 (2026-04-29):
-- material-news flagging is a manual CLI action on the Render shell.
-- A flag persists until manually cleared; while present, T6 fires
-- on every management cycle for any open position on that ticker.
--
-- Ticker is the *underlying* per spec (TSLA news -> close TSLL position).

CREATE TABLE IF NOT EXISTS goliath_news_flags (
    ticker      VARCHAR(10) PRIMARY KEY,
    reason      TEXT NOT NULL DEFAULT '',
    flagged_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flagged_by  TEXT NOT NULL DEFAULT 'cli'
);

COMMENT ON TABLE goliath_news_flags IS
    'Manual material-news flags driving T6 trigger fires. '
    'CLI-managed (trading.goliath.management.cli). One row per '
    'ticker; presence = active flag; row removal = unflag.';
