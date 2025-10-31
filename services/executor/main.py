"""Model executor service for real-time signal generation."""

import asyncio
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.cfg import get_config
from common.logging import setup_logging
from common.db import get_db, Model, Candle
from common.streams import get_redis, Streams
from common.models import Signal, SignalType
from common import indicators as ta

logger = setup_logging('executor')


class FeatureCalculator:
    """Calculate features from recent candles."""
    
    @staticmethod
    def calculate_features(df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate technical indicators for latest bar."""
        features = {}
        
        # EMA
        features['ema_9'] = float(df['ema_9'].iloc[-1]) if 'ema_9' in df.columns else None
        features['ema_21'] = float(df['ema_21'].iloc[-1]) if 'ema_21' in df.columns else None
        features['ema_50'] = float(df['ema_50'].iloc[-1]) if 'ema_50' in df.columns else None
        features['ema_200'] = float(df['ema_200'].iloc[-1]) if 'ema_200' in df.columns else None
        
        # RSI
        features['rsi_14'] = float(df['rsi_14'].iloc[-1]) if 'rsi_14' in df.columns else None
        
        # MACD
        features['macd'] = float(df['macd'].iloc[-1]) if 'macd' in df.columns else None
        features['macd_signal'] = float(df['macd_signal'].iloc[-1]) if 'macd_signal' in df.columns else None
        features['macd_histogram'] = float(df['macd_histogram'].iloc[-1]) if 'macd_histogram' in df.columns else None
        
        # ATR
        features['atr_14'] = float(df['atr_14'].iloc[-1]) if 'atr_14' in df.columns else None
        
        # Bollinger Bands
        features['bollinger_upper'] = float(df['bollinger_upper'].iloc[-1]) if 'bollinger_upper' in df.columns else None
        features['bollinger_middle'] = float(df['bollinger_middle'].iloc[-1]) if 'bollinger_middle' in df.columns else None
        features['bollinger_lower'] = float(df['bollinger_lower'].iloc[-1]) if 'bollinger_lower' in df.columns else None
        
        # Volume
        features['volume_sma'] = float(df['volume_sma'].iloc[-1]) if 'volume_sma' in df.columns else None
        
        return features


class SignalGenerator:
    """Generate trading signals from model."""
    
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config
    
    def generate_signal(self, df: pd.DataFrame) -> int:
        """
        Generate signal based on model configuration.
        
        Returns:
            signal: 1 (BUY), -1 (SELL), 0 (HOLD)
        """
        strategy = self.config.get('strategy')
        
        if strategy == 'ema_rsi':
            return self._ema_rsi_signal(df)
        elif strategy == 'macd_bb':
            return self._macd_bb_signal(df)
        else:
            return 0
    
    def _ema_rsi_signal(self, df: pd.DataFrame) -> int:
        """EMA + RSI signal generation."""
        if len(df) < 22:
            return 0
        
        ema_fast = df['ema_9'].iloc[-1]
        ema_slow = df['ema_21'].iloc[-1]
        ema_fast_prev = df['ema_9'].iloc[-2]
        ema_slow_prev = df['ema_21'].iloc[-2]
        
        rsi = df['rsi_14'].iloc[-1]
        
        # Golden cross
        if ema_fast > ema_slow and ema_fast_prev <= ema_slow_prev:
            if rsi < 30:
                return 1  # BUY
        
        # Death cross
        if ema_fast < ema_slow and ema_fast_prev >= ema_slow_prev:
            if rsi > 70:
                return -1  # SELL
        
        return 0
    
    def _macd_bb_signal(self, df: pd.DataFrame) -> int:
        """MACD + Bollinger Bands signal generation."""
        if len(df) < 22:
            return 0
        
        macd = df['macd'].iloc[-1]
        macd_signal = df['macd_signal'].iloc[-1]
        macd_prev = df['macd'].iloc[-2]
        macd_signal_prev = df['macd_signal'].iloc[-2]
        
        bb_upper = df['bollinger_upper'].iloc[-1]
        bb_lower = df['bollinger_lower'].iloc[-1]
        close = df['close'].iloc[-1]
        
        # MACD bullish crossover
        if macd > macd_signal and macd_prev <= macd_signal_prev:
            if close < bb_lower:
                return 1  # BUY
        
        # MACD bearish crossover
        if macd < macd_signal and macd_prev >= macd_signal_prev:
            if close > bb_upper:
                return -1  # SELL
        
        return 0


class ModelExecutor:
    """Model executor service."""
    
    def __init__(self):
        """Initialize executor."""
        self.config = get_config()
        self.executor_config = self.config.get('executor', {})
        self.app_config = self.config.get('app', {})
        
        self.db = get_db()
        self.redis = get_redis()
        self.symbol = self.app_config.get('symbol', 'BTC-USDT')
        self.interval = self.app_config.get('interval', '1m')
        
        self.model = None
        self.model_config = None
        self.signal_generator = None
        self.feature_calc = FeatureCalculator()
        
        self.last_signal_time = None
        self.max_signals_per_minute = self.executor_config.get('max_signals_per_minute', 5)
        self.signal_count = 0
    
    async def init(self):
        """Initialize connections and load active model."""
        await self.db.connect()
        await self.redis.connect()
        
        # Load active model
        await self.load_active_model()
        
        logger.info("Executor initialized")
    
    async def cleanup(self):
        """Cleanup connections."""
        await self.redis.close()
        await self.db.close()
        logger.info("Executor shut down")
    
    async def load_active_model(self):
        """Load active model from database."""
        self.model = await Model.get_active(self.db)
        
        if self.model:
            # Parse config if it's a string
            config = self.model.get('config', {})
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except (json.JSONDecodeError, TypeError):
                    config = {}
            self.model_config = config
            self.signal_generator = SignalGenerator(self.model_config)
            logger.info("Active model loaded", extra={'model_id': self.model['id'], 'name': self.model['name']})
        else:
            logger.warning("No active model found")
    
    async def process_candle(self):
        """Process new candle and generate signal if needed."""
        # Get latest candles for feature calculation (need enough history)
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND interval = $2
            ORDER BY timestamp DESC
            LIMIT 250
        """
        
        rows = await self.db.fetch(query, self.symbol, self.interval)
        
        if not rows or len(rows) < 22:  # Need at least 22 bars for indicators
            logger.debug("Not enough data for signal generation")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame([dict(row) for row in reversed(rows)])
        
        # Calculate features
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        
        macd = ta.macd(df['close'])
        if macd is not None and isinstance(macd, pd.DataFrame):
            df['macd'] = macd['MACD']
            df['macd_signal'] = macd['MACDs']
            df['macd_histogram'] = macd['MACDh']
        
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        bbands = ta.bollinger_bands(df['close'], length=20)
        if bbands is not None and isinstance(bbands, pd.DataFrame):
            df['bollinger_upper'] = bbands['BBU']
            df['bollinger_middle'] = bbands['BBM']
            df['bollinger_lower'] = bbands['BBL']
        
        df['volume_sma'] = ta.sma(df['volume'], length=20)
        
        # Generate signal
        if self.signal_generator:
            signal_value = self.signal_generator.generate_signal(df)
            
            if signal_value != 0:
                await self.emit_signal(signal_value, df)
    
    async def emit_signal(self, signal_value: int, df: pd.DataFrame):
        """Emit trading signal."""
        # Rate limiting
        now = datetime.utcnow()
        if self.last_signal_time:
            time_diff = (now - self.last_signal_time).total_seconds()
            if time_diff < 60:  # Within same minute
                self.signal_count += 1
                if self.signal_count > self.max_signals_per_minute:
                    logger.warning("Signal rate limit exceeded")
                    return
            else:
                self.signal_count = 1
                self.last_signal_time = now
        else:
            self.last_signal_time = now
            self.signal_count = 1
        
        # Determine signal type
        signal_type = SignalType.BUY if signal_value == 1 else SignalType.SELL
        
        # Get features
        features = self.feature_calc.calculate_features(df)
        
        # Get current price
        current_price = float(df['close'].iloc[-1])
        
        # Calculate signal strength (0.0 to 1.0)
        signal_strength = self._calculate_signal_strength(df, signal_value)
        
        # Create signal
        signal = Signal(
            model_id=self.model['id'],
            symbol=self.symbol,
            signal_type=signal_type,
            timestamp=datetime.utcnow(),
            price=current_price,
            signal_strength=signal_strength,
            features=features
        )
        
        # Publish to stream
        await Streams.publish_signal(
            self.redis,
            signal.model_id,
            signal.symbol,
            signal.signal_type.value,
            signal.timestamp,
            signal.to_dict()
        )
        
        logger.info("Signal generated", extra={
            'model_id': signal.model_id,
            'signal_type': signal.signal_type.value,
            'price': signal.price,
            'strength': signal_strength
        })
    
    def _calculate_signal_strength(self, df: pd.DataFrame, signal_value: int) -> float:
        """Calculate signal strength (0.0 to 1.0)."""
        # Simple strength calculation based on momentum
        if len(df) < 2:
            return 0.5
        
        strength = 0.5  # Base strength
        
        if signal_value == 1:  # BUY
            # Check momentum
            if 'rsi_14' in df.columns:
                rsi = df['rsi_14'].iloc[-1]
                if rsi < 30:
                    strength += 0.2
                elif rsi < 40:
                    strength += 0.1
        
        elif signal_value == -1:  # SELL
            if 'rsi_14' in df.columns:
                rsi = df['rsi_14'].iloc[-1]
                if rsi > 70:
                    strength += 0.2
                elif rsi > 60:
                    strength += 0.1
        
        return min(strength, 1.0)
    
    async def listen_for_candles(self):
        """Listen for new candles and generate signals."""
        logger.info("Starting candle listener")
        
        while True:
            try:
                # Listen to candle stream
                messages = await self.redis.read(
                    {Streams.CANDLES: '0'},
                    count=10,
                    block=5000
                )
                
                for msg in messages:
                    if msg['fields'].get('symbol') == self.symbol:
                        await self.process_candle()
                        
                        # Reset read position
                        await self.redis.client.xsetid(Streams.CANDLES, msg['id'])
                
                # Also check periodically if no messages
                await asyncio.sleep(self.executor_config.get('check_interval', 60))
                
            except Exception as e:
                logger.error("Error in candle listener", extra={'error': str(e)})
                await asyncio.sleep(10)
    
    async def run(self):
        """Main execution loop."""
        # Wait for active model if not available
        if not self.model:
            logger.warning("No active model found, waiting for one to be created...")
            while not self.model:
                await asyncio.sleep(60)  # Check every minute
                await self.load_active_model()
        
        # Start listening for candles
        await self.listen_for_candles()


async def main():
    """Main entry point."""
    executor = ModelExecutor()
    
    try:
        await executor.init()
        await executor.run()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error("Fatal error", extra={'error': str(e)})
        raise
    finally:
        await executor.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

