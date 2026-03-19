"""
Agent configuration, state machine, and typed output models.

This module replaces the hardcoded, module-level globals with
dependency-injectable configuration that enables:
  - Per-agent model selection (Opus for planning, Sonnet for code gen)
  - Accurate per-model cost tracking
  - Agent lifecycle state management
  - Typed artifacts for inter-agent communication
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Model Pricing (per 1M tokens) ────────────────────────────────────────────

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input_cost_per_1M, output_cost_per_1M)
    "claude-opus-4-5":            (15.00, 75.00),
    "claude-sonnet-4-5":          (3.00, 15.00),
    "claude-haiku-4-5-20251001":  (0.80, 4.00),
    # Add new models here as they become available
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate USD cost for a given model and token counts."""
    input_rate, output_rate = MODEL_PRICING.get(model, (15.00, 75.00))
    return (input_tokens / 1_000_000 * input_rate) + (output_tokens / 1_000_000 * output_rate)


# ── Agent State Machine ──────────────────────────────────────────────────────

class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    ERROR = "error"
    RETRYING = "retrying"


# ── Agent Configuration ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentConfig:
    """
    Per-agent configuration. Every agent gets its own config,
    allowing different models, token limits, and retry policies.
    """
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096
    temperature: float = 0.0

    # Retry policy
    max_retries: int = 3
    retry_backoff_base: float = 2.0      # seconds: 2, 4, 8, ...
    retry_max_wait: float = 30.0         # never wait longer than this

    # Cost control
    max_cost_per_run: float = 2.0        # abort single agent run if exceeded

    # Context window management
    max_context_messages: int = 20       # keep last N message pairs
    summarise_after: int = 10            # summarise older messages

    @property
    def input_cost_per_1m(self) -> float:
        return MODEL_PRICING.get(self.model, (15.0, 75.0))[0]

    @property
    def output_cost_per_1m(self) -> float:
        return MODEL_PRICING.get(self.model, (15.0, 75.0))[1]


# ── Default Configs Per Agent Role ────────────────────────────────────────────

AGENT_CONFIGS: dict[str, AgentConfig] = {
    # Planning agents → Opus (needs deep reasoning)
    "pm":           AgentConfig(model="claude-opus-4-5", max_tokens=8192),
    "architect":    AgentConfig(model="claude-opus-4-5", max_tokens=8192),

    # Security → Opus (safety-critical)
    "security":     AgentConfig(model="claude-opus-4-5", max_tokens=8192),

    # Code generation → Sonnet (strong at code, 5x cheaper)
    "frontend":     AgentConfig(model="claude-sonnet-4-5", max_tokens=8192),
    "backend":      AgentConfig(model="claude-sonnet-4-5", max_tokens=8192),
    "mobile":       AgentConfig(model="claude-sonnet-4-5", max_tokens=8192),
    "code_review":  AgentConfig(model="claude-sonnet-4-5", max_tokens=4096),

    # Template-heavy → Sonnet
    "qa":           AgentConfig(model="claude-sonnet-4-5", max_tokens=8192),
    "devops":       AgentConfig(model="claude-sonnet-4-5", max_tokens=4096),
    "monetisation": AgentConfig(model="claude-sonnet-4-5", max_tokens=4096),
    "ui_ux":        AgentConfig(model="claude-sonnet-4-5", max_tokens=4096),

    # Verification → Sonnet
    "verification": AgentConfig(model="claude-sonnet-4-5", max_tokens=4096),
}


def get_agent_config(agent_name: str) -> AgentConfig:
    """Get config for an agent, falling back to sensible defaults."""
    return AGENT_CONFIGS.get(agent_name, AgentConfig())


# ── Typed Agent Artifact ──────────────────────────────────────────────────────

@dataclass
class AgentArtifact:
    """
    Typed output from an agent. Replaces raw string output with
    structured, machine-readable data for inter-agent communication.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    artifact_type: str = ""       # prd | api_spec | component | test_suite | security_report | ...
    structured_data: dict = field(default_factory=dict)
    display_text: str = ""        # Human-readable for dashboard
    files_generated: list[dict] = field(default_factory=list)  # [{path: str, content: str}]
    validation_status: str = "unchecked"  # valid | invalid | unchecked
    validation_errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent_name,
            "type": self.artifact_type,
            "display_text": self.display_text[:500],
            "files_count": len(self.files_generated),
            "validation": self.validation_status,
            "validation_errors": self.validation_errors,
            "created_at": self.created_at,
        }


# ── Agent Factory ─────────────────────────────────────────────────────────────

# Single source of truth for agent registration. Replaces the 3 separate registries.
_AGENT_REGISTRY: dict[str, type] = {}


def register_agent(cls: type) -> type:
    """Decorator to register an agent class. Used by specialist agents."""
    name = getattr(cls, "name", cls.__name__.lower())
    _AGENT_REGISTRY[name] = cls
    return cls


def get_registered_agents() -> dict[str, type]:
    """Return all registered agent classes."""
    return dict(_AGENT_REGISTRY)


def create_agent(name: str, project_id: str | None = None, **overrides: Any):
    """
    Factory function — single entry point for creating agents.
    Replaces the 3 hardcoded registries in api/main.py, orchestrator.py, and /api/agents.
    """
    cls = _AGENT_REGISTRY.get(name)
    if cls is None:
        available = list(_AGENT_REGISTRY.keys())
        raise ValueError(f"Unknown agent: {name}. Available: {available}")
    return cls(project_id=project_id, **overrides)


def list_agent_metadata() -> list[dict]:
    """Return metadata for all registered agents (for API /api/agents endpoint)."""
    agents = []
    for name, cls in _AGENT_REGISTRY.items():
        agents.append({
            "name": name,
            "role": getattr(cls, "role", "Agent"),
            "description": (cls.__doc__ or "").strip().split("\n")[0],
            "config": get_agent_config(name).__dict__,
        })
    return agents
""",
<parameter name="Description">Core DI config module: per-agent model selection, accurate cost calculation, agent state machine, typed artifacts, and a single agent registry that replaces the 3 hardcoded registries.
