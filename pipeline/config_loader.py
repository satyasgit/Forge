"""
Pipeline configuration loader and validator.

Supports loading pipeline definitions from YAML files and dictionaries.
Provides validation, dependency resolution, and conversion to PipelineTask objects.

Design inspired by Haystack's pipeline configuration system.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models for Configuration Schema
# ============================================================================

class AgentTaskConfig(BaseModel):
    """Configuration for a single agent in a pipeline."""

    agent: str = Field(..., description="Agent name (must exist in registry)")
    enabled: bool = Field(True, description="Whether this agent runs")
    task: str | None = Field(None, description="Override default task prompt")
    model: str | None = Field(None, description="Override default model (opus/sonnet/haiku)")
    max_tokens: int | None = Field(None, description="Max tokens for this agent")
    depends_on: list[str] = Field(default_factory=list, description="Additional dependencies")
    meta: dict[str, Any] = Field(default_factory=dict, description="Custom metadata")

    @field_validator("agent")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        """Ensure agent name is lowercase alphanumeric."""
        if not v.isidentifier():
            raise ValueError(f"Invalid agent name: {v}")
        return v


class PipelineConfig(BaseModel):
    """Complete pipeline configuration."""

    version: str = Field("1.0", description="Schema version")
    name: str = Field(..., description="Pipeline name/template identifier")
    description: str = Field("", description="Human-readable description")
    project_types: list[str] = Field(default_factory=list, description="Suitable project types (web, mobile, api, saas, etc.)")

    agents: list[AgentTaskConfig] = Field(..., description="List of agent configurations")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="Explicit edges (overrides auto deps)")

    auto_resolve: bool = Field(True, description="Auto-add missing dependencies from global deps")
    strict_validation: bool = Field(False, description="Fail on validation warnings (vs just warn)")

    settings: dict[str, Any] = Field(default_factory=dict, description="Pipeline-level settings")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @model_validator(mode='after')
    def validate_no_duplicate_agents(self) -> PipelineConfig:
        """Ensure no agent appears twice."""
        agent_names = [a.agent for a in self.agents if a.enabled]
        if len(agent_names) != len(set(agent_names)):
            duplicates = [name for name in agent_names if agent_names.count(name) > 1]
            raise ValueError(f"Duplicate agents in pipeline: {duplicates}")
        return self

    @property
    def enabled_agents(self) -> list[AgentTaskConfig]:
        """Return only enabled agents."""
        return [a for a in self.agents if a.enabled]

    @property
    def agent_names(self) -> list[str]:
        """Return names of enabled agents."""
        return [a.agent for a in self.enabled_agents]


# ============================================================================
# YAML Loading and Validation
# ============================================================================

class PipelineValidationError(Exception):
    """Raised when pipeline configuration is invalid."""
    pass


class PipelineValidationWarning(Exception):
    """Warning that doesn't block execution but should be reported."""
    pass


@dataclass
class ValidationResult:
    """Result of pipeline validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config: PipelineConfig | None = None


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load YAML file and return dict."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    with open(path, 'r') as f:
        try:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a mapping/dict")
            return data
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")


def load_pipeline_from_yaml(path: str | Path) -> PipelineConfig:
    """
    Load and validate pipeline configuration from YAML file.

    Args:
        path: Path to YAML file

    Returns:
        Validated PipelineConfig

    Raises:
        PipelineValidationError: If validation fails
        FileNotFoundError: If file doesn't exist
    """
    data = load_yaml(path)
    return load_pipeline_from_dict(data)


def load_pipeline_from_dict(data: dict[str, Any]) -> PipelineConfig:
    """
    Load and validate pipeline configuration from dictionary.

    Args:
        data: Dictionary with pipeline configuration

    Returns:
        Validated PipelineConfig

    Raises:
        PipelineValidationError: If validation fails
    """
    try:
        config = PipelineConfig(**data)
        logger.info("Loaded pipeline '%s' with %d agents", config.name, len(config.agents))
        return config
    except Exception as e:
        raise PipelineValidationError(f"Failed to parse pipeline config: {e}")


def validate_pipeline(config: PipelineConfig, agent_registry: set[str] | None = None) -> ValidationResult:
    """
    Validate a pipeline configuration.

    Checks:
    - All specified agents exist in registry (if provided)
    - Dependencies are resolvable
    - No circular dependencies
    - Project types are valid (if any)

    Args:
        config: Pipeline configuration to validate
        agent_registry: Set of known agent names (from @register_agent)

    Returns:
        ValidationResult with errors/warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check agent existence
    if agent_registry:
        for agent_cfg in config.agents:
            if agent_cfg.agent not in agent_registry:
                errors.append(f"Unknown agent: {agent_cfg.agent}. Available: {sorted(agent_registry)}")

    # Check enabled agents have non-empty names
    enabled_agents = [a.agent for a in config.agents if a.enabled]
    if not enabled_agents:
        errors.append("Pipeline has no enabled agents")

    # Load global dependencies from agent_deps.yaml
    deps_file = Path(__file__).parent.parent / "config" / "agent_deps.yaml"
    global_deps: dict[str, list[str]] = {}
    if deps_file.exists():
        try:
            deps_data = load_yaml(deps_file)
            global_deps = deps_data.get("dependencies", {})
        except Exception as e:
            warnings.append(f"Could not load agent dependencies: {e}")

    # Build dependency graph
    dep_graph: dict[str, set[str]] = {agent: set() for agent in enabled_agents}

    # Add global deps
    for agent in enabled_agents:
        if agent in global_deps:
            for dep in global_deps[agent]:
                if dep in enabled_agents:
                    dep_graph[agent].add(dep)
                else:
                    # Dep missing or disabled
                    # Check if dep exists in config but is disabled
                    dep_in_config_disabled = any(
                        a.agent == dep and not a.enabled for a in config.agents
                    )
                    if dep_in_config_disabled:
                        warnings.append(
                            f"Agent '{agent}' depends on '{dep}' which is not in pipeline or is disabled"
                        )
                    elif config.auto_resolve:
                        warnings.append(
                            f"Agent '{agent}' depends on '{dep}' which will be auto-added"
                        )
                    else:
                        warnings.append(
                            f"Agent '{agent}' depends on '{dep}' which is not in pipeline or is disabled"
                        )

    # Add per-agent overrides (dependencies)
    for agent_cfg in config.agents:
        if agent_cfg.enabled and agent_cfg.depends_on:
            for dep in agent_cfg.depends_on:
                if dep in enabled_agents:
                    dep_graph[agent_cfg.agent].add(dep)
                else:
                    warnings.append(
                        f"Agent '{agent_cfg.agent}' depends on '{dep}' "
                        f"which is not in pipeline or is disabled"
                    )

    # Check circular dependencies
    try:
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycle: list[str] = []

        def has_cycle(agent: str) -> bool:
            visited.add(agent)
            rec_stack.add(agent)
            for dep in dep_graph.get(agent, set()):
                if dep not in visited:
                    if has_cycle(dep):
                        cycle.append(dep)
                        return True
                elif dep in rec_stack:
                    cycle.append(dep)
                    return True
            rec_stack.remove(agent)
            return False

        for agent in enabled_agents:
            if agent not in visited:
                if has_cycle(agent):
                    cycle_str = " → ".join(cycle[::-1] + [agent])
                    errors.append(f"Circular dependency detected: {cycle_str}")
                    break
    except Exception as e:
        errors.append(f"Error checking dependencies: {e}")

    # Auto-resolve missing deps if enabled
    if config.auto_resolve:
        auto_added = _auto_add_missing_dependencies(enabled_agents, global_deps, dep_graph)
        if auto_added:
            warnings.append(f"Auto-added missing dependencies: {auto_added}")

    # Validate project types (if any)
    if config.project_types:
        valid_project_types = {"web", "mobile", "api", "saas", "security", "audit", "backend", "mvp"}
        invalid = [pt for pt in config.project_types if pt not in valid_project_types]
        if invalid:
            warnings.append(f"Unknown project_types: {invalid}. Valid: {valid_project_types}")

    # Determine overall validity
    valid = len(errors) == 0
    if not valid and config.strict_validation:
        # Even if strict, we want to report errors. valid=False already.
        pass
    elif not valid:
        # Non-strict mode still invalid if there are errors (not just warnings)
        pass

    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        config=config if valid else None
    )


def _auto_add_missing_dependencies(
    enabled_agents: list[str],
    global_deps: dict[str, list[str]],
    dep_graph: dict[str, set[str]]
) -> list[str]:
    """
    Auto-add agents that are required by global dependencies but missing.

    Includes transitive dependencies (deps of deps).

    Modifies dep_graph in-place and returns list of agents that were effectively added.
    """
    added: set[str] = set()
    to_visit: set[str] = set(enabled_agents)

    while to_visit:
        agent = to_visit.pop()
        if agent in global_deps:
            for dep in global_deps[agent]:
                if dep not in enabled_agents and dep not in added:
                    added.add(dep)
                    to_visit.add(dep)  # Also check deps of this dep

    return sorted(added)


def build_pipeline_from_config(
    config: PipelineConfig,
    agent_deps_override: dict[str, list[str]] | None = None
) -> list[PipelineTask]:
    """
    Convert PipelineConfig to list of PipelineTask objects with resolved dependencies.

    Args:
        config: Validated pipeline configuration
        agent_deps_override: Override global dependencies (for testing)

    Returns:
        List of PipelineTask objects in topological order

    Raises:
        ValueError: If dependency resolution fails
    """
    from agents.agent_config import create_agent
    from pipeline.orchestrator import PipelineTask

    # Load global dependencies
    deps_file = Path(__file__).parent.parent / "config" / "agent_deps.yaml"
    global_deps: dict[str, list[str]] = {}
    if deps_file.exists():
        try:
            deps_data = load_yaml(deps_file)
            global_deps = deps_data.get("dependencies", {})
        except Exception as e:
            logger.warning("Could not load agent dependencies: %s", e)

    if agent_deps_override:
        global_deps.update(agent_deps_override)

    # Build dependency map
    enabled_agents = config.enabled_agents
    agent_names = [a.agent for a in enabled_agents]

    dep_map: dict[str, set[str]] = {name: set() for name in agent_names}

    # Global deps
    for agent_name in agent_names:
        if agent_name in global_deps:
            for dep in global_deps[agent_name]:
                if dep in agent_names:
                    dep_map[agent_name].add(dep)

    # Override with per-agent depends_on
    for agent_cfg in enabled_agents:
        if agent_cfg.depends_on:
            for dep in agent_cfg.depends_on:
                if dep in agent_names:
                    dep_map[agent_cfg.agent].add(dep)

    # Auto-resolve if enabled: add missing deps as enabled agents
    if config.auto_resolve:
        added_agents = _auto_add_missing_dependencies(agent_names, global_deps, dep_map)
        if added_agents:
            logger.info("Auto-adding missing agents: %s", added_agents)
            # In a real implementation, we'd need to also fetch these agents' configs
            # For now, warn and continue with original set
            warnings_msg = f"Would auto-add agents: {added_agents} (not yet implemented)"
            logger.warning(warnings_msg)

    # Topological sort (Kahn's algorithm)
    # in_degree[x] = number of dependencies that x has (i.e., number of agents that must run before x)
    in_degree = {name: len(dep_map.get(name, set())) for name in agent_names}

    # For efficient lookup of dependents: which agents depend on a given node?
    dependents: dict[str, list[str]] = {name: [] for name in agent_names}
    for agent, deps in dep_map.items():
        for dep in deps:
            if dep in dependents:
                dependents[dep].append(agent)

    # Queue of agents with no dependencies (can run first)
    queue = [name for name, deg in in_degree.items() if deg == 0]
    ordered: list[str] = []

    while queue:
        current = queue.pop(0)
        ordered.append(current)

        # For each agent that depends on current, reduce their unmet dependencies
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Check for circular deps (remaining agents)
    if len(ordered) != len(agent_names):
        remaining = set(agent_names) - set(ordered)
        raise ValueError(f"Circular dependency or unresolved agents: {remaining}")

    # Build PipelineTask list in order
    tasks: list[PipelineTask] = []
    agent_cfg_map = {a.agent: a for a in enabled_agents}

    for agent_name in ordered:
        agent_cfg = agent_cfg_map[agent_name]

        # Create agent instance
        agent = create_agent(agent_name)

        # Determine task prompt
        task_prompt = agent_cfg.task if agent_cfg.task else f"Execute {agent_name} agent for: {{feature}}"

        # Override config if specified (AgentConfig is frozen, so create new instance)
        if agent_cfg.model or agent_cfg.max_tokens:
            import dataclasses
            from agents.agent_config import AgentConfig

            cfg = agent.config
            # Use dataclasses.replace to create new config with overrides
            new_cfg = dataclasses.replace(
                cfg,
                model=agent_cfg.model if agent_cfg.model else cfg.model,
                max_tokens=agent_cfg.max_tokens if agent_cfg.max_tokens else cfg.max_tokens
            )
            agent.config = new_cfg

        # Determine dependencies (previous agents in order)
        # agents that this agent depends on
        deps = [t.name for t in tasks if t.name in dep_map.get(agent_name, set())]

        task = PipelineTask(
            agent=agent,
            task=task_prompt,
            depends_on=deps,
        )
        tasks.append(task)

    logger.info("Built pipeline with %d agents in order: %s", len(tasks), [t.name for t in tasks])
    return tasks


# ============================================================================
# Helper Functions for Pipeline DAG (for UI)
# ============================================================================

def build_dag_dict(tasks: list[PipelineTask]) -> dict[str, Any]:
    """
    Build DAG representation for visualization.

    Returns:
        Dict with "nodes" and "edges" suitable for React Flow or similar.
    """
    nodes = []
    edges = []

    for i, task in enumerate(tasks):
        nodes.append({
            "id": task.name,
            "type": "agent",
            "data": {
                "agentName": task.name,
                "agentRole": task.agent.role if hasattr(task.agent, 'role') else "Agent",
            },
            "position": {"x": 100 + (i * 200) % 600, "y": 100 + (i // 3) * 150},  # Simple layout
        })

    for task in tasks:
        for dep in task.depends_on:
            edges.append({
                "id": f"{dep}->{task.name}",
                "source": dep,
                "target": task.name,
                "type": "smoothstep",
            })

    return {"nodes": nodes, "edges": edges}


def estimate_cost(tasks: list[PipelineTask]) -> float:
    """
    Estimate total pipeline cost based on agent configs and typical token usage.
    """
    from agents.agent_config import calculate_cost

    total = 0.0
    for task in tasks:
        # Rough estimate: input_tokens ~ 2000, output ~ 1000 for most agents
        # Could be refined per agent type
        input_tokens = 2000
        output_tokens = 1000
        total += calculate_cost(task.agent.config.model, input_tokens, output_tokens)

    return round(total, 4)


def estimate_duration(tasks: list[PipelineTask]) -> float:
    """
    Estimate total duration in seconds.
    Assumes parallel execution where possible (based on DAG).
    """
    # Simple approximation: longest path through DAG
    # Build adjacency and find critical path

    if not tasks:
        return 0.0

    # Rough per-agent duration (could be based on historical data)
    agent_durations = {
        "pm": 20.0,
        "ui_ux": 15.0,
        "frontend": 18.0,
        "backend": 20.0,
        "security": 25.0,
        "code_review": 15.0,
        "qa": 18.0,
        "devops": 12.0,
        "mobile": 20.0,
        "monetisation": 15.0,
    }

    # Build graph
    task_map = {task.name: task for task in tasks}
    durations = {}
    for task in tasks:
        durations[task.name] = agent_durations.get(task.name, 15.0)

    # Topological order already in tasks (should be)
    # Calculate earliest start time (EST)
    est = {task.name: 0.0 for task in tasks}

    for task in tasks:
        if task.depends_on:
            max_dep_finish = max(
                est[dep] + durations.get(dep, 15.0)
                for dep in task.depends_on
                if dep in est
            )
            est[task.name] = max_dep_finish

    # Total duration = max(est + duration)
    total = max(est[name] + durations.get(name, 15.0) for name in est)

    return round(total, 1)


# ============================================================================
# Convenience Functions
# ============================================================================

def load_all_templates() -> list[dict[str, Any]]:
    """
    Load all available pipeline templates from config/pipelines/.

    Returns:
        List of template metadata (name, description, agent count, etc.)
    """
    templates_dir = Path(__file__).parent.parent / "config" / "pipelines"
    if not templates_dir.exists():
        logger.warning("Templates directory does not exist: %s", templates_dir)
        return []

    templates = []
    for yaml_file in templates_dir.glob("*.yaml"):
        if yaml_file.name.startswith('_'):
            continue  # Skip partials
        try:
            data = load_yaml(yaml_file)
            # Extract metadata without full validation (fast)
            template_info = {
                "name": data.get("name", yaml_file.stem),
                "description": data.get("description", ""),
                "project_types": data.get("project_types", []),
                "agent_count": len(data.get("agents", [])),
                "file": str(yaml_file.relative_to(Path(__file__).parent.parent)),
            }
            templates.append(template_info)
        except Exception as e:
            logger.warning("Failed to load template %s: %s", yaml_file, e)

    return templates


def load_template(name: str) -> PipelineConfig | None:
    """
    Load a specific template by name.

    Searches in config/pipelines/ for matching YAML file.

    Args:
        name: Template name (filename without .yaml or full path)

    Returns:
        PipelineConfig if found, None otherwise
    """
    templates_dir = Path(__file__).parent.parent / "config" / "pipelines"

    # Try exact filename
    candidate = templates_dir / f"{name}.yaml"
    if candidate.exists():
        return load_pipeline_from_yaml(candidate)

    # Search for matching 'name' field in YAMLs
    for yaml_file in templates_dir.glob("*.yaml"):
        try:
            data = load_yaml(yaml_file)
            if data.get("name") == name:
                return load_pipeline_from_dict(data)
        except Exception:
            continue

    return None


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "AgentTaskConfig",
    "PipelineConfig",
    "PipelineValidationError",
    "PipelineValidationWarning",
    "ValidationResult",
    "load_pipeline_from_yaml",
    "load_pipeline_from_dict",
    "validate_pipeline",
    "build_pipeline_from_config",
    "build_dag_dict",
    "estimate_cost",
    "estimate_duration",
    "load_all_templates",
    "load_template",
]
