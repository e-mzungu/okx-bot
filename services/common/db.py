"""Database connection and utilities."""

import asyncio
import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from .cfg import get_config


class Database:
    """Database connection manager."""
    
    def __init__(self):
        """Initialize database connection."""
        self.config = get_config()
        self.db_config = self.config.get('database', {})
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create connection pool."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 5432),
                user=self.db_config.get('user', 'postgres'),
                password=self.db_config.get('password'),
                database=self.db_config.get('name', 'okx_bot'),
                min_size=2,
                max_size=self.db_config.get('pool_size', 10),
                command_timeout=60
            )
    
    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def execute(self, query: str, *args) -> str:
        """
        Execute a query without returning results.
        
        Returns:
            Execution status
        """
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def transaction(self):
        """Get transaction context manager."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn


class Candle:
    """Candle data model."""
    
    def __init__(self, symbol: str, interval: str, timestamp: datetime,
                 open: float, high: float, low: float, close: float,
                 volume: float, quote_volume: float = None,
                 trades_count: int = None):
        self.symbol = symbol
        self.interval = interval
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.quote_volume = quote_volume
        self.trades_count = trades_count
    
    @classmethod
    async def insert_many(cls, db: Database, candles: List['Candle']) -> None:
        """Bulk insert candles."""
        query = """
            INSERT INTO candles (
                symbol, interval, timestamp, open, high, low, close, volume,
                quote_volume, trades_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (symbol, interval, timestamp) DO NOTHING
        """
        
        values = [
            (
                c.symbol, c.interval, c.timestamp, c.open, c.high, c.low, c.close,
                c.volume, c.quote_volume, c.trades_count
            )
            for c in candles
        ]
        
        async with db.pool.acquire() as conn:
            await conn.executemany(query, values)
    
    @classmethod
    async def get_latest(cls, db: Database, symbol: str, interval: str) -> Optional['Candle']:
        """Get latest candle for symbol and interval."""
        query = """
            SELECT * FROM candles
            WHERE symbol = $1 AND interval = $2
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        row = await db.fetchrow(query, symbol, interval)
        if row:
            return cls(
                symbol=row['symbol'],
                interval=row['interval'],
                timestamp=row['timestamp'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                quote_volume=float(row['quote_volume']) if row['quote_volume'] else None,
                trades_count=row['trades_count']
            )
        return None


class Model:
    """Trading model data model."""
    
    @classmethod
    async def get_active(cls, db: Database) -> Optional[Dict[str, Any]]:
        """Get active model."""
        query = """
            SELECT * FROM models
            WHERE status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
        """
        row = await db.fetchrow(query)
        if row:
            return dict(row)
        return None
    
    @classmethod
    async def update_status(cls, db: Database, model_id: int, status: str) -> None:
        """Update model status."""
        query = """
            UPDATE models
            SET status = $1, updated_at = NOW()
            WHERE id = $2
        """
        await db.execute(query, status, model_id)
    
    @classmethod
    async def create(cls, db: Database, name: str, version: int, model_type: str,
                    config: Dict[str, Any], performance: Dict[str, Any]) -> int:
        """Create new model."""
        query = """
            INSERT INTO models (
                name, version, model_type, config, sharpe_ratio, profit_factor,
                win_rate, max_drawdown_pct, total_return_pct, total_trades, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'approved')
            RETURNING id
        """
        return await db.fetchval(
            query, name, version, model_type, 
            str(config).replace("'", '"'),  # Simple JSON conversion
            performance.get('sharpe_ratio'),
            performance.get('profit_factor'),
            performance.get('win_rate'),
            performance.get('max_drawdown_pct'),
            performance.get('total_return_pct'),
            performance.get('total_trades')
        )


# Global database instance
_db_instance = None


def get_db() -> Database:
    """Get or create global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

