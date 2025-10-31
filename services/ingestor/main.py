"""Market data ingestion service for OKX."""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta
import httpx
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.cfg import get_config
from common.logging import setup_logging
from common.db import get_db, Candle
from common.streams import get_redis, Streams

logger = setup_logging('ingestor')


class OKXIngestor:
    """OKX market data ingestor."""
    
    def __init__(self):
        """Initialize ingestor."""
        self.config = get_config()
        self.okx_config = self.config.get('okx', {})
        self.ingestor_config = self.config.get('ingestor', {})
        self.app_config = self.config.get('app', {})
        
        self.base_url = "https://www.okx.com" if not self.okx_config.get('sandbox') else "https://www.okx.com"
        self.api_key = self.okx_config.get('api_key')
        self.api_secret = self.okx_config.get('api_secret')
        self.passphrase = self.okx_config.get('passphrase')
        
        self.db = get_db()
        self.redis = get_redis()
        self.http_client = None
        
        self.symbol = self.app_config.get('symbol', 'BTC-USDT')
        self.interval = self.app_config.get('interval', '1m')
        
        # Interval to OKX format mapping
        self.interval_map = {
            '1m': '1m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1H': '1H',
            '4H': '4H',
            '1D': '1D'
        }
    
    async def init(self):
        """Initialize connections."""
        await self.db.connect()
        await self.redis.connect()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Ingestor initialized", extra={'symbol': self.symbol, 'interval': self.interval})
    
    async def cleanup(self):
        """Cleanup connections."""
        if self.http_client:
            await self.http_client.aclose()
        await self.redis.close()
        await self.db.close()
        logger.info("Ingestor shut down")
    
    async def fetch_historical_candles(self, after: datetime = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch historical candles from OKX.
        
        Args:
            after: Fetch candles after this timestamp
            limit: Maximum number of candles
            
        Returns:
            List of candle data
        """
        url = f"{self.base_url}/api/v5/market/candles"
        params = {
            'instId': self.symbol,
            'bar': self.interval_map.get(self.interval, '1m'),
            'limit': limit
        }
        
        if after:
            params['after'] = str(int(after.timestamp() * 1000))
        
        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == '0':
                return data.get('data', [])
            else:
                logger.error("Failed to fetch candles", extra={'error': data.get('msg')})
                return []
        except Exception as e:
            logger.error("Error fetching historical candles", extra={'error': str(e)})
            return []
    
    def parse_candle(self, candle_data: List[str]) -> Candle:
        """
        Parse OKX candle data to Candle object.
        
        OKX format: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        """
        ts = int(candle_data[0]) / 1000  # Convert ms to seconds
        timestamp = datetime.fromtimestamp(ts)
        
        return Candle(
            symbol=self.symbol,
            interval=self.interval,
            timestamp=timestamp,
            open=float(candle_data[1]),
            high=float(candle_data[2]),
            low=float(candle_data[3]),
            close=float(candle_data[4]),
            volume=float(candle_data[5]),
            quote_volume=float(candle_data[6]),
            trades_count=None
        )
    
    async def backfill(self):
        """Backfill historical data."""
        logger.info("Starting backfill", extra={'symbol': self.symbol, 'interval': self.interval})
        
        # Check latest candle in DB
        latest_candle = await Candle.get_latest(self.db, self.symbol, self.interval)
        if latest_candle:
            start_time = latest_candle.timestamp
            logger.info("Resuming from existing data", extra={'from': start_time.isoformat()})
        else:
            # Start from N days ago
            backfill_days = self.ingestor_config.get('backfill_days', 180)
            start_time = datetime.utcnow() - timedelta(days=backfill_days)
            logger.info("Starting fresh backfill", extra={'from': start_time.isoformat()})
        
        batch_size = self.ingestor_config.get('batch_size', 1000)
        total_fetched = 0
        
        while True:
            # Fetch batch
            candles_data = await self.fetch_historical_candles(after=start_time, limit=100)
            
            if not candles_data:
                logger.info("No more data to fetch")
                break
            
            # Parse candles
            candles = [self.parse_candle(c) for c in candles_data]
            
            # Insert to database
            await Candle.insert_many(self.db, candles)
            
            # Update start time for next batch
            if candles:
                start_time = candles[-1].timestamp
                total_fetched += len(candles)
            
            logger.info("Backfilled batch", extra={'count': len(candles), 'total': total_fetched})
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        logger.info("Backfill completed", extra={'total_candles': total_fetched})
    
    async def stream_live_candles(self):
        """Stream live candles from OKX WebSocket."""
        # For simplicity, we'll poll the REST API
        # In production, use WebSocket for real-time data
        logger.info("Starting live candle streaming")
        
        while True:
            try:
                # Fetch latest candle
                candles_data = await self.fetch_historical_candles(limit=1)
                
                if candles_data:
                    candle = self.parse_candle(candles_data[0])
                    
                    # Check if it's new
                    latest = await Candle.get_latest(self.db, self.symbol, self.interval)
                    
                    if not latest or candle.timestamp > latest.timestamp:
                        # Insert new candle
                        await Candle.insert_many(self.db, [candle])
                        
                        # Publish to stream
                        await Streams.publish_candle(
                            self.redis,
                            candle.symbol,
                            candle.interval,
                            candle.timestamp,
                            {
                                'open': candle.open,
                                'high': candle.high,
                                'low': candle.low,
                                'close': candle.close,
                                'volume': candle.volume
                            }
                        )
                        
                        logger.info("New candle received", extra={'timestamp': candle.timestamp.isoformat()})
                
                # Wait for next interval
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error("Error in live streaming", extra={'error': str(e)})
                await asyncio.sleep(10)


async def main():
    """Main entry point."""
    ingestor = OKXIngestor()
    
    try:
        await ingestor.init()
        
        # Run backfill first
        await ingestor.backfill()
        
        # Then stream live data
        await ingestor.stream_live_candles()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error("Fatal error", extra={'error': str(e)})
        raise
    finally:
        await ingestor.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

