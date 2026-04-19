"""
Database models for AI Coworkers (Phase 3).
Includes models for Sprints, User Stories, Standups, and persistent Agent Identity.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Any, List, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Float, Text, JSON, ForeignKey, Integer, Date
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from config.database import Base

def generate_uuid():
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())

# ── Agent Persona ─────────────────────────────────────────────────────────────

class AgentPersonaDB(Base):
    """Persistent identity and memory profile for an AI agent."""
    __tablename__ = "agent_personas"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    seniority: Mapped[str] = mapped_column(String(50), default="senior")
    style: Mapped[str | None] = mapped_column(Text, nullable=True)
    specializations: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    
    # Persistent memory across sprints
    decision_log: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    collaboration_history: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AgentPersonaDB(name={self.name}, title={self.title})>"

# ── Sprint ────────────────────────────────────────────────────────────────────

class SprintDB(Base):
    """Agile sprint record."""
    __tablename__ = "sprints"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default="planning", index=True) # planning | active | review | closed
    
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity_points: Mapped[int] = mapped_column(Integer, default=0)
    velocity_actual: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    stories: Mapped[List[UserStoryDB]] = relationship("UserStoryDB", back_populates="sprint", cascade="all, delete-orphan")
    standups: Mapped[List[StandupReportDB]] = relationship("StandupReportDB", back_populates="sprint", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<SprintDB(name={self.name}, status={self.status})>"

# ── User Story ────────────────────────────────────────────────────────────────

class UserStoryDB(Base):
    """Individual task/story within a sprint."""
    __tablename__ = "user_stories"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    sprint_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=False), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=True, index=True)
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    story_points: Mapped[int] = mapped_column(Integer, default=0)
    
    assigned_to: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="todo", index=True) # todo | in_progress | in_review | done | blocked
    
    depends_on: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    sprint: Mapped[SprintDB] = relationship("SprintDB", back_populates="stories")

    def __repr__(self) -> str:
        return f"<UserStoryDB(title={self.title[:30]}, status={self.status})>"

# ── Standup Report ─────────────────────────────────────────────────────────────

class StandupReportDB(Base):
    """Daily standup update from an agent."""
    __tablename__ = "standup_reports"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    sprint_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    report_date: Mapped[date] = mapped_column(Date, default=datetime.utcnow().date(), index=True)
    
    completed_yesterday: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    working_on_today: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    blockers: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list)
    mood: Mapped[str | None] = mapped_column(String(50), nullable=True) # on_track | at_risk | blocked
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    sprint: Mapped[SprintDB] = relationship("SprintDB", back_populates="standups")

    def __repr__(self) -> str:
        return f"<StandupReportDB(agent={self.agent_name}, date={self.report_date})>"

# ── Agent Message (Persistent Bus Log) ────────────────────────────────────────

class AgentMessageDB(Base):
    """Persistent log of all agent communication bus messages."""
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    sender: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    recipient: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    channel: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), index=True) # broadcast | ask | answer | blocker | decision
    
    references: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=list) # IDs of referenced messages
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=False), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AgentMessageDB(from={self.sender}, type={self.message_type})>"
