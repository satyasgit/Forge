"""
Pipeline Orchestrator.
Resolves agent dependencies, runs independent agents in parallel,
tracks costs, and notifies on completion.

v2: Configurable pipelines via YAML templates.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anthropic

from agents.base import AgentResult
from config.settings import settings
from memory.store import ProjectMemory
from pipeline.config_loader import (
    PipelineConfig,
    build_pipeline_from_config as build_tasks_from_config,
)

if TYPE_CHECKING:
    from agents.base import BaseAgent

logger = logging.getLogger(__name__)

aclient = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


@dataclass
class PipelineTask:
    agent: "BaseAgent"
    task: str
    depends_on: list[str] = field(default_factory=list)
    result: AgentResult | None = None

    @property
    def name(self) -> str:
        return self.agent.name


@dataclass
class PipelineRun:
    project_id: str
    tasks: list[PipelineTask]
    results: dict[str, AgentResult] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    aborted: bool = False
    abort_reason: str = ""

    @property
    def duration(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.results.values())

    @property
    def total_tokens(self) -> dict:
        return {
            "input": sum(r.input_tokens for r in self.results.values()),
            "output": sum(r.output_tokens for r in self.results.values()),
        }

    def summary(self) -> str:
        lines = [
            f"Pipeline: {self.project_id}",
            f"Duration: {self.duration:.1f}s",
            f"Cost: ${self.total_cost:.4f}",
            f"Tokens: {self.total_tokens}",
            "",
        ]
        for name, result in self.results.items():
            status = "ERROR" if result.errors else "OK"
            lines.append(f"  [{status}] {name}: {result.duration_seconds:.1f}s, ${result.cost_usd:.4f}")
        return "\n".join(lines)


class Orchestrator:
    """
    Run a list of PipelineTasks respecting dependencies.

    Tasks with no pending dependencies execute in parallel.
    Each task's output is injected as context for downstream tasks.

    v2: Can build pipeline from PipelineConfig (YAML templates).
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.memory = ProjectMemory(project_id)

    def build_from_config(self, config: PipelineConfig) -> list[PipelineTask]:
        """
        Build pipeline tasks from a PipelineConfig.

        This is the main entry point for configurable pipelines.
        Uses config_loader to resolve dependencies and create tasks.

        Args:
            config: Validated pipeline configuration

        Returns:
            List of PipelineTask objects in topological order
        """
        return build_tasks_from_config(config)

    async def run(self, tasks: list[PipelineTask]) -> PipelineRun:
        run = PipelineRun(project_id=self.project_id, tasks=tasks)
        pending = {t.name: t for t in tasks}
        completed: dict[str, AgentResult] = {}

        logger.info(f"[orchestrator] Starting pipeline with {len(tasks)} tasks")

        while pending:
            # Check cost cap
            total_cost = sum(r.cost_usd for r in completed.values())
            if total_cost > settings.max_pipeline_cost_usd:
                run.aborted = True
                run.abort_reason = f"Cost cap ${settings.max_pipeline_cost_usd} reached at ${total_cost:.4f}"
                logger.warning(f"[orchestrator] {run.abort_reason}")
                break

            # Find tasks ready to run
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.depends_on)
            ]
            if not ready:
                names = list(pending.keys())
                raise RuntimeError(f"Dependency deadlock: {names}")

            # Build context for each ready task
            async def execute(task: PipelineTask) -> tuple[str, AgentResult]:
                ctx_parts = []
                for dep in task.depends_on:
                    dep_result = completed[dep]
                    ctx_parts.append(f"## Output from {dep} agent:\n{dep_result.output}")
                context = "\n\n".join(ctx_parts)

                logger.info(f"[orchestrator] Running: {task.name}")
                # Run synchronous agent in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda t=task, c=context: t.agent.run(t.task, context=c)
                )
                return task.name, result

            # Execute all ready tasks in parallel
            pairs = await asyncio.gather(*[execute(t) for t in ready])

            for name, result in pairs:
                completed[name] = result
                run.results[name] = result
                del pending[name]
                logger.info(
                    f"[orchestrator] {name} done — "
                    f"${result.cost_usd:.4f}, {result.duration_seconds:.1f}s"
                )
                if result.errors:
                    logger.warning(f"[orchestrator] {name} had errors: {result.errors}")

        run.finished_at = time.time()
        logger.info(f"[orchestrator] Pipeline complete\n{run.summary()}")
        return run


# ── Pre-built pipelines ────────────────────────────────────────────────────────

def make_full_app_pipeline(feature: str, project_id: str) -> list[PipelineTask]:
    """Standard pipeline for building any mobile/web feature end-to-end."""
    from agents.agent_config import create_agent

    return [
        PipelineTask(
            agent=create_agent("pm", project_id),
            task=f"Create a detailed PRD with user stories and acceptance criteria for: {feature}",
            depends_on=[],
        ),
        PipelineTask(
            agent=create_agent("ui_ux", project_id),
            task=f"Design the UI/UX for: {feature}",
            depends_on=["pm"],
        ),
        PipelineTask(
            agent=create_agent("frontend", project_id),
            task=f"Build React web components for: {feature}",
            depends_on=["ui_ux"],
        ),
        PipelineTask(
            agent=create_agent("mobile", project_id),
            task=f"Build React Native mobile screens for: {feature}",
            depends_on=["ui_ux"],
        ),
        PipelineTask(
            agent=create_agent("backend", project_id),
            task=f"Build FastAPI backend with database models for: {feature}",
            depends_on=["pm"],
        ),
        PipelineTask(
            agent=create_agent("security", project_id),
            task=f"Security audit of the backend API for: {feature}",
            depends_on=["backend"],
        ),
        PipelineTask(
            agent=create_agent("code_review", project_id),
            task="Code review of frontend and backend code",
            depends_on=["frontend", "backend"],
        ),
        PipelineTask(
            agent=create_agent("qa", project_id),
            task=f"Write comprehensive test suite for: {feature}",
            depends_on=["frontend", "backend", "code_review"],
        ),
        PipelineTask(
            agent=create_agent("devops", project_id),
            task=f"Create Docker + CI/CD pipeline for: {feature}",
            depends_on=["backend", "security"],
        ),
        PipelineTask(
            agent=create_agent("monetisation", project_id),
            task=f"Design monetisation strategy and Stripe integration for: {feature}",
            depends_on=["backend", "pm"],
        ),
    ]


async def run_full_pipeline(
    feature: str,
    project_id: str,
    config: PipelineConfig | None = None
) -> PipelineRun:
    """
    Run the full pipeline for a feature.

    Args:
        feature: Feature description (substituted into task prompts)
        project_id: Project identifier for memory
        config: Optional PipelineConfig. If None, uses default full pipeline.

    Returns:
        PipelineRun with results
    """
    orch = Orchestrator(project_id)

    if config is not None:
        # Build from config (YAML template or custom)
        tasks = orch.build_from_config(config)
        # Substitute {feature} in task prompts
        for task in tasks:
            if task.task:
                task.task = task.task.format(feature=feature, project_id=project_id)
    else:
        # Backward compatible: default full pipeline
        tasks = make_full_app_pipeline(feature, project_id)

    return await orch.run(tasks)


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_full_pipeline(
        feature="User subscription management with Stripe",
        project_id="my-saas-app",
    ))
    print(result.summary())
