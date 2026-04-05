# Current System Architecture - AI Agent Org

**Last Updated**: 2026-04-05 (Phase 4 Repository & History API complete)
**Status**: Production prototype ready, needs DB setup for full E2E testing
**Scope**: Covers the implemented system after Phase 3 completion

---

## 1. System Overview

AI Agent Org is a **configurable multi-agent pipeline system** that builds software using AI agents. Users define pipelines in YAML or via API, and the system executes agents in parallel based on dependencies.

**Key Characteristics**:
- **Pipeline-as-Code**: Declarative YAML configuration → DAG execution
- **Agent Orchestration**: Dependency-aware parallel execution
- **Persistent Storage**: PostgreSQL (production) or SQLite (dev) via SQLAlchemy 2.0
- **REST API**: FastAPI async endpoints for all operations
- **Visual UI**: React + React Flow pipeline builder (TypeScript)
- **Cost Tracking**: Per-agent token usage and cost calculation
- **Human Approval**: Checkpoint-based pause/resume workflow

**Architecture Style**: Layered monolith with repository pattern
```
┌─────────────────┐
│   React UI      │  (pipeline-ui/)
├─────────────────┤
│   FastAPI       │  (api/main.py)
├─────────────────┤
│  Orchestrator   │  (pipeline/orchestrator.py)
├─────────────────┤
│  Repository     │  (pipeline/repository.py)
├─────────────────┤
│  Database       │  (PostgreSQL / SQLite)
└─────────────────┘
```

---

## 2. Core Components

### 2.1 Configuration Layer

**Files**:
- `pipeline/config_loader.py` - YAML loading, validation, DAG generation
- `config/pipelines/*.yaml` - Pre-built pipeline templates (4 templates)
- `config/agent_deps.yaml` - Centralized agent dependency definitions

**Purpose**: Convert YAML configs → executable pipeline DAGs with cost/duration estimates.

Key Classes:
- `PipelineConfig` - Pydantic model for pipeline definition
- `build_from_config()` - Expands agents, resolves dependencies, builds DAG

### 2.2 Agent Layer

**Files**:
- `agents/base.py` - `BaseAgent` abstract base class
- `agents/*_agent.py` - Concrete agent implementations (11 agents)
- `agents/agent_config.py` - Agent registry with `@register_agent` decorator

**Purpose**: Individual AI agents that perform specific tasks (PM, frontend, backend, security, QA, etc.)

Each agent:
- Inherits from `BaseAgent`
- Can use tools (file operations, HTTP requests, etc.)
- Produces structured results (`AgentResult` dataclass)
- Tracks tokens, cost, duration

### 2.3 Orchestration Layer

**File**: `pipeline/orchestrator.py`

**Purpose**: Execute pipelines, manage parallel execution, handle checkpoints/resume.

Key Classes:
- `PipelineTask` - Individual agent task with dependencies
- `PipelineDAG` - Directed acyclic graph with topological sort
- `PipelineRun` - Execution state (results, summary, pause/resume)
- `Orchestrator` - Main orchestrator with `run()` method

Features:
- Parallel execution based on dependency resolution
- Checkpoint integration (auto-pause, resume)
- State serialization for resume
- Cost aggregation

### 2.4 Repository Layer (NEW - Phase 4)

**Files**:
- `pipeline/repository.py` - Repository implementations (sync + async)
- `pipeline/models_database.py` - SQLAlchemy 2.0+ models

**Purpose**: Data persistence abstraction. Decouples business logic from database.

Classes:
- `PipelineRepository` (sync) - For scripts, migrations
- `AsyncPipelineRepository` (async) - For FastAPI routes

CRUD Operations:
- `create_run(project_id, config, job_id)` → PipelineRunDB
- `list_runs(project_id, limit, offset)` → list[PipelineRunDB]
- `update_run_status(run_id, status, **updates)` → PipelineRunDB
- `save_agent_result(run_id, agent_name, result)` → AgentResultDB
- `get_agent_results(run_id)` → list[AgentResultDB]
- `create_checkpoint(...)` → CheckpointDB
- `get_checkpoints_for_run(run_id)` → list[CheckpointDB]
- `update_checkpoint_decision(checkpoint_id, status, approver)` → CheckpointDB

### 2.5 API Layer

**Files**:
- `api/main.py` - FastAPI application and routes
- `api/pipelines_schemas.py` - Pydantic request/response models

**Endpoints**:

| Method | Endpoint | Purpose | Repository Used |
|--------|----------|---------|-----------------|
| GET | `/health` | Health check | No |
| POST | `/api/pipeline/run` | Legacy job-based run | Yes (async) |
| GET | `/api/pipeline/jobs/{job_id}` | Job status | No (in-memory) |
| POST | `/api/agents/security/audit` | Direct security audit | No |
| POST | `/api/agents/run` | Run single agent | No |
| GET | `/api/projects/{project_id}/cost` | Project cost from memory | No |
| GET | `/api/agents` | List registered agents | No |
| GET | `/api/pipelines/templates` | List templates | No |
| GET | `/api/pipelines/templates/{name}` | Get template config | No |
| POST | `/api/pipelines/validate` | Validate config | No |
| POST | `/api/pipelines/preview` | Cost/DAG preview | No |
| POST | `/api/pipelines/run` | Run custom pipeline | Yes (async) |
| GET | `/api/pipelines/{run_id}/checkpoints` | List checkpoints | Yes (async) |
| POST | `/api/pipelines/resume/{run_id}` | Resume paused pipeline | Yes (async) |
| GET | `/api/projects/{project_id}/pipelines/history` | Run history ✅ | Yes (async) |
| GET | `/api/pipelines/health` | Pipeline system health | No |

### 2.6 UI Layer

**Directory**: `pipeline-ui/`

**Tech Stack**: React 18 + TypeScript + Vite + React Flow + Zustand

**Components**:
- `App.tsx` - Main application with router
- `components/AgentNode.tsx` - Custom node for agent tasks
- `components/CheckpointPanel.tsx` - Approval panel overlay
- `hooks/usePipelineStore.ts` - Zustand state store
- `api.ts` - API client functions
- `types.ts` - TypeScript type definitions

Features:
- Drag-and-drop pipeline builder with React Flow
- Visual DAG editing (nodes, edges)
- Real-time validation and preview
- Pipeline execution with job polling
- Checkpoint approval UI

### 2.7 Memory Layer

**Files**: `memory/store.py`

**Purpose**: Long-term memory for agents (conversation history, project context)

**Implementation**:
- SQLite database (`data/agent_memory.db`) with WAL mode
- `ProjectMemory` - Project-scoped memory operations
- `AgentMemory` - Agent-specific memory
- `checkpoints` table - Legacy checkpoint storage (being migrated to repository)

---

## 3. Data Flow

### 3.1 Create & Run Pipeline (API → Orchestrator → Repository)

```
1. Client POST /api/pipelines/run
   └─> FastAPI validates request (PipelineRunRequest)
   └─> Creates job_id, stores in _jobs (in-memory)

2. Background task _run()
   ├─> Get AsyncPipelineRepository (dependency)
   ├─> repo.create_run(project_id, config, job_id)
   │   └─> Inserts PipelineRunDB (status="pending")
   ├─> Build PipelineDAG from config
   │   └─> config_loader.build_from_config()
   ├─> orch.run(dag, run_id=run_record.id)
   │   ├─> Topological sort → execution order
   │   ├─> Parallel execution with asyncio.gather()
   │   ├─> Each agent: create Agent, run, save result
   │   │   └─> orch.repo.save_agent_result() (if checkpoint, creates CheckpointDB)
   │   ├─> If checkpoint hit: pipeline pauses, returns
   │   └─> Aggregates results, total_cost, summary
   ├─> repo.update_run_status(run_id, status, finished_at, total_cost)
   └─> Update _jobs[job_id] with results

3. Client GET /api/pipeline/jobs/{job_id}
   └─> Returns job status from _jobs dict
```

### 3.2 History Endpoint (Repository → Database)

```
Client GET /api/projects/{project_id}/pipelines/history?limit=20
└─> FastAPI dependency get_repo() → AsyncPipelineRepository
└─> repo.list_runs(project_id, limit)
    └─> SELECT * FROM pipeline_runs WHERE project_id = ?
        ORDER BY created_at DESC LIMIT ?
└─> Transform each PipelineRunDB to PipelineHistoryItem:
    - config_name = run.config["name"]
    - agent_count = len(run.config["agents"])
    - duration_seconds = (finished_at - started_at).total_seconds()
    - cost_usd = run.total_cost
└─> Return PipelineHistoryResponse(runs=[...], total_cost_usd=sum(costs))
```

---

## 4. Database Schema (PostgreSQL/SQLite)

### 4.1 Tables

```sql
-- Pipeline runs (main execution record)
pipeline_runs (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(100) NOT NULL,
  config JSONB NOT NULL,              -- Full PipelineConfig
  status VARCHAR(20) NOT NULL,        -- pending|running|paused|completed|aborted|failed
  run_id VARCHAR(100),                -- Orchestrator's run_id (for resume)
  job_id VARCHAR(100),                -- Legacy job correlation
  created_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  total_cost FLOAT,
  checkpoint_id VARCHAR(36)           -- Current active checkpoint (if paused)
);

-- Individual agent execution results
agent_results (
  id VARCHAR(36) PRIMARY KEY,
  pipeline_run_id VARCHAR(36) REFERENCES pipeline_runs(id) ON DELETE CASCADE,
  agent_name VARCHAR(100) NOT NULL,
  output TEXT,
  tool_calls JSONB,
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  cost_usd FLOAT DEFAULT 0.0,
  duration_seconds FLOAT DEFAULT 0.0,
  errors JSONB,
  model_used VARCHAR(100),
  retries INTEGER DEFAULT 0,
  state VARCHAR(20) DEFAULT 'done',
  created_at TIMESTAMPTZ NOT NULL
);

-- Human approval checkpoints (repository)
-- Note: Distinct from memory.store checkpoints table
pipeline_checkpoints (
  id VARCHAR(36) PRIMARY KEY,
  pipeline_run_id VARCHAR(36) REFERENCES pipeline_runs(id) ON DELETE CASCADE,
  agent_name VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,        -- pending|approved|rejected|timeout
  checkpoint_type VARCHAR(50) NOT NULL,-- human_approval|budget_approval|etc.
  approver VARCHAR(200),
  decision_at TIMESTAMPTZ,
  message TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL
);

-- Job status (legacy compatibility, for in-memory _jobs)
jobs (
  id VARCHAR(36) PRIMARY KEY,
  run_id VARCHAR(36) REFERENCES pipeline_runs(id) ON DELETE SET NULL,
  status VARCHAR(20) NOT NULL,        -- pending|running|paused|completed|aborted|failed
  progress JSONB,
  results JSONB,
  summary TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

-- Indexes for performance
CREATE INDEX idx_pipeline_runs_project_id ON pipeline_runs(project_id);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX idx_pipeline_runs_created_at ON pipeline_runs(created_at DESC);
CREATE INDEX idx_agent_results_run_id ON agent_results(pipeline_run_id);
CREATE INDEX idx_pipeline_checkpoints_run_id ON pipeline_checkpoints(pipeline_run_id);
CREATE INDEX idx_pipeline_checkpoints_status ON pipeline_checkpoints(status);
```

---

## 5. Configuration Items (E2E Setup)

### 5.1 Required Dependencies

```bash
# Install all dependencies from requirements.txt
pip install -r requirements.txt

# Ensure PostgreSQL driver is available
pip install psycopg2-binary  # OR install system libpq-dev and psycopg2
```

**Note**: Current setup may fail without `psycopg2` because `settings.database_url` defaults to PostgreSQL. Two options:

**Option A - Use PostgreSQL** (Production):
```bash
# Install PostgreSQL driver
pip install psycopg2-binary

# Start PostgreSQL locally
createdb ai_agent_org  # Create database

# Edit .env to customize connection if needed
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_agent_org
```

**Option B - Use SQLite Fallback** (Development/Easier):
```bash
# Edit .env file, set DATABASE_URL to empty:
DATABASE_URL=

# Or leave unset (code checks: if database_url starts with "postgresql")
# But CURRENT DEFAULT in settings.py is PostgreSQL! Must change:
# In config/settings.py, change:
#   database_url: str = "postgresql://postgres:postgres@localhost:5432/ai_agent_org"
# To:
#   database_url: str = ""
```

**Recommendation**: Temporarily change default to empty string until PostgreSQL is set up. This will auto-use SQLite at `data/agent_memory.db` (for memory) and `sqlite:///data/pipelines.db` (for repository). However, the repository currently uses the same `database_url` from settings, so it will also use SQLite.

### 5.2 Environment Variables (.env)

Required:
```
ANTHROPIC_API_KEY=sk-ant-your-real-key-here  # Your Claude API key
```

Optional (defaults provided):
```
# Database (see above)
DATABASE_URL=  # Empty for SQLite, or postgresql://... for PostgreSQL

# Models (can use any Claude model)
MODEL=claude-opus-4-5
FAST_MODEL=claude-haiku-4-5-20251001
MAX_TOKENS=4096

# API
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=change-me-in-production

# Cost Control
MAX_PIPELINE_COST_USD=5.00

# Feature Flags
ENABLE_COST_TRACKING=true
ENABLE_SLACK_NOTIFICATIONS=false
ENABLE_JIRA_INTEGRATION=false
ENABLE_GITHUB_INTEGRATION=false
```

### 5.3 Initialize Database

If using PostgreSQL:
```bash
# Create database (if not exists)
createdb ai_agent_org

# Option 1: Let app auto-create on startup (dev)
# The config/database.py will call Base.metadata.create_all() when module loads
# This requires the database to exist and permissions to CREATE TABLE

# Option 2: Use Alembic migrations (future)
alembic upgrade head
```

If using SQLite:
- Tables auto-created on first module import (if DB file doesn't exist)
- No manual setup needed

### 5.4 Create Required Directories

```bash
mkdir -p data workspace
```

The FastAPI lifespan handler (`api/main.py:36-40`) tries to create these on startup, but better to create manually.

### 5.5 Run the Application

```bash
# Terminal 1: Start API server
.venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal 2: Start React UI (optional)
cd pipeline-ui
npm install  # if not done
npm run dev

# Or build for production
cd pipeline-ui
npm run build
# Then serve the dist/ folder
```

### 5.6 Verify Setup

```bash
# Test API health
curl http://localhost:8000/api/pipelines/health

# Should return:
# {"status":"ok","features":["templates","validation","preview","run"]}

# Test database connection
curl http://localhost:8000/api/projects/default/pipelines/history

# Should return:
# {"project_id":"default","runs":[],"total_cost_usd":0.0}

# Run tests
.venv/bin/pytest tests/pipeline/test_repository.py -v
# Should pass: test_repository_create_run, test_repository_list_runs, etc.
```

---

## 6. E2E Working Checklist

- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] PostgreSQL driver: `psycopg2-binary` installed **OR** `DATABASE_URL=` empty
- [ ] `.env` file configured with `ANTHROPIC_API_KEY`
- [ ] If using PostgreSQL: database `ai_agent_org` created
- [ ] If using SQLite: `data/` directory exists (or will be auto-created)
- [ ] FastAPI app starts without errors: `uvicorn api.main:app --reload`
- [ ] Health endpoint returns: `{"status": "ok"}`
- [ ] History endpoint returns 200 with empty list
- [ ] Repository tests pass (SQLite in-memory works)
- [ ] Can create a pipeline run (POST `/api/pipelines/run`) and see job created
- [ ] Can retrieve job status (GET `/api/pipeline/jobs/{job_id}`)
- [ ] (Optional) React UI builds and connects to API

---

## 7. Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            User / Client                                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP/REST (JSON)
                                │
                    ┌───────────▼────────────┐
                    │   FastAPI (api/main.py)│
                    │   - Routes            │
                    │   - Dependency Inj.   │
                    │   - Request Models   │
                    └───────────┬────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
        ┌───────▼──────┐  ┌────▼─────┐  ┌────▼─────┐
        │ Config       │  │Repo (async)│  │Memory    │
        │ Loader       │  │           │  │Store     │
        │ - YAML parse │  │CRUD ops   │  │          │
        │ - Validation │  │           │  │          │
        │ - DAG build  │  └───────┬───┘  └──────────┘
        └───────┬──────┘          │
                │                 │
                │         ┌───────▼────────────┐
                │         │  SQLAlchemy        │
                │         │  (AsyncSession)    │
                │         └───────┬────────────┘
                │                 │
                │         ┌───────▼────────────┐
                │         │  Database          │
                │         │  PostgreSQL /      │
                │         │  SQLite            │
                │         └───────────────────┘
                │
                │
        ┌───────▼──────────────────────────────┐
        │   Orchestrator (pipeline/orchestrator.py)   │
        │   - PipelineRun state machine              │
        │   - Topological sort                       │
        │   - Parallel execution (asyncio.gather)   │
        │   - Checkpoint handling                    │
        │   - Cost & summary aggregation            │
        └───────┬──────────────────────────────┘
                │
                │ spawns
                │
        ┌───────▼──────────────────────────────┐
        │   Agents (agents/*_agent.py)         │
        │   - BaseAgent.run()                  │
        │   - Tool execution                   │
        │   - Claude API calls                 │
        │   - Result generation                │
        └──────────────────────────────────────┘
```

---

## 8. Repository Pattern Rationale

**Why we added repository layer**:
- Decouple business logic (orchestrator) from database specifics
- Enable easy testing (mock repository, swap SQLite/PostgreSQL)
- Centralize CRUD operations, avoid SQL scattered throughout code
- Prepare for future data sources (Redis for jobs, event store for audit)

**Key Design Decisions**:
1. **Separate sync and async repositories**: FastAPI async routes need `AsyncSession`, but migrations/scripts need sync `Session`. Both share same DB models.
2. **Repository returns DB models**: Not Pydantic schemas. API layer transforms to response models. This keeps repository focused on persistence only.
3. **Orchestrator accepts repository**: `Orchestrator(project_id, repository=repo)`. Allows injecting mock repository for testing or alternative implementation.
4. **Async context manager**: `get_async_repository()` yields `AsyncPipelineRepository` via dependency injection.

---

## 9. Testing Strategy

### Unit Tests
- `tests/pipeline/test_config_loader.py` - YAML parsing, validation, DAG generation
- `tests/pipeline/test_dependency_resolution.py` - Dependency graph algorithms
- `tests/pipeline/test_repository.py` - Repository CRUD (uses SQLite in-memory)

### Integration Tests
- `tests/api/test_pipelines.py` - All API endpoints (32 tests)

### Agent Tests (Flaky)
- `tests/agents/test_*.py` - Individual agent integration (requires Claude API quota)

### Running Tests
```bash
# All pipeline tests (should pass)
.venv/bin/pytest tests/pipeline/ -v

# API tests (may need database setup)
.venv/bin/pytest tests/api/test_pipelines.py -v

# Specific repository tests (no external deps)
.venv/bin/pytest tests/pipeline/test_repository.py -v
```

---

## 10. Next Steps (Post-Setup)

After E2E setup is working:

1. **Alembic migrations** - Replace `Base.metadata.create_all()` with proper migration scripts
2. **Template import/export** - UI + API for saving/loading custom templates
3. **History UI** - Connect React UI to `/api/projects/{project_id}/pipelines/history`
4. **Analytics** - Cost trends, success rates, agent performance
5. **Redis for jobs** - Replace `_jobs` dict with Redis for horizontal scaling
6. **Authentication** - Add API key or OAuth2 protection
7. **Rate limiting** - Protect endpoints from abuse
8. **Docker** - Containerize API + UI + PostgreSQL
9. **CLI tool** - `ai-agent-org` command for pipeline execution from terminal
10. **Documentation** - User guide, deployment guide, API reference

---

## 11. Summary

**Architecture**: Layered monolith with clear separation:
- Config → Orchestrator → Repository → Database
- FastAPI → React UI
- Agents injected via registry

**Status**: Core pipeline execution fully functional. Persistence layer implemented and tested. UI integrated for checkpoints. History API now works with database.

**To Go E2E**: Install psycopg2-binary OR switch to SQLite, set up .env, create data/workspace dirs, start server, verify health/history endpoints.

**Production Readiness**: Need migrations, auth, rate limiting, Redis, Docker, monitoring.
