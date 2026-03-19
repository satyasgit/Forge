"""
FastAPI application — main entry point.
Run: uvicorn api.main:app --reload --port 8000
"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.settings import settings
from pipeline.orchestrator import Orchestrator, make_full_app_pipeline, PipelineRun

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# In-memory job store (swap for Redis in production)
_jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    os.makedirs("data", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)
    yield


app = FastAPI(
    title="AI Agent Org API",
    description="One-person AI engineering org — build any product with agents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class BuildFeatureRequest(BaseModel):
    description: str = Field(..., min_length=10, description="Feature to build")
    project_id: str = Field(default="default", description="Project namespace")
    agents: list[str] = Field(
        default=["pm", "ui_ux", "frontend", "backend", "security", "qa", "devops"],
        description="Which agents to include"
    )

class SecurityAuditRequest(BaseModel):
    code: dict[str, str] = Field(..., description="filename → code content")
    language: str = "python"
    context: str = ""
    project_id: str = "default"

class SingleAgentRequest(BaseModel):
    agent: str = Field(..., description="Agent name: security|frontend|backend|etc.")
    task: str = Field(..., min_length=5)
    project_id: str = "default"
    context: str = ""

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: dict | None = None
    results: dict | None = None
    summary: str | None = None
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_agent(name: str, project_id: str):
    from agents.security_agent import SecurityAgent
    from agents.frontend_agent import FrontendAgent
    from agents.backend_agent import BackendAgent
    from agents.mobile_agent import MobileAgent
    from agents.devops_agent import DevOpsAgent
    from agents.code_review_agent import CodeReviewAgent
    from agents.qa_agent import QAAgent
    from agents.pm_agent import PMAgent
    from agents.ui_ux_agent import UIUXAgent
    from agents.monetisation_agent import MonetisationAgent

    registry = {
        "security":      SecurityAgent,
        "frontend":      FrontendAgent,
        "backend":       BackendAgent,
        "mobile":        MobileAgent,
        "devops":        DevOpsAgent,
        "code_review":   CodeReviewAgent,
        "qa":            QAAgent,
        "pm":            PMAgent,
        "ui_ux":         UIUXAgent,
        "monetisation":  MonetisationAgent,
    }
    cls = registry.get(name)
    if not cls:
        raise HTTPException(400, f"Unknown agent: {name}. Valid: {list(registry)}")
    return cls(project_id=project_id)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": settings.model}


@app.post("/api/pipeline/run", response_model=JobStatus)
async def run_pipeline(req: BuildFeatureRequest, background: BackgroundTasks):
    """Kick off the full multi-agent build pipeline asynchronously."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "progress": {}, "results": None}

    async def _run():
        import asyncio
        _jobs[job_id]["status"] = "running"
        try:
            orch = Orchestrator(req.project_id)
            tasks = make_full_app_pipeline(req.description, req.project_id)
            # Filter to requested agents
            tasks = [t for t in tasks if t.name in req.agents]
            run: PipelineRun = await orch.run(tasks)
            _jobs[job_id].update({
                "status": "done" if not run.aborted else "aborted",
                "results": {k: v.to_dict() for k, v in run.results.items()},
                "summary": run.summary(),
            })
        except Exception as e:
            _jobs[job_id].update({"status": "failed", "error": str(e)})

    background.add_task(_run)
    return JobStatus(job_id=job_id, status="pending")


@app.get("/api/pipeline/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatus(job_id=job_id, **job)


@app.post("/api/agents/security/audit")
async def security_audit(req: SecurityAuditRequest):
    """Run a direct security audit (synchronous — for small codebases)."""
    from agents.security_agent import SecurityAgent
    agent = SecurityAgent(project_id=req.project_id)
    result = agent.run_full_audit(req.code, req.language, req.context)
    return result.to_dict()


@app.post("/api/agents/run")
async def run_single_agent(req: SingleAgentRequest):
    """Run any single agent with a custom task."""
    agent = _get_agent(req.agent, req.project_id)
    result = agent.run(req.task, context=req.context)
    return result.to_dict()


@app.get("/api/projects/{project_id}/cost")
def project_cost(project_id: str):
    from memory.store import ProjectMemory
    mem = ProjectMemory(project_id)
    return {"project_id": project_id, "total_cost_usd": mem.total_cost()}


@app.get("/api/agents")
def list_agents():
    return {
        "agents": [
            {"name": "pm",           "role": "Product Manager",           "description": "PRDs, user stories, Jira tickets"},
            {"name": "ui_ux",        "role": "UI/UX Designer",            "description": "Wireframes, component specs, design tokens"},
            {"name": "frontend",     "role": "Frontend Engineer",         "description": "React/TypeScript components"},
            {"name": "mobile",       "role": "Mobile Engineer",           "description": "React Native / Expo screens"},
            {"name": "backend",      "role": "Backend Engineer",          "description": "FastAPI, SQLAlchemy, PostgreSQL"},
            {"name": "security",     "role": "Security Engineer",         "description": "OWASP, SAST, threat models"},
            {"name": "code_review",  "role": "Principal Engineer",        "description": "Code quality, patterns, bugs"},
            {"name": "qa",           "role": "QA Engineer",               "description": "Unit, integration, E2E, load tests"},
            {"name": "devops",       "role": "DevOps Engineer",           "description": "Docker, CI/CD, Terraform"},
            {"name": "monetisation", "role": "Growth Engineer",           "description": "Stripe, IAP, pricing, growth"},
        ]
    }
