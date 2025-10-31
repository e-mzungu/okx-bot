# Architecture Overview

## System Design

The BTC Trading Platform follows a microservices architecture with clear separation of concerns and async event-driven communication.

## Component Architecture

### 1. **Ingestor Service**
**Purpose**: Collects and stores market data from OKX

**Responsibilities**:
- Fetch historical OHLCV data via REST API
- Stream live 1-minute candles
- Store data in TimescaleDB (hypertable)
- Publish candles to Redis Streams

**Technology Stack**:
- `httpx` for HTTP requests
- TimescaleDB for time-series storage
- Redis Streams for real-time events

**Key Features**:
- Automatic backfill on startup
- Configurable history depth (default: 180 days)
- Rate limiting protection
- Bulk inserts for performance

### 2. **ModelGen Service**
**Purpose**: Trains and validates trading strategies

**Responsibilities**:
- Calculate technical indicators (EMA, RSI, MACD, ATR, Bollinger Bands)
- Generate trading signals from historical data
- Backtest strategies with walk-forward validation
- Evaluate performance metrics (Sharpe, win rate, drawdown)
- Save approved models to database

**Strategies Implemented**:
1. **EMA + RSI**: Golden/death cross with momentum confirmation
2. **MACD + Bollinger Bands**: Mean reversion with trend confirmation

**Technology Stack**:
- `pandas` for data manipulation
- `pandas_ta` for technical indicators
- `scikit-learn` for statistical analysis

**Performance Metrics**:
- Sharpe ratio >= 1.2
- Win rate >= 45%
- Profit factor >= 1.5
- Max drawdown <= 15%

### 3. **Executor Service**
**Purpose**: Runs active model in real-time

**Responsibilities**:
- Subscribe to candle stream
- Calculate features for each new candle
- Generate BUY/SELL signals based on model
- Publish signals to Redis Streams
- Rate limiting (max signals per minute)

**Technology Stack**:
- Real-time feature calculation with `pandas_ta`
- Redis Streams for pub/sub
- Async I/O for responsiveness

**Signal Logic**:
- Loads active model from database
- Calculates technical indicators on-demand
- Applies model-specific signal rules
- Includes signal strength scoring

### 4. **Trader Service**
**Purpose**: Executes trading signals with risk management

**Responsibilities**:
- Listen to signal stream
- Validate risk limits
- Execute orders (paper/live)
- Update positions and PnL
- Implement circuit breakers

**Modes**:
- **Paper**: Simulates orders locally with slippage/fees
- **Shadow**: Live data but no execution
- **Live**: Real orders to OKX

**Risk Management**:
- Position size limits
- Daily loss limits
- Consecutive loss protection
- Kill switch for emergencies

**Technology Stack**:
- OKX REST API for live trading
- Async order execution
- Position tracking in PostgreSQL

## Data Flow

```
OKX Exchange
    ↓ REST API (historical) / WebSocket (live)
Ingestor
    ↓ TimescaleDB (storage) + Redis Streams (events)
    ↓ OHLCV data
Feature Engine
    ↓ Technical indicators
Executor
    ↓ Trading signals
Redis Streams
    ↓ Signal events
Trader
    ↓ Risk checks
    ↓ Order execution (paper/live)
OKX API + PostgreSQL
```

## Database Schema

### Time-Series Tables (TimescaleDB)

**candles**: OHLCV data
- Partitioned by timestamp
- Indexed by symbol + interval
- UNIQUE constraint on (symbol, interval, timestamp)

**features**: Technical indicators
- Calculated per candle
- Indexed for fast retrieval
- Also partitioned by timestamp

### Relational Tables

**models**: Trading strategies
- Configuration (JSONB)
- Performance metrics
- Status workflow (draft → approved → active → archived)

**signals**: Trading signals
- Model reference
- Signal type (BUY/SELL/HOLD)
- Strength and context

**orders**: Executed orders
- OKX order ID
- Execution details (price, quantity, fees, slippage)
- Status tracking

**positions**: Current positions
- Entry price and quantity
- Unrealized PnL
- Open/close tracking

**trades**: Completed round trips
- Entry/exit details
- Realized PnL
- Duration analysis

**performance_summary**: Aggregated metrics
- Daily/weekly/monthly/all-time
- Sharpe, drawdown, win rate
- For reporting and dashboards

## Communication Patterns

### Redis Streams

**Streams**:
- `stream:candles`: New OHLCV data
- `stream:features`: Calculated indicators
- `stream:signals`: Trading signals
- `stream:orders`: Order updates
- `stream:fills`: Trade fills

**Benefits**:
- Decoupled services
- At-least-once delivery
- Backpressure handling with maxlen
- Consumer groups for scaling

### PostgreSQL

**Purpose**: Persistent storage and queries
- ACID guarantees
- Complex joins and aggregations
- Relational integrity
- TimescaleDB for time-series

## Configuration Management

### Config Hierarchy

1. **config.yaml**: Base configuration
2. **Environment variables**: Override defaults
3. **Runtime flags**: Service-specific

### Key Configuration Sections

```yaml
app:
  mode: paper  # Trading mode
  symbol: BTC-USDT
  interval: 1m

risk:
  max_position_size_usdt: 1000
  max_daily_loss_usdt: 200
  circuit_breaker_enabled: true

modelgen:
  min_sharpe_ratio: 1.2
  validation_period_days: 30
```

## Deployment

### Docker Compose

**Services**:
- `postgres`: TimescaleDB
- `redis`: Streams broker
- `ingestor`: Data collection
- `modelgen`: Strategy training
- `executor`: Signal generation
- `trader`: Order execution
- `prometheus`: Metrics
- `grafana`: Dashboards

**Orchestration**:
- Health checks
- Restart policies
- Network isolation
- Volume persistence

### Scaling Considerations

**Horizontal Scaling**:
- Executor: Multiple instances (consumer groups)
- Trader: Shard by symbol
- Redis: Cluster mode

**Vertical Scaling**:
- PostgreSQL: Shared buffers, connection pooling
- Ingestor: Batch size tuning

## Monitoring & Observability

### Logging

- **Format**: JSON structured logs
- **Levels**: DEBUG, INFO, WARNING, ERROR
- **Rotation**: 10MB files, 5 backups
- **Fields**: Timestamp, level, service, message, metadata

### Metrics (Prometheus)

- API request latency
- Signal generation rate
- Order fill rate
- PnL tracking
- Database query performance

### Dashboards (Grafana)

- Real-time PnL
- Trade history
- Win rate
- Drawdown curve
- Position status

## Testing Strategy

### Unit Tests
- Feature calculations
- Signal generation logic
- Risk checks
- Backtest engine

### Integration Tests
- Database operations
- Redis streaming
- OKX API mock
- End-to-end flow

### Paper Trading
- Default mode
- Real-time simulation
- Production-like behavior
- Safe for development

## Security

### API Keys
- Stored in environment variables
- Never committed to git
- Rotation support

### Risk Controls
- Position limits enforced
- Daily loss caps
- Circuit breakers
- Kill switch

### Audit Trail
- All signals logged
- Order history preserved
- Performance tracked
- Full auditability

## Future Enhancements

### Phase 2
- [ ] WebSocket for live data (replacing polling)
- [ ] Machine learning models
- [ ] Multi-symbol support
- [ ] Grid trading strategies

### Phase 3
- [ ] Portfolio optimization
- [ ] Risk parity models
- [ ] Cryptocurrency support
- [ ] Mobile dashboard

### Phase 4
- [ ] Cloud deployment (K8s)
- [ ] CI/CD pipeline
- [ ] Load testing
- [ ] Production hardening

