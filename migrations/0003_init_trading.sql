-- Migration 0003: Initialize Trading Schema

-- Signals table for trading signals
CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL, -- 'BUY', 'SELL', 'HOLD'
    signal_strength DECIMAL(10, 4), -- 0.0 to 1.0
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Market context
    price DECIMAL(20, 8) NOT NULL,
    features JSONB,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'sent', 'filled', 'rejected', 'expired'
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

-- Indexes for signals
CREATE INDEX IF NOT EXISTS idx_signals_model_id ON signals(model_id);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_timestamp ON signals(symbol, timestamp DESC);

-- Orders table for executed orders
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES signals(id) ON DELETE RESTRICT,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    
    -- Order details
    order_id VARCHAR(100) UNIQUE, -- OKX order ID
    client_order_id VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell'
    order_type VARCHAR(20) NOT NULL, -- 'market', 'limit'
    
    -- Execution details
    price DECIMAL(20, 8) NOT NULL,
    filled_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8) NOT NULL,
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    
    -- Fees and slippage
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10),
    slippage_pct DECIMAL(10, 6),
    
    -- Status
    status VARCHAR(20) NOT NULL, -- 'pending', 'partially_filled', 'filled', 'cancelled', 'rejected'
    
    -- Mode
    mode VARCHAR(20) NOT NULL DEFAULT 'paper', -- 'paper', 'shadow', 'live'
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ,
    
    -- OKX metadata
    okx_response JSONB
);

-- Indexes for orders
CREATE INDEX IF NOT EXISTS idx_orders_signal_id ON orders(signal_id);
CREATE INDEX IF NOT EXISTS idx_orders_model_id ON orders(model_id);
CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_okx_order_id ON orders(order_id);

-- Positions table for current positions
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    symbol VARCHAR(20) NOT NULL,
    
    -- Position details
    side VARCHAR(10) NOT NULL, -- 'long', 'short'
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    
    -- Current values
    current_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    unrealized_pnl_pct DECIMAL(10, 4),
    
    -- Mode
    mode VARCHAR(20) NOT NULL DEFAULT 'paper',
    
    -- Timestamps
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    
    UNIQUE(model_id, symbol)
);

-- Indexes for positions
CREATE INDEX IF NOT EXISTS idx_positions_model_id ON positions(model_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(opened_at DESC) WHERE closed_at IS NULL;

-- Trades table for completed round trips
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    position_id INTEGER REFERENCES positions(id) ON DELETE RESTRICT,
    
    -- Entry
    entry_signal_id BIGINT REFERENCES signals(id),
    entry_order_id BIGINT REFERENCES orders(id),
    entry_price DECIMAL(20, 8) NOT NULL,
    entry_quantity DECIMAL(20, 8) NOT NULL,
    entry_fee DECIMAL(20, 8) DEFAULT 0,
    
    -- Exit
    exit_signal_id BIGINT REFERENCES signals(id),
    exit_order_id BIGINT REFERENCES orders(id),
    exit_price DECIMAL(20, 8),
    exit_quantity DECIMAL(20, 8),
    exit_fee DECIMAL(20, 8) DEFAULT 0,
    
    -- PnL
    pnl_usdt DECIMAL(20, 8),
    pnl_pct DECIMAL(10, 4),
    total_fee DECIMAL(20, 8),
    
    -- Metadata
    duration_minutes INTEGER,
    symbol VARCHAR(20) NOT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'paper',
    
    -- Timestamps
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);

-- Indexes for trades
CREATE INDEX IF NOT EXISTS idx_trades_model_id ON trades(model_id);
CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_closed_at ON trades(symbol, closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades(pnl_usdt DESC);

-- Performance summary table for aggregated metrics
CREATE TABLE IF NOT EXISTS performance_summary (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    
    -- Period
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    period_type VARCHAR(20) NOT NULL, -- 'daily', 'weekly', 'monthly', 'all-time'
    
    -- Metrics
    total_pnl_usdt DECIMAL(20, 8),
    total_return_pct DECIMAL(10, 4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(10, 4),
    avg_win DECIMAL(20, 8),
    avg_loss DECIMAL(20, 8),
    profit_factor DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),
    max_drawdown_duration_days INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(model_id, period_start, period_end, period_type)
);

-- Indexes for performance summary
CREATE INDEX IF NOT EXISTS idx_perf_summary_model ON performance_summary(model_id);
CREATE INDEX IF NOT EXISTS idx_perf_summary_period ON performance_summary(period_start DESC, period_end DESC);

-- System state table for tracking circuit breakers and kill switches
CREATE TABLE IF NOT EXISTS system_state (
    id SERIAL PRIMARY KEY,
    
    -- Circuit breaker state
    circuit_breaker_active BOOLEAN DEFAULT FALSE,
    circuit_breaker_reason TEXT,
    circuit_breaker_activated_at TIMESTAMPTZ,
    
    -- Kill switch state
    kill_switch_active BOOLEAN DEFAULT FALSE,
    kill_switch_reason TEXT,
    kill_switch_activated_at TIMESTAMPTZ,
    
    -- Daily limits
    daily_pnl_usdt DECIMAL(20, 8) DEFAULT 0,
    daily_trades_count INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    
    -- Timestamps
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Initialize system state
INSERT INTO system_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Trigger for updated_at
CREATE TRIGGER update_positions_updated_at 
    BEFORE UPDATE ON positions 
    FOR EACH ROW 
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at 
    BEFORE UPDATE ON orders 
    FOR EACH ROW 
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION update_updated_at_column();

