# AI Agent Org

A one-person AI engineering organisation. Ten fully-built specialist agents collaborate
to design, build, review, secure, test, and deploy any mobile or web product.
Every agent runs a local pre-scanner (zero API cost) before calling Claude,
exactly like a linter runs before a compiler.

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
