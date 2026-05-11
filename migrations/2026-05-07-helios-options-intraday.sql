-- HELIOS — historical 1-min SPY option bars (ThetaData backfill, 2020-2025).
--
-- Pruned to ATM ± $10 strikes per trade_date so we don't store the full chain.
-- Indexed for two query patterns the backtest engine uses:
--   (a) point lookup by (trade_date, expiration, strike, right)
--   (b) intraday scan by (trade_date, bar_time)
--
-- New table only — no existing tables touched. Idempotent (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS helios_options_intraday (
    trade_date       DATE         NOT NULL,
    expiration_date  DATE         NOT NULL,
    strike           NUMERIC(8,2) NOT NULL,
    "right"          CHAR(1)      NOT NULL CHECK ("right" IN ('C','P')),
    bar_time         TIMESTAMPTZ  NOT NULL,
    open             NUMERIC(10,4),
    high             NUMERIC(10,4),
    low              NUMERIC(10,4),
    close            NUMERIC(10,4),
    volume           INTEGER,
    bid              NUMERIC(10,4),
    ask              NUMERIC(10,4),
    PRIMARY KEY (trade_date, expiration_date, strike, "right", bar_time)
);

CREATE INDEX IF NOT EXISTS ix_helios_options_intraday_lookup
    ON helios_options_intraday (trade_date, expiration_date, strike, "right");

CREATE INDEX IF NOT EXISTS ix_helios_options_intraday_time
    ON helios_options_intraday (trade_date, bar_time);
