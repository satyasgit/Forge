"""
Sprint Manager for AI Coworkers (Phase 3).
Facilitates Agile ceremonies (planning, standups) and tracks story progress.
"""
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agile.models import SprintDB, UserStoryDB, StandupReportDB, AgentPersonaDB
from config.database import get_async_db

logger = logging.getLogger(__name__)

class SprintManager:
    """Manages the lifecycle of sprints and user stories for AI agents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Sprint Operations ─────────────────────────────────────────────────────

    async def create_sprint(self, project_id: str, name: str, goal: str, duration_days: int = 14) -> SprintDB:
        """Create a new sprint."""
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=duration_days)
        
        sprint = SprintDB(
            project_id=project_id,
            name=name,
            goal=goal,
            start_date=start_date,
            end_date=end_date,
            status="planning"
        )
        self.db.add(sprint)
        await self.db.flush()
        logger.info(f"Created sprint {name} for project {project_id}")
        return sprint

    async def start_sprint(self, sprint_id: str):
        """Transition sprint to active state."""
        await self.db.execute(
            update(SprintDB).where(SprintDB.id == sprint_id).values(status="active")
        )
        logger.info(f"Sprint {sprint_id} is now ACTIVE")

    async def get_active_sprint(self, project_id: str) -> Optional[SprintDB]:
        """Get the currently active sprint for a project."""
        result = await self.db.execute(
            select(SprintDB).where(
                SprintDB.project_id == project_id,
                SprintDB.status == "active"
            )
        )
        return result.scalars().first()

    # ── User Story Operations ──────────────────────────────────────────────────

    async def create_story(self, sprint_id: str, title: str, description: str, story_points: int, assigned_to: str = None) -> UserStoryDB:
        """Add a user story to a sprint."""
        story = UserStoryDB(
            sprint_id=sprint_id,
            title=title,
            description=description,
            story_points=story_points,
            assigned_to=assigned_to
        )
        self.db.add(story)
        await self.db.flush()
        return story

    async def update_story_status(self, story_id: str, status: str):
        """Update the status of a user story."""
        values = {"status": status}
        if status == "done":
            values["completed_at"] = datetime.utcnow()
        
        await self.db.execute(
            update(UserStoryDB).where(UserStoryDB.id == story_id).values(**values)
        )

    async def get_sprint_backlog(self, sprint_id: str) -> List[UserStoryDB]:
        """Retrieve all stories for a sprint."""
        result = await self.db.execute(
            select(UserStoryDB).where(UserStoryDB.sprint_id == sprint_id)
        )
        return result.scalars().all()

    # ── Standup Operations ────────────────────────────────────────────────────

    async def submit_standup(self, sprint_id: str, agent_name: str, 
                             completed_yesterday: List[str], 
                             working_on_today: List[str], 
                             blockers: List[str], 
                             mood: str = "on_track") -> StandupReportDB:
        """Submit a daily standup report for an agent."""
        report = StandupReportDB(
            sprint_id=sprint_id,
            agent_name=agent_name,
            report_date=datetime.utcnow().date(),
            completed_yesterday=completed_yesterday,
            working_on_today=working_on_today,
            blockers=blockers,
            mood=mood
        )
        self.db.add(report)
        await self.db.flush()
        return report

    async def get_daily_standup_summary(self, sprint_id: str, report_date: date = None) -> List[StandupReportDB]:
        """Get all standup reports for a specific date."""
        if report_date is None:
            report_date = datetime.utcnow().date()
            
        result = await self.db.execute(
            select(StandupReportDB).where(
                StandupReportDB.sprint_id == sprint_id,
                StandupReportDB.report_date == report_date
            )
        )
        return result.scalars().all()

    # ── Agent Persona Operations ──────────────────────────────────────────────

    async def get_or_create_persona(self, name: str, title: str, style: str = None) -> AgentPersonaDB:
        """Retrieve or create an agent's persistent persona."""
        result = await self.db.execute(select(AgentPersonaDB).where(AgentPersonaDB.name == name))
        persona = result.scalars().first()
        
        if not persona:
            persona = AgentPersonaDB(
                name=name,
                title=title,
                style=style
            )
            self.db.add(persona)
            await self.db.flush()
        return persona
