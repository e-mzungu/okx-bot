"""Technical indicator calculations using pandas and numpy."""

import pandas as pd
import numpy as np


def ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    
    Args:
        series: Price series (typically closing prices)
        length: Period length (default 14)
        
    Returns:
        RSI values (0-100)
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD - Moving Average Convergence Divergence.
    
    Returns:
        DataFrame with columns: MACD, MACD_signal, MACD_histogram
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_signal = ema(macd_line, signal)
    macd_histogram = macd_line - macd_signal
    
    return pd.DataFrame({
        'MACD': macd_line,
        'MACDs': macd_signal,
        'MACDh': macd_histogram
    })


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """
    Average True Range.
    
    Args:
        high: High prices
        low: Low prices
        close: Closing prices
        length: Period length (default 14)
        
    Returns:
        ATR values
    """
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=length).mean()
    
    return atr


def bollinger_bands(series: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    """
    Bollinger Bands.
    
    Args:
        series: Price series
        length: Period length (default 20)
        std: Standard deviation multiplier (default 2.0)
        
    Returns:
        DataFrame with columns: BBU (upper), BBM (middle), BBL (lower)
    """
    middle = sma(series, length)
    std_dev = series.rolling(window=length).std()
    
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return pd.DataFrame({
        'BBU': upper,
        'BBM': middle,
        'BBL': lower
    })

