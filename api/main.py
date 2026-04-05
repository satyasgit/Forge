"""
FastAPI application — main entry point.
Run: uvicorn api.main:app --reload --port 8000
"""
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

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
from pipeline.repository import get_async_repository, AsyncPipelineRepository
from config.database import get_async_db, AsyncSessionLocal

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

logger = logging.getLogger(__name__)

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


# ── Database Dependency ───────────────────────────────────────────────────────

from fastapi import Depends

async def get_repo() -> AsyncGenerator[AsyncPipelineRepository, None]:
    """Dependency for async repository. Yields a repository with managed session."""
    from sqlalchemy.ext.asyncio import AsyncSession
    # We'll use the existing AsyncSessionLocal directly
    async with AsyncSessionLocal() as session:
        yield AsyncPipelineRepository(session)


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
    run_id: str | None = None  # Pipeline orchestrator run ID (for resume)


class CheckpointDecisionRequest(BaseModel):
    """Request to approve or reject a checkpoint."""
    decision: str = Field(..., description="'approved' or 'rejected'")
    approver: str | None = Field(None, description="Who made the decision")
    reason: str | None = Field(None, description="Reason for decision")


class CheckpointInfo(BaseModel):
    """Checkpoint details."""
    id: str
    checkpoint_type: str
    agent_name: str
    status: str
    message: str
    created_at: str
    approver: str | None = None
    metadata: dict[str, Any] | None = None


class CheckpointListResponse(BaseModel):
    """List of checkpoints for a run."""
    project_id: str
    run_id: str
    checkpoints: list[CheckpointInfo]


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
    from agents.checkpoint_agent import CheckpointAgent

    for cls in [
        PMAgent, FrontendAgent, BackendAgent, MobileAgent,
        SecurityAgent, QAAgent, CodeReviewAgent, DevOpsAgent,
        UIUXAgent, MonetisationAgent, CheckpointAgent
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
    _jobs[job_id] = {"status": "pending", "progress": {}, "results": None, "run_id": None}

    async def _run():
        from datetime import datetime, timezone
        from pipeline.repository import get_async_db
        async with get_async_db() as db:
            repo = AsyncPipelineRepository(db)
            # Create pipeline run record
            config_dict = {
                "name": f"job-{job_id}",
                "description": req.description,
                "agents": [{"agent": a, "enabled": True} for a in req.agents],
                "version": "1.0",
            }
            run_record = await repo.create_run(
                project_id=req.project_id,
                config=config_dict,
                job_id=job_id
            )
            # Store run_id in job for correlation
            _jobs[job_id]["run_id"] = run_record.id

            _jobs[job_id]["status"] = "running"
            try:
                orch = Orchestrator(req.project_id, repository=repo)
                tasks = make_full_app_pipeline(req.description, req.project_id)
                # Filter to requested agents
                tasks = [t for t in tasks if t.name in req.agents]
                run: PipelineRun = await orch.run(tasks, run_id=run_record.id)

                # Determine status
                if run.paused:
                    status = "paused"
                elif run.aborted:
                    status = "aborted"
                else:
                    status = "done"

                # Update pipeline run record
                await repo.update_run_status(
                    run_id=run_record.id,
                    status=status,
                    finished_at=datetime.now(timezone.utc) if not run.paused else None,
                    total_cost=run.total_cost,
                )

                _jobs[job_id].update({
                    "status": status,
                    "results": {k: v.to_dict() for k, v in run.results.items()},
                    "summary": run.summary(),
                    "run_id": run.run_id,
                })
            except Exception as e:
                logger.error(f"Pipeline run {job_id} failed: {e}", exc_info=True)
                _jobs[job_id].update({
                    "status": "failed",
                    "error": str(e)
                })
                # Mark run as failed
                await repo.update_run_status(
                    run_id=run_record.id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                )

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
        dag_result = orchestrator.build_from_config(config)
        tasks = dag_result.tasks
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
    _jobs[job_id] = {"status": "pending", "progress": {}, "results": None, "run_id": None}

    async def _run():
        from datetime import datetime, timezone
        from pipeline.repository import get_async_db
        async with get_async_db() as db:
            repo = AsyncPipelineRepository(db)
            # Create pipeline run record
            config_dict = req.config.dict()
            # Add feature description to config for record
            config_dict["feature"] = req.feature
            run_record = await repo.create_run(
                project_id=req.project_id,
                config=config_dict,
                job_id=job_id
            )
            _jobs[job_id]["run_id"] = run_record.id

            _jobs[job_id]["status"] = "running"
            try:
                orch = Orchestrator(req.project_id, repository=repo)

                # Convert API config to core config and build tasks
                from pipeline.config_loader import PipelineConfig
                config = PipelineConfig(**config_dict)
                dag = orch.build_from_config(config)
                tasks = dag.tasks

                # Substitute template variables
                for task in tasks:
                    if task.task:
                        task.task = task.task.format(
                            feature=req.feature,
                            project_id=req.project_id
                        )

                # Update dag with modified tasks
                dag.tasks = tasks

                # Run (pass run_id for correlation)
                run: PipelineRun = await orch.run(dag, run_id=run_record.id)

                # Determine status
                if run.paused:
                    status = "paused"
                elif run.aborted:
                    status = "aborted"
                else:
                    status = "done"

                # Update pipeline run record
                await repo.update_run_status(
                    run_id=run_record.id,
                    status=status,
                    finished_at=datetime.now(timezone.utc) if not run.paused else None,
                    total_cost=run.total_cost,
                )

                _jobs[job_id].update({
                    "status": status,
                    "results": {k: v.to_dict() for k, v in run.results.items()},
                    "summary": run.summary(),
                    "run_id": run.run_id,
                })
            except Exception as e:
                logger.error(f"Pipeline run {job_id} failed: {e}", exc_info=True)
                _jobs[job_id].update({
                    "status": "failed",
                    "error": str(e)
                })
                # Mark run as failed
                await repo.update_run_status(
                    run_id=run_record.id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                )

    background.add_task(_run)
    return PipelineRunResponse(
        success=True,
        run={"job_id": job_id, "status": "pending"},
        message="Pipeline started"
    )


@app.get("/api/pipelines/{run_id}/checkpoints", response_model=CheckpointListResponse)
async def get_run_checkpoints(run_id: str, project_id: str = "default", repo: AsyncPipelineRepository = Depends(get_repo)):
    """
    Get all checkpoints for a specific pipeline run.
    """
    try:
        # Get run to verify it exists and get project_id
        run = await repo.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        # Use actual project_id from run if different from query param
        actual_project_id = run.project_id

        checkpoints = await repo.get_checkpoints_for_run(run_id)
        checkpoint_infos = []
        for cp in checkpoints:
            metadata = cp.checkpoint_metadata if cp.checkpoint_metadata else {}
            checkpoint_infos.append(CheckpointInfo(
                id=cp.id,
                checkpoint_type=cp.checkpoint_type,
                agent_name=cp.agent_name,
                status=cp.status,
                message=cp.message or "",
                created_at=cp.created_at.isoformat() if cp.created_at else "",
                approver=cp.approver,
                metadata=metadata,
            ))
        return CheckpointListResponse(project_id=actual_project_id, run_id=run_id, checkpoints=checkpoint_infos)
    except Exception as e:
        logger.error(f"Failed to get checkpoints for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipelines/resume/{run_id}")
async def resume_pipeline(
    run_id: str,
    req: CheckpointDecisionRequest,
    background: BackgroundTasks,
    repo: AsyncPipelineRepository = Depends(get_repo)
):
    """
    Resume a paused pipeline by making a checkpoint decision (approve/reject).
    """
    # Get pipeline run to find project_id
    run = await repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"No paused run found with ID {run_id}")

    project_id = run.project_id
    orch = Orchestrator(project_id, repository=repo)
    try:
        result = await orch.resume(
            run_id=run_id,
            decision=req.decision,
            approver=req.approver,
            reason=req.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Determine status
    if run.paused:
        status = "paused"
    elif run.aborted:
        status = "aborted"
    else:
        status = "completed"

    # Update any associated job status
    for jid, jinfo in _jobs.items():
        if jinfo.get("run_id") == run_id:
            jinfo["status"] = status
            jinfo["results"] = {k: v.to_dict() for k, v in run.results.items()}
            jinfo["summary"] = run.summary()
            if status == "aborted":
                jinfo["error"] = run.abort_reason
            break

    return {
        "run_id": run.run_id,
        "status": status,
        "checkpoint_id": run.checkpoint_id,
        "checkpoint_type": run.checkpoint_type,
        "results": {k: v.to_dict() for k, v in run.results.items()},
        "summary": run.summary(),
    }


@app.get("/api/projects/{project_id}/pipelines/history", response_model=PipelineHistoryResponse)
async def get_pipeline_history(project_id: str, limit: int = 20, repo: AsyncPipelineRepository = Depends(get_repo)):
    """
    Get recent pipeline runs for a project.

    Returns history of pipeline executions with cost, duration, and status.
    """
    try:
        # Get pipeline runs from database
        runs = await repo.list_runs(project_id=project_id, limit=limit)

        history_items = []
        total_cost_usd = 0.0

        for run in runs:
            # Extract config name and agent count from stored config
            config = run.config or {}
            config_name = config.get("name", "Unnamed Pipeline")
            agent_count = len(config.get("agents", []))

            # Calculate duration from run timing
            duration_seconds = 0.0
            if run.started_at and run.finished_at:
                duration_seconds = (run.finished_at - run.started_at).total_seconds()

            # Get cost from run record
            cost_usd = run.total_cost or 0.0
            total_cost_usd += cost_usd

            history_items.append(PipelineHistoryItem(
                run_id=run.id,
                timestamp=run.created_at.isoformat() if run.created_at else "",
                config_name=config_name,
                status=run.status,
                cost_usd=cost_usd,
                duration_seconds=duration_seconds,
                agent_count=agent_count,
            ))

        return PipelineHistoryResponse(
            project_id=project_id,
            runs=history_items,
            total_cost_usd=total_cost_usd,
        )
    except Exception as e:
        logger.error(f"Failed to get pipeline history for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
