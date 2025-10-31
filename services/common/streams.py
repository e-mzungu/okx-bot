"""Redis Streams utilities."""

import json
import asyncio
import redis.asyncio as aioredis
from typing import Dict, List, Any, Optional
from datetime import datetime

from .cfg import get_config


class RedisStreams:
    """Redis Streams manager."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.config = get_config()
        self.redis_config = self.config.get('redis', {})
        self.client: Optional[aioredis.Redis] = None
    
    async def connect(self):
        """Connect to Redis."""
        if self.client is None:
            self.client = aioredis.Redis(
                host=self.redis_config.get('host', 'localhost'),
                port=self.redis_config.get('port', 6379),
                db=self.redis_config.get('db', 0),
                decode_responses=self.redis_config.get('decode_responses', True)
            )
    
    async def close(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            self.client = None
    
    async def add(self, stream: str, fields: Dict[str, Any], maxlen: int = None) -> str:
        """
        Add message to stream.
        
        Args:
            stream: Stream name
            fields: Message fields
            maxlen: Optional max length (uses config default if not set)
            
        Returns:
            Message ID
        """
        # Serialize values
        serialized = {}
        for key, value in fields.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            else:
                serialized[key] = str(value)
        
        maxlen = maxlen or self.redis_config.get('stream_maxlen', 10000)
        
        return await self.client.xadd(stream, serialized, maxlen=maxlen)
    
    async def read(self, streams: Dict[str, str], count: int = 10,
                   block: int = None) -> List[Dict[str, Any]]:
        """
        Read messages from streams.
        
        Args:
            streams: Dict mapping stream names to last ID
            count: Maximum number of messages per stream
            block: Block time in milliseconds (None for non-blocking)
            
        Returns:
            List of messages
        """
        messages = await self.client.xread(streams, count=count, block=block)
        
        result = []
        for stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                # Deserialize values
                deserialized = {}
                for key, value in fields.items():
                    # Try to deserialize JSON
                    try:
                        deserialized[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        # Keep as string if not JSON
                        deserialized[key] = value
                
                result.append({
                    'stream': stream_name,
                    'id': msg_id,
                    'fields': deserialized
                })
        
        return result
    
    async def group_create(self, stream: str, group: str, start_id: str = '0'):
        """Create consumer group."""
        await self.client.xgroup_create(stream, group, start_id)
    
    async def read_group(self, group: str, consumer: str, streams: Dict[str, str],
                        count: int = 10, block: int = None) -> List[Dict[str, Any]]:
        """
        Read messages from group.
        
        Args:
            group: Consumer group name
            consumer: Consumer name
            streams: Dict mapping stream names to '>' (next unread) or specific ID
            count: Maximum number of messages
            block: Block time in milliseconds
            
        Returns:
            List of messages
        """
        messages = await self.client.xreadgroup(
            group, consumer, streams, count=count, block=block
        )
        
        result = []
        for stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                deserialized = {}
                for key, value in fields.items():
                    try:
                        deserialized[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        deserialized[key] = value
                
                result.append({
                    'stream': stream_name,
                    'id': msg_id,
                    'fields': deserialized
                })
        
        return result
    
    async def ack(self, group: str, stream: str, *message_ids: str):
        """Acknowledge messages."""
        await self.client.xack(group, stream, *message_ids)
    
    async def pending(self, group: str, stream: str, count: int = 100):
        """Get pending messages."""
        return await self.client.xpending(stream, group, count=count)


class Streams:
    """Stream name constants and utilities."""
    
    # Stream names
    CANDLES = 'stream:candles'
    FEATURES = 'stream:features'
    SIGNALS = 'stream:signals'
    ORDERS = 'stream:orders'
    FILLS = 'stream:fills'
    
    @staticmethod
    async def publish_candle(redis: RedisStreams, symbol: str, interval: str,
                            timestamp: datetime, candle: Dict[str, Any]) -> str:
        """Publish candle to stream."""
        return await redis.add(
            Streams.CANDLES,
            {
                'symbol': symbol,
                'interval': interval,
                'timestamp': timestamp.isoformat(),
                'candle': candle
            }
        )
    
    @staticmethod
    async def publish_features(redis: RedisStreams, symbol: str, interval: str,
                              timestamp: datetime, features: Dict[str, Any]) -> str:
        """Publish features to stream."""
        return await redis.add(
            Streams.FEATURES,
            {
                'symbol': symbol,
                'interval': interval,
                'timestamp': timestamp.isoformat(),
                'features': features
            }
        )
    
    @staticmethod
    async def publish_signal(redis: RedisStreams, model_id: int, symbol: str,
                            signal_type: str, timestamp: datetime,
                            signal_data: Dict[str, Any]) -> str:
        """Publish signal to stream."""
        return await redis.add(
            Streams.SIGNALS,
            {
                'model_id': model_id,
                'symbol': symbol,
                'signal_type': signal_type,
                'timestamp': timestamp.isoformat(),
                'data': signal_data
            }
        )


# Global Redis instance
_redis_instance = None


def get_redis() -> RedisStreams:
    """Get or create global Redis instance."""
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisStreams()
    return _redis_instance

