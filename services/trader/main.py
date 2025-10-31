"""Trade execution service for OKX."""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.cfg import get_config
from common.logging import setup_logging
from common.db import get_db, Model
from common.streams import get_redis, Streams
from common.models import Order, OrderSide, OrderType, OrderStatus, TradingMode, SignalType

logger = setup_logging('trader')


class PaperTrader:
    """Paper trading simulator."""
    
    def __init__(self, fee_pct: float = 0.001, slippage_pct: float = 0.001):
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
    
    async def execute_order(self, order: Order, current_price: float) -> Dict[str, Any]:
        """
        Simulate order execution.
        
        Args:
            order: Order to execute
            current_price: Current market price
            
        Returns:
            Execution result
        """
        # Simulate slippage
        if order.order_type == OrderType.MARKET:
            filled_price = current_price
            if order.side == OrderSide.BUY:
                filled_price *= (1 + self.slippage_pct)
            else:
                filled_price *= (1 - self.slippage_pct)
        else:
            filled_price = order.price
        
        # Simulate fee
        value = order.quantity * filled_price
        fee = value * self.fee_pct
        
        logger.info("Paper trade executed", extra={
            'symbol': order.symbol,
            'side': order.side.value,
            'quantity': order.quantity,
            'price': filled_price,
            'fee': fee
        })
        
        return {
            'order_id': f"PAPER_{datetime.utcnow().timestamp()}",
            'filled_price': filled_price,
            'filled_quantity': order.quantity,
            'fee': fee,
            'fee_currency': 'USDT',
            'slippage_pct': self.slippage_pct if order.order_type == OrderType.MARKET else 0.0,
            'status': OrderStatus.FILLED.value
        }


class OKXTrader:
    """OKX live trader."""
    
    def __init__(self):
        self.config = get_config()
        self.okx_config = self.config.get('okx', {})
        self.base_url = "https://www.okx.com" if not self.okx_config.get('sandbox') else "https://www.okx.com"
        self.api_key = self.okx_config.get('api_key')
        self.api_secret = self.okx_config.get('api_secret')
        self.passphrase = self.okx_config.get('passphrase')
        self.http_client = None
    
    async def init(self):
        """Initialize HTTP client."""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("OKX Trader initialized")
    
    async def cleanup(self):
        """Cleanup client."""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("OKX Trader shut down")
    
    async def execute_order(self, order: Order, current_price: float) -> Dict[str, Any]:
        """
        Execute order on OKX.
        
        Args:
            order: Order to execute
            current_price: Current market price (for reference)
            
        Returns:
            Execution result
        """
        # TODO: Implement OKX API integration
        # This is a placeholder for actual API calls
        logger.warning("Live trading not yet implemented")
        return {}


class RiskManager:
    """Risk management and position limits."""
    
    def __init__(self, trader_config: Dict[str, Any]):
        self.trader_config = trader_config
        self.max_position_size = trader_config.get('max_position_size_usdt', 1000)
        self.max_daily_loss = trader_config.get('max_daily_loss_usdt', 200)
        self.max_consecutive_losses = trader_config.get('max_consecutive_losses', 3)
        
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
    
    def check_risk_limits(self, order: Order) -> tuple[bool, str]:
        """
        Check if order violates risk limits.
        
        Returns:
            (allowed, reason)
        """
        # Check position size
        order_value = order.quantity * order.price
        if order_value > self.max_position_size:
            return False, f"Order size {order_value} exceeds max {self.max_position_size}"
        
        # Check daily loss limit
        if self.daily_pnl < -self.max_daily_loss:
            return False, f"Daily loss {self.daily_pnl} exceeds limit {self.max_daily_loss}"
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, f"Consecutive losses {self.consecutive_losses} exceeds limit"
        
        return True, ""
    
    def update_pnl(self, pnl: float):
        """Update daily PnL."""
        self.daily_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def reset_daily(self):
        """Reset daily metrics."""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0


class Trader:
    """Trade execution service."""
    
    def __init__(self):
        """Initialize trader."""
        self.config = get_config()
        self.trader_config = self.config.get('trader', {})
        self.app_config = self.config.get('app', {})
        self.risk_config = self.config.get('risk', {})
        
        self.db = get_db()
        self.redis = get_redis()
        self.symbol = self.app_config.get('symbol', 'BTC-USDT')
        self.mode = TradingMode(self.app_config.get('mode', 'paper'))
        
        # Initialize traders
        self.paper_trader = PaperTrader(
            fee_pct=self.trader_config.get('fee_pct', 0.001),
            slippage_pct=self.trader_config.get('slippage_pct', 0.001)
        )
        self.live_trader = OKXTrader()
        
        self.risk_manager = RiskManager(self.trader_config)
        
        self.position_size = self.trader_config.get('position_size_usdt', 100)
    
    async def init(self):
        """Initialize connections."""
        await self.db.connect()
        await self.redis.connect()
        await self.live_trader.init()
        
        logger.info("Trader initialized", extra={'mode': self.mode.value})
    
    async def cleanup(self):
        """Cleanup connections."""
        await self.live_trader.cleanup()
        await self.redis.close()
        await self.db.close()
        logger.info("Trader shut down")
    
    async def execute_signal(self, signal_data: Dict[str, Any]):
        """Execute trading signal."""
        signal_type = signal_data.get('signal_type')
        price = signal_data.get('price', 0)
        model_id = signal_data.get('model_id')
        
        # Only process BUY/SELL signals
        if signal_type not in ['BUY', 'SELL']:
            return
        
        # Create order
        side = OrderSide.BUY if signal_type == 'BUY' else OrderSide.SELL
        
        # Calculate quantity
        quantity = self.position_size / price
        
        order = Order(
            signal_id=None,  # Will be set after signal is saved
            model_id=model_id,
            symbol=self.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=price,
            mode=self.mode
        )
        
        # Check risk limits
        allowed, reason = self.risk_manager.check_risk_limits(order)
        if not allowed:
            logger.warning("Order rejected by risk manager", extra={'reason': reason})
            return
        
        # Execute based on mode
        if self.mode == TradingMode.PAPER:
            execution_result = await self.paper_trader.execute_order(order, price)
        elif self.mode == TradingMode.LIVE:
            execution_result = await self.live_trader.execute_order(order, price)
        else:  # SHADOW mode
            logger.info("Shadow mode: signal received but not executed", extra={'signal': signal_data})
            return
        
        # Save order to database
        await self.save_order(order, execution_result)
        
        # Update risk metrics
        if execution_result.get('status') == OrderStatus.FILLED.value:
            await self.update_position(model_id, order, execution_result)
    
    async def save_order(self, order: Order, execution_result: Dict[str, Any]):
        """Save order to database."""
        query = """
            INSERT INTO orders (
                signal_id, model_id, order_id, symbol, side, order_type, price,
                filled_price, quantity, filled_quantity, fee, fee_currency, status, mode
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """
        
        order_id = await self.db.fetchval(
            query,
            order.signal_id,
            order.model_id,
            execution_result.get('order_id'),
            order.symbol,
            order.side.value,
            order.order_type.value,
            order.price,
            execution_result.get('filled_price'),
            order.quantity,
            execution_result.get('filled_quantity'),
            execution_result.get('fee'),
            execution_result.get('fee_currency'),
            execution_result.get('status'),
            self.mode.value
        )
        
        logger.info("Order saved", extra={'order_id': order_id})
    
    async def update_position(self, model_id: int, order: Order, execution_result: Dict[str, Any]):
        """Update trading position."""
        # Check if position exists
        query = """
            SELECT * FROM positions
            WHERE model_id = $1 AND symbol = $2 AND closed_at IS NULL
        """
        
        position = await self.db.fetchrow(query, model_id, self.symbol)
        
        filled_price = execution_result.get('filled_price')
        filled_quantity = execution_result.get('filled_quantity')
        
        if not position:
            # Create new position
            if order.side == OrderSide.BUY:
                await self.db.execute(
                    "INSERT INTO positions (model_id, symbol, side, quantity, entry_price, mode) VALUES ($1, $2, 'long', $3, $4, $5)",
                    model_id, self.symbol, filled_quantity, filled_price, self.mode.value
                )
        else:
            # Update or close position
            if order.side == OrderSide.SELL and position['side'] == 'long':
                # Close long position
                pnl = (filled_price - position['entry_price']) * filled_quantity
                
                await self.db.execute(
                    "UPDATE positions SET closed_at = NOW() WHERE id = $1",
                    position['id']
                )
                
                # Update risk manager
                self.risk_manager.update_pnl(pnl)
    
    async def listen_for_signals(self):
        """Listen for trading signals."""
        logger.info("Starting signal listener")
        
        while True:
            try:
                # Listen to signal stream
                messages = await self.redis.read(
                    {Streams.SIGNALS: '0'},
                    count=10,
                    block=5000
                )
                
                for msg in messages:
                    signal_data = msg['fields'].get('data', {})
                    await self.execute_signal(signal_data)
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error("Error in signal listener", extra={'error': str(e)})
                await asyncio.sleep(10)
    
    async def run(self):
        """Main execution loop."""
        await self.listen_for_signals()


async def main():
    """Main entry point."""
    trader = Trader()
    
    try:
        await trader.init()
        await trader.run()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error("Fatal error", extra={'error': str(e)})
        raise
    finally:
        await trader.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

