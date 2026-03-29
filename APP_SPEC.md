# AI Agent Org - Application Specification

## Overview

**AI Agent Org** is an enterprise-grade multi-agent system that orchestrates specialized AI agents to build full-stack applications. It functions as a "one-person AI engineering org" where each agent represents a different engineering role (PM, Frontend, Backend, Security, QA, DevOps, etc.).

## Core Purpose

The system takes a feature description as input and orchestrates multiple specialized agents to:
1. Create product requirements (PRD)
2. Design UI/UX
3. Implement frontend and backend code
4. Conduct security audits
5. Write comprehensive tests
6. Set up CI/CD pipelines
7. Design monetization strategies

## Architecture

### Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.13+ |
| API Framework | FastAPI |
| LLM Provider | Anthropic Claude (Opus, Sonnet, Haiku) |
| Database | SQLite (development) / PostgreSQL (production) |
| Async Runtime | asyncio |
| Type Checking | Pyright |
| Testing | pytest |
| Formatting | Black |

### Core Components

```
ai-agent-org/
├── agents/           # Specialized AI agents
├── api/              # FastAPI REST API
├── config/           # Configuration management
├── memory/           # Persistent memory store
├── pipeline/         # Orchestration engine
├── skills/           # Agent skill libraries
├── tools/            # Tool registry
├── tests/            # Test suite
└── dashboard/        # React dashboard (optional)
```

## Agent System

### Agent Registry

All agents are registered via a centralized registry pattern:

```python
from agents.agent_config import register_agent

@register_agent
class FrontendAgent(BaseAgent):
    name = "frontend"
    role = "Senior Frontend Engineer"
    # ...
```

### Available Agents

| Agent | Role | Model | Purpose |
|-------|------|-------|---------|
| `pm` | Product Manager | Opus | PRDs, user stories, Jira tickets |
| `ui_ux` | UI/UX Designer | Sonnet | Wireframes, component specs, design tokens |
| `frontend` | Frontend Engineer | Sonnet | React/TypeScript components |
| `mobile` | Mobile Engineer | Sonnet | React Native / Expo screens |
| `backend` | Backend Engineer | Sonnet | FastAPI, SQLAlchemy, PostgreSQL |
| `security` | Security Engineer | Opus | OWASP, SAST, threat models |
| `code_review` | Principal Engineer | Sonnet | Code quality, patterns, bugs |
| `qa` | QA Engineer | Sonnet | Unit, integration, E2E, load tests |
| `devops` | DevOps Engineer | Sonnet | Docker, CI/CD, Terraform |
| `monetisation` | Growth Engineer | Sonnet | Stripe, IAP, pricing, growth |

### Agent Configuration

Each agent has a configuration that defines:
- **Model**: Which Claude model to use (Opus for planning, Sonnet for code gen)
- **Max tokens**: Maximum output tokens per run
- **Temperature**: Creativity level (0.0 for deterministic, 1.0 for creative)
- **Retry policy**: Max retries, backoff strategy
- **Cost control**: Max cost per run
- **Context management**: Message history limits

```python
@dataclass(frozen=True)
class AgentConfig:
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096
    temperature: float = 0.0
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    retry_max_wait: float = 30.0
    max_cost_per_run: float = 2.0
    max_context_messages: int = 20
    summarise_after: int = 10
```

## Pipeline Orchestration

### Pipeline Execution

The orchestrator manages agent execution with:
- **Dependency resolution**: Agents run in correct order based on dependencies
- **Parallel execution**: Independent agents run concurrently
- **Cost tracking**: Real-time cost monitoring with caps
- **Context injection**: Agent outputs are passed as context to downstream agents

### Pre-built Pipelines

#### Full App Pipeline
Standard pipeline for building any mobile/web feature end-to-end:

```
pm → ui_ux → frontend (parallel with) mobile
         ↓
      backend → security
         ↓
      code_review → qa
         ↓
      devops (parallel with) monetisation
```

## Memory System

### Persistent Storage

The memory system stores:
- **Artifacts**: Agent outputs (code, docs, configs)
- **Decisions**: Key decisions with rationale
- **Agent messages**: Conversation history for context continuity
- **Cost logs**: Token usage and cost tracking

### Context Management

Each agent receives:
1. **Project context**: Recent artifacts and decisions
2. **Dependency context**: Outputs from upstream agents
3. **Task context**: The specific task to execute

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/pipeline/run` | POST | Start full pipeline |
| `/api/pipeline/jobs/{job_id}` | GET | Get job status |
| `/api/agents/run` | POST | Run single agent |
| `/api/agents/security/audit` | POST | Run security audit |
| `/api/agents` | GET | List all agents |
| `/api/projects/{project_id}/cost` | GET | Get project cost |

### Request/Response Models

```python
class BuildFeatureRequest(BaseModel):
    description: str = Field(..., min_length=10)
    project_id: str = Field(default="default")
    agents: list[str] = Field(default=["pm", "ui_ux", "frontend", "backend", "security", "qa", "devops"])

class SingleAgentRequest(BaseModel):
    agent: str
    task: str = Field(..., min_length=5)
    project_id: str = "default"
    context: str = ""
```

## Skill Libraries

### Skill Categories

| Category | Skills |
|----------|--------|
| **Backend** | API patterns, FastAPI patterns, NestJS patterns |
| **Frontend** | React patterns, Vue patterns, Vitest patterns |
| **Mobile** | Expo patterns, Flutter patterns, Kotlin patterns, Swift patterns |
| **Enterprise** | Audit logging, Multi-tenancy, SAML SSO, SCIM provisioning |
| **Integrations** | Redis, S3, Elasticsearch, Message queues, WebSockets, Email/SMS, Sentry |
| **Security** | OWASP, SAST, Threat modeling |
| **QA** | Pytest patterns, Fixture library |
| **DevOps** | CI/CD templates, Infrastructure patterns |
| **PM** | Jira templates, PRD structure |
| **UI/UX** | Design patterns |
| **Monetisation** | Stripe patterns |
| **Code Review** | Review patterns |

## Tool System

### Tool Registry

Tools are functions that agents can call during execution:

```python
TOOL_REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "execute_command": execute_command,
    # ... more tools
}

def get_tools_for_agent(enabled_tools: list[str]) -> list[dict]:
    """Get tool definitions for agent's enabled tools."""
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `MODEL` | Default model | `claude-opus-4-5` |
| `FAST_MODEL` | Fast model for summaries | `claude-haiku-4-5-20251001` |
| `MAX_TOKENS` | Default max tokens | `4096` |
| `MEMORY_DB_PATH` | SQLite database path | `data/agent_memory.db` |
| `WORKSPACE_ROOT` | Workspace root path | `{cwd}/workspace` |
| `MAX_PIPELINE_COST_USD` | Pipeline cost cap | `5.0` |
| `GITHUB_TOKEN` | GitHub integration | Optional |
| `JIRA_TOKEN` | Jira integration | Optional |
| `FIGMA_TOKEN` | Figma integration | Optional |
| `SLACK_BOT_TOKEN` | Slack notifications | Optional |

## Error Handling

### Circuit Breaker

The system implements a circuit breaker pattern for the Claude API:
- **Closed**: Normal operation
- **Open**: Too many consecutive failures, requests blocked
- **Half-Open**: Testing if API has recovered

### Retry Logic

Agents retry on transient failures with exponential backoff:
- Max retries: 3 (configurable)
- Backoff base: 2 seconds
- Max wait: 30 seconds

## Cost Management

### Cost Tracking

- Per-model pricing (Opus: $15/$75 per 1M tokens, Sonnet: $3/$15, Haiku: $0.80/$4)
- Real-time cost calculation
- Per-run cost caps
- Pipeline-level cost caps
- Cost breakdown by agent

## Testing

### Test Structure

```
tests/
├── agents/           # Agent unit tests
├── pipeline/         # Pipeline tests
├── tools/            # Tool tests
└── conftest.py       # Shared fixtures
```

### Test Fixtures

- Circuit breaker reset before each test
- Mock LLM clients
- Test databases

## Development Workflow

### Local Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run tests
pytest

# Start API server
uvicorn api.main:app --reload --port 8000
```

### Code Style

- **Formatter**: Black
- **Type checker**: Pyright
- **Line length**: 88 characters
- **Import sorting**: isort

## Deployment

### Production Considerations

1. **Database**: Migrate from SQLite to PostgreSQL
2. **Caching**: Add Redis for session/cache
3. **Queue**: Add message queue for async jobs
4. **Monitoring**: Add observability stack
5. **Security**: Add authentication/authorization
6. **Scaling**: Horizontal scaling with load balancer

## Future Enhancements

- [ ] Web dashboard for monitoring
- [ ] GitHub integration for PR creation
- [ ] Jira integration for ticket management
- [ ] Slack notifications
- [ ] Custom agent creation
- [ ] Agent marketplace
- [ ] Multi-model support (GPT-4, Gemini)
- [ ] Voice interface
- [ ] IDE plugins (VS Code, JetBrains)
