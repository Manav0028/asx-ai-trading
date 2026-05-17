-- =============================================================================
-- AI Trading System — Supabase Cloud Tables Setup
-- Run this once in: Supabase Dashboard → SQL Editor → New Query → Run
-- Project: AITrading (bhztefmozidvfqmjepwa.supabase.co)
-- =============================================================================

-- 1. Signals — daily composite scores per ticker per exchange
CREATE TABLE IF NOT EXISTS signals (
    ticker              TEXT        NOT NULL,
    date                DATE        NOT NULL,
    exchange            TEXT        NOT NULL,   -- 'asx' | 'nse'
    composite_score     FLOAT,
    sentiment_score     FLOAT,
    fundamental_score   FLOAT,
    technical_score     FLOAT,
    insider_score       FLOAT,
    regime_ok           BOOLEAN,
    position_size_aud   FLOAT,
    entry_price         FLOAT,
    target_price        FLOAT,
    stop_loss_price     FLOAT,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS ix_signals_exchange_date
    ON signals (exchange, date, composite_score DESC);

-- 2. Watchlist — active open positions per exchange
CREATE TABLE IF NOT EXISTS watchlist (
    ticker              TEXT        NOT NULL PRIMARY KEY,
    exchange            TEXT        NOT NULL,
    entry_date          DATE,
    entry_price         FLOAT,
    current_price       FLOAT,
    target_price        FLOAT,
    stop_loss_price     FLOAT,
    shares              FLOAT,
    position_size_aud   FLOAT,
    unrealised_pnl      FLOAT,
    unrealised_pnl_pct  FLOAT,
    days_held           INTEGER,
    signal_score        FLOAT,
    is_active           BOOLEAN     DEFAULT TRUE,
    synced_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_watchlist_exchange
    ON watchlist (exchange, is_active);

-- 3. Trades — closed trade history per exchange (last 90 days)
CREATE TABLE IF NOT EXISTS trades (
    ticker              TEXT        NOT NULL,
    exchange            TEXT        NOT NULL,
    trade_type          TEXT,
    mode                TEXT        DEFAULT 'paper',
    entry_date          DATE,
    exit_date           DATE,
    entry_price         FLOAT,
    exit_price          FLOAT,
    shares              FLOAT,
    gross_pnl           FLOAT,
    net_pnl             FLOAT,
    brokerage           FLOAT,
    exit_reason         TEXT,
    signal_score        FLOAT,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, entry_date, trade_type)
);

CREATE INDEX IF NOT EXISTS ix_trades_exchange_exit
    ON trades (exchange, exit_date DESC);

-- 4. Regime — latest market regime status per exchange (one row per exchange)
CREATE TABLE IF NOT EXISTS regime (
    exchange            TEXT        NOT NULL PRIMARY KEY,
    regime_ok           BOOLEAN,
    index_val           FLOAT,
    index_name          TEXT,
    ema200              FLOAT,
    pct_above           FLOAT,
    synced_at           TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Backtest cache — Sunday walk-forward results per exchange
CREATE TABLE IF NOT EXISTS backtest_cache (
    exchange            TEXT        NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    results_json        JSONB       NOT NULL,
    PRIMARY KEY (exchange, computed_at)
);

CREATE INDEX IF NOT EXISTS ix_backtest_exchange_time
    ON backtest_cache (exchange, computed_at DESC);

-- =============================================================================
-- Row Level Security — allow anon (publishable) key to read all tables
-- The scheduler uses the service role key and bypasses RLS automatically.
-- =============================================================================

ALTER TABLE signals       ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist     ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades        ENABLE ROW LEVEL SECURITY;
ALTER TABLE regime        ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_cache ENABLE ROW LEVEL SECURITY;

-- Drop old policies if re-running this script
DROP POLICY IF EXISTS "allow anon read" ON signals;
DROP POLICY IF EXISTS "allow anon read" ON watchlist;
DROP POLICY IF EXISTS "allow anon read" ON trades;
DROP POLICY IF EXISTS "allow anon read" ON regime;
DROP POLICY IF EXISTS "allow anon read" ON backtest_cache;

-- Create read policies for publishable (anon) key used by Streamlit Cloud
CREATE POLICY "allow anon read" ON signals         FOR SELECT USING (true);
CREATE POLICY "allow anon read" ON watchlist       FOR SELECT USING (true);
CREATE POLICY "allow anon read" ON trades          FOR SELECT USING (true);
CREATE POLICY "allow anon read" ON regime          FOR SELECT USING (true);
CREATE POLICY "allow anon read" ON backtest_cache  FOR SELECT USING (true);

-- =============================================================================
-- Verify setup
-- =============================================================================
SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('signals', 'watchlist', 'trades', 'regime', 'backtest_cache')
ORDER BY table_name;
