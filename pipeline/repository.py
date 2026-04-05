"""
Repository layer for pipeline persistence (PostgreSQL).

Provides CRUD operations for:
- Pipeline runs
- Agent results
- Checkpoints
- Jobs (legacy compatibility)

This is the abstraction layer between the orchestrator/API and the database.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db, get_async_db
from .models_database import (
    PipelineRunDB,
    AgentResultDB,
    CheckpointDB,
    JobDB,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SYNC REPOSITORY (for migrations, scripts, current FastAPI sync usage)
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineRepository:
    """
    Synchronous repository for pipeline data.

    Use in: migrations, CLI scripts, sync FastAPI routes (for now).
    Async version below for async routes.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── Pipeline Runs ──────────────────────────────────────────────────────────

    def create_run(self, project_id: str, config: dict[str, Any], job_id: str | None = None) -> PipelineRunDB:
        """Create a new pipeline run record."""
        run = PipelineRunDB(
            project_id=project_id,
            config=config,
            status="pending",
            job_id=job_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info("Created pipeline run: %s (project=%s)", run.id, project_id)
        return run

    def get_run(self, run_id: str) -> PipelineRunDB | None:
        """Get pipeline run by ID."""
        return self.db.get(PipelineRunDB, run_id)

    def get_run_by_job_id(self, job_id: str) -> PipelineRunDB | None:
        """Get pipeline run by job_id."""
        stmt = select(PipelineRunDB).where(PipelineRunDB.job_id == job_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_run_status(self, run_id: str, status: str, **updates) -> PipelineRunDB | None:
        """Update pipeline run status and optional fields."""
        run = self.db.get(PipelineRunDB, run_id)
        if not run:
            return None

        run.status = status
        if "started_at" in updates:
            run.started_at = updates["started_at"]
        if "finished_at" in updates:
            run.finished_at = updates["finished_at"]
        if "total_cost" in updates:
            run.total_cost = updates["total_cost"]
        if "checkpoint_id" in updates:
            run.checkpoint_id = updates["checkpoint_id"]
        if "run_id_orchestrator" in updates:  # orchestrator's run_id
            run.run_id = updates["run_id_orchestrator"]

        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(self, project_id: str, limit: int = 20, offset: int = 0) -> list[PipelineRunDB]:
        """List pipeline runs for a project, newest first."""
        stmt = (
            select(PipelineRunDB)
            .where(PipelineRunDB.project_id == project_id)
            .order_by(desc(PipelineRunDB.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def delete_run(self, run_id: str) -> bool:
        """Delete a pipeline run (cascades to agent results, checkpoints)."""
        run = self.db.get(PipelineRunDB, run_id)
        if not run:
            return False
        self.db.delete(run)
        self.db.commit()
        return True

    # ── Agent Results ───────────────────────────────────────────────────────────

    def save_agent_result(self, run_id: str, agent_name: str, result: dict[str, Any]) -> AgentResultDB:
        """Save agent execution result."""
        agent_result = AgentResultDB(
            pipeline_run_id=run_id,
            agent_name=agent_name,
            output=result.get("output", ""),
            tool_calls=result.get("tool_calls"),
            input_tokens=result.get("tokens", {}).get("input", 0),
            output_tokens=result.get("tokens", {}).get("output", 0),
            cost_usd=result.get("cost_usd", 0.0),
            duration_seconds=result.get("duration_seconds", 0.0),
            errors=result.get("errors", []),
            model_used=result.get("model", ""),
            retries=result.get("retries", 0),
            state=result.get("state", "done"),
            created_at=datetime.utcnow(),
        )
        self.db.add(agent_result)
        self.db.commit()
        self.db.refresh(agent_result)
        return agent_result

    def get_agent_results(self, run_id: str) -> list[AgentResultDB]:
        """Get all agent results for a pipeline run."""
        stmt = select(AgentResultDB).where(AgentResultDB.pipeline_run_id == run_id).order_by(AgentResultDB.created_at)
        return list(self.db.execute(stmt).scalars().all())

    # ── Checkpoints ─────────────────────────────────────────────────────────────

    def create_checkpoint(
        self,
        pipeline_run_id: str,
        agent_name: str,
        checkpoint_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointDB:
        """Create a checkpoint record."""
        checkpoint = CheckpointDB(
            pipeline_run_id=pipeline_run_id,
            agent_name=agent_name,
            status="pending",
            checkpoint_type=checkpoint_type,
            message=message,
            metadata=metadata,
            created_at=datetime.utcnow(),
        )
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        logger.info("Created checkpoint: %s (run=%s, type=%s)", checkpoint.id, pipeline_run_id, checkpoint_type)
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointDB | None:
        """Get checkpoint by ID."""
        return self.db.get(CheckpointDB, checkpoint_id)

    def get_checkpoints_for_run(self, run_id: str) -> list[CheckpointDB]:
        """Get all checkpoints for a pipeline run."""
        stmt = select(CheckpointDB).where(CheckpointDB.pipeline_run_id == run_id).order_by(CheckpointDB.created_at)
        return list(self.db.execute(stmt).scalars().all())

    def get_pending_checkpoints(self, run_id: str | None = None) -> list[CheckpointDB]:
        """Get all pending checkpoints, optionally filtered by run_id."""
        stmt = select(CheckpointDB).where(CheckpointDB.status == "pending").order_by(CheckpointDB.created_at)
        if run_id:
            stmt = stmt.where(CheckpointDB.pipeline_run_id == run_id)
        return list(self.db.execute(stmt).scalars().all())

    def update_checkpoint_decision(
        self,
        checkpoint_id: str,
        status: str,
        approver: str | None = None,
    ) -> CheckpointDB | None:
        """Update checkpoint with decision (approved/rejected)."""
        checkpoint = self.db.get(CheckpointDB, checkpoint_id)
        if not checkpoint or checkpoint.status != "pending":
            return None

        checkpoint.status = status
        checkpoint.approver = approver
        checkpoint.decision_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    # ── Jobs (legacy compatibility) ────────────────────────────────────────────

    def create_job(self, job_id: str, run_id: str | None = None) -> JobDB:
        """Create job record (for backward compatibility with in-memory _jobs)."""
        job = JobDB(
            id=job_id,
            run_id=run_id,
            status="pending",
            created_at=datetime.utcnow(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def update_job(self, job_id: str, **updates) -> JobDB | None:
        """Update job status and results."""
        job = self.db.get(JobDB, job_id)
        if not job:
            return None

        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> JobDB | None:
        """Get job by ID."""
        return self.db.get(JobDB, job_id)


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC REPOSITORY (for FastAPI async routes)
# ═══════════════════════════════════════════════════════════════════════════════

class AsyncPipelineRepository:
    """
    Asynchronous repository for use in async FastAPI routes.

    Methods are async and use AsyncSession.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(self, project_id: str, config: dict[str, Any], job_id: str | None = None) -> PipelineRunDB:
        """Create a new pipeline run record."""
        run = PipelineRunDB(
            project_id=project_id,
            config=config,
            status="pending",
            job_id=job_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        logger.info("Created pipeline run: %s (project=%s)", run.id, project_id)
        return run

    async def get_run(self, run_id: str) -> PipelineRunDB | None:
        """Get pipeline run by ID."""
        return await self.db.get(PipelineRunDB, run_id)

    async def update_run_status(self, run_id: str, status: str, **updates) -> PipelineRunDB | None:
        """Update pipeline run status and optional fields."""
        run = await self.db.get(PipelineRunDB, run_id)
        if not run:
            return None

        run.status = status
        if "started_at" in updates:
            run.started_at = updates["started_at"]
        if "finished_at" in updates:
            run.finished_at = updates["finished_at"]
        if "total_cost" in updates:
            run.total_cost = updates["total_cost"]
        if "checkpoint_id" in updates:
            run.checkpoint_id = updates["checkpoint_id"]
        if "run_id_orchestrator" in updates:
            run.run_id = updates["run_id_orchestrator"]

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(self, project_id: str, limit: int = 20, offset: int = 0) -> list[PipelineRunDB]:
        """List pipeline runs for a project, newest first."""
        from sqlalchemy import select, desc
        stmt = (
            select(PipelineRunDB)
            .where(PipelineRunDB.project_id == project_id)
            .order_by(desc(PipelineRunDB.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_run_by_job_id(self, job_id: str) -> PipelineRunDB | None:
        """Get pipeline run by job_id."""
        from sqlalchemy import select
        stmt = select(PipelineRunDB).where(PipelineRunDB.job_id == job_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_agent_result(self, run_id: str, agent_name: str, result: dict[str, Any]) -> AgentResultDB:
        """Save agent execution result."""
        agent_result = AgentResultDB(
            pipeline_run_id=run_id,
            agent_name=agent_name,
            output=result.get("output", ""),
            tool_calls=result.get("tool_calls"),
            input_tokens=result.get("tokens", {}).get("input", 0),
            output_tokens=result.get("tokens", {}).get("output", 0),
            cost_usd=result.get("cost_usd", 0.0),
            duration_seconds=result.get("duration_seconds", 0.0),
            errors=result.get("errors", []),
            model_used=result.get("model", ""),
            retries=result.get("retries", 0),
            state=result.get("state", "done"),
            created_at=datetime.utcnow(),
        )
        self.db.add(agent_result)
        await self.db.commit()
        await self.db.refresh(agent_result)
        return agent_result

    async def get_agent_results(self, run_id: str) -> list[AgentResultDB]:
        """Get all agent results for a pipeline run."""
        from sqlalchemy import select
        stmt = select(AgentResultDB).where(AgentResultDB.pipeline_run_id == run_id).order_by(AgentResultDB.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_checkpoint(
        self,
        pipeline_run_id: str,
        agent_name: str,
        checkpoint_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointDB:
        """Create a checkpoint record."""
        checkpoint = CheckpointDB(
            pipeline_run_id=pipeline_run_id,
            agent_name=agent_name,
            status="pending",
            checkpoint_type=checkpoint_type,
            message=message,
            metadata=metadata,
            created_at=datetime.utcnow(),
        )
        self.db.add(checkpoint)
        await self.db.commit()
        await self.db.refresh(checkpoint)
        logger.info("Created checkpoint: %s (run=%s, type=%s)", checkpoint.id, pipeline_run_id, checkpoint_type)
        return checkpoint

    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointDB | None:
        """Get checkpoint by ID."""
        return await self.db.get(CheckpointDB, checkpoint_id)

    async def get_checkpoints_for_run(self, run_id: str) -> list[CheckpointDB]:
        """Get all checkpoints for a pipeline run."""
        from sqlalchemy import select
        stmt = select(CheckpointDB).where(CheckpointDB.pipeline_run_id == run_id).order_by(CheckpointDB.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_checkpoints(self, run_id: str | None = None) -> list[CheckpointDB]:
        """Get all pending checkpoints, optionally filtered by run_id."""
        from sqlalchemy import select
        stmt = select(CheckpointDB).where(CheckpointDB.status == "pending").order_by(CheckpointDB.created_at)
        if run_id:
            stmt = stmt.where(CheckpointDB.pipeline_run_id == run_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_checkpoint_decision(
        self,
        checkpoint_id: str,
        status: str,
        approver: str | None = None,
    ) -> CheckpointDB | None:
        """Update checkpoint with decision (approved/rejected)."""
        checkpoint = await self.db.get(CheckpointDB, checkpoint_id)
        if not checkpoint or checkpoint.status != "pending":
            return None

        checkpoint.status = status
        checkpoint.approver = approver
        checkpoint.decision_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(checkpoint)
        return checkpoint


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_repository() -> PipelineRepository:
    """Get sync repository (for use in scripts, migrations)."""
    db = next(get_db())
    return PipelineRepository(db)


async def get_async_repository() -> AsyncPipelineRepository:
    """Get async repository (for FastAPI dependency injection)."""
    async with get_async_db() as db:
        yield AsyncPipelineRepository(db)


# Alias for backward compatibility
get_async_repo = get_async_repository
