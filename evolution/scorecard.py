"""
Performance Scorecard: Measures agent evolution over time.

Without measurement, self-evolution is decorative. This module tracks
per-agent, per-sprint metrics so you can answer: "Is the system
actually making agents better?"
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class SprintMetrics:
    """Metrics for a single agent in a single sprint."""
    agent_name: str
    sprint_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    first_pass_count: int = 0          # Tasks that passed review on first try
    total_revisions: int = 0
    total_cost_usd: float = 0.0
    self_corrections: int = 0          # Issues caught by self-reflection
    lessons_stored: int = 0

    @property
    def first_pass_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return round((self.first_pass_count / total) * 100, 1)

    @property
    def avg_revisions(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return round(self.total_revisions / total, 2)


@dataclass
class AgentScorecard:
    """Aggregated performance scorecard for an agent across sprints."""
    agent_name: str
    
    # Quality metrics
    first_pass_review_rate: float = 0.0
    avg_revision_rounds: float = 0.0
    
    # Efficiency metrics
    avg_cost_per_task: float = 0.0
    self_correction_rate: float = 0.0
    
    # Growth metrics
    lessons_learned: int = 0
    
    # Trend (sprint-over-sprint)
    quality_trend: str = "stable"  # "improving" | "stable" | "declining"
    
    # History
    sprint_history: list[dict] = field(default_factory=list)


class PerformanceTracker:
    """
    Records and queries agent performance metrics.
    Uses the agent_performance table in Supabase/PostgreSQL.
    """
    
    async def record_task_outcome(
        self,
        agent_name: str,
        sprint_id: str,
        review_passed: bool,
        revision_count: int = 0,
        cost_usd: float = 0.0,
        self_corrections: int = 0,
    ):
        """Record a single task outcome for an agent in a sprint."""
        try:
            async with AsyncSessionLocal() as session:
                # Upsert: increment counters for this agent+sprint
                sql = text("""
                    INSERT INTO agent_performance (agent_name, sprint_id, tasks_completed, tasks_failed,
                        first_pass_rate, avg_revisions, total_cost_usd, self_corrections)
                    VALUES (:agent_name, :sprint_id, 
                        CASE WHEN :review_passed THEN 1 ELSE 0 END,
                        CASE WHEN :review_passed THEN 0 ELSE 1 END,
                        CASE WHEN :review_passed AND :revision_count = 0 THEN 100.0 ELSE 0.0 END,
                        :revision_count,
                        :cost_usd,
                        :self_corrections)
                    ON CONFLICT (agent_name, sprint_id) DO UPDATE SET
                        tasks_completed = agent_performance.tasks_completed + 
                            CASE WHEN :review_passed THEN 1 ELSE 0 END,
                        tasks_failed = agent_performance.tasks_failed + 
                            CASE WHEN :review_passed THEN 0 ELSE 1 END,
                        total_cost_usd = agent_performance.total_cost_usd + :cost_usd,
                        self_corrections = agent_performance.self_corrections + :self_corrections,
                        avg_revisions = (
                            (agent_performance.avg_revisions * (agent_performance.tasks_completed + agent_performance.tasks_failed) 
                             + :revision_count) 
                            / (agent_performance.tasks_completed + agent_performance.tasks_failed + 1)
                        ),
                        first_pass_rate = (
                            (agent_performance.first_pass_rate * (agent_performance.tasks_completed + agent_performance.tasks_failed)
                             + CASE WHEN :review_passed AND :revision_count = 0 THEN 100.0 ELSE 0.0 END)
                            / (agent_performance.tasks_completed + agent_performance.tasks_failed + 1)
                        )
                """)
                await session.execute(sql, {
                    "agent_name": agent_name,
                    "sprint_id": sprint_id,
                    "review_passed": review_passed,
                    "revision_count": revision_count,
                    "cost_usd": cost_usd,
                    "self_corrections": self_corrections,
                })
                await session.commit()
                logger.info(
                    "[%s] Performance recorded: sprint=%s, passed=%s, revisions=%d",
                    agent_name, sprint_id, review_passed, revision_count
                )
        except Exception as e:
            logger.error("[%s] Failed to record performance: %s", agent_name, e)

    async def get_scorecard(self, agent_name: str, last_n_sprints: int = 5) -> AgentScorecard:
        """Build an aggregated scorecard for an agent from recent sprint data."""
        try:
            async with AsyncSessionLocal() as session:
                sql = text("""
                    SELECT sprint_id, tasks_completed, tasks_failed, 
                           first_pass_rate, avg_revisions, total_cost_usd, self_corrections
                    FROM agent_performance
                    WHERE agent_name = :agent_name
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                result = await session.execute(sql, {
                    "agent_name": agent_name,
                    "limit": last_n_sprints,
                })
                rows = result.fetchall()

            if not rows:
                return AgentScorecard(agent_name=agent_name)

            # Aggregate
            total_tasks = sum(r.tasks_completed + r.tasks_failed for r in rows)
            total_completed = sum(r.tasks_completed for r in rows)

            scorecard = AgentScorecard(
                agent_name=agent_name,
                first_pass_review_rate=round(sum(r.first_pass_rate for r in rows) / len(rows), 1),
                avg_revision_rounds=round(sum(r.avg_revisions for r in rows) / len(rows), 2),
                avg_cost_per_task=round(sum(r.total_cost_usd for r in rows) / max(total_tasks, 1), 4),
                self_correction_rate=round(sum(r.self_corrections for r in rows) / max(total_tasks, 1) * 100, 1),
                lessons_learned=0,  # Could query agent_memory_vectors count
                sprint_history=[
                    {
                        "sprint_id": r.sprint_id,
                        "first_pass_rate": r.first_pass_rate,
                        "avg_revisions": r.avg_revisions,
                        "tasks": r.tasks_completed + r.tasks_failed,
                    }
                    for r in rows
                ],
            )

            # Determine trend from the last 3 sprints
            if len(rows) >= 3:
                recent_rates = [r.first_pass_rate for r in rows[:3]]
                if recent_rates[0] > recent_rates[-1] + 5:
                    scorecard.quality_trend = "improving"
                elif recent_rates[0] < recent_rates[-1] - 5:
                    scorecard.quality_trend = "declining"
                else:
                    scorecard.quality_trend = "stable"

            return scorecard

        except Exception as e:
            logger.error("[%s] Failed to build scorecard: %s", agent_name, e)
            return AgentScorecard(agent_name=agent_name)
