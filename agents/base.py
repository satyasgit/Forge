"""
Base agent class. Every specialist agent inherits from this.

v2: Dependency-injected, retry-enabled, state-tracked, context-managed.

Changes from v1:
  - No module-level Anthropic client — injected via constructor
  - Per-agent model selection via AgentConfig
  - Accurate per-model cost calculation
  - Retry with exponential backoff on transient failures
  - Circuit breaker prevents cascading failures
  - Context window management (message truncation + summarisation)
  - Agent state machine (IDLE → EXECUTING → DONE | ERROR)
  - Backward compatible: all existing agents work without changes
"""
from __future__ import annotations

import json
import time
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from config.settings import settings
from memory.store import ProjectMemory
from tools.registry import TOOL_REGISTRY, get_tools_for_agent
from llm.client import LLMClient
from communication.bus import MessageBus, AgentMessage
from config.database import AsyncSessionLocal, get_async_db
from agile.models import AgentPersonaDB
from agile.sprint_manager import SprintManager
from memory.vector_store import VectorMemory
from evolution.outcome_tracker import OutcomeTracker, TaskOutcome
from evolution.self_reflection import SelfReflector
from agents.agent_config import (
    AgentConfig,
    AgentState,
    AgentArtifact,
    get_agent_config,
    calculate_cost,
    register_agent,
)
from agents.retry import (
    with_retry,
    get_circuit_breaker,
    CircuitBreakerOpenError,
    RETRYABLE_EXCEPTIONS,
)

logger = logging.getLogger(__name__)


# ── Lazy client factory (replaces module-level global) ────────────────────────

# Legacy client factory removed in favor of LLMClient


@dataclass
class AgentResult:
    agent_name: str
    output: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    model_used: str = ""
    retries: int = 0
    state: str = "done"
    artifact: AgentArtifact | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # For custom attributes in conditions

    def __post_init__(self):
        """Validate that result has meaningful output or errors."""
        if not self.output and not self.errors and self.state == "done":
            import warnings
            warnings.warn(
                f"AgentResult for '{self.agent_name}' has no output and no errors. "
                "This may indicate the agent did not produce any results.",
                UserWarning,
                stacklevel=2,
            )

    @property
    def cost_usd(self) -> float:
        """Accurate per-model cost calculation."""
        if self.model_used:
            return calculate_cost(self.model_used, self.input_tokens, self.output_tokens)
        # Fallback for backward compatibility
        return (self.input_tokens / 1_000_000 * 15) + (self.output_tokens / 1_000_000 * 75)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "output": self.output,
            "tool_calls": self.tool_calls,
            "tokens": {"input": self.input_tokens, "output": self.output_tokens},
            "cost_usd": round(self.cost_usd, 4),
            "duration_seconds": round(self.duration_seconds, 2),
            "errors": self.errors,
            "model": self.model_used,
            "retries": self.retries,
            "state": self.state,
        }

    def __getattr__(self, name: str) -> Any:
        """Allow access to custom attributes via metadata (for conditions, etc.)."""
        if name in self.metadata:
            return self.metadata[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class BaseAgent(ABC):
    """
    Base class for all agents in the org.

    Subclasses must define:
        name: str
        role: str
        system_prompt: str (property)
        enabled_tools: list[str]   (tool names from registry)
    """

    name: str = "base"
    role: str = "Agent"
    enabled_tools: list[str] = []

    def __init__(
        self,
        project_id: str | None = None,
        *,
        config: AgentConfig | None = None,
        llm_client: anthropic.Anthropic | None = None,
        memory: ProjectMemory | None = None,
    ):
        self.project_id = project_id
        self.config = config or get_agent_config(self.name)
        self._llm = llm_client or LLMClient()
        self.bus = MessageBus()
        self.persona: Optional[AgentPersonaDB] = None
        self._state = AgentState.IDLE
        self._messages: list[dict] = []

        # Memory: use injected, or create from project_id, or None
        if memory is not None:
            self.memory = memory
        elif project_id:
            self.memory = ProjectMemory(project_id)
        else:
            self.memory = None

        if self.memory:
            self._messages = self.memory.restore_agent_messages(self.name)
            logger.info("[%s] Restored %d messages from memory", self.name, len(self._messages))

        # Semantic memory for long-term self-evolution
        self.vector_memory = VectorMemory(self.name)
        self.outcome_tracker = OutcomeTracker(self.client)
        self.reflector = SelfReflector(self._llm)
        self.recent_lessons = []
        self.recent_mistakes = []  # Past mistakes for self-reflection

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    async def init_persona(self):
        """Load persistent persona from DB."""
        try:
            async with AsyncSessionLocal() as db:
                sm = SprintManager(db)
                self.persona = await sm.get_or_create_persona(
                    name=self.name,
                    title=self.role,
                    style=getattr(self, 'style', "Professional and engineering-focused")
                )
                logger.info("[%s] Persona loaded: %s (%s)", self.name, self.persona.title, self.persona.seniority)
        except Exception as e:
            logger.warning("[%s] Failed to load persona from DB, using defaults: %s", self.name, e)

    @property
    def effective_system_prompt(self) -> str:
        """Enrich system prompt with persona and memory."""
        prompt = self.system_prompt
        
        # Inject recent lessons from semantic memory
        lessons_prefix = ""
        if getattr(self, 'recent_lessons', []):
            lessons_prefix = "## LESSONS FROM PAST EXPERIENCES\n" + "\n".join(f"- {l}" for l in self.recent_lessons) + "\n\n"
            
        if self.persona:
            persona_prefix = textwrap.dedent(f"""
                ## YOUR IDENTITY
                You are {self.persona.name}, {self.persona.title}.
                Your seniority level is {self.persona.seniority}.
                Working style: {self.persona.style}
                
                ## YOUR MEMORY
                Recent decisions you've made:
                {self.persona.decision_log[-5:] if self.persona.decision_log else "None logged yet."}
            """).strip()
            return f"{persona_prefix}\n\n{lessons_prefix}{prompt}"
        return f"{lessons_prefix}{prompt}"

    @property
    def state(self) -> AgentState:
        return self._state

    # ── Communication Bus ─────────────────────────────────────────────────────

    async def broadcast(self, content: str, channel: str = "general", metadata: dict = None):
        """Broadcast a message to a channel."""
        msg = AgentMessage(
            sender=self.name,
            content=content,
            message_type="broadcast",
            channel=channel,
            metadata=metadata or {}
        )
        await self.bus.publish(msg)

    async def ask(self, recipient: str, question: str, channel: str = "general") -> str:
        """
        Ask another agent a question and wait for an answer.
        (Note: Full bidirectional sync ask/answer requires the background listener).
        For now, this just publishes the question.
        """
        msg = AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=question,
            message_type="ask",
            channel=channel
        )
        await self.bus.publish(msg)
        logger.info("[%s] Asked %s: %s", self.name, recipient, question[:50])
        return msg.id

    async def answer(self, recipient: str, reply_to: str, content: str):
        """Answer a question from another agent."""
        msg = AgentMessage(
            sender=self.name,
            recipient=recipient,
            reply_to=reply_to,
            content=content,
            message_type="answer",
            channel="general"
        )
        await self.bus.publish(msg)

    # ── Execution ─────────────────────────────────────────────────────────────

    async def run(self, task: str, context: str = "", use_memory: bool = True) -> AgentResult:
        """
        Execute the agent on a task.
        Runs a tool-use loop until Claude returns end_turn.
        Includes retry logic, cost tracking, and context window management.
        """
        # Initialization
        if not self.persona:
            await self.init_persona()

        # Self-Evolution: Recall similar tasks before starting
        try:
            similar_memories = await self.vector_memory.search(task, memory_type="lesson", top_k=5)
            self.recent_lessons = [m.content for m in similar_memories if m.similarity > 0.65]
            # Separate mistakes (from failed outcomes) for self-reflection
            self.recent_mistakes = [
                m.content for m in similar_memories
                if m.similarity > 0.65 and m.metadata.get("review_passed") is False
            ]
            if self.recent_lessons:
                logger.info("[%s] Recalled %d relevant lessons from past tasks.", self.name, len(self.recent_lessons))
            if self.recent_mistakes:
                logger.info("[%s] Recalled %d past mistakes to watch for.", self.name, len(self.recent_mistakes))
        except Exception as e:
            logger.warning("[%s] Failed to recall memory: %s", self.name, e)

        self._state = AgentState.EXECUTING
        start = time.time()
        result = AgentResult(agent_name=self.name, model_used=self.config.model)

        # Build context from memory
        project_ctx = ""
        if use_memory and self.memory:
            project_ctx = self.memory.get_context_for_agent(self.name)

        parts = [p for p in [project_ctx, context, task] if p]
        user_content = "\n\n".join(parts)
        self._messages.append({"role": "user", "content": user_content})

        # Manage context window
        self._trim_messages()

        tools = get_tools_for_agent(self.enabled_tools)

        logger.info("[%s] Starting task (model=%s): %s...", self.name, self.config.model, task[:80])

        # Circuit breaker check
        breaker = get_circuit_breaker("claude_api")
        if not breaker.allow_request():
            self._state = AgentState.ERROR
            result.errors.append("Circuit breaker is OPEN — Claude API has too many consecutive failures")
            result.output = "Agent unavailable: API circuit breaker is open. Try again later."
            result.state = "circuit_breaker_open"
            return result

        try:
            while True:
                # Cost cap check
                current_cost = calculate_cost(self.config.model, result.input_tokens, result.output_tokens)
                if current_cost > self.config.max_cost_per_run:
                    logger.warning(
                        "[%s] Cost cap reached: $%.4f > $%.4f",
                        self.name, current_cost, self.config.max_cost_per_run,
                    )
                    result.errors.append(f"Cost cap ${self.config.max_cost_per_run} exceeded")
                    break

                response = await self._call_llm_with_retry(tools, result)

                result.input_tokens += response.usage.prompt_tokens
                result.output_tokens += response.usage.completion_tokens
                
                msg = response.choices[0].message
                self._messages.append(msg.to_dict())

                if response.choices[0].finish_reason in ["stop", "end_turn"]:
                    result.output = msg.content or ""
                    breaker.record_success()
                    break

                if response.choices[0].finish_reason == "tool_use" or msg.tool_calls:
                    tool_results = await self._execute_tools(msg.tool_calls or [], result)
                    self._messages.append({"role": "user", "content": tool_results})

        except CircuitBreakerOpenError:
            self._state = AgentState.ERROR
            result.errors.append("Circuit breaker tripped during execution")
            result.output = "Agent failed: too many consecutive API errors."
            result.state = "error"
        except Exception as e:
            self._state = AgentState.ERROR
            breaker.record_failure()
            logger.error("[%s] Error: %s", self.name, e)
            result.errors.append(str(e))
            result.output = f"Agent error: {e}"
            result.state = "error"

        result.duration_seconds = time.time() - start

        if not result.errors:
            self._state = AgentState.DONE
            result.state = "done"

        # Self-Reflection: Critique output before returning
        if result.output and not result.errors:
            try:
                reflection = await self.reflector.reflect(
                    agent_name=self.name,
                    task=task,
                    output=result.output,
                    past_mistakes=self.recent_mistakes,
                )
                if reflection.self_fixed:
                    logger.info(
                        "[%s] Self-reflection caught %d issues and self-corrected.",
                        self.name, len(reflection.issues_found)
                    )
                    result.output = reflection.revised_output
                    result.metadata["self_reflection_applied"] = True
                    result.metadata["issues_self_corrected"] = len(reflection.issues_found)
                    result.metadata["self_reflection_confidence"] = reflection.confidence
                else:
                    result.metadata["self_reflection_applied"] = False
                    result.metadata["self_reflection_confidence"] = reflection.confidence
            except Exception as e:
                logger.warning("[%s] Self-reflection failed: %s. Returning unreviewed output.", self.name, e)

        # Persist to memory
        if self.memory:
            self.memory.save_agent_messages(self.name, self._messages)
            self.memory.save_artifact(self.name, "output", result.output)

        logger.info(
            "[%s] Done — %d tokens, $%.4f, %.1fs, %d retries",
            self.name, result.output_tokens, result.cost_usd,
            result.duration_seconds, result.retries,
        )
        return result

    async def remember_outcome(self, outcome: TaskOutcome):
        """Analyze the outcome and save the lesson to semantic memory."""
        try:
            lesson = await self.outcome_tracker.extract_lesson(outcome)
            logger.info("[%s] Lesson learned: %s", self.name, lesson)
            
            await self.vector_memory.store(
                content=lesson,
                memory_type="lesson",
                metadata={
                    "task": outcome.task_summary,
                    "review_passed": outcome.review_passed,
                    "tests_passed": outcome.tests_passed,
                }
            )
        except Exception as e:
            logger.error("[%s] Failed to remember outcome: %s", self.name, e)

    async def _call_llm_with_retry(self, tools: list[dict], result: AgentResult):
        """Call LLM API via LiteLLM with retry logic."""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return await self._llm.create_message(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=self.effective_system_prompt,
                    messages=self._messages,
                    tools=tools,
                )

            except Exception as e:
                # Check if it's a retryable exception (LiteLLM wraps these)
                last_exception = e
                if attempt >= self.config.max_retries:
                    break

                wait = min(
                    self.config.retry_backoff_base ** attempt,
                    self.config.retry_max_wait,
                )
                result.retries += 1
                self._state = AgentState.RETRYING
                logger.warning(
                    "[%s] Retry %d/%d after %s — waiting %.1fs",
                    self.name, attempt + 1, self.config.max_retries, e, wait,
                )
                await asyncio.sleep(wait)

        raise last_exception  # type: ignore[misc]

    async def _execute_tools(self, tool_calls: list, result: AgentResult) -> list[dict]:
        tool_results = []
        for block in tool_calls:
            # Handle both object-style and dict-style tool calls
            tool_name = getattr(block.function, "name", None) or block.function["name"]
            tool_input_raw = getattr(block.function, "arguments", None) or block.function["arguments"]
            tool_id = getattr(block, "id", None) or block["id"]
            
            if isinstance(tool_input_raw, str):
                tool_input = json.loads(tool_input_raw)
            else:
                tool_input = tool_input_raw

            fn = TOOL_REGISTRY.get(tool_name)
            call_record = {"tool": tool_name, "input": tool_input}

            if not fn:
                output = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    # Execute tool (synchronously for now as they are synchronous)
                    output = fn(**tool_input)
                    call_record["output"] = output
                    logger.info("  [tool] %s → %s", tool_name, str(output)[:120])
                except Exception as e:
                    output = {"error": str(e)}
                    call_record["error"] = str(e)
                    logger.warning("  [tool] %s failed: %s", tool_name, e)

            result.tool_calls.append(call_record)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(output),
            })

        return tool_results

    def _trim_messages(self) -> None:
        """
        Manage context window by keeping only the most recent messages.
        Prevents unbounded growth that would exceed Claude's context limit.
        """
        max_msgs = self.config.max_context_messages * 2  # pairs of user+assistant
        if len(self._messages) > max_msgs:
            # Keep first message (original task context) + last N messages
            trimmed_count = len(self._messages) - max_msgs
            logger.info(
                "[%s] Trimming %d old messages (keeping %d)",
                self.name, trimmed_count, max_msgs,
            )
            # Keep the first user message (has project context) and the most recent messages
            first = self._messages[:1]
            recent = self._messages[-max_msgs + 1:]
            self._messages = first + recent

    def reset_messages(self):
        """Clear in-session message history (keeps project memory)."""
        self._messages = []
        self._state = AgentState.IDLE
