# Architecture Overhaul: From Pipeline Engine to AI Engineering Company

> **Scope**: This document recommends **fundamental** changes to infrastructure, data layer, orchestration, LLM integration, and application architecture. Nothing is off the table. If Supabase needs to go, it goes. If the orchestrator needs to be torn out and replaced, it gets replaced.
>
> **Philosophy**: Build the system the way you'd build it if you were starting fresh in 2026, but map a migration path from where you are today.

---

## Table of Contents

1. [The Verdict: What Stays, What Goes, What Changes](#1-the-verdict)
2. [Infrastructure Overhaul](#2-infrastructure-overhaul)
3. [LLM Layer: Multi-Provider with LiteLLM](#3-llm-layer)
4. [Orchestration: Replace DAG with Temporal.io](#4-orchestration)
5. [Communication: Real-Time Agent Bus](#5-communication)
6. [Data Architecture: Polyglot Persistence](#6-data-architecture)
7. [Agent Architecture: From Functions to Microservices](#7-agent-architecture)
8. [Frontend: Sprint Dashboard](#8-frontend)
9. [Migration Path](#9-migration-path)
10. [Cost Analysis](#10-cost-analysis)

---

## 1. The Verdict: What Stays, What Goes, What Changes {#1-the-verdict}

### ✅ KEEP (Strong Foundation)

| Component | Why It's Good | File(s) |
|-----------|--------------|---------|
| **Agent Specialization** | 10 well-defined roles with deep system prompts, local pre-scanners, and tool access | `agents/*.py` |
| **Skills Library** | Rich domain knowledge (OWASP, React patterns, FastAPI patterns, Jira templates) | `skills/` |
| **Tool Registry** | Allowlist-based security, clean plugin architecture | `tools/registry.py` |
| **Agent Config + Cost Tracking** | Per-model pricing, cost caps, typed artifacts | `agents/agent_config.py` |
| **Circuit Breaker + Retry** | Production-grade fault tolerance | `agents/retry.py` |
| **YAML Template System** | Declarative pipeline definitions with variable substitution | `pipeline/config_loader.py` |

### ⚠️ EVOLVE (Keep but Significantly Rearchitect)

| Component | Current | Problem | Target |
|-----------|---------|---------|--------|
| **`BaseAgent`** | Synchronous, single-LLM, no communication | Can't hold conversations, no mid-task delegation, anthropic-only | Async, multi-LLM, with inbox/outbox |
| **FastAPI Backend** | Monolith with in-memory `_jobs` dict | Won't survive restarts, no horizontal scaling | Keep FastAPI but split into service modules, use external job queue |
| **Memory Store** | SQLite local + Supabase PostgreSQL (dual) | Two competing stores, no vector search, no semantic recall | Unified PostgreSQL (keep Supabase) + pgvector + Redis |
| **Pipeline UI** | Template → Validate → Preview → Run | Static pipeline builder, no sprint/team view | Add Sprint Board, Agent Chat Viewer, Burndown Chart |

### 🔴 REPLACE (Fundamental Limitations)

| Component | Current | Why Replace | Replacement |
|-----------|---------|-------------|-------------|
| **Orchestrator Engine** | Custom DAG walker in `orchestrator.py` | No durability (crashes lose state), no cross-process signals, can't pause for days | **Temporal.io** — battle-tested workflow engine |
| **In-Memory Job Store** | `_jobs: dict[str, dict]` in `api/main.py:35` | Lost on restart, no scaling | **Redis** — shared job state |
| **Direct Anthropic Client** | Hardcoded `anthropic.Anthropic()` everywhere | Single provider, no fallback, no cost governance | **LiteLLM Proxy** — multi-provider routing |
| **String-Based Communication** | Raw text passed as context between agents | No structure, no bidirectional flow | **Typed Message Protocol + Redis Pub/Sub** |

---

## 2. Infrastructure Overhaul {#2-infrastructure-overhaul}

### Current Stack

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  React UI  │────▶│  FastAPI    │────▶│  Anthropic  │
│  (Vite)    │     │  (single)   │     │  API only   │
└────────────┘     └─────┬──────┘     └────────────┘
                         │
                   ┌─────▼──────┐
                   │  Supabase  │
                   │  (PG only) │
                   └────────────┘
```

### Target Stack (v2)

```
┌───────────────────────────────────────────────────────────────────────┐
│                          React Dashboard (Vite)                       │
│   Sprint Board │ Agent Chat │ Pipeline Builder │ Burndown │ Standups  │
└──────────┬──────────────────────────┬────────────────────────────────┘
           │ REST/WebSocket           │ SSE (live status)
┌──────────▼──────────────────────────▼────────────────────────────────┐
│                       FastAPI Gateway                                 │
│  Auth │ Rate Limit │ Route to Services │ WebSocket Hub                │
└──────────┬──────────────┬────────────────┬───────────────────────────┘
           │              │                │
    ┌──────▼──────┐ ┌─────▼─────┐   ┌─────▼──────┐
    │  Sprint     │ │  Pipeline │   │  Agent     │
    │  Service    │ │  Service  │   │  Service   │
    └──────┬──────┘ └─────┬─────┘   └─────┬──────┘
           │              │                │
    ┌──────▼──────────────▼────────────────▼──────┐
    │              Temporal.io                      │
    │   Workflows: Sprint │ Pipeline │ Review       │
    │   Activities: AgentRun │ Review │ Standup      │
    └──────────────────────┬──────────────────────┘
                           │
    ┌─────────┬────────────┼────────────┬──────────┐
    │         │            │            │          │
┌───▼──┐ ┌───▼──┐   ┌─────▼─────┐ ┌───▼──┐  ┌───▼────┐
│Redis │ │Supa- │   │  LiteLLM  │ │S3/   │  │GitHub/ │
│Cache │ │base  │   │  Proxy    │ │Minio │  │Jira/   │
│+Pub/ │ │PG +  │   │           │ │Files │  │Slack   │
│Sub   │ │pgvec │   │  ┌──┬──┐  │ │      │  │        │
└──────┘ └──────┘   │  │C │O │  │ └──────┘  └────────┘
                    │  │l │A │  │
                    │  │a │I │  │
                    │  │u │  │  │
                    │  │d │G │  │
                    │  │e │e │  │
                    │  │  │m │  │
                    │  └──┴──┘  │
                    └───────────┘
```

### New Infrastructure Components

| Component | Product | Why | Self-Hosted vs Managed |
|-----------|---------|-----|----------------------|
| **Workflow Engine** | Temporal.io | Durable, event-sourced workflows that survive crashes. Built-in signals, queries, timers. Sprint workflows that run for weeks. | **Self-hosted** (Docker) for dev, **Temporal Cloud** for prod |
| **Cache + Pub/Sub** | Redis 7 | Agent message bus, job state, session cache, rate limiting | **Upstash** (serverless Redis, free tier) or self-hosted |
| **Vector Search** | pgvector (Supabase extension) | Semantic memory recall ("find similar past decisions") — no new infra, just enable the extension | **Supabase** (already there, just enable pgvector) |
| **LLM Gateway** | LiteLLM Proxy | Multi-provider routing, cost tracking, fallback, budget enforcement | **Self-hosted** (Docker, lightweight) |
| **File Storage** | Supabase Storage or S3 | Generated code artifacts, sprint reports, build outputs | **Supabase Storage** (already included) |

> [!IMPORTANT]
> **Supabase stays** — but its role changes. It becomes the **relational + vector store** only. Redis handles real-time. Temporal handles workflows. LiteLLM handles LLM calls.

---

## 3. LLM Layer: Multi-Provider with LiteLLM {#3-llm-layer}

### Problem: Anthropic Lock-In

Your entire system is hardwired to the Anthropic SDK:

```python
# agents/base.py:25
import anthropic

# agents/base.py:53-58
_clients: dict[str, anthropic.Anthropic] = {}
def _get_client(api_key: str | None = None) -> anthropic.Anthropic:
    key = api_key or settings.anthropic_api_key
    ...
    _clients[key] = anthropic.Anthropic(api_key=key)

# pipeline/orchestrator.py:35
aclient = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
```

This means:
- No fallback if Anthropic has an outage (happened multiple times in 2025)
- Can't use cheaper models for simple tasks (Gemini Flash at $0.075/1M input)
- Can't use specialized models (GPT-4o for vision tasks, Gemini for search-grounded tasks)

### Solution: LiteLLM Proxy + Provider Abstraction

```python
# llm/client.py — NEW FILE (replaces direct anthropic imports)
"""
LLM abstraction layer.
All agent-to-LLM communication goes through this module.
Supports Anthropic, OpenAI, Google, local models via LiteLLM.
"""
import litellm
from dataclasses import dataclass

@dataclass
class LLMConfig:
    """Model routing configuration."""
    # Planning/Architecture (highest quality)
    planning_model: str = "anthropic/claude-opus-4-5"
    # Code generation (fast + good)
    coding_model: str = "anthropic/claude-sonnet-4-5"
    # Cheap tasks (summaries, routing, classification)
    fast_model: str = "anthropic/claude-haiku-4-5-20251001"
    # Vision tasks (screenshots, UI mockups)
    vision_model: str = "openai/gpt-4o"
    # Search-grounded tasks (research, docs lookup)
    search_model: str = "google/gemini-2.0-flash"
    # Fallback chain
    fallback_models: list[str] = None

    def __post_init__(self):
        if self.fallback_models is None:
            self.fallback_models = [
                "anthropic/claude-sonnet-4-5",
                "openai/gpt-4o",
                "google/gemini-2.0-flash",
            ]

class LLMClient:
    """Unified LLM client with routing, fallback, and cost tracking."""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()

    async def create_message(
        self,
        model: str,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Send a message to any LLM provider.

        Uses LiteLLM under the hood — model string format:
          "anthropic/claude-sonnet-4-5"
          "openai/gpt-4o"
          "google/gemini-2.0-flash"
        """
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + messages
        if tools:
            kwargs["tools"] = tools

        # LiteLLM handles provider-specific translation
        response = await litellm.acompletion(**kwargs)
        return response

    async def create_with_fallback(self, **kwargs) -> dict:
        """Try primary model, fall back to alternatives on failure."""
        primary_model = kwargs.pop("model")
        models_to_try = [primary_model] + self.config.fallback_models

        last_error = None
        for model in models_to_try:
            try:
                return await self.create_message(model=model, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed: {e}, trying next...")
                continue

        raise last_error
```

### Agent Config Changes

```python
# agents/agent_config.py — UPDATED
AGENT_CONFIGS: dict[str, AgentConfig] = {
    # Planning agents → Opus (reasoning-heavy)
    "ceo":          AgentConfig(model="anthropic/claude-opus-4-5", max_tokens=8192),
    "cto":          AgentConfig(model="anthropic/claude-opus-4-5", max_tokens=8192),
    "pm":           AgentConfig(model="anthropic/claude-opus-4-5", max_tokens=8192),

    # Code generation → Sonnet (fast + high quality code)
    "be_architect": AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=8192),
    "fe_architect": AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=8192),
    "backend":      AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=8192),
    "frontend":     AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=8192),

    # Cheap tasks → Haiku or Gemini Flash
    "standup_bot":  AgentConfig(model="anthropic/claude-haiku-4-5-20251001", max_tokens=2048),
    "scrum_master": AgentConfig(model="google/gemini-2.0-flash", max_tokens=4096),

    # Security → Opus (safety-critical)
    "security":     AgentConfig(model="anthropic/claude-opus-4-5", max_tokens=8192),

    # Reviews → Sonnet (needs to read + critique code)
    "code_review":  AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=4096),
    "qa":           AgentConfig(model="anthropic/claude-sonnet-4-5", max_tokens=8192),
}
```

### Why This Matters

| Scenario | Before (Anthropic-only) | After (Multi-LLM) |
|----------|------------------------|-------------------|
| Anthropic outage | **System down** | Automatic fallback to OpenAI/Google |
| Standup summary | $0.015/standup (Haiku) | $0.005/standup (Gemini Flash) |
| CEO strategic planning | $15/1M tokens (Opus) | Same quality, but can A/B test against GPT-4o |
| Code review with screenshots | **Not possible** | GPT-4o vision model analyzes UI |
| Cost of 100 standups/month | ~$1.50 | ~$0.50 |

---

## 4. Orchestration: Replace Custom DAG with Temporal.io {#4-orchestration}

### Problem: The Orchestrator is a Liability

Your current `pipeline/orchestrator.py` is a **600-line custom state machine**. Here's what breaks:

| Failure Scenario | Current Behavior | Should Be |
|-----------------|-----------------|-----------|
| Server crashes during pipeline | **All state lost** — `_jobs` dict is in memory | Workflow resumes exactly where it stopped |
| Agent takes 30 minutes | `asyncio.gather` blocks the event loop | Background worker, non-blocking |
| Pipeline paused for 3 days | Memory store holds state, but process must stay alive | Temporal persists state indefinitely |
| 10 concurrent pipelines | Single Python process, GIL contention | Distributed workers across machines |
| Sprint that runs for 2 weeks | **Impossible** — pipelines are single-shot | Temporal workflow with daily timers for standups |

### Solution: Temporal.io Workflows

```python
# workflows/sprint_workflow.py — NEW
"""
Sprint Workflow: Runs for the duration of a sprint (1-4 weeks).
Orchestrates daily standups, story execution, reviews, and retrospective.
"""
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class SprintWorkflow:
    """
    A Sprint is a Temporal workflow that:
    1. Runs for 1-4 weeks
    2. Triggers daily standups via timer
    3. Executes stories as child workflows
    4. Pauses for human review at checkpoints
    5. Generates retrospective on completion
    """

    @workflow.run
    async def run(self, sprint_config: SprintConfig) -> SprintResult:
        # Phase 1: Sprint Planning
        stories = await workflow.execute_activity(
            plan_sprint,
            sprint_config,
            start_to_close_timeout=timedelta(minutes=30),
        )

        # Phase 2: Execute Stories (parallel where possible)
        for story in stories:
            workflow.start_child_workflow(
                StoryWorkflow.run,
                story,
            )

        # Phase 3: Daily Standups (timer-based)
        while not self.sprint_complete:
            await workflow.sleep(timedelta(hours=24))  # Temporal timer — survives crashes
            await workflow.execute_activity(
                run_standup,
                self.sprint_id,
                start_to_close_timeout=timedelta(minutes=10),
            )

        # Phase 4: Sprint Review
        return await workflow.execute_activity(
            generate_sprint_review,
            self.sprint_id,
            start_to_close_timeout=timedelta(minutes=15),
        )


@workflow.defn
class StoryWorkflow:
    """
    Execute a single user story through agents.
    Handles review loops, quality gates, and blocker escalation.
    """

    @workflow.run
    async def run(self, story: UserStory) -> StoryResult:
        # Step 1: Agent executes the story
        result = await workflow.execute_activity(
            run_agent,
            args=[story.assigned_to, story.task],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 2: Code Review (review loop)
        review_approved = False
        for round in range(3):
            review = await workflow.execute_activity(
                run_code_review,
                args=[result, story],
                start_to_close_timeout=timedelta(minutes=15),
            )
            if review.approved:
                review_approved = True
                break
            # Author revises
            result = await workflow.execute_activity(
                run_agent_revision,
                args=[story.assigned_to, review.feedback, result],
                start_to_close_timeout=timedelta(minutes=20),
            )

        # Step 3: Quality Gate
        if not review_approved:
            # Signal human for intervention
            await workflow.wait_condition(lambda: self.human_approved)

        return StoryResult(story_id=story.id, output=result, reviewed=review_approved)
```

### Why Temporal > Custom Orchestrator

| Feature | Custom (Current) | Temporal.io |
|---------|-----------------|-------------|
| **Durability** | State in memory (lost on crash) | Event-sourced (survives anything) |
| **Long-running** | Max ~hours | Runs for weeks/months |
| **Timers** | `asyncio.sleep()` (blocks process) | Persistent timers (server-side) |
| **Signals** | None (can't interrupt running pipeline) | Send signals to running workflows |
| **Queries** | Poll `_jobs` dict | Query workflow state in real-time |
| **Retries** | Custom retry.py | Built-in with exponential backoff |
| **Scaling** | Single process | Distributed workers |
| **Visibility** | `logger.info()` | Full Web UI showing all workflows |
| **Versioning** | Breaking changes break running pipelines | Workflow versioning for safe deploys |

### Migration Path

Your existing `Orchestrator.run()` becomes a **Temporal Activity** (a function that Temporal calls). The DAG logic moves into Temporal Workflow definitions. Your pipeline YAML templates become Temporal workflow configs.

```
BEFORE:  YAML Template → config_loader.py → Orchestrator.run() → agents
AFTER:   YAML Template → config_loader.py → Temporal Workflow → Activities → agents
```

---

## 5. Communication: Real-Time Agent Bus {#5-communication}

### Problem: Agents Are Deaf and Mute

```python
# Current: One-way context injection (orchestrator.py:190-195)
ctx_parts = []
for dep in task.depends_on:
    if dep in completed:
        dep_result = completed[dep]
        ctx_parts.append(f"## Output from {dep} agent:\n{dep_result.output}")
```

This is a **dead drop** — agents leave output, downstream agents pick it up. No one can:
- Ask a clarifying question
- Request a code change
- Flag a blocker
- Disagree with a decision

### Solution: Redis Pub/Sub + Typed Messages

```python
# communication/bus.py — NEW
"""
Agent Communication Bus.
Redis-backed pub/sub for real-time inter-agent messaging.
"""
import redis.asyncio as redis
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

class MessageType(str, Enum):
    QUESTION = "question"          # "What's the API response shape?"
    ANSWER = "answer"              # Reply to a question
    REVIEW_REQUEST = "review"      # "Please review my code"
    REVIEW_FEEDBACK = "feedback"   # "Found 3 issues, see below"
    STATUS_UPDATE = "status"       # "Completed endpoint 3/5"
    BLOCKER = "blocker"            # "Can't proceed — need API spec"
    DECISION = "decision"          # "We'll use PostgreSQL, not MongoDB"
    BROADCAST = "broadcast"        # CEO: "Security-first this sprint"
    DELEGATION = "delegation"      # "Delegating DB migration to BE agent"

@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""                 # "backend_architect"
    channel: str = ""                # "sprint-23" | "code-review" | "direct:frontend"
    message_type: MessageType = MessageType.STATUS_UPDATE
    content: str = ""
    structured_data: dict = field(default_factory=dict)  # Typed payload
    reply_to: Optional[str] = None   # ID of message being replied to
    priority: str = "normal"         # "urgent" | "normal" | "low"
    sprint_id: Optional[str] = None
    story_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AgentBus:
    """Redis-backed communication bus for inter-agent messaging."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.pubsub = self.redis.pubsub()

    async def publish(self, message: AgentMessage):
        """Publish a message to a channel."""
        payload = json.dumps(message.__dict__, default=str)
        # 1. Persist to Redis Stream (durable log)
        await self.redis.xadd(
            f"stream:{message.channel}",
            {"data": payload},
            maxlen=10000,
        )
        # 2. Publish for real-time subscribers
        await self.redis.publish(f"channel:{message.channel}", payload)
        # 3. Add to agent's inbox
        await self.redis.lpush(f"inbox:{message.channel}", payload)

    async def get_inbox(self, agent_name: str, count: int = 10) -> list[AgentMessage]:
        """Get unread messages for an agent."""
        raw = await self.redis.lrange(f"inbox:direct:{agent_name}", 0, count - 1)
        return [AgentMessage(**json.loads(m)) for m in raw]

    async def ask_and_wait(
        self,
        sender: str,
        recipient: str,
        question: str,
        timeout_seconds: int = 300
    ) -> Optional[AgentMessage]:
        """Ask a question and wait for a reply (synchronous Q&A)."""
        msg = AgentMessage(
            sender=sender,
            channel=f"direct:{recipient}",
            message_type=MessageType.QUESTION,
            content=question,
        )
        await self.publish(msg)

        # Wait for reply on a dedicated reply channel
        reply_channel = f"reply:{msg.id}"
        async with self.redis.pubsub() as ps:
            await ps.subscribe(reply_channel)
            async for raw_msg in ps.listen():
                if raw_msg["type"] == "message":
                    return AgentMessage(**json.loads(raw_msg["data"]))
        return None

    async def subscribe(self, channel: str, callback):
        """Subscribe to a channel with a callback."""
        await self.pubsub.subscribe(channel)
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                parsed = AgentMessage(**json.loads(message["data"]))
                await callback(parsed)
```

### How Agents Use the Bus

```python
# In an agent's run() method (enhanced BaseAgent):

# 1. Ask a question to another agent
answer = await self.bus.ask_and_wait(
    sender="frontend",
    recipient="backend",
    question="What's the response schema for GET /api/users? I need it for the TypeScript interface.",
)

# 2. Flag a blocker
await self.bus.publish(AgentMessage(
    sender="qa",
    channel="sprint-23",
    message_type=MessageType.BLOCKER,
    content="Login endpoint returns 500 — BE agent needs to fix before I can test auth flow.",
    priority="urgent",
    story_id="STORY-42",
))

# 3. CEO makes a decision
await self.bus.publish(AgentMessage(
    sender="ceo",
    channel="all-hands",
    message_type=MessageType.BROADCAST,
    content="Security audit is now P0. All agents: pause feature work, prioritize security findings.",
))
```

---

## 6. Data Architecture: Polyglot Persistence {#6-data-architecture}

### The Verdict on Supabase

**Supabase stays** as the primary relational store. Here's why:
- You already have it configured and working
- It's PostgreSQL under the hood — production-grade
- It has **pgvector** support (enable the extension for semantic memory)
- It has **Supabase Storage** for file artifacts
- It has **Supabase Realtime** for live dashboard updates
- Free tier covers development

**But Supabase alone is not enough.** You need:

### Data Layer Map

```
┌──────────────────────────────────────────────────────────────────┐
│                     Data Access Layer (DAL)                       │
│              Unified async interface for all stores               │
└───────┬──────────────┬──────────────┬───────────────┬────────────┘
        │              │              │               │
┌───────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐ ┌─────▼──────┐
│  Supabase    │ │  Redis    │ │  Supabase  │ │  Supabase  │
│  PostgreSQL  │ │  7.x      │ │  pgvector  │ │  Storage   │
│              │ │           │ │            │ │            │
│ • Sprints    │ │ • Msg bus │ │ • Semantic │ │ • Code     │
│ • Stories    │ │ • Jobs    │ │   memory   │ │   artifacts│
│ • Agent      │ │ • Cache   │ │ • Decision │ │ • Reports  │
│   results    │ │ • Sessions│ │   recall   │ │ • Assets   │
│ • Reviews    │ │ • Pub/Sub │ │ • Pattern  │ │            │
│ • Standups   │ │ • Rate    │ │   matching │ │            │
│ • Audit log  │ │   limits  │ │            │ │            │
│ • Personas   │ │           │ │            │ │            │
└──────────────┘ └───────────┘ └────────────┘ └────────────┘
```

### pgvector: Semantic Agent Memory

Enable pgvector on your Supabase instance and add:

```sql
-- Enable the extension (Supabase Dashboard → Extensions → pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Agent semantic memory — stores embeddings of past decisions, code patterns, outcomes
CREATE TABLE agent_memory_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    project_id VARCHAR(100),
    content TEXT NOT NULL,                   -- The actual text being remembered
    memory_type VARCHAR(50) NOT NULL,        -- "decision" | "pattern" | "mistake" | "success"
    embedding VECTOR(1536) NOT NULL,         -- OpenAI ada-002 or Cohere embed v3
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast similarity search
CREATE INDEX idx_memory_vectors_embedding
    ON agent_memory_vectors USING hnsw (embedding vector_cosine_ops);

-- Index on agent + type for filtered search
CREATE INDEX idx_memory_vectors_agent_type
    ON agent_memory_vectors(agent_name, memory_type);
```

**Usage**: Before executing a task, the agent queries semantic memory:

```python
# "Have I solved something like this before?"
similar_memories = await memory.search(
    agent_name="backend",
    query="Stripe webhook handling with idempotency",
    memory_type="pattern",
    top_k=5,
)
# Returns: "In project 'saas-billing' (Sprint 12), we used idempotency keys stored in
#           Redis with a 24h TTL. The webhook endpoint verified the Stripe signature
#           first, then checked Redis for duplicate event IDs..."
```

### Redis: Real-Time State

```
Purpose                     Key Pattern                    TTL
─────────────────────────────────────────────────────────────────
Agent message inbox         inbox:direct:{agent}           7d
Channel streams             stream:{channel}               30d
Job status                  job:{job_id}                   24h
Agent session state         session:{agent}:{run_id}       1h
Rate limiting               ratelimit:{agent}:{window}     60s
Sprint dashboard cache      cache:sprint:{id}:burndown     5m
WebSocket presence          presence:{agent}               30s
```

---

## 7. Agent Architecture: From Functions to Workers {#7-agent-architecture}

### Current: Agents Are Inline Functions

```python
# Current flow (simplified):
# 1. Orchestrator creates agent instance
agent = create_agent("backend", project_id)
# 2. Runs it inline (blocks the orchestrator's asyncio loop)
result = await loop.run_in_executor(None, lambda: agent.run(task, context=ctx))
```

### Target: Agents Are Temporal Activities with Communication

```python
# activities/agent_activities.py — NEW
"""
Temporal Activities wrapping agent execution.
Each activity is a self-contained unit of work that Temporal can:
  - Retry on failure
  - Time out gracefully
  - Execute on any worker
  - Track with full observability
"""
from temporalio import activity

@activity.defn
async def run_agent_activity(
    agent_name: str,
    task: str,
    context: str = "",
    project_id: str = "default",
    sprint_id: str | None = None,
    story_id: str | None = None,
) -> dict:
    """Execute an agent as a Temporal activity."""
    from agents.agent_config import create_agent
    from communication.bus import AgentBus, AgentMessage, MessageType

    # 1. Create the agent with full context
    agent = create_agent(agent_name, project_id=project_id)
    bus = AgentBus()

    # 2. Retrieve semantic memories
    similar = await agent.recall_similar(task)

    # 3. Check inbox for relevant messages
    inbox = await bus.get_inbox(agent_name)
    message_context = "\n".join([
        f"[{m.sender}] {m.content}" for m in inbox
        if m.sprint_id == sprint_id
    ])

    # 4. Build enriched context
    full_context = "\n\n".join(filter(None, [
        context,
        f"## Relevant past experience:\n{similar}" if similar else None,
        f"## Team messages:\n{message_context}" if message_context else None,
    ]))

    # 5. Execute
    result = agent.run(task, context=full_context)

    # 6. Post status update
    await bus.publish(AgentMessage(
        sender=agent_name,
        channel=f"sprint-{sprint_id}" if sprint_id else "general",
        message_type=MessageType.STATUS_UPDATE,
        content=f"Completed: {task[:100]}...",
        structured_data=result.to_dict(),
        story_id=story_id,
    ))

    # 7. Save to semantic memory
    await agent.remember(
        content=f"Task: {task}\nOutcome: {result.output[:500]}",
        memory_type="pattern",
        metadata={"sprint_id": sprint_id, "story_id": story_id},
    )

    return result.to_dict()
```

### Enhanced BaseAgent (Diff from Current)

```python
# agents/base.py — KEY CHANGES

class BaseAgent(ABC):
    def __init__(self, project_id=None, *, config=None, llm_client=None, memory=None):
        # ... existing init ...

        # NEW: Communication bus
        self.bus = AgentBus()

        # NEW: LLM client (replaces direct anthropic)
        self._llm = llm_client or LLMClient()

        # NEW: Semantic memory
        self._vector_store = VectorMemory(self.name)

    async def ask(self, recipient: str, question: str) -> str:
        """Ask another agent a question (synchronous Q&A via bus)."""
        reply = await self.bus.ask_and_wait(self.name, recipient, question)
        return reply.content if reply else "No response received."

    async def flag_blocker(self, description: str, sprint_id: str = None):
        """Flag a blocker for the sprint/team."""
        await self.bus.publish(AgentMessage(
            sender=self.name,
            channel=f"sprint-{sprint_id}" if sprint_id else "blockers",
            message_type=MessageType.BLOCKER,
            content=description,
            priority="urgent",
        ))

    async def recall_similar(self, query: str, top_k: int = 5) -> str:
        """Semantic memory recall — find similar past work."""
        results = await self._vector_store.search(query, top_k=top_k)
        if not results:
            return ""
        return "\n".join([f"- {r.content}" for r in results])

    async def remember(self, content: str, memory_type: str, metadata: dict = None):
        """Save to semantic memory for future recall."""
        await self._vector_store.store(content, memory_type, metadata or {})
```

---

## 8. Frontend: Sprint Dashboard {#8-frontend}

### Current UI: Pipeline Builder Only

Your React UI (`pipeline-ui/`) is a single-purpose pipeline builder:
- Select template → Validate → Preview → Run

### Target UI: Full Sprint Dashboard

```
┌─────────────────────────────────────────────────────────────────────┐
│  AI Engineering Co.                        Sprint 23 ▼  │ 🔴 Live  │
├────────────┬────────────┬──────────────┬───────────────────────────┤
│            │            │              │                           │
│  📋 Sprint │  💬 Team   │  📊 Metrics  │  🔧 Pipeline              │
│  Board     │  Chat      │              │  Builder                  │
│            │            │              │  (existing)               │
├────────────┴────────────┴──────────────┴───────────────────────────┤
│                                                                     │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐          │
│  │ TO DO   │  │IN PROGRESS│  │ IN REVIEW │  │  DONE    │          │
│  │         │  │           │  │           │  │          │          │
│  │ ┌─────┐ │  │ ┌───────┐ │  │ ┌───────┐ │  │ ┌──────┐ │          │
│  │ │AUTH │ │  │ │ OAuth │ │  │ │ Login │ │  │ │ MFA  │ │          │
│  │ │Story│ │  │ │ Flow  │ │  │ │ Page  │ │  │ │Setup │ │          │
│  │ │ 5pt │ │  │ │ 8pt   │ │  │ │ 5pt   │ │  │ │ 8pt  │ │          │
│  │ │🤖 BE│ │  │ │🤖 BE  │ │  │ │🤖 FE  │ │  │ │🤖 BE │ │          │
│  │ └─────┘ │  │ └───────┘ │  │ └───────┘ │  │ └──────┘ │          │
│  └─────────┘  └──────────┘  └───────────┘  └──────────┘          │
│                                                                     │
│  ── Burndown ────────────────────  ── Agent Activity ──────────    │
│  30│ ╲                             │ 🤖 BE: "OAuth endpoint done"  │
│  20│   ╲     ╲                     │ 🤖 FE: "Login page in review" │
│  10│     ╲     · · ·               │ 🤖 QA: "Writing auth tests"   │
│   0│_______╲________               │ 🤖 SEC: "JWT vuln in review"  │
│    M  T  W  T  F                   │ ⚠️  BE: BLOCKED on API spec   │
└─────────────────────────────────────────────────────────────────────┘
```

### New Pages Needed

| Page | Description | Data Source |
|------|------------|-------------|
| **Sprint Board** | Kanban view of stories with agent avatars, drag-and-drop status changes | Supabase `user_stories` + WebSocket |
| **Team Chat** | Real-time view of inter-agent messages organized by channel (#code-review, #architecture, blockers) | Redis Pub/Sub → WebSocket → UI |
| **Standup View** | Daily summary per agent: done, doing, blocked | Supabase `standup_reports` |
| **Burndown Chart** | Points remaining vs. ideal line | Supabase `user_stories` aggregate |
| **Agent Profiles** | Each agent's persona, history, decisions, cost | Supabase `agent_personas` |
| **Cost Dashboard** | Per-sprint, per-agent, per-model cost breakdown | Supabase `cost_log` + LiteLLM metrics |

---

## 9. Migration Path {#9-migration-path}

### Phase 0: Foundation (Week 1–2) — Low Risk

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Install Redis (docker-compose or Upstash free tier)     │
│ 2. Install LiteLLM Proxy (pip install litellm, docker run) │
│ 3. Enable pgvector on Supabase                              │
│ 4. Add new tables (sprints, stories, standups, messages)    │
│ 5. Update .env with Redis URL, LiteLLM endpoint            │
│                                                              │
│ Risk: ZERO — nothing changes for existing functionality      │
└─────────────────────────────────────────────────────────────┘
```

### Phase 1: LLM Abstraction (Week 3) — Low Risk

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Create llm/client.py (LiteLLM wrapper)                   │
│ 2. Update BaseAgent to use LLMClient instead of anthropic   │
│ 3. Update agent_config.py with "provider/model" format      │
│ 4. Test: all existing agents work identically               │
│                                                              │
│ Risk: LOW — LiteLLM is backward-compatible with anthropic   │
│ Rollback: Revert to direct anthropic client                  │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2: Communication Bus (Week 4–5) — Medium Risk

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Build communication/bus.py (Redis Pub/Sub)               │
│ 2. Add bus to BaseAgent (opt-in, doesn't break existing)    │
│ 3. Move job store from _jobs dict to Redis                   │
│ 4. Add WebSocket endpoint for live agent status              │
│                                                              │
│ Risk: MEDIUM — new capability, but opt-in per agent          │
│ Rollback: Disable bus, fall back to string passthrough       │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Temporal Integration (Week 6–8) — High Risk

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Install Temporal (docker-compose for dev)                 │
│ 2. Wrap existing agents as Temporal Activities               │
│ 3. Convert Orchestrator.run() → PipelineWorkflow             │
│ 4. Add SprintWorkflow and StoryWorkflow                      │
│ 5. Wire FastAPI endpoints to start Temporal workflows        │
│                                                              │
│ Risk: HIGH — core execution model changes                    │
│ Rollback: Keep original Orchestrator alongside Temporal      │
│ Strategy: Run both in parallel, compare outputs              │
└─────────────────────────────────────────────────────────────┘
```

### Phase 4: New Agents + Sprint UI (Week 9–12) — Medium Risk

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Build CEO, CTO, VP Eng, Scrum Master agents              │
│ 2. Build Sprint Board UI (React + WebSocket)                 │
│ 3. Build Agent Chat UI                                       │
│ 4. Build Standup + Burndown views                            │
│ 5. Implement review loop engine                              │
│                                                              │
│ Risk: MEDIUM — new features, doesn't break existing          │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Cost Analysis {#10-cost-analysis}

### Infrastructure Costs

| Component | Free Tier | Production | Notes |
|-----------|----------|-----------|-------|
| **Supabase** (PG + pgvector + Storage) | ✅ Free (500MB DB) | $25/mo (8GB) | Already using |
| **Redis** (Upstash serverless) | ✅ Free (10K cmds/day) | $10/mo (unlimited) | New |
| **Temporal** (self-hosted Docker) | ✅ Free | $0 (self-hosted) | New — free forever if self-hosted |
| **LiteLLM Proxy** (self-hosted) | ✅ Free | $0 (self-hosted) | New — open source |
| **LLM API Costs** (per sprint) | — | $5-15/sprint | Reduced via multi-model routing |
| **Total Monthly** | **$0** | **$35-50/mo** | vs. current ~$0 + API costs |

### LLM Cost Savings from Multi-Model Routing

| Task | Current (Anthropic Only) | After (Multi-LLM) | Savings |
|------|------------------------|-------------------|---------|
| Standup summaries (30/mo) | $0.45 (Haiku) | $0.15 (Gemini Flash) | 67% |
| Code reviews (20/mo) | $1.20 (Sonnet) | $1.20 (Sonnet) | Same |
| Planning (5 sprints/mo) | $3.75 (Opus) | $3.75 (Opus) | Same |
| Quick classifications | $0.30 (Haiku) | $0.10 (Gemini Flash) | 67% |
| **Total/month** | **~$5.70** | **~$5.20** | **~9%** |

> [!NOTE]
> The main cost benefit of multi-LLM isn't savings — it's **resilience**. When Anthropic goes down, your team keeps working.

---

## Summary: The 6 Big Bets

| # | Change | Why | Effort | Impact |
|---|--------|-----|--------|--------|
| 1 | **LiteLLM** for multi-provider LLM | Resilience + flexibility + future-proof | Low | 🟢🟢🟢 |
| 2 | **Redis** for real-time bus + cache | Agent communication + live dashboard | Low | 🟢🟢🟢🟢 |
| 3 | **pgvector** for semantic memory | Agents learn from past projects | Low | 🟢🟢🟢 |
| 4 | **Temporal.io** for workflow engine | Durable sprints, review loops, timers | High | 🟢🟢🟢🟢🟢 |
| 5 | **New Agent Roles** (CEO/CTO/VP) | Org structure + decision hierarchy | Medium | 🟢🟢🟢🟢 |
| 6 | **Sprint Dashboard** (React) | Full team visibility, Kanban, chat | Medium | 🟢🟢🟢🟢 |

**Start with #1 (LiteLLM) and #2 (Redis) — they're low-risk, high-impact, and unlock everything else.**

---

*Created: 2026-04-11 | Status: Architecture Proposal — Unrestricted Recommendations*
*Companion doc: [AI_COWORKERS_VISION.md](./AI_COWORKERS_VISION.md)*
