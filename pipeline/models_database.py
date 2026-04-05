"""
Database models for pipeline persistence (Phase 4 - PostgreSQL).

These models map to the tables created in the repository schema.
Separate from agent/memory models to keep concerns separate.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, String, Boolean, DateTime, Float, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from config.database import Base


def generate_uuid():
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())


# ── Pipeline Run ──────────────────────────────────────────────────────────────

class PipelineRunDB(Base):
    """Pipeline execution run record."""
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # Full PipelineConfig

    # Execution status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="pending, running, paused, completed, aborted, failed"
    )
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # Orchestrator run_id

    # Job tracking (legacy)
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Results
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=False), nullable=True)  # FK to checkpoints

    # Relationships
    agent_results: Mapped[list[AgentResultDB]] = relationship("AgentResultDB", back_populates="pipeline_run", cascade="all, delete-orphan")
    checkpoints: Mapped[list[CheckpointDB]] = relationship("CheckpointDB", back_populates="pipeline_run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PipelineRunDB(id={self.id}, status={self.status}, project={self.project_id})>"


# ── Agent Result ──────────────────────────────────────────────────────────────

class AgentResultDB(Base):
    """Individual agent execution result within a pipeline run."""
    __tablename__ = "agent_results"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    pipeline_run_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    # Token usage
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cost
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Timing
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Errors and state
    errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="done", nullable=False)

    # Relationships
    pipeline_run: Mapped[PipelineRunDB] = relationship("PipelineRunDB", back_populates="agent_results")

    def __repr__(self) -> str:
        return f"<AgentResultDB(agent={self.agent_name}, run_id={self.pipeline_run_id}, cost=${self.cost_usd:.4f})>"


# ── Checkpoint ────────────────────────────────────────────────────────────────

class CheckpointDB(Base):
    """Checkpoint record for pause/resume functionality."""
    __tablename__ = "pipeline_checkpoints"  # Distinct from memory.store checkpoints

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    pipeline_run_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="pending, approved, rejected, timeout"
    )
    checkpoint_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Decision tracking
    approver: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Checkpoint metadata
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    pipeline_run: Mapped[PipelineRunDB] = relationship("PipelineRunDB", back_populates="checkpoints")

    def __repr__(self) -> str:
        return f"<CheckpointDB(id={self.id}, type={self.checkpoint_type}, status={self.status})>"


# ── Job Status (for backward compatibility with current job system) ──────────

class JobDB(Base):
    """Job status tracking (will eventually replace in-memory _jobs dict)."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    run_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=False), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="pending, running, paused, completed, aborted, failed"
    )
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    pipeline_run: Mapped[PipelineRunDB] = relationship("PipelineRunDB", backref="jobs")

    def __repr__(self) -> str:
        return f"<JobDB(id={self.id}, status={self.status})>"
