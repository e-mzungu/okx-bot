"""Data models and types."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum


class SignalType(str, Enum):
    """Trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class SignalStatus(str, Enum):
    """Signal status."""
    PENDING = "pending"
    SENT = "sent"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ModelStatus(str, Enum):
    """Model status."""
    DRAFT = "draft"
    TESTING = "testing"
    APPROVED = "approved"
    ACTIVE = "active"
    ARCHIVED = "archived"


class TradingMode(str, Enum):
    """Trading mode."""
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


@dataclass
class OHLCV:
    """OHLCV candle data."""
    symbol: str
    interval: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None
    trades_count: Optional[int] = None


@dataclass
class Features:
    """Technical indicators and features."""
    symbol: str
    interval: str
    timestamp: datetime
    
    # Price features
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    
    # Momentum
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    
    # Volatility
    atr_14: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    
    # Volume
    volume_sma: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'interval': self.interval,
            'timestamp': self.timestamp.isoformat(),
            'ema_9': self.ema_9,
            'ema_21': self.ema_21,
            'ema_50': self.ema_50,
            'ema_200': self.ema_200,
            'rsi_14': self.rsi_14,
            'macd': self.macd,
            'macd_signal': self.macd_signal,
            'macd_histogram': self.macd_histogram,
            'atr_14': self.atr_14,
            'bollinger_upper': self.bollinger_upper,
            'bollinger_middle': self.bollinger_middle,
            'bollinger_lower': self.bollinger_lower,
            'volume_sma': self.volume_sma,
        }


@dataclass
class Signal:
    """Trading signal."""
    model_id: int
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    signal_strength: float = 0.0
    features: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'model_id': self.model_id,
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'timestamp': self.timestamp.isoformat(),
            'price': self.price,
            'signal_strength': self.signal_strength,
            'features': self.features
        }


@dataclass
class Order:
    """Trade order."""
    signal_id: Optional[int]
    model_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float
    mode: TradingMode = TradingMode.PAPER
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'signal_id': self.signal_id,
            'model_id': self.model_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'mode': self.mode.value
        }


@dataclass
class TradeResult:
    """Trade execution result."""
    order_id: Optional[str]
    filled_price: float
    filled_quantity: float
    fee: float
    fee_currency: str
    slippage_pct: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'order_id': self.order_id,
            'filled_price': self.filled_price,
            'filled_quantity': self.filled_quantity,
            'fee': self.fee,
            'fee_currency': self.fee_currency,
            'slippage_pct': self.slippage_pct
        }


@dataclass
class Position:
    """Trading position."""
    model_id: int
    symbol: str
    side: str  # 'long', 'short'
    quantity: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    mode: TradingMode = TradingMode.PAPER
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None


@dataclass
class PerformanceMetrics:
    """Performance metrics for a model."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl_usdt: float = 0.0
    total_return_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'total_pnl_usdt': self.total_pnl_usdt,
            'total_return_pct': self.total_return_pct,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_drawdown_duration_days': self.max_drawdown_duration_days
        }

