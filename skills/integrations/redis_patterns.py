"""
Integration skill: Redis patterns for caching, rate limiting, sessions, and queues.
Mirrors skills/backend/api_patterns.py structure — patterns with code templates.
"""

REDIS_CACHING_PATTERNS = {
    "cache_aside": {
        "name": "Cache-Aside (Lazy Loading)",
        "description": "Application manages cache directly. Check cache first, fall back to DB, then populate cache.",
        "pros": ["Simple to understand", "Only cached data is stored", "Cache misses are predictable"],
        "cons": ["Cache miss penalty (additional DB call)", "Stale data between invalidation"],
        "python_fastapi": '''
# async version with asyncpg/asyncpg
from redis.asyncio import Redis

redis = Redis.from_url(os.getenv('REDIS_URL'))

async def get_user(user_id: str) -> User:
    # 1. Check cache
    cached = await redis.get(f"user:{user_id}")
    if cached:
        return User.parse_raw(cached)

    # 2. DB hit
    user = await db.users.get(user_id)
    if not user:
        return None

    # 3. Cache with TTL (adjust based on data volatility)
    await redis.setex(f"user:{user_id}", 3600, user.json())

    return user

async def update_user(user_id: str, updates: dict):
    # Update DB first
    user = await db.users.update(user_id, updates)

    # Invalidate cache (not update — simpler, avoids race conditions)
    await redis.delete(f"user:{user_id}")

    return user
''',
        "node_nest": '''
import { Redis } from 'ioredis'

async getUser(userId: string): Promise<User> {
  const cacheKey = `user:${userId}`
  const cached = await this.redis.get(cacheKey)
  if (cached) {
    return JSON.parse(cached)
  }

  const user = await this.userRepo.findOneBy({ id: userId })
  if (!user) return null

  await this.redis.setex(cacheKey, 3600, JSON.stringify(user))
  return user
}

async updateUser(userId: string, updates: UpdateUserDto) {
  const user = await this.userRepo.update(userId, updates)
  await this.redis.del(`user:${userId}`)
  return user
}
''',
        "when_to_use": "Read-heavy workloads (80% reads, 20% writes), data changes infrequently",
        "ttl_guidelines": {
            "user_profile": "1 hour",
            "product_catalog": "1 day",
            "configuration": "1 week",
            "session_data": "15 minutes",
        },
    },
    "write_through": {
        "name": "Write-Through Cache",
        "description": "Write to both cache and DB synchronously. Cache is always fresh.",
        "pros": ["Cache always up-to-date", "Subsequent reads always hit cache"],
        "cons": ["Write latency ↑ (two writes)", "Complex to manage consistency"],
        "python_fastapi": '''
async def update_user(user_id: str, updates: dict):
    # Update cache first (or DB first — order doesn't matter if both succeed)
    user = await db.users.update(user_id, updates)
    await redis.setex(f"user:{user_id}", 3600, user.json())
    return user
''',
        "when_to_use": "Small datasets, write-heavy with immediate read-after-write (e.g. shopping cart)",
    },
    "read_through": {
        "name": "Read-Through Cache",
        "description": "Cache intercepts all reads. Application never checks cache directly.",
        "pros": ["Application code simpler", "Cache logic centralized"],
        "cons": ["Requires cache proxy layer", "Less control over cache strategy"],
        "pattern": "Use Redis as front cache for DB. Read hits Redis → Redis checks DB if miss",
        "when_to_use": "Transparent caching without app changes (use Twemproxy, Envoy)",
    },
}

REDIS_RATE_LIMITING = '''
# ── Token Bucket Algorithm (Fixed Window Counter) ─────────────────────────────
# Limit: 100 requests per minute per user

import time
from redis import Redis

redis = Redis.from_url(os.getenv('REDIS_URL'))

def rate_limit(user_id: str, limit: int = 100, window: int = 60) -> bool:
    """
    Returns True if request is allowed, False if rate limited.
    Uses Redis INCR with expiry (fixed window).
    """
    key = f"ratelimit:{user_id}:{int(time.time() // window)}"

    # INCR is atomic — safe for concurrent requests
    current = redis.incr(key)

    if current == 1:
        # First request in this window — set expiry
        redis.expire(key, window)

    return current <= limit

# Usage in FastAPI middleware:
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    user_id = get_current_user_id(request) or request.client.host
    if not rate_limit(user_id, limit=100, window=60):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Try again later."}
        )
    return await call_next(request)
'''

REDIS_RATE_LIMITING_ALGORITHMS = {
    "fixed_window": {
        "description": "Simple counter reset at interval boundaries (e.g., 60s)",
        "code": "INCR key, EXPIRE key on first request",
        "pros": ["Simple", "O(1) operation"],
        "cons": ["Burst at window boundaries (user can exceed limit twice)"],
    },
    "sliding_window": {
        "description": "Track timestamps in sorted set, count items in time window",
        "code": '''
import time

def allow_request(user_id: str, limit: int = 100, window: int = 60) -> bool:
    now = time.time()
    key = f"ratelimit:{user_id}"

    # Add current timestamp
    redis.zadd(key, {str(now): now})

    # Remove old entries (outside window)
    redis.zremrangebyscore(key, 0, now - window)

    # Count current requests
    count = redis.zcard(key)

    # Set expiry on key to auto-cleanup
    redis.expire(key, window)

    return count <= limit
''',
        "pros": ["Accurate sliding window", "No burst at boundaries"],
        "cons": ["Memory ↑ (store timestamps)", "ZSET operations more expensive"],
    },
    "token_bucket": {
        "description": "Bucket of tokens refills at constant rate. Allows bursts up to bucket size.",
        "code": '''
import time

def consume_token(user_id: str, bucket_size: int = 100, refill_rate: float = 1.67) -> bool:
    """
    bucket_size: max tokens (burst capacity)
    refill_rate: tokens per second (100/min = 1.67/sec)
    """
    key = f"bucket:{user_id}"
    now = time.time()

    # Lua script for atomicity
    lua_script = '''
    local tokens = tonumber(redis.call('get', KEYS[1])) or ARGV[1]
    local last_refill = tonumber(redis.call('get', KEYS[2])) or ARGV[3]
    local now = tonumber(ARGV[2])
    local rate = tonumber(ARGV[3])

    local delta = math.max(0, now - last_refill)
    tokens = math.min(ARGV[1], tokens + delta * rate)

    if tokens >= 1 then
      tokens = tokens - 1
      redis.call('set', KEYS[1], tokens)
      redis.call('set', KEYS[2], now)
      redis.call('expire', KEYS[1], 60)
      redis.call('expire', KEYS[2], 60)
      return 1
    else
      return 0
    end
    '''

    result = redis.eval(
        lua_script,
        2,
        f"{key}:tokens",
        f"{key}:timestamp",
        bucket_size,  # ARGV[1] — bucket capacity
        now,         # ARGV[2] — current time
        last_refill, # ARGV[3] — last refill timestamp
        refill_rate  # ARGV[4] — tokens per second
    )

    return result == 1
''',
        "pros": ["Allows bursts", "Rate-limited over time"],
        "cons": ["Lua script complexity"],
    },
}

REDIS_SESSION_STORE = '''
# Store user session with expiry
async def create_session(user_id: str, session_data: dict) -> str:
    session_id = uuid4().hex
    key = f"session:{session_id}"

    await redis.hset(key, mapping={
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "user_agent": session_data.get("user_agent", ""),
        "ip_address": session_data.get("ip_address", ""),
    })
    await redis.expire(key, 86400)  # 24 hour expiry

    return session_id

async def get_session(session_id: str) -> dict | None:
    data = await redis.hgetall(f"session:{session_id}")
    return data if data else None

async def refresh_session(session_id: str, ttl: int = 86400):
    """Extend session expiry on activity"""
    await redis.expire(f"session:{session_id}", ttl)

async def revoke_session(session_id: str):
    await redis.delete(f"session:{session_id}")

# Session middleware for FastAPI
@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = request.cookies.get("session_id")
    if session_id:
        session = await get_session(session_id)
        if session:
            request.state.user_id = session["user_id"]
            await refresh_session(session_id)

    response = await call_next(request)
    return response
'''

REDIS_QUEUES = {
    "simple_queue": {
        "description": "Simple FIFO queue using LPUSH + BRPOP",
        "producer": "redis.lpush('queue:email', json.dumps(msg))",
        "consumer": "while True: data = redis.brpop('queue:email', timeout=5); process(data)",
        "use_case": "Simple background jobs without priority",
    },
    "reliable_queue": {
        "description": "Reliable queue with ack/nack using lists + pending set",
        "pattern": '''
# Producer: push to main list
LPUSH queue:email <message>

# Consumer:
# 1. BRPOPLPOP (atomic pop from main + push to pending)
message = BRPOPLPUSH queue:email queue:email:pending timeout

# 2. Process message
process(message)

# 3. Ack → remove from pending
LREM queue:email:pending 1 message

# If consumer crashes: messages stay in pending
# Periodic retry: RPOPLPUSH pending → queue for redelivery
# Dead letter: if retries > N, move to queue:email:dead
''',
        "pros": ["At-least-once delivery", "No message loss on crash"],
        "cons": ["Manual ack management", "Duplicate delivery possible"],
    },
    "priority_queue": {
        "description": "Use sorted set (ZSET) with score = priority",
        "push": '''
# Lower score = higher priority (processed first)
priority = 0  # 0 = highest, 10 = lowest
redis.zadd('queue:priority', {message: priority})
''',
        "pop": '''
# Get highest priority (lowest score)
message = redis.zrange('queue:priority', 0, 0)
redis.zrem('queue:priority', message)
''',
        "pros": ["Multiple priority levels"],
        "cons": ["Not FIFO within priority level unless score includes timestamp"],
    },
    "delayed_queue": {
        "description": "Schedule execution using ZSET with execution timestamp as score",
        "schedule": '''
execute_at = time.time() + 3600  # 1 hour from now
redis.zadd('queue:delayed', {message: execute_at})
''',
        "process_due": '''
now = time.time()
due = redis.zrangebyscore('queue:delayed', 0, now)
for msg in due:
    process(msg)
    redis.zrem('queue:delayed', msg)
''',
        "pros": ["Exactly-once scheduling", "No duplicate workers needed"],
        "cons": ["Must run periodic job to check for due messages"],
    },
}

REDIS_PUBSUB_PATTERNS = {
    "simple_pubsub": {
        "description": "Fire-and-forget broadcast to multiple subscribers",
        "publish": "redis.publish('channel:notifications', json.dumps(event))",
        "subscribe": '''
for message in redis.subscribe('channel:notifications'):
    event = json.loads(message)
    handle(event)
''',
        "characteristics": "No persistence, messages lost if subscriber offline",
        "use_cases": "Real-time notifications, chat messages, updates broadcast",
    },
    "sharded_pubsub": {
        "description": "Use Streams instead of PubSub for message persistence",
        "producer": "redis.xadd('stream:events', {'event': json.dumps(event)})",
        "consumer": '''
# Consumer group (multiple consumers share load)
redis.xgroup_create('stream:events', 'workers', mkstream=True)

# Each consumer:
messages = redis.xreadgroup('workers', consumer_name, {'stream:events': '>'}, count=10)
for msg in messages:
    process(msg)
    redis.xack('stream:events', 'workers', msg_id)
''',
        "pros": ["Message persistence", "Consumer groups", "Replay capability"],
        "cons": ["Streams grow unbounded — set maxlen"],
    },
}

REDIS_DISTRIBUTED_LOCKS = '''
# Using SET with NX + EX + unique value (Redlock algorithm requires multiple nodes, but simple lock works for single node)

async def acquire_lock(resource: str, timeout: int = 10) -> str | None:
    """
    Try to acquire lock on resource.
    Returns lock token if successful, None otherwise.
    """
    token = uuid4().hex
    acquired = await redis.set(
        f"lock:{resource}",
        token,
        nx=True,      # Only set if not exists
        ex=timeout    # Auto-expire after timeout (prevents deadlock)
    )
    return token if acquired else None

async def release_lock(resource: str, token: str):
    """
    Release lock using Lua script (atomic check-and-delete).
    Only release if token matches (prevents releasing someone else's lock).
    """
    lua = '''
    if redis.call("GET", KEYS[1]) == ARGV[1] then
      return redis.call("DEL", KEYS[1])
    else
      return 0
    end
    '''
    await redis.eval(lua, 1, f"lock:{resource}", token)

# Usage:
# lock = await acquire_lock("user:123:update")
# if lock:
#   try:
#     await update_user()
#   finally:
#     await release_lock("user:123:update", lock)
# else:
#   raise Exception("Resource busy")
'''

REDIS_CONNECTION_MANAGEMENT = {
    "single_connection": {
        "description": "Single Redis connection shared across app",
        "code": "redis = Redis.from_url(REDIS_URL, decode_responses=True)",
        "pros": ["Simple", "Connection pool handled by library"],
        "cons": ["Not optimal for multi-threaded apps"],
    },
    "connection_pool": {
        "description": "Explicit pool for multi-threaded/async apps",
        "python_sync": '''
from redis import RedisPool
pool = ConnectionPool(
    host='localhost',
    port=6379,
    max_connections=50,
    decode_responses=True
)
redis = Redis(connection_pool=pool)
''',
        "python_async": '''
from redis.asyncio import ConnectionPool
pool = ConnectionPool(
    host='localhost',
    port=6379,
    max_connections=100
)
redis = Redis(connection_pool=pool)
''',
        "node": '''
import ioredis from 'ioredis'

const redis = new Redis({
  host: 'localhost',
  port: 6379,
  maxRetriesPerRequest: null,  // retry failed commands
  enableReadyCheck: true,
  maxConnections: 100,
  family: 4,  // IPv4
})
''',
    },
}

REDIS_MONITORING_METRICS = {
    "memory_usage": "INFO memory → used_memory_human, mem_fragmentation_ratio",
    "hit_rate": "INFO stats → keyspace_hits / (keyspace_hits + keyspace_misses)",
    "connections": "INFO clients → connected_clients, client_recent_max_input_buffer",
    "slowlog": "SLOWLOG GET 10 → queries taking > slowlog-log-slower-than (default 10ms)",
    "keyspace": "INFO keyspace → keys, expires, avg_ttl",
    "alerts": [
        "Memory usage > 80% → eviction or scale up",
        "Hit rate < 80% → check cache effectiveness",
        "Connected clients > 1000 → connection pool tuning",
        "CPU > 70% → optimize queries or scale out",
    ],
}

REDIS_BEST_PRACTICES = [
    "Always set expiry on keys (avoid cache that never expires)",
    "Use meaningful key naming: `type:entity:id` (user:123, product:456:reviews)",
    "Don't store large objects (>10KB) in Redis — keep it small, cache IDs only",
    "Pipeline multiple commands: redis.pipeline() to reduce round trips",
    "Use JSON (not pickle) for Python serialization — faster, language-agnostic",
    "Monitor memory — enable maxmemory policy (allkeys-lru for cache)",
    "Avoid KEYS * in production — use SCAN or maintain index set",
    "Use Redis modules (RediSearch, RedisJSON) for complex data needs",
    "Backup: RDB for snapshots, AOF for durability (choose based on tolerance)",
    "Sentinel for HA, Cluster for sharding (>50GB dataset)",
]

REDIS_ANTI_PATTERNS = [
    "❌ Storing session data without expiry → memory leak",
    "❌ Using Redis as primary database (no persistence guarantees)",
    "❌ Cache invalidation on every write — defeats purpose of cache",
    "❌ Large keys (>10KB) — network bandwidth + memory waste",
    "❌ Not handling cache failures — app crashes if Redis down",
    "❌ KEYS * in production — blocks entire server (use SCAN)",
    "❌ WATCH/MULTI/EXEC for high contention — use Lua scripts instead",
]
