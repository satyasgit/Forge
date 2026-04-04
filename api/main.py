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
from pipeline.config_loader import (
    load_all_templates,
    load_template,
    validate_pipeline as validate_config,
    build_pipeline_from_config,
    build_dag_dict,
    estimate_cost,
    estimate_duration,
)

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

from agents.agent_config import create_agent, list_agent_metadata, register_agent

# Explicit agent registration (no import side effects)
def _register_all_agents():
    from agents.pm_agent import PMAgent
    from agents.frontend_agent import FrontendAgent
    from agents.backend_agent import BackendAgent
    from agents.mobile_agent import MobileAgent
    from agents.security_agent import SecurityAgent
    from agents.qa_agent import QAAgent
    from agents.code_review_agent import CodeReviewAgent
    from agents.devops_agent import DevOpsAgent
    from agents.ui_ux_agent import UIUXAgent
    from agents.monetisation_agent import MonetisationAgent

    for cls in [
        PMAgent, FrontendAgent, BackendAgent, MobileAgent,
        SecurityAgent, QAAgent, CodeReviewAgent, DevOpsAgent,
        UIUXAgent, MonetisationAgent
    ]:
        register_agent(cls)

_register_all_agents()

def _get_agent(name: str, project_id: str):
    try:
        return create_agent(name, project_id=project_id)
    except ValueError as e:
        logging.error(f"Failed to create agent '{name}': {e}")
        raise HTTPException(400, str(e))


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
    agent = _get_agent("security", req.project_id)
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
    return {"agents": list_agent_metadata()}


# ============================================================================
# Pipeline Configuration & Templates API
# ============================================================================

from api.pipelines_schemas import (
    TemplateMetadata,
    TemplateListResponse,
    TemplateDetailResponse,
    PipelineConfigAPI,
    PipelinePreviewResponse,
    ValidationRequest,
    ValidationResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineHistoryItem,
    PipelineHistoryResponse,
)


@app.get("/api/pipelines/templates", response_model=TemplateListResponse)
def list_pipeline_templates():
    """
    List all available pipeline templates.

    Returns metadata for each template (name, description, agent count, etc.)
    without loading the full configuration.
    """
    templates = load_all_templates()
    return TemplateListResponse(templates=[
        TemplateMetadata(**t) for t in templates
    ])


@app.get("/api/pipelines/templates/{name}", response_model=TemplateDetailResponse)
def get_pipeline_template(name: str):
    """
    Get full configuration for a specific template.

    Args:
        name: Template name (as defined in the YAML's `name` field)

    Returns:
        Full PipelineConfig as dict
    """
    config = load_template(name)
    if config is None:
        raise HTTPException(404, f"Template '{name}' not found")
    return TemplateDetailResponse(template=config.dict())


@app.post("/api/pipelines/validate", response_model=ValidationResponse)
def validate_pipeline_endpoint(req: ValidationRequest):
    """
    Validate a pipeline configuration without running it.

    Checks:
    - All agents exist in registry
    - Dependencies are resolvable
    - No circular dependencies
    - Schema validity
    """
    # Convert API model to core model
    config_dict = req.config.dict()
    try:
        from pipeline.config_loader import PipelineConfig
        config = PipelineConfig(**config_dict)
    except Exception as e:
        return ValidationResponse(
            valid=False,
            errors=[f"Invalid configuration: {e}"]
        )

    # Get agent registry
    from agents.agent_config import get_registered_agents
    agent_registry = set(get_registered_agents().keys())

    # Validate
    result = validate_config(config, agent_registry=agent_registry)
    return ValidationResponse(
        valid=result.valid,
        errors=result.errors,
        warnings=result.warnings,
    )


@app.post("/api/pipelines/preview", response_model=PipelinePreviewResponse)
def preview_pipeline(req: PipelineConfigAPI):
    """
    Preview a pipeline configuration: estimate cost, duration, and DAG.

    Does NOT validate or execute. Useful for UI to show estimates.
    """
    # Convert to core config
    config_dict = req.dict()
    try:
        from pipeline.config_loader import PipelineConfig
        config = PipelineConfig(**config_dict)
    except Exception as e:
        raise HTTPException(400, f"Invalid configuration: {e}")

    # Build tasks (resolves dependencies)
    try:
        orchestrator = Orchestrator(project_id="preview")
        tasks = orchestrator.build_from_config(config)
    except ValueError as e:
        raise HTTPException(400, f"Failed to build pipeline: {e}")

    # Generate DAG
    dag = build_dag_dict(tasks)

    # Estimate cost and duration
    cost_usd = estimate_cost(tasks)
    duration_min = estimate_duration(tasks)

    return PipelinePreviewResponse(
        agents=[t.name for t in tasks],
        agent_count=len(tasks),
        estimated_cost_usd=cost_usd,
        estimated_duration_minutes=duration_min,
        dag=dag,
        validation=None,
    )


@app.post("/api/pipelines/run", response_model=PipelineRunResponse)
async def run_custom_pipeline(req: PipelineRunRequest, background: BackgroundTasks):
    """
    Run a custom pipeline configuration.

    This is async - returns immediately with a job_id.
    Use GET /api/pipeline/jobs/{job_id} to check status.

    Args:
        req: PipelineRunRequest with config, feature, project_id
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "progress": {}, "results": None}

    async def _run():
        try:
            _jobs[job_id]["status"] = "running"
            orch = Orchestrator(req.project_id)

            # Convert API config to core config and build tasks
            config_dict = req.config.dict()
            from pipeline.config_loader import PipelineConfig
            config = PipelineConfig(**config_dict)
            tasks = orch.build_from_config(config)

            # Substitute template variables
            for task in tasks:
                if task.task:
                    task.task = task.task.format(
                        feature=req.feature,
                        project_id=req.project_id
                    )

            # Run
            run: PipelineRun = await orch.run(tasks)
            _jobs[job_id].update({
                "status": "done" if not run.aborted else "aborted",
                "results": {k: v.to_dict() for k, v in run.results.items()},
                "summary": run.summary(),
            })
        except Exception as e:
            logging.error(f"Pipeline run {job_id} failed: {e}", exc_info=True)
            _jobs[job_id].update({
                "status": "failed",
                "error": str(e)
            })

    background.add_task(_run)
    return PipelineRunResponse(
        success=True,
        run={"job_id": job_id, "status": "pending"},
        message="Pipeline started"
    )


@app.get("/api/projects/{project_id}/pipelines/history", response_model=PipelineHistoryResponse)
def get_pipeline_history(project_id: str, limit: int = 20):
    """
    Get recent pipeline runs for a project.

    Note: Requires ProjectMemory to store pipeline history.
    This is a stub - full implementation in Phase 4.
    """
    # Placeholder - will be implemented in Phase 4 with memory integration
    return PipelineHistoryResponse(
        project_id=project_id,
        runs=[],
        total_cost_usd=0.0,
    )


@app.get("/api/pipelines/health")
def pipelines_health():
    """Health check for pipeline system."""
    return {
        "status": "ok",
        "features": [
            "templates",
            "validation",
            "preview",
            "run"
        ]
    }
