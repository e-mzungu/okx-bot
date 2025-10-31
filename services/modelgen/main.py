"""Model generation and backtesting service."""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import pandas as pd
from dataclasses import asdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.cfg import get_config
from common.logging import setup_logging
from common.db import get_db, Model, Candle
from common.models import PerformanceMetrics, OHLCV
from common.streams import get_redis
from common import indicators as ta

logger = setup_logging('modelgen')


class FeatureEngine:
    """Technical indicator and feature calculation."""
    
    @staticmethod
    def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators.
        
        Args:
            df: DataFrame with OHLCV columns
            
        Returns:
            DataFrame with additional feature columns
        """
        df = df.copy()
        
        # Moving averages
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        
        # Momentum indicators
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        macd = ta.macd(df['close'])
        if macd is not None and isinstance(macd, pd.DataFrame):
            df['macd'] = macd['MACD']
            df['macd_signal'] = macd['MACDs']
            df['macd_histogram'] = macd['MACDh']
        
        # Volatility
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        bbands = ta.bollinger_bands(df['close'], length=20)
        if bbands is not None and isinstance(bbands, pd.DataFrame):
            df['bollinger_upper'] = bbands['BBU']
            df['bollinger_middle'] = bbands['BBM']
            df['bollinger_lower'] = bbands['BBL']
        
        # Volume
        df['volume_sma'] = ta.sma(df['volume'], length=20)
        
        return df


class TradingStrategy:
    """Base trading strategy interface."""
    
    def __init__(self, name: str):
        self.name = name
    
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals.
        
        Args:
            df: DataFrame with features
            
        Returns:
            Series with signals: 1 (BUY), -1 (SELL), 0 (HOLD)
        """
        raise NotImplementedError
    
    def get_config(self) -> Dict[str, Any]:
        """Get strategy configuration."""
        raise NotImplementedError


class EMARSIStrategy(TradingStrategy):
    """EMA + RSI based strategy."""
    
    def __init__(self, name: str = "EMA_RSI"):
        super().__init__(name)
        self.ema_fast = 9
        self.ema_slow = 21
        self.rsi_overbought = 70
        self.rsi_oversold = 30
    
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on EMA crossover and RSI."""
        signals = pd.Series(0, index=df.index)
        
        # Ensure required columns exist
        if not all(col in df.columns for col in ['ema_9', 'ema_21', 'rsi_14']):
            return signals
        
        # EMA crossover
        ema_fast = df['ema_9']
        ema_slow = df['ema_21']
        
        # Golden cross
        golden_cross = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        
        # Death cross
        death_cross = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
        
        # RSI conditions
        rsi = df['rsi_14']
        rsi_oversold = rsi < self.rsi_oversold
        rsi_overbought = rsi > self.rsi_overbought
        
        # Generate signals
        signals[golden_cross & rsi_oversold] = 1  # BUY
        signals[death_cross & rsi_overbought] = -1  # SELL
        
        return signals
    
    def get_config(self) -> Dict[str, Any]:
        """Get strategy configuration."""
        return {
            'strategy': 'ema_rsi',
            'ema_fast': self.ema_fast,
            'ema_slow': self.ema_slow,
            'rsi_overbought': self.rsi_overbought,
            'rsi_oversold': self.rsi_oversold
        }


class MACDBBStrategy(TradingStrategy):
    """MACD + Bollinger Bands strategy."""
    
    def __init__(self, name: str = "MACD_BB"):
        super().__init__(name)
    
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MACD and Bollinger Bands."""
        signals = pd.Series(0, index=df.index)
        
        # Ensure required columns exist
        if not all(col in df.columns for col in ['macd', 'macd_signal', 'bollinger_lower', 'bollinger_upper']):
            return signals
        
        macd = df['macd']
        macd_signal = df['macd_signal']
        bb_upper = df['bollinger_upper']
        bb_lower = df['bollinger_lower']
        close = df['close']
        
        # MACD bullish crossover
        macd_bullish = (macd > macd_signal) & (macd.shift(1) <= macd_signal.shift(1))
        
        # MACD bearish crossover
        macd_bearish = (macd < macd_signal) & (macd.shift(1) >= macd_signal.shift(1))
        
        # Bollinger Bands
        bb_oversold = close < bb_lower
        bb_overbought = close > bb_upper
        
        # Generate signals
        signals[macd_bullish & bb_oversold] = 1  # BUY
        signals[macd_bearish & bb_overbought] = -1  # SELL
        
        return signals
    
    def get_config(self) -> Dict[str, Any]:
        """Get strategy configuration."""
        return {'strategy': 'macd_bb'}


class Backtester:
    """Backtesting engine."""
    
    def __init__(self, initial_capital: float = 10000.0, fee_pct: float = 0.001):
        self.initial_capital = initial_capital
        self.fee_pct = fee_pct
    
    def backtest(self, df: pd.DataFrame, signals: pd.Series) -> PerformanceMetrics:
        """
        Run backtest on strategy.
        
        Args:
            df: DataFrame with OHLCV and features
            signals: Series with trading signals
            
        Returns:
            Performance metrics
        """
        capital = self.initial_capital
        position = 0  # Number of coins held
        entry_price = 0
        trades = []
        
        for i in range(1, len(df)):
            price = df['close'].iloc[i]
            signal = signals.iloc[i]
            
            if signal == 1 and position == 0:  # BUY signal
                # Open position
                fee = capital * self.fee_pct
                position = (capital - fee) / price
                entry_price = price
                trades.append({
                    'type': 'entry',
                    'price': price,
                    'capital': capital,
                    'fee': fee
                })
            
            elif signal == -1 and position > 0:  # SELL signal
                # Close position
                value = position * price
                fee = value * self.fee_pct
                capital = value - fee
                
                trades.append({
                    'type': 'exit',
                    'price': price,
                    'capital': capital,
                    'fee': fee
                })
                
                position = 0
        
        # Calculate metrics
        metrics = self.calculate_metrics(trades, df)
        return metrics
    
    def calculate_metrics(self, trades: List[Dict], df: pd.DataFrame) -> PerformanceMetrics:
        """Calculate performance metrics from trades."""
        # Pair entry/exit trades
        paired_trades = []
        i = 0
        while i < len(trades) - 1:
            if trades[i]['type'] == 'entry' and trades[i+1]['type'] == 'exit':
                entry = trades[i]
                exit = trades[i+1]
                
                pnl = exit['capital'] - entry['capital']
                pnl_pct = (pnl / entry['capital']) * 100
                
                paired_trades.append({
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })
                i += 2
            else:
                i += 1
        
        if not paired_trades:
            return PerformanceMetrics()
        
        # Calculate metrics
        total_trades = len(paired_trades)
        winning_trades = sum(1 for t in paired_trades if t['pnl'] > 0)
        losing_trades = total_trades - winning_trades
        
        total_pnl = sum(t['pnl'] for t in paired_trades)
        total_return_pct = ((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100
        
        wins = [t['pnl'] for t in paired_trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in paired_trades if t['pnl'] < 0]
        
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        profit_factor = abs(sum(wins) / sum(losses)) if sum(losses) != 0 else 0
        
        # Simple Sharpe ratio calculation
        returns = [t['pnl_pct'] for t in paired_trades]
        sharpe_ratio = self._calculate_sharpe(returns)
        
        # Max drawdown
        max_drawdown_pct, max_drawdown_duration = self._calculate_drawdown(df)
        
        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl_usdt=total_pnl,
            total_return_pct=total_return_pct,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_duration_days=max_drawdown_duration
        )
    
    def _calculate_sharpe(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio."""
        if not returns:
            return 0.0
        
        import numpy as np
        returns_array = np.array(returns)
        
        if len(returns_array) < 2 or returns_array.std() == 0:
            return 0.0
        
        # Annualized Sharpe
        sharpe = (returns_array.mean() / returns_array.std()) * (252 ** 0.5)  # Assuming daily returns
        return float(sharpe)
    
    def _calculate_drawdown(self, df: pd.DataFrame) -> Tuple[float, int]:
        """Calculate maximum drawdown."""
        if len(df) < 2:
            return 0.0, 0
        
        # Calculate running maximum
        running_max = df['close'].expanding().max()
        drawdown_pct = ((df['close'] - running_max) / running_max) * 100
        
        max_drawdown = abs(drawdown_pct.min())
        max_drawdown_duration = 0
        
        return max_drawdown, max_drawdown_duration


class ModelGenerator:
    """Model generation service."""
    
    def __init__(self):
        """Initialize model generator."""
        self.config = get_config()
        self.modelgen_config = self.config.get('modelgen', {})
        self.app_config = self.config.get('app', {})
        
        self.db = get_db()
        self.symbol = self.app_config.get('symbol', 'BTC-USDT')
        self.interval = self.app_config.get('interval', '1m')
        
        self.feature_engine = FeatureEngine()
        self.backtester = Backtester(
            initial_capital=10000.0,
            fee_pct=self.config.get('trader', {}).get('fee_pct', 0.001)
        )
    
    async def init(self):
        """Initialize connections."""
        await self.db.connect()
        logger.info("ModelGenerator initialized")
    
    async def cleanup(self):
        """Cleanup connections."""
        await self.db.close()
        logger.info("ModelGenerator shut down")
    
    async def generate_models(self):
        """Generate and test multiple model variants."""
        logger.info("Starting model generation")
        
        # Fetch historical data
        now = datetime.now(timezone.utc)
        training_start = now - timedelta(
            days=self.modelgen_config.get('training_period_days', 180)
        )
        validation_start = now - timedelta(
            days=self.modelgen_config.get('validation_period_days', 30)
        )
        
        # Get all candles
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND interval = $2 AND timestamp >= $3
            ORDER BY timestamp ASC
        """
        
        rows = await self.db.fetch(query, self.symbol, self.interval, training_start)
        
        if not rows:
            logger.error("No historical data found")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame([dict(row) for row in rows])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        logger.info("Loaded historical data", extra={'rows': len(df)})
        
        # Calculate features
        df = self.feature_engine.calculate_features(df)
        
        # Split into train/validation
        train_df = df[df.index < validation_start]
        val_df = df[df.index >= validation_start]
        
        logger.info("Split data", extra={'train_rows': len(train_df), 'val_rows': len(val_df)})
        
        # Test strategies
        strategies = [
            EMARSIStrategy("EMA_RSI_v1"),
            MACDBBStrategy("MACD_BB_v1")
        ]
        
        best_metrics = None
        best_strategy = None
        
        for strategy in strategies:
            logger.info("Testing strategy", extra={'strategy': strategy.name})
            
            # Generate signals
            signals = strategy.generate_signals(train_df)
            
            # Backtest
            metrics = self.backtester.backtest(train_df, signals)
            
            logger.info("Strategy metrics", extra={
                'strategy': strategy.name,
                'sharpe': metrics.sharpe_ratio,
                'win_rate': metrics.win_rate,
                'profit_factor': metrics.profit_factor,
                'total_trades': metrics.total_trades
            })
            
            # Check if meets criteria
            if self.meets_criteria(metrics):
                if best_metrics is None or metrics.sharpe_ratio > best_metrics.sharpe_ratio:
                    best_metrics = metrics
                    best_strategy = strategy
        
        # Create and save best model
        if best_strategy and best_metrics:
            logger.info("Best strategy selected", extra={'strategy': best_strategy.name})
            
            # Create model in database
            model_config = best_strategy.get_config()
            
            model_id = await Model.create(
                self.db,
                name=best_strategy.name,
                version=1,
                model_type='rule-based',
                config=model_config,
                performance=best_metrics.to_dict()
            )
            
            logger.info("Model created", extra={'model_id': model_id})
        else:
            logger.warning("No strategy met criteria")
    
    def meets_criteria(self, metrics: PerformanceMetrics) -> bool:
        """Check if metrics meet minimum criteria."""
        min_sharpe = self.modelgen_config.get('min_sharpe_ratio', 1.2)
        min_win_rate = self.modelgen_config.get('min_win_rate', 0.45)
        min_profit_factor = self.modelgen_config.get('min_profit_factor', 1.5)
        max_drawdown = self.modelgen_config.get('max_drawdown_pct', 0.15)
        
        return (
            metrics.sharpe_ratio >= min_sharpe and
            metrics.win_rate >= min_win_rate and
            metrics.profit_factor >= min_profit_factor and
            abs(metrics.max_drawdown_pct) <= max_drawdown and
            metrics.total_trades > 0
        )


async def main():
    """Main entry point."""
    generator = ModelGenerator()
    
    try:
        await generator.init()
        await generator.generate_models()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error("Fatal error", extra={'error': str(e)})
        raise
    finally:
        await generator.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

