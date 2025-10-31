-- Migration 0001: Initialize Market Data Schema
-- TimescaleDB extension for time-series data

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Candles table for storing OHLCV data
CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    quote_volume DECIMAL(30, 8),
    trades_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, interval, timestamp)
);

-- Convert candles to hypertable (if TimescaleDB is available)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('candles', 'timestamp', if_not_exists => TRUE);
    END IF;
END $$;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval 
    ON candles(symbol, interval);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_timestamp 
    ON candles(symbol, timestamp DESC);

-- Features table for technical indicators
CREATE TABLE IF NOT EXISTS features (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Price features
    ema_9 DECIMAL(20, 8),
    ema_21 DECIMAL(20, 8),
    ema_50 DECIMAL(20, 8),
    ema_200 DECIMAL(20, 8),
    
    -- Momentum indicators
    rsi_14 DECIMAL(10, 4),
    macd DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    macd_histogram DECIMAL(20, 8),
    
    -- Volatility indicators
    atr_14 DECIMAL(20, 8),
    bollinger_upper DECIMAL(20, 8),
    bollinger_middle DECIMAL(20, 8),
    bollinger_lower DECIMAL(20, 8),
    
    -- Volume indicators
    volume_sma DECIMAL(30, 8),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, interval, timestamp)
);

-- Convert features to hypertable (if TimescaleDB is available)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('features', 'timestamp', if_not_exists => TRUE);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_features_symbol_timestamp 
    ON features(symbol, timestamp DESC);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_candles_updated_at 
    BEFORE UPDATE ON candles 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

