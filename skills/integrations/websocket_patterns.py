"""
Integration skill: WebSocket real-time communication patterns.
Covers connection management, broadcasting, scaling with Redis adapter, and reliability.
"""

WEBSOCKET_FASTAPI_PATTERNS = '''
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import asyncio

class ConnectionManager:
    """Manages active WebSocket connections grouped by room."""

    def __init__(self):
        # active_connections: Dict[room, List[WebSocket]]
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        """Accept connection and add to room."""
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        # Notify room of new participant
        await self.broadcast(
            room,
            {"type": "user_joined", "user_id": get_user_id(websocket)}
        )

    async def disconnect(self, websocket: WebSocket, room: str):
        """Remove connection and notify room if needed."""
        if room in self.active_connections:
            try:
                self.active_connections[room].remove(websocket)
            except ValueError:
                pass  # Already removed
            if not self.active_connections[room]:
                del self.active_connections[room]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send to single connection."""
        await websocket.send_json(message)

    async def broadcast(self, message: dict, room: str, exclude: WebSocket = None):
        """Send to all in room, optionally excluding one."""
        if room not in self.active_connections:
            return

        for conn in self.active_connections[room]:
            if conn != exclude:
                try:
                    await conn.send_json(message)
                except WebSocketDisconnect:
                    # Clean up disconnected
                    await self.disconnect(conn, room)

    async def broadcast_global(self, message: dict):
        """Send to all connections in all rooms."""
        for room in list(self.active_connections.keys()):
            await self.broadcast(message, room)

manager = ConnectionManager()

@app.websocket("/ws/{room}")
async def websocket_endpoint(
    websocket: WebSocket,
    room: str,
    token: str
):
    """Authenticated WebSocket endpoint with room-based broadcast."""
    # 1. Authenticate
    try:
        user = authenticate_ws(token)
        websocket.state.user_id = user.id
    except Exception as e:
        await websocket.accept()
        await websocket.send_json({"error": "Unauthorized"})
        await websocket.close()
        return

    # 2. Connect to room
    await manager.connect(websocket, room)

    try:
        # 3. Message loop
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "chat":
                # Broadcast chat message to room
                await manager.broadcast({
                    "type": "chat",
                    "user_id": user.id,
                    "username": user.username,
                    "content": data["content"],
                    "timestamp": datetime.utcnow().isoformat(),
                }, room, exclude=websocket)

            elif message_type == "typing":
                # Typing indicator (broadcast to room, exclude sender)
                await manager.broadcast({
                    "type": "typing",
                    "user_id": user.id,
                    "is_typing": data["is_typing"],
                }, room, exclude=websocket)

            elif message_type == "presence":
                # Update presence status
                await manager.broadcast({
                    "type": "presence",
                    "user_id": user.id,
                    "status": data["status"],  # online, away, offline
                }, room, exclude=websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, room)
        # Notify room of departure
        await manager.broadcast({
            "type": "user_left",
            "user_id": user.id,
        }, room)
'''

WEBSOCKET_REACT_CLIENT = '''
import { useEffect, useRef, useState, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

export function useWebSocket(roomId: string, token: string) {
  const socketRef = useRef<Socket | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set())

  useEffect(() => {
    // 1. Connect
    socketRef.current = io(process.env.WS_URL!, {
      auth: { token },
      query: { room: roomId },
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    })

    const socket = socketRef.current

    // 2. Event handlers
    socket.on('connect', () => {
      console.log('Connected to WebSocket')
      setIsConnected(true)
    })

    socket.on('disconnect', () => {
      console.log('Disconnected')
      setIsConnected(false)
    })

    socket.on('chat', (msg: Message) => {
      setMessages(prev => [...prev, msg])
    })

    socket.on('user_joined', (data) => {
      console.log(`${data.user_id} joined`)
    })

    socket.on('typing', (data) => {
      setTypingUsers(prev => {
        const next = new Set(prev)
        if (data.is_typing) {
          next.add(data.user_id)
        } else {
          next.delete(data.user_id)
        }
        return next
      })
    })

    socket.on('error', (err) => {
      console.error('WebSocket error:', err)
    })

    // 3. Cleanup on unmount
    return () => {
      socket.disconnect()
    }
  }, [roomId, token])

  // 4. Send functions
  const sendMessage = useCallback((content: string) => {
    socketRef.current?.emit('chat', { content })
  }, [])

  const sendTyping = useCallback((isTyping: boolean) => {
    socketRef.current?.emit('typing', { is_typing: isTyping })
  }, [])

  return {
    messages,
    isConnected,
    typingUsers,
    sendMessage,
    sendTyping,
  }
}
'''

SCALABILITY_PATTERNS = {
    "single_redis": {
        "description": "Single Redis Pub/Sub for small apps (<10k connections)",
        "architecture": """
All socket servers subscribe to same Redis channels
PubSub acts as message bus between servers
""",
        "pros": ["Simple", "No infrastructure overhead"],
        "cons": ["Single point of failure", "Redis bottleneck at scale"],
        "when": "Prototype, small team app (<10k concurrent)",
    },
    "redis_cluster_sharded": {
        "description": "Shard connections across multiple Redis instances",
        "architecture": """
Room hash % N → route to Redis shard N
Socket servers connect to all shards or subset
""",
        "pros": ["Horizontal scale", "No single point"],
        "cons": ["Cross-shard broadcast requires N messages"],
        "when": "Medium scale (10-100k connections)",
    },
    "socket_io_adapter": {
        "description": "Use Socket.IO Redis adapter for Node.js",
        "setup": '''
import { createAdapter } from '@socket.io/redis-adapter'
import { createClient } from 'redis'

const pubClient = createClient({ url: process.env.REDIS_URL })
const subClient = pubClient.duplicate()

await Promise.all([pubClient.connect(), subClient.connect()])

io.adapter(createAdapter(pubClient, subClient))
''',
        "benefits": "Multi-process Node app can share rooms/events",
    },
    "horizontal_scale": {
        "description": "Multiple socket server instances + load balancer",
        "load_strategies": [
            "IP Hash (sticky sessions — same user → same server)",
            "Consistent hashing on room ID",
            "No stickiness (requires Redis adapter for cross-server broadcast)",
        ],
        "lb_config": """
# Nginx sticky sessions:
upstream websocket {
  ip_hash;  # Or sticky cookie
  server ws1.example.com;
  server ws2.example.com;
}
""",
    },
}

RELIABILITY_PATTERNS = {
    "heartbeat": {
        "description": "Client sends ping every 30s, server responds pong",
        "client": '''
setInterval(() => {
  socket.emit('ping', Date.now())
}, 30000)

socket.on('pong', (timestamp) => {
  const latency = Date.now() - timestamp
  console.log(`Latency: ${latency}ms`)
})
''',
        "server": '''
# FastAPI
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    async def heartbeat():
        while True:
            try:
                await websocket.send_json({"type": "pong", "ts": time.time()})
                await asyncio.sleep(30)
            except:
                break

    asyncio.create_task(heartbeat())
    # ... main message loop
''',
        "purpose": "Detect dead connections (close them after missed pings)",
    },
    "reconnection": {
        "client": "Socket.IO auto-reconnects with exponential backoff",
        "offline_queue": '''
# Queue messages while offline, send on reconnect
const offlineQueue = []

socket.on('disconnect', () => {
  console.log('Offline — buffering messages')
})

socket.on('reconnect', () => {
  while (offlineQueue.length > 0) {
    const msg = offlineQueue.shift()
    socket.emit(msg.type, msg.data)
  }
})

// Buffer while disconnected
function send(type, data) {
  if (socket.connected) {
    socket.emit(type, data)
  } else {
    offlineQueue.push({ type, data })
  }
}
''',
    },
}

SECURITY_PATTERNS = {
    "authentication": {
        "jwt": "Pass JWT in auth header during socket handshake (not in messages)",
        "connection_validation": '''
# Validate token on connection
@app.websocket("/ws")
async def ws(websocket: WebSocket, token: str = Query(...)):
    user = verify_jwt(token)
    if not user:
        await websocket.close(code=4001)  # Custom close code for auth failure
    await manager.connect(websocket, room)
''',
        "refresh": "Reject connection if token expired, client must re-auth",
    },
    "authorization": {
        "room_permissions": "Check user has access to room before joining",
        "per_room_check": '''
async def join_room(user: User, room: str):
    if room.startswith('private:'):
        room_user_id = room.split(':')[1]
        if room_user_id != user.id:
            raise PermissionError()
''',
    },
    "rate_limiting": {
        "per_connection": "Limit messages per second per connection",
        "global": "Limit total messages per room per second",
        "implementation": '''
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.websocket("/ws/{room}")
@limiter.limit("100/minute")  # Max 100 messages per minute
async def ws(...): ...
''',
    },
    "input_validation": {
        "message_schema": "Validate all incoming messages against JSON schema",
        "max_size": "Reject messages > 1MB (memory exhaustion attack)",
        "rate_limit_user": "Enforce per-user rate limits (not just connection)",
    },
}

CHAT_APPLICATION_PATTERN = '''
# Full chat app: rooms, private messages, message history

POSTGRES_SCHEMA = '''
-- messages table (canonical source)
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  room_id VARCHAR(100) NOT NULL,
  user_id UUID NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- indexes
CREATE INDEX idx_messages_room_created ON messages(room_id, created_at DESC);
'''

# Flow:
# 1. WebSocket for real-time delivery (push new messages to room)
# 2. REST API for history (GET /rooms/{room}/messages?before=timestamp)
# 3. Optional: Redis cache for recent messages (last 100 per room)

# WebSocket handler:
@app.websocket("/ws/chat/{room_id}")
async def chat_ws(websocket: WebSocket, room_id: str, token: str):
    user = authenticate(token)
    await manager.connect(websocket, room_id)

    # Load recent history
    recent = await db.fetch("""
        SELECT m.*, u.username, u.avatar_url
        FROM messages m
        JOIN users u ON u.id = m.user_id
        WHERE m.room_id = $1
        ORDER BY m.created_at DESC LIMIT 50
    """, room_id)
    await websocket.send_json({"type": "history", "messages": recent[::-1]})

    # Message loop
    while True:
        data = await websocket.receive_json()
        content = data["content"]

        # Save to Postgres (source of truth)
        msg = await db.fetchrow("""
            INSERT INTO messages (id, room_id, user_id, content)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """, uuid4(), room_id, user.id, content)

        # Broadcast to room via Redis (Pub/Sub)
        await redis.publish(f"room:{room_id}", json.dumps({
            "type": "message",
            "message": dict(msg),
            "user": {"id": user.id, "username": user.username},
        }))
'''

NOTIFICATION_SYSTEM_PATTERN = '''
# User notifications (real-time + offline storage)

NOTIFICATION_TYPES = [
    "friend_request",
    "message_received",
    "subscription_expiring",
    "mention",
]

# 1. Create notification in DB
async def create_notification(user_id: str, type: str, data: dict):
    notification = await db.fetchrow("""
        INSERT INTO notifications (id, user_id, type, data, is_read)
        VALUES ($1, $2, $3, $4, false)
        RETURNING *
    """, uuid4(), user_id, type, data)

    # 2. Push via WebSocket if user online
    if user_id in online_users:
        await send_ws(user_id, {
            "type": "notification",
            "notification": notification,
        })

    # 3. Push to mobile (APNs/FCM) for offline
    device_tokens = await get_device_tokens(user_id)
    for token in device_tokens:
        apns.send(token, title="New notification", body=data["summary"])

# 4. Client receives WS notification → shows banner/badge
'''

WEBSOCKET_MONITORING = {
    "metrics": [
        "active_connections (gauge)",
        "messages_sent_total (counter)",
        "messages_received_total (counter)",
        "connection_duration_seconds (histogram)",
        "messages_per_connection (counter)",
        "ws_latency_ms (histogram)",
        "disconnect_reason (counter: normal, error, timeout)",
    ],
    "log_sampling": "Log connection open/close at WARN, errors at ERROR",
    "alerts": [
        "Connection count > threshold (scale up workers)",
        "Message rate spikes (possible abuse)",
        "High latency (>500ms) to region",
        "Disconnect error rate > 5% (network issues)",
    ],
}

WEBSOCKET_ERROR_HANDLING = [
    "Handle WebSocketDisconnect gracefully (cleanup resources)",
    "Catch JSON parse errors (malformed messages)",
    "Retry reconnect with backoff (client-side)",
    "Close with appropriate code (1000 normal, 1001 going away, 4001 auth fail)",
    "Log unexpected exceptions but don't crash loop",
    "Timeout idle connections (30min no messages)",
    "Validate message size (<1MB default limit)",
]

WEBSOCKET_TESTING = {
    "unit_tests": "Test ConnectionManager connect/disconnect/broadcast logic",
    "integration_tests": [
        "Full client-server connection (socket.io-client in test)",
        "Send message → verify broadcast to room",
        "Auth failure → connection rejected",
        "Disconnection → cleanup verified",
        "Message persistence → message saved to DB",
    ],
    "load_testing": [
        "Autobahn Test Suite (WebSocket protocol compliance)",
        "Custom: 1000 concurrent connections, measure latency",
        "autobahntestsuite (fuzzing, edge cases)",
    ],
}
