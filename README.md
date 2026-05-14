# AI Agent Org (V2)

**Status**: V2 Architecture Overhaul Complete — LiteLLM ✅, Redis Bus ✅, Temporal Orchestration ✅, Agile Engine ✅, Semantic Memory ✅, Sprint Dashboard ✅

A one-person AI engineering organisation. A team of specialized AI agents collaborate as "AI Coworkers" to design, build, review, secure, test, and deploy software products. 

---

## 🚀 Key Features

### 1. Multi-LLM Resilience (LiteLLM)
Agents use **LiteLLM** to route tasks to Claude 3.5, GPT-4, Gemini 1.5, or local models. This ensures high availability and allows for cost-optimized routing.

### 2. Real-Time Communication Bus (Redis)
Agents communicate via a Redis-backed **MessageBus**. They can `broadcast` status updates, `ask` questions to specialists, and `answer` technical queries in real-time.

### 3. Agile Sprint Engine
Full Agile lifecycle management:
- **CEO & VP Engineering**: Strategy, planning, and standup summarization.
- **Persistent Sprint State**: Sprints and User Stories are stored in Supabase/PostgreSQL.

### 4. Durable Orchestration (Temporal.io)
Powered by **Temporal**. Sprints and User Stories are long-running workflows that survive restarts. Agent tasks are wrapped in auto-retrying activities.

### 5. Agent Self-Evolution (Semantic Memory)
Agents learn from outcomes using **pgvector**. They extract lessons post-task and recall them automatically before starting new, similar tasks.

### 6. Interactive Sprint Dashboard (React)
A comprehensive dashboard featuring:
- **Kanban Board**: Drag-and-drop tracking of User Stories.
- **Team Chat**: Real-time view of inter-agent messages and decision logs.
- **Pipeline Builder**: Visual canvas for building custom agent flows with working connections.

---

## 👥 The AI Team (Agent Roster)

| Role | Agent | Key Responsibilities |
|------|-------|----------------------|
| **Strategy** | `ceo`, `vp_eng` | Vision, sprint planning, team orchestration, standups. |
| **Product** | `pm`, `ui_ux` | PRDs, user stories, component specs, design tokens. |
| **Engineering** | `backend`, `frontend`, `mobile` | FastAPI, React/TS, React Native, SQLAlchemy. |
| **Quality** | `qa`, `code_review`, `security` | Pytest/Playwright, PR reviews, OWASP audits, SAST. |
| **Ops & Growth** | `devops`, `monetisation` | Docker/K8s, CI/CD, Stripe integration, billing models. |

---

## 🏁 Quick Start

### 1. Environment Setup
```bash
git clone https://github.com/satyasgit/Forge.git && cd Forge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add API keys and DATABASE_URL
```

### 2. Start Services
V2 requires several services running in parallel:

1.  **Infra**: Start Temporal (`temporal server start-dev`) and Redis.
2.  **Worker**: `python api/worker.py` (Executes agent tasks)
3.  **Backend**: `uvicorn api.main:app --reload` (FastAPI)
4.  **Frontend**: `cd pipeline-ui && npm run dev` (Dashboard)

### 3. Run a Demo Sprint
Create a script `run_demo.py`:
```python
import asyncio
from pipeline.orchestrator import run_sprint_with_temporal

async def main():
    backlog = [{"id": "web-1", "title": "Coffee Shop Landing Page", "description": "Modern React landing page"}]
    workflow_id = await run_sprint_with_temporal(sprint_id="demo-1", project_id="demo", backlog=backlog)
    print(f"🚀 Started! ID: {workflow_id}. Watch the Team Chat at http://localhost:5173")

if __name__ == "__main__":
    asyncio.run(main())
```
Run it: `python run_demo.py`

---

## 🏗️ Project Structure

```
ai-agent-org/
├── agents/              # 12+ Specialist Agents (pm, backend, security, etc.)
├── activities/          # Temporal activities wrapping agent tasks
├── workflows/           # Temporal workflows (SprintWorkflow, StoryWorkflow)
├── agile/               # Sprint management logic and database models
├── communication/       # Redis MessageBus and JobStore
├── evolution/           # Outcome tracking and reflection engine
├── memory/              # Project memory and pgvector VectorMemory
├── pipeline/            # Orchestrator and config loader
├── pipeline-ui/         # React Dashboard (Sprint Board, Chat, Builder)
├── skills/              # Domain-specific knowledge patterns
└── docs/                # Architecture and vision documents
```

---

## 📊 Documentation
- [Architecture Overhaul](./docs/ARCHITECTURE_OVERHAUL.md)
- [AI Coworkers Vision](./docs/AI_COWORKERS_VISION.md)
- [Agent Self-Evolution](./docs/AGENT_SELF_EVOLUTION.md)
- [Project Progress](./PROGRESS.md)
