-- Migration 0002: Initialize Model Registry Schema

-- Models table for storing trading strategies
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL,
    description TEXT,
    model_type VARCHAR(50) NOT NULL, -- 'rule-based', 'ml', 'ensemble'
    
    -- Model configuration (JSONB for flexibility)
    config JSONB NOT NULL,
    
    -- Performance metrics
    sharpe_ratio DECIMAL(10, 4),
    profit_factor DECIMAL(10, 4),
    win_rate DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),
    total_return_pct DECIMAL(10, 4),
    total_trades INTEGER,
    
    -- Training metadata
    training_period_start TIMESTAMPTZ,
    training_period_end TIMESTAMPTZ,
    validation_period_start TIMESTAMPTZ,
    validation_period_end TIMESTAMPTZ,
    
    -- Status
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'testing', 'approved', 'active', 'archived'
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(name, version)
);

-- Model parameters for detailed configuration
CREATE TABLE IF NOT EXISTS model_parameters (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    parameter_name VARCHAR(100) NOT NULL,
    parameter_value DECIMAL(20, 8) NOT NULL,
    parameter_type VARCHAR(20) NOT NULL, -- 'integer', 'decimal', 'boolean'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(model_id, parameter_name)
);

-- Model performance history for tracking over time
CREATE TABLE IF NOT EXISTS model_performance (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Daily metrics
    daily_return_pct DECIMAL(10, 4),
    daily_trades INTEGER,
    daily_win_rate DECIMAL(10, 4),
    daily_pnl_usdt DECIMAL(20, 8),
    
    -- Running totals
    total_return_pct DECIMAL(10, 4),
    total_trades INTEGER,
    total_pnl_usdt DECIMAL(20, 8),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(model_id, date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_models_status ON models(status);
CREATE INDEX IF NOT EXISTS idx_models_created_at ON models(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_params_model_id ON model_parameters(model_id);
CREATE INDEX IF NOT EXISTS idx_model_perf_model_date ON model_performance(model_id, date DESC);

-- Trigger for updated_at
CREATE TRIGGER update_models_updated_at 
    BEFORE UPDATE ON models 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

