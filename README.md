# AI Agent Org (V2)

**Status**: V2 Architecture Overhaul Complete — LiteLLM ✅, Redis Bus ✅, Temporal Orchestration ✅, Agile Engine ✅, Semantic Memory ✅, Sprint Dashboard ✅

A one-person AI engineering organisation. A team of specialized AI agents collaborate as "AI Coworkers" to design, build, review, secure, test, and deploy software products. 

This V2 release transforms the platform into a durable, event-driven, and self-evolving multi-agent team.

---

## 🚀 Key Features

### 1. Multi-LLM Resilience (LiteLLM)
Agents are no longer tied to a single provider. Using **LiteLLM**, agents can route tasks to Claude 3.5, GPT-4, Gemini 1.5, or local models. This ensures high availability and allows for cost-optimized routing (e.g., using Haiku for standups and Opus for architecture).

### 2. Real-Time Communication Bus (Redis)
Agents communicate via a Redis-backed **MessageBus**. They can `broadcast` status updates, `ask` questions to specialists, and `answer` technical queries in real-time. This replaces static pipelines with a dynamic, collaborative team environment.

### 3. Agile Sprint Engine
Full Agile lifecycle management:
- **CEO Agent**: Defines product vision and high-level goals.
- **VP Engineering Agent**: Plans sprints, assigns tasks, and summarizes daily standups.
- **Persistent Sprint State**: Sprints, User Stories, and Standup Reports are stored in Supabase/PostgreSQL.

### 4. Durable Orchestration (Temporal.io)
The execution engine is powered by **Temporal**. Sprints and User Stories are long-running workflows that can survive process restarts and network failures. Agent tasks are wrapped in auto-retrying activities with exponential backoff.

### 5. Agent Self-Evolution (Semantic Memory)
Agents learn from their own successes and failures:
- **pgvector Integration**: Lessons learned are stored as embeddings in Supabase.
- **Outcome Tracking**: Post-task reflection analyzes results to extract actionable rules.
- **Recall**: Agents automatically query their semantic memory before a task to avoid repeating past mistakes.

### 6. Interactive Sprint Dashboard (React)
A comprehensive dashboard for visibility into your AI team:
- **Kanban Board**: Drag-and-drop tracking of User Stories.
- **Team Chat**: Real-time view of inter-agent messages and decision logs.
- **Pipeline Builder**: Legacy visual canvas for building custom agent flows.

---

## 🛠️ Infrastructure Requirements

V2 requires the following services:
- **Redis**: For the message bus and task caching.
- **Supabase / PostgreSQL**: With `pgvector` enabled for state and semantic memory.
- **Temporal.io**: For durable workflow orchestration.
- **LiteLLM Proxy**: (Optional) For centralized model management and cost tracking.

---

## 🏁 Quick Start

### 1. Environment Setup
```bash
git clone https://github.com/satyasgit/Forge.git && cd Forge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure DATABASE_URL, REDIS_URL, etc.
```

### 2. Initialize Database
Apply the latest schema updates to your Supabase instance:
```bash
# Apply SQL from docs/schema_updates.sql via Supabase UI or psql
```

### 3. Start Services
```bash
# Start Redis & Temporal (if using Docker)
docker-compose up -d

# Start the Temporal Worker
python api/worker.py

# Start the FastAPI Server
uvicorn api.main:app --reload --port 8000
```

### 4. Launch Dashboard
```bash
cd pipeline-ui
npm install
npm run dev
# Open http://localhost:5173
```

---

## 🏗️ Project Structure

```
ai-agent-org/
├── agents/              # 12+ Specialist Agents (pm, backend, security, etc.)
│   └── base.py          # Core logic: memory, tool loop, cost tracking
├── activities/          # Temporal activities wrapping agent tasks
├── workflows/           # Temporal workflows (SprintWorkflow, StoryWorkflow)
├── agile/               # Sprint management logic and database models
├── communication/       # Redis MessageBus and JobStore
├── evolution/           # Outcome tracking and reflection engine
├── memory/              # Project memory and pgvector VectorMemory
├── pipeline/            # Orchestrator and config loader
├── pipeline-ui/         # React Dashboard (Sprint Board, Chat, Builder)
├── skills/              # Domain-specific knowledge patterns
├── tools/               # External integrations (GitHub, Jira, etc.)
└── docs/                # Architecture and vision documents
```

---

## 📊 Documentation
- [Architecture Overhaul](./docs/ARCHITECTURE_OVERHAUL.md)
- [AI Coworkers Vision](./docs/AI_COWORKERS_VISION.md)
- [Agent Self-Evolution](./docs/AGENT_SELF_EVOLUTION.md)
- [Project Progress](./PROGRESS.md)
