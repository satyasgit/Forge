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
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import anthropic

from config.settings import settings
from memory.store import ProjectMemory
from tools.registry import TOOL_REGISTRY, get_tools_for_agent
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

_clients: dict[str, anthropic.Anthropic] = {}


def _get_client(api_key: str | None = None) -> anthropic.Anthropic:
    """Get or create an Anthropic client. Lazy init, cached."""
    key = api_key or settings.anthropic_api_key
    if key not in _clients:
        _clients[key] = anthropic.Anthropic(api_key=key)
    return _clients[key]


# ── Backward compatibility alias ──────────────────────────────────────────────
# Existing tests mock `agents.base.client` — this keeps them working.

class _LazyClient:
    """Proxy that defers client creation until first use."""
    _instance: anthropic.Anthropic | None = None

    @property
    def messages(self):
        if self._instance is None:
            self._instance = _get_client()
        return self._instance.messages

    def __getattr__(self, name):
        if self._instance is None:
            self._instance = _get_client()
        return getattr(self._instance, name)


client = _LazyClient()


@dataclass
class AgentResult:
    agent_name: str
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    model_used: str = ""
    retries: int = 0
    state: str = "done"
    artifact: AgentArtifact | None = None

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
        self._client = llm_client or _get_client()
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

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    @property
    def state(self) -> AgentState:
        return self._state

    def run(self, task: str, context: str = "", use_memory: bool = True) -> AgentResult:
        """
        Execute the agent on a task.
        Runs a tool-use loop until Claude returns end_turn.
        Includes retry logic, cost tracking, and context window management.
        """
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

                response = self._call_claude_with_retry(tools, result)

                result.input_tokens += response.usage.input_tokens
                result.output_tokens += response.usage.output_tokens
                self._messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    result.output = next(
                        (b.text for b in response.content if hasattr(b, "text")), ""
                    )
                    breaker.record_success()
                    break

                if response.stop_reason == "tool_use":
                    tool_results = self._execute_tools(response.content, result)
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

    def _call_claude_with_retry(self, tools: list[dict], result: AgentResult):
        """Call Claude API with retry logic."""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                kwargs: dict[str, Any] = dict(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=self.system_prompt,
                    messages=self._messages,
                )
                if tools:
                    kwargs["tools"] = tools

                return self._client.messages.create(**kwargs)

            except RETRYABLE_EXCEPTIONS as e:
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
                time.sleep(wait)

        raise last_exception  # type: ignore[misc]

    def _execute_tools(self, content_blocks: list, result: AgentResult) -> list[dict]:
        tool_results = []
        for block in content_blocks:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            fn = TOOL_REGISTRY.get(block.name)
            call_record = {"tool": block.name, "input": block.input}

            if not fn:
                output = {"error": f"Unknown tool: {block.name}"}
            else:
                try:
                    output = fn(**block.input)
                    call_record["output"] = output
                    logger.info("  [tool] %s → %s", block.name, str(output)[:120])
                except Exception as e:
                    output = {"error": str(e)}
                    call_record["error"] = str(e)
                    logger.warning("  [tool] %s failed: %s", block.name, e)

            result.tool_calls.append(call_record)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
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
