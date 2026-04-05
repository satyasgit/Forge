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
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anthropic

from agents.base import AgentResult
from config.settings import settings
from memory.store import ProjectMemory
from pipeline.repository import get_async_repository, AsyncPipelineRepository
from pipeline.config_loader import (
    PipelineConfig,
    PipelineDAG,
    EdgeConfig,
    build_pipeline_from_config as build_dag_from_config,
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
    paused: bool = False
    checkpoint_id: str | None = None
    checkpoint_type: str | None = None
    run_id: str | None = None  # Unique identifier for this run

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
        ]
        if self.paused:
            lines.append(f"Status: PAUSED at checkpoint ({self.checkpoint_type})")
        elif self.aborted:
            lines.append(f"Status: ABORTED - {self.abort_reason}")
        else:
            lines.append("Status: COMPLETED")
        lines.append("")
        for name, result in self.results.items():
            status = "ERROR" if result.errors else "OK"
            if result.errors:
                lines.append(f"  [{status}] {name}: {result.duration_seconds:.1f}s, ${result.cost_usd:.4f}")
                for err in result.errors:
                    lines.append(f"    - {err}")
            else:
                lines.append(f"  [{status}] {name}: {result.duration_seconds:.1f}s, ${result.cost_usd:.4f}")
        return "\n".join(lines)


class Orchestrator:
    """
    Run a list of PipelineTasks respecting dependencies.

    Tasks with no pending dependencies execute in parallel.
    Each task's output is injected as context for downstream tasks.

    v2: Can build pipeline from PipelineConfig (YAML templates).
    v3 (Phase 4): Optional repository for persistent storage.
    """

    def __init__(self, project_id: str, repository: AsyncPipelineRepository | None = None):
        self.project_id = project_id
        self.memory = ProjectMemory(project_id)
        self.repository = repository

    def build_from_config(self, config: PipelineConfig) -> PipelineDAG:
        """
        Build pipeline DAG from a PipelineConfig.

        This is the main entry point for configurable pipelines.
        Uses config_loader to resolve dependencies and create tasks with edges.

        Args:
            config: Validated pipeline configuration

        Returns:
            PipelineDAG with tasks in topological order and edges (with conditions)
        """
        return build_dag_from_config(config)

    async def run(self, dag: PipelineDAG, run_id: str | None = None,
                  initial_completed: dict[str, AgentResult] | None = None) -> PipelineRun:
        """
        Execute pipeline with support for conditional edges and checkpoints.

        Args:
            dag: PipelineDAG with tasks and edges (with optional conditions)
            run_id: Optional unique identifier for this run. If None, generates UUID.

        Returns:
            PipelineRun with results. If paused at a checkpoint, run.paused=True
            and run.checkpoint_id is set.
        """
        if run_id is None:
            run_id = str(uuid.uuid4())

        tasks = dag.tasks
        run = PipelineRun(project_id=self.project_id, tasks=tasks, run_id=run_id)
        # Initialize completed and pending, considering initial_completed (for resume)
        if initial_completed:
            completed = initial_completed.copy()
            pending = {t.name: t for t in tasks if t.name not in completed}
        else:
            pending = {t.name: t for t in tasks}
            completed = {}

        # Build edge lookup: target -> list of (source, condition)
        edges_by_target: dict[str, list[tuple[str, str | None]]] = {}
        for edge in dag.edges:
            edges_by_target.setdefault(edge.target, []).append((edge.source, edge.condition))

        logger.info(f"[orchestrator] Starting pipeline run {run_id} with {len(tasks)} tasks, {len(dag.edges)} edges")

        while pending:
            # Check cost cap
            total_cost = sum(r.cost_usd for r in completed.values())
            if total_cost > settings.max_pipeline_cost_usd:
                run.aborted = True
                run.abort_reason = f"Cost cap ${settings.max_pipeline_cost_usd} reached at ${total_cost:.4f}"
                logger.warning(f"[orchestrator] {run.abort_reason}")
                break

            # Find tasks ready to run (considering conditional edges)
            ready = []
            for task in pending.values():
                if self._is_task_ready(task, completed, edges_by_target):
                    ready.append(task)

            if not ready and pending:
                names = list(pending.keys())
                raise RuntimeError(f"Dependency deadlock or unmet conditions: {names}")

            # Build context for each ready task (includes all completed deps)
            async def execute(task: PipelineTask) -> tuple[str, AgentResult]:
                ctx_parts = []
                for dep in task.depends_on:
                    if dep in completed:
                        dep_result = completed[dep]
                        ctx_parts.append(f"## Output from {dep} agent:\n{dep_result.output}")
                context = "\n\n".join(ctx_parts)

                logger.info(f"[orchestrator] Running: {task.name}")
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

                # Check if this task is a checkpoint that requires pausing
                if self._is_checkpoint_pause(result):
                    run.paused = True
                    run.checkpoint_id = getattr(result, 'checkpoint_id', None)
                    run.checkpoint_type = getattr(result, 'checkpoint_type', None)

                    # Save checkpoint to repository if available
                    if self.repository and run.checkpoint_id:
                        checkpoint_type = getattr(result, 'checkpoint_type', 'human_approval')
                        message = getattr(result, 'checkpoint_message', 'Action required')
                        metadata = getattr(result, 'checkpoint_metadata', {})
                        await self.repository.create_checkpoint(
                            pipeline_run_id=run_id,
                            agent_name=name,
                            checkpoint_type=checkpoint_type,
                            message=message,
                            metadata=metadata,
                        )
                        logger.info(f"[orchestrator] Checkpoint saved to repository: {run.checkpoint_id}")
                    else:
                        # Fallback to memory store
                        checkpoint_type = getattr(result, 'checkpoint_type', 'human_approval')
                        message = getattr(result, 'checkpoint_message', 'Action required')
                        metadata = getattr(result, 'checkpoint_metadata', {})
                        self.memory.create_checkpoint(
                            pipeline_run_id=run_id,
                            agent_name=name,
                            checkpoint_type=checkpoint_type,
                            message=message,
                            metadata=metadata,
                        )
                        logger.info(f"[orchestrator] Checkpoint saved to memory: {run.checkpoint_id}")

                    # Save pipeline state for later resume
                    state = self._serialize_state(dag, completed)
                    self.memory.save_pipeline_state(run_id, state, checkpoint_id=run.checkpoint_id)

                    logger.info(f"[orchestrator] Pipeline paused at checkpoint {run.checkpoint_id} (type: {run.checkpoint_type})")
                    # Break out of the while loop - stop execution
                    break

            if run.paused:
                # Exit the loop
                break

        run.finished_at = time.time()
        # Cleanup saved state if pipeline fully completed (not paused)
        if not run.paused:
            try:
                self.memory.delete_pipeline_state(run_id)
            except Exception as e:
                logger.warning(f"[orchestrator] Failed to delete pipeline state for {run_id}: {e}")
        status = "PAUSED" if run.paused else ("ABORTED" if run.aborted else "COMPLETED")
        logger.info(f"[orchestrator] Pipeline {status}\n{run.summary()}")
        return run

    def _is_task_ready(
        self,
        task: PipelineTask,
        completed: dict[str, AgentResult],
        edges_by_target: dict[str, list[tuple[str, str | None]]]
    ) -> bool:
        """
        Check if a task is ready to execute.

        A task is ready if all its dependencies are satisfied:
        - For each source in task.depends_on, there must be an edge (source->task) that is satisfied
        - An edge is satisfied if:
          1. source is in completed
          2. If there's a condition, it evaluates to True using source's result

        For tasks with no explicit edges, falls back to simple 'all deps in completed'.
        """
        # If no edges mapped for this target, use simple check (all deps completed)
        if task.name not in edges_by_target:
            return all(dep in completed for dep in task.depends_on)

        # Check all incoming edges are satisfied
        incoming_edges = edges_by_target[task.name]
        for source, condition in incoming_edges:
            # Source must be completed
            if source not in completed:
                logger.debug(f"Task {task.name} waiting: source {source} not completed")
                return False

            # If there's a condition, evaluate it
            if condition:
                source_result = completed[source]
                if not self._evaluate_condition(condition, source_result):
                    logger.debug(f"Task {task.name} waiting: condition '{condition}' not met from {source}")
                    return False

        # All edges satisfied
        return True

    def _evaluate_condition(self, condition: str, result: AgentResult) -> bool:
        """
        Safely evaluate a condition expression against an AgentResult.

        The condition can access the result via 'result' variable.
        Example: "result.security_score >= 80" expects result to have attribute security_score.
        Or: "result.output contains 'PASS'"

        Args:
            condition: Python expression string
            result: AgentResult from the source agent

        Returns:
            True if condition evaluates to True, False otherwise
        """
        try:
            # Create a restricted evaluation context with essential constants
            safe_dict = {
                "__builtins__": {},
                "True": True,
                "False": False,
                "None": None,
            }
            # Expose result attributes safely - allow attribute access only
            safe_dict["result"] = result
            # Also expose common fields directly for convenience
            safe_dict["output"] = result.output
            safe_dict["cost"] = result.cost_usd

            # Evaluate
            return bool(eval(condition, safe_dict))

        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition}': {e}")
            return False


    # Checkpoint helpers (Phase 3)

    def _is_checkpoint_pause(self, result: AgentResult) -> bool:
        """Check if this agent result indicates the pipeline should pause."""
        return result.state == "checkpoint_created"

    def _serialize_state(self, dag: PipelineDAG, completed: dict[str, AgentResult]) -> dict:
        """Serialize pipeline state for persistence."""
        return {
            "dag": {
                "tasks": [
                    {
                        "agent_name": task.agent.name,
                        "task": task.task,
                        "depends_on": task.depends_on,
                        "model": task.agent.config.model,
                        "max_tokens": task.agent.config.max_tokens,
                    } for task in dag.tasks
                ],
                "edges": [
                    {"source": e.source, "target": e.target, "condition": e.condition}
                    for e in dag.edges
                ]
            },
            "completed": {name: result.to_dict() for name, result in completed.items()}
        }

    def _deserialize_state(self, state: dict) -> PipelineDAG:
        """Deserialize pipeline state from persistence."""
        from agents.agent_config import create_agent
        import dataclasses
        from agents.agent_config import AgentConfig

        task_data_list = state["dag"]["tasks"]
        tasks = []
        for td in task_data_list:
            agent = create_agent(td["agent_name"])
            # Apply config overrides if present
            if td.get("model") or td.get("max_tokens"):
                cfg = agent.config
                new_cfg = dataclasses.replace(
                    cfg,
                    model=td["model"] if td.get("model") else cfg.model,
                    max_tokens=td["max_tokens"] if td.get("max_tokens") else cfg.max_tokens
                )
                agent.config = new_cfg
            task = PipelineTask(
                agent=agent,
                task=td["task"],
                depends_on=td["depends_on"]
            )
            tasks.append(task)
        edges = [EdgeConfig(**e) for e in state["dag"]["edges"]]
        return PipelineDAG(tasks=tasks, edges=edges)

    def _result_from_dict(self, data: dict) -> AgentResult:
        """Deserialize an AgentResult from dict (as produced by to_dict)."""
        tokens = data.get("tokens", {})
        return AgentResult(
            agent_name=data["agent"],
            output=data.get("output", ""),
            tool_calls=data.get("tool_calls", []),
            input_tokens=tokens.get("input", 0),
            output_tokens=tokens.get("output", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            errors=data.get("errors", []),
            model_used=data.get("model", ""),
            retries=data.get("retries", 0),
            state=data.get("state", "done"),
        )

    async def resume(self, run_id: str, decision: str, approver: str | None = None, reason: str | None = None) -> PipelineRun:
        """
        Resume a paused pipeline after checkpoint decision.

        Args:
            run_id: The original pipeline run ID
            decision: 'approved' or 'rejected'
            approver: Who made the decision (email/ID)
            reason: Optional reason note

        Returns:
            PipelineRun with final results
        """
        # Use repository if available, otherwise fallback to memory
        if self.repository:
            # Get checkpoint ID from pipeline state
            run = await self.repository.get_run(run_id)
            if not run:
                raise ValueError(f"No pipeline run found with ID {run_id}")
            checkpoint_id = run.checkpoint_id
            if not checkpoint_id:
                raise ValueError(f"No paused checkpoint found for run {run_id}")

            # Get and update checkpoint
            checkpoint = await self.repository.get_checkpoint(checkpoint_id)
            if not checkpoint:
                raise ValueError(f"Checkpoint {checkpoint_id} not found")
            if checkpoint.status != "pending":
                raise ValueError(f"Checkpoint already decided: {checkpoint.status}")

            updated = await self.repository.update_checkpoint_decision(checkpoint_id, decision, approver)
            if not updated:
                raise ValueError(f"Failed to update checkpoint {checkpoint_id}")
        else:
            # Fallback to memory store
            checkpoint_id = self.memory.get_checkpoint_id_for_run(run_id)
            if not checkpoint_id:
                raise ValueError(f"No paused checkpoint found for run {run_id}")

            if not self.memory.update_checkpoint_decision(checkpoint_id, decision, approver, reason):
                checkpoint = self.memory.get_checkpoint(checkpoint_id)
                if checkpoint and checkpoint["status"] != "pending":
                    raise ValueError(f"Checkpoint already decided: {checkpoint['status']}")
                else:
                    raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # If rejected, abort the pipeline
        if decision == "rejected":
            state = self.memory.load_pipeline_state(run_id)
            if state:
                dag = self._deserialize_state(state)
                completed_raw = state["completed"]
                completed = {name: self._result_from_dict(data) for name, data in completed_raw.items()}
                run = PipelineRun(
                    project_id=self.project_id,
                    tasks=dag.tasks,
                    run_id=run_id,
                    results=completed,
                    aborted=True,
                    abort_reason=f"Checkpoint rejected by {approver}: {reason or 'no reason'}",
                )
                run.finished_at = time.time()
                # Cleanup state
                self.memory.delete_pipeline_state(run_id)
                logger.info(f"[orchestrator] Pipeline run {run_id} aborted at checkpoint {checkpoint_id}")
                return run
            else:
                raise ValueError(f"Saved state missing for run {run_id}")

        # If approved, continue execution
        state = self.memory.load_pipeline_state(run_id)
        if not state:
            raise ValueError(f"No saved state found for run {run_id}")
        dag = self._deserialize_state(state)
        completed_raw = state["completed"]
        completed = {name: self._result_from_dict(data) for name, data in completed_raw.items()}

        # Continue from where we left off
        logger.info(f"[orchestrator] Resuming pipeline run {run_id} from checkpoint {checkpoint_id}")
        return await self.run(dag, run_id=run_id, initial_completed=completed)

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
        dag = orch.build_from_config(config)
        tasks = dag.tasks
        # Substitute {feature} in task prompts
        for task in tasks:
            if task.task:
                task.task = task.task.format(feature=feature, project_id=project_id)
        # Update dag with modified tasks
        dag.tasks = tasks
    else:
        # Backward compatible: default full pipeline
        tasks = make_full_app_pipeline(feature, project_id)
        # Create a dag with no edges for backward compatibility
        dag = PipelineDAG(tasks=tasks, edges=[])

    return await orch.run(dag)


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_full_pipeline(
        feature="User subscription management with Stripe",
        project_id="my-saas-app",
    ))
    print(result.summary())
