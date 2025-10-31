# 🪙 BTC Trading Platform

A production-ready automated trading platform for **BTC/USDT** using the **OKX API**. The system provides end-to-end automation from data collection → strategy generation → real-time signal execution → trade execution and PnL tracking.

![Status](https://img.shields.io/badge/status-development-yellow)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 🎯 Overview

This platform implements a microservices-based architecture with four core services:

- **Ingestor**: Collects historical and live market data from OKX
- **ModelGen**: Trains and validates trading strategies using backtesting
- **Executor**: Runs active models in real-time to generate trading signals
- **Trader**: Executes signals with risk management (paper/live modes)

### Features

- ✅ **Automated Strategy Generation**: Multiple rule-based strategies (EMA+RSI, MACD+Bollinger Bands)
- ✅ **Comprehensive Backtesting**: Walk-forward validation with Sharpe ratio, win rate, drawdown metrics
- ✅ **Real-time Signal Generation**: Live feature calculation and signal emission
- ✅ **Risk Management**: Position limits, daily loss limits, consecutive loss protection
- ✅ **Multi-mode Trading**: Paper (simulation), Shadow (live data, no orders), Live (real trading)
- ✅ **Time-series Database**: PostgreSQL with TimescaleDB for efficient OHLCV storage
- ✅ **Event Streaming**: Redis Streams for real-time data flow
- ✅ **Production-ready**: Docker Compose, structured logging, health checks

## 📋 Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- OKX API credentials (sandbox or production)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd okx-bot
```

### 2. Configure Environment

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Edit `.env` and add your OKX API credentials:

```env
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_PASSPHRASE=your_passphrase_here

# For testing, use sandbox=true
OKX_SANDBOX=true
```

### 3. Start the Platform

```bash
make build    # Build Docker images
make up       # Start all services
```

Or using Docker Compose directly:

```bash
docker compose up -d
```

### 4. Run Database Migrations

```bash
make migrate
```

### 5. Verify Services

Check service status:

```bash
make status
```

View logs:

```bash
make logs              # All services
make logs-ingestor     # Data ingestion only
make logs-executor     # Signal generation only
make logs-trader       # Trade execution only
```

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        OKX Exchange                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │   Ingestor     │  ← Fetches historical & live OHLCV data
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  Redis Streams │  ← Real-time event streaming
        │    (Candles)   │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │   Executor     │  ← Calculates features & generates signals
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  Redis Streams │  ← Signal queue
        │   (Signals)    │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │    Trader      │  ← Risk checks & order execution
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │     OKX API    │  ← Place orders (paper/live)
        └────────────────┘

PostgreSQL (TimescaleDB) ← Stores candles, models, orders, trades
     ↓
Grafana ← Visualize performance metrics
```

## 🔧 Services

### Ingestor Service

Collects market data from OKX:
- Backfills historical data (default: 180 days)
- Streams live 1-minute candles
- Publishes to Redis Streams
- Stores in TimescaleDB

**Manual trigger:**

```bash
make backfill
```

### ModelGen Service

Generates and validates trading strategies:
- Tests multiple strategy variants
- Backtests on historical data
- Validates on out-of-sample period
- Saves approved models to database

**Strategies implemented:**

1. **EMA + RSI**: Golden/death cross with RSI oversold/overbought conditions
2. **MACD + Bollinger Bands**: MACD crossover with Bollinger Band mean reversion

**Manual trigger:**

```bash
make models
```

### Executor Service

Runs active model in real-time:
- Subscribes to candle stream
- Calculates technical indicators
- Generates BUY/SELL signals
- Publishes signals to Redis

### Trader Service

Executes trading signals:
- Validates signals against risk limits
- Simulates orders (paper mode) or sends to OKX (live mode)
- Updates positions and PnL
- Implements circuit breakers

## 📈 Database Schema

### Core Tables

- `candles`: OHLCV data (TimescaleDB hypertable)
- `features`: Technical indicators per candle
- `models`: Trading strategy definitions and metrics
- `signals`: Generated trading signals
- `orders`: Executed orders with fill details
- `positions`: Current open positions
- `trades`: Completed round-trip trades
- `performance_summary`: Aggregated performance metrics

See `migrations/` for full schema definitions.

## 🎛️ Configuration

Configuration is managed in `configs/config.yaml`:

```yaml
app:
  mode: "paper"           # paper, shadow, live
  symbol: "BTC-USDT"
  interval: "1m"

risk:
  max_position_size_usdt: 1000
  max_daily_loss_usdt: 200
  max_consecutive_losses: 3

modelgen:
  min_sharpe_ratio: 1.2
  min_win_rate: 0.45
  min_profit_factor: 1.5
```

## 📊 Monitoring

### Grafana Dashboard

Access at http://localhost:3000 (admin/admin)

### Prometheus Metrics

Access at http://localhost:9090

## 🧪 Testing

### Paper Trading

The default mode is `paper` - all orders are simulated locally:

```yaml
app:
  mode: "paper"  # No real orders
```

### Shadow Mode

Connect to live OKX data but don't execute orders:

```yaml
app:
  mode: "shadow"  # Live data, no execution
```

### Live Trading

⚠️ **WARNING**: Only enable after thorough testing!

```yaml
app:
  mode: "live"  # Real orders
OKX_SANDBOX=false  # Production API
```

## 🛠️ Development

### Local Development Setup

```bash
make dev-setup  # Install Python dependencies
python -m services.ingestor.main  # Run ingestor locally
```

### Database Access

```bash
make shell-postgres  # psql shell
make shell-redis     # redis-cli
```

### View Logs

```bash
make logs
make logs-ingestor
make logs-executor
make logs-trader
```

## 📝 Common Tasks

| Task | Command |
|------|---------|
| Start services | `make up` |
| Stop services | `make down` |
| View logs | `make logs` |
| Trigger backfill | `make backfill` |
| Generate models | `make models` |
| Restart service | `make restart-executor` |
| Clean everything | `make clean` |

See all commands:

```bash
make help
```

## 🔒 Security

- API keys stored in `.env` only (not committed to git)
- Circuit breakers prevent runaway losses
- Kill switch for emergency stops
- Position limits and daily loss caps
- Structured logging for audit trail

## 🐛 Troubleshooting

### Services won't start

```bash
docker compose down -v  # Remove volumes
docker compose up --build  # Rebuild and start
```

### Database connection errors

Check PostgreSQL is healthy:

```bash
docker compose ps
make shell-postgres  # Test connection
```

### No data in database

```bash
make backfill  # Manually trigger ingestion
make logs-ingestor  # Check for errors
```

## 📚 Next Steps

1. **Backfill historical data**: `make backfill`
2. **Generate models**: `make models`
3. **Verify active model**: Check database `models` table
4. **Monitor signals**: `make logs-executor`
5. **Track trades**: `make logs-trader`
6. **Analyze performance**: Grafana dashboard

## 🤝 Contributing

Contributions welcome! Please read contributing guidelines first.

## 📄 License

MIT License - see LICENSE file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading cryptocurrencies carries significant risk. Always test thoroughly in paper mode before considering live trading. The authors are not responsible for any financial losses.

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- See documentation in `/docs`
- Check logs: `make logs`

---

Built with ❤️ for the crypto trading community
