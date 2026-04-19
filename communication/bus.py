"""
Redis-based communication bus for agents.
Enables real-time inter-agent messaging (Ask/Answer/Broadcast)
and persistent job state tracking.
"""
import json
import logging
import uuid
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import redis.asyncio as redis
from config.settings import settings

logger = logging.getLogger(__name__)

@dataclass
class AgentMessage:
    """Standard message format for the Agent Bus."""
    sender: str
    content: str
    message_type: str = "broadcast"  # broadcast | ask | answer | blocker | decision
    channel: str = "general"
    recipient: Optional[str] = None
    reply_to: Optional[str] = None
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: Union[str, bytes]) -> "AgentMessage":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls(**json.loads(data))

class MessageBus:
    """Redis Pub/Sub wrapper for agent communication."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.redis_url
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None

    async def connect(self):
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            logger.info(f"Connected to Redis at {self.redis_url}")

    async def publish(self, message: AgentMessage):
        """Publish a message to a channel."""
        await self.connect()
        # Publish to specific channel
        await self._redis.publish(f"agent_bus:{message.channel}", message.to_json())
        # Also publish to recipient's private channel if specified
        if message.recipient:
            await self._redis.publish(f"agent_bus:private:{message.recipient}", message.to_json())
        # Also log to a global stream for the dashboard
        await self._redis.publish("agent_bus:stream", message.to_json())

    async def subscribe(self, channels: List[str], callback: Callable[[AgentMessage], Any]):
        """Subscribe to channels and call callback on message."""
        await self.connect()
        pubsub = self._redis.pubsub()
        
        full_channels = [f"agent_bus:{c}" for c in channels]
        await pubsub.subscribe(*full_channels)
        
        logger.info(f"Subscribed to channels: {channels}")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    agent_msg = AgentMessage.from_json(message["data"])
                    if asyncio.iscoroutinefunction(callback):
                        await callback(agent_msg)
                    else:
                        callback(agent_msg)
                except Exception as e:
                    logger.error(f"Error in bus callback: {e}")

class JobStore:
    """Redis-backed storage for pipeline jobs."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)

    async def set_job(self, job_id: str, data: Dict[str, Any], ttl: int = 86400):
        """Store job data with 24h default TTL."""
        await self.connect()
        await self._redis.set(f"job:{job_id}", json.dumps(data), ex=ttl)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job data."""
        await self.connect()
        data = await self._redis.get(f"job:{job_id}")
        return json.loads(data) if data else None

    async def update_job(self, job_id: str, updates: Dict[str, Any]):
        """Update specific fields in job data."""
        await self.connect()
        job = await self.get_job(job_id)
        if job:
            job.update(updates)
            await self.set_job(job_id, job)

    async def list_jobs(self, pattern: str = "job:*") -> List[Dict[str, Any]]:
        """List all jobs matching pattern."""
        await self.connect()
        keys = await self._redis.keys(pattern)
        if not keys:
            return []
        
        jobs_json = await self._redis.mget(keys)
        return [json.loads(j) for j in jobs_json if j]
