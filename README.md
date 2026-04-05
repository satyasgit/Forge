# AI Agent Org

**Status**: Phase 4 In Progress — Persistent Storage ✅, Configurable Pipelines ✅, History API ✅

A one-person AI engineering organisation. Ten fully-built specialist agents collaborate
to design, build, review, secure, test, and deploy any mobile or web product.
Every agent runs a local pre-scanner (zero API cost) before calling Claude,
exactly like a linter runs before a compiler.

** Latest: Phase 4 Repository layer complete — PostgreSQL/SQLite persistence, History API now returns real data from database. **

## Agent roster

| Agent | Role | Pre-scanner detects | Key output |
|-------|------|---------------------|-----------|
| `pm` | Product Manager | Entities, integrations, complexity signals | PRD, user stories, Jira tickets |
| `ui_ux` | Product Designer | Auth/billing/mobile/upload screens needed | Component specs, user flows, design tokens |
| `frontend` | Frontend Engineer | onClick gaps, missing error/loading states, a11y | React/TypeScript + Vitest tests |
| `mobile` | Mobile Engineer | Push, camera, biometrics, IAP, deep links | React Native / Expo screens |
| `backend` | Backend Engineer | Missing response_model, N+1, bare except, raw dict body | FastAPI + SQLAlchemy + Alembic |
| `security` | Security Engineer | SQL injection, secrets, JWT issues, path traversal | OWASP audit, SAST, threat model |
| `code_review` | Principal Engineer | print(), assert, star import, TODO, TS any, console.log | Severity-tagged review with fixes |
| `qa` | QA / SDET | Untested routes, missing auth tests, time.sleep antipatterns | pytest + Playwright + Locust |
| `devops` | DevOps Engineer | FROM :latest, GHA @main, SSH open, unencrypted RDS | Docker + GitHub Actions + Terraform |
| `monetisation` | Growth Engineer | Trial, team billing, annual, enterprise, usage-based signals | Stripe webhooks + entitlement middleware |

## Architecture

Each agent follows the **SecurityAgent pattern**:

```
skill files (knowledge)  →  local pre-scanner (free)  →  enriched Claude prompt  →  typed output
owasp.py, sast.py           _run_sast(), _scan_secrets()   pre-tagged findings       AgentResult
```

Every pre-scanner:
- Runs on the source code/files before any API call
- Tags findings by severity (critical → high → medium → low)
- Injects structured findings into the Claude prompt
- Costs $0 — only regex matching

## Quick start

```bash
unzip ai-agent-org.zip && cd ai-agent-org
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY

# Open in VS Code with all settings + launch configs
code ai-agent-org.code-workspace
```

## Run any agent

```python
# Security audit
from agents.security_agent import SecurityAgent
agent = SecurityAgent(project_id="my-app")
result = agent.run_full_audit({"auth.py": open("auth.py").read()}, "python")
print(result.output)   # Full OWASP report with fixes

# Code review
from agents.code_review_agent import CodeReviewAgent
agent = CodeReviewAgent(project_id="my-app")
result = agent.review({"routes.py": open("routes.py").read()})

# Generate tests
from agents.qa_agent import QAAgent
agent = QAAgent(project_id="my-app")
result = agent.generate_tests({"routes/users.py": open("routes/users.py").read()})

# Write PRD + Jira tickets
from agents.pm_agent import PMAgent
agent = PMAgent(project_id="my-app")
result = agent.write_prd("Stripe subscription with team seats and annual plan")

# Build backend
from agents.backend_agent import BackendAgent
agent = BackendAgent(project_id="my-app")
result = agent.build_feature("User subscription management", async_mode=True)

# Design monetisation
from agents.monetisation_agent import MonetisationAgent
agent = MonetisationAgent(project_id="my-app")
result = agent.design_monetisation("SaaS with free trial, Pro $29/mo, Business $99/mo")
```

## Run the full pipeline

```python
import asyncio
from pipeline.orchestrator import run_full_pipeline

result = asyncio.run(run_full_pipeline(
    feature="Stripe subscription billing with team seats and admin portal",
    project_id="my-saas",
))
print(result.summary())
# Pipeline: my-saas | Duration: 87.3s | Cost: $1.24
# [OK] pm: 12.1s, $0.0842
# [OK] ui_ux: 8.4s, $0.0631
# [OK] frontend: 11.2s, $0.1104
# ...
```

## 🛠️ Configurable Pipelines (NEW!)

### Run with a YAML Template

Instead of the full 10-agent pipeline, choose a template that fits your needs:

```python
from pipeline.config_loader import load_template, run_full_pipeline

# Load a template (e.g., api_only, mvp, security_audit_only)
config = load_template("api_only")

# Run with the template
result = asyncio.run(run_full_pipeline(
    feature="User authentication API with JWT",
    project_id="my-api",
    config=config,  # ← Optional: if None, uses full pipeline
))
```

**Available templates** (see `config/pipelines/`):
- `full_stack_web` - All 10 agents, complete web app
- `api_only` - Backend + security + QA + DevOps (no UI)
- `mvp` - Lean pipeline (PM, Frontend, Backend, QA) - fast & cheap
- `security_audit_only` - Deep security review only

### Run via API

Start the server and use new endpoints:

```bash
uvicorn api.main:app --reload --port 8000
```

```bash
# List templates
curl http://localhost:8000/api/pipelines/templates

# Get template details
curl http://localhost:8000/api/pipelines/templates/api_only

# Validate custom config
curl -X POST http://localhost:8000/api/pipelines/validate \
  -H "Content-Type: application/json" \
  -d '{"config": {"name": "my_pipeline", "agents": [{"agent": "backend"}]}}'

# Preview (estimate cost/duration)
curl -X POST http://localhost:8000/api/pipelines/preview \
  -H "Content-Type: application/json" \
  -d @my_pipeline.json

# Run custom pipeline
curl -X POST "http://localhost:8000/api/pipelines/run?feature=User%20API&project_id=my-project" \
  -H "Content-Type: application/json" \
  -d @my_pipeline.json
```

Interactive API docs: http://localhost:8000/docs

### Create Custom Templates

Copy and edit `config/pipelines/mvp.yaml`:

```yaml
version: "1.0"
name: "my_custom"
description: "My custom pipeline"
agents:
  - agent: "pm"
    enabled: true
    task: "PRD for: {feature}"
  - agent: "backend"
    enabled: true
    depends_on: ["pm"]
auto_resolve: true
```

Validation:
```bash
python -c "from pipeline.config_loader import load_template, validate_pipeline; cfg = load_template('my_custom'); result = validate_pipeline(cfg); print('OK' if result.valid else result.errors)"
```

See `config/pipelines/README.md` for complete template reference.

---

## 📊 Pipeline History & Persistence

Phase 4 introduces persistent storage for all pipeline executions using PostgreSQL (production) or SQLite (development).

**History API**:
```bash
# Get recent pipeline runs for a project
curl "http://localhost:8000/api/projects/my-project/pipelines/history?limit=20"
```

Response includes:
- Run ID, timestamp, config name
- Status (completed, failed, paused)
- Cost in USD
- Duration in seconds
- Agent count

All runs are stored in the `pipeline_runs` table with full configuration and results.

**Database Setup**:
- **SQLite** (dev): No setup needed — auto-creates `data/pipelines.db`
- **PostgreSQL** (prod): Set `DATABASE_URL` in `.env` and run `createdb ai_agent_org`
- Tables created automatically on first run (or use `init_db()` utility)

See `SETUP.md` for complete database configuration.

---

## 🔄 Checkpoints & Human Approval

Pipelines can include `checkpoint_agent` with `human_approval` type to pause execution awaiting manual approval.

**How it works**:
1. Pipeline reaches checkpoint agent → auto-pauses
2. Checkpoint appears in UI/memory with status "pending"
3. Approve or reject via API:
   ```bash
   curl -X POST http://localhost:8000/api/pipelines/resume/<run_id> \
     -H "Content-Type: application/json" \
     -d '{"decision": "approved", "approver": "user@co.com"}'
   ```
4. Pipeline resumes from paused state

**UI Integration**: The React pipeline builder (`pipeline-ui/`) shows checkpoint nodes with octagon icons and approval panel overlay.

---

## 🎨 Visual Pipeline Builder (React UI)

A modern React + TypeScript UI for building pipelines visually:

```bash
cd pipeline-ui
npm install
npm run dev
# Open http://localhost:5173
```

Features:
- Drag-and-drop agent nodes (React Flow)
- Dependency graph editing
- Real-time validation & preview
- Cost/duration estimates
- Pipeline execution with job polling
- Checkpoint approval overlay

See `pipeline-ui/README.md` (if present) for usage.

---

## 🏗️ Project Structure

```
ai-agent-org/
├── agents/              11 specialist agents (all fully built)
│   ├── base.py          Tool loop, cost tracking, memory — all agents inherit this
│   ├── checkpoint_agent.py  Human approval support
│   ├── security_agent.py  ← original reference implementation
│   ├── qa_agent.py        ← matches SecurityAgent pattern exactly
│   ├── pm_agent.py        ← matches SecurityAgent pattern exactly
│   ├── frontend_agent.py  ← matches SecurityAgent pattern exactly
│   ├── backend_agent.py   ← matches SecurityAgent pattern exactly
│   ├── code_review_agent.py
│   ├── devops_agent.py
│   ├── ui_ux_agent.py
│   ├── mobile_agent.py
│   └── monetisation_agent.py
│
├── skills/              Domain knowledge for each agent
│   ├── security/        owasp.py · sast.py · threat_model.py
│   ├── qa/              pytest_patterns.py · fixture_library.py
│   ├── pm/              prd_structure.py · jira_templates.py
│   ├── frontend/        react_patterns.py · vitest_patterns.py
│   ├── backend/         fastapi_patterns.py · api_patterns.py
│   ├── code_review/     review_patterns.py
│   ├── devops/          ci_cd_templates.py · infra_patterns.py
│   ├── ui_ux/           design_patterns.py
│   ├── mobile/          expo_patterns.py
│   └── monetisation/    stripe_patterns.py
│
├── tools/registry.py    GitHub, Jira, Figma, Slack integrations
├── memory/store.py      SQLite/PostgreSQL cross-session memory per project
├── pipeline/
│   ├── config_loader.py   YAML loading, validation, DAG generation
│   ├── orchestrator.py    Parallel execution with dependency resolution
│   ├── repository.py      CRUD operations for pipeline data (NEW ✅)
│   ├── models_database.py SQLAlchemy 2.0+ models (NEW ✅)
│   └── config_loader.py   Template system with 4 built-in templates
│
├── api/main.py          FastAPI server with 16 endpoints
├── config/
│   ├── settings.py      Centralized configuration
│   ├── database.py      Database connection management
│   └── pipelines/       YAML templates (4 templates + README)
│
├── pipeline-ui/         React pipeline builder (TypeScript + React Flow)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── components/AgentNode.tsx
│   │   ├── components/CheckpointPanel.tsx
│   │   ├── hooks/usePipelineStore.ts
│   │   └── types.ts
│   └── package.json
│
├── tests/
│   ├── pipeline/        Config loader, dependency resolution, repository tests
│   ├── api/             API endpoint tests (32 tests)
│   └── agents/          Scanner tests (59 tests)
│
├── docs/
│   ├── CURRENT_ARCHITECTURE.md      ⭐ NEW - Full system architecture
│   ├── PHASE4_POLISH_MARKETPLACE_PLAN.md
│   ├── IMPLEMENTATION_STATUS.md     Progress tracker
│   └── ...
│
├── SETUP.md            ⭐ NEW - Complete E2E setup guide
├── requirements.txt
├── .env.example
└── .venv/              Virtual environment (create with `python -m venv .venv`)
```

## Start the API server

```bash
uvicorn api.main:app --reload --port 8000
# Docs: http://localhost:8000/docs
```

## Run all tests (59 scanner tests, no API key needed)

```bash
pytest tests/ -v --tb=short
```

## Project structure

```
ai-agent-org/
├── agents/              10 specialist agents (all fully built)
│   ├── base.py          Tool loop, cost tracking, memory — all agents inherit this
│   ├── security_agent.py  ← original reference implementation
│   ├── qa_agent.py        ← matches SecurityAgent pattern exactly
│   ├── pm_agent.py        ← matches SecurityAgent pattern exactly
│   ├── frontend_agent.py  ← matches SecurityAgent pattern exactly
│   ├── backend_agent.py   ← matches SecurityAgent pattern exactly
│   ├── code_review_agent.py
│   ├── devops_agent.py
│   ├── ui_ux_agent.py
│   ├── mobile_agent.py
│   └── monetisation_agent.py
│
├── skills/              Domain knowledge for each agent
│   ├── security/        owasp.py · sast.py · threat_model.py
│   ├── qa/              pytest_patterns.py · fixture_library.py
│   ├── pm/              prd_structure.py · jira_templates.py
│   ├── frontend/        react_patterns.py · vitest_patterns.py
│   ├── backend/         fastapi_patterns.py · api_patterns.py
│   ├── code_review/     review_patterns.py
│   ├── devops/          ci_cd_templates.py · infra_patterns.py
│   ├── ui_ux/           design_patterns.py
│   ├── mobile/          expo_patterns.py
│   └── monetisation/    stripe_patterns.py
│
├── tools/registry.py    GitHub, Jira, Figma, Slack integrations
├── memory/store.py      SQLite cross-session memory per project
├── pipeline/orchestrator.py  Parallel pipeline with dependency graph
├── api/main.py          FastAPI server
├── dashboard/src/       React dashboard
└── tests/agents/        59 scanner tests — all run without API key
```

## Cost management

Set `MAX_PIPELINE_COST_USD=5.00` in `.env` to cap spending per run.
Track cost per project:
```python
from memory.store import ProjectMemory
print(f"Project cost so far: ${ProjectMemory('my-project').total_cost():.4f}")
```

## Adding a new agent

1. Create `agents/my_agent.py` inheriting `BaseAgent`
2. Add skill files to `skills/my_domain/` with patterns + templates
3. Implement `_scan_*()` methods that run the skill patterns locally
4. Implement the public API methods (e.g. `run_full_audit()`, `generate_tests()`)
5. Add `PipelineTask` to `pipeline/orchestrator.py`
6. Register in `api/main.py` `_get_agent()`
7. Write tests in `tests/agents/test_my_agent.py`
