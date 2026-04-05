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


class EdgeConfig(BaseModel):
    """Configuration for an edge (dependency) between agents."""

    source: str = Field(..., description="Source agent name")
    target: str = Field(..., description="Target agent name")
    condition: str | None = Field(None, description="Optional Python expression to evaluate (uses 'results' dict)")

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        """Basic validation of condition expression (syntax only)."""
        if v is None:
            return v
        # Very basic check - full validation happens at runtime
        if not v.strip():
            raise ValueError("Condition cannot be empty")
        return v


class SubgraphDefinition(BaseModel):
    """Definition of a reusable subgraph (pipeline component)."""

    name: str = Field(..., description="Unique subgraph identifier")
    description: str = Field("", description="Human-readable description")
    agents: list[AgentTaskConfig] = Field(..., description="Agents within the subgraph")
    edges: list[EdgeConfig] = Field(default_factory=list, description="Explicit edges within subgraph")

    @model_validator(mode='after')
    def validate_no_duplicate_agents(self) -> SubgraphDefinition:
        """Ensure no agent appears twice in subgraph."""
        agent_names = [a.agent for a in self.agents if a.enabled]
        if len(agent_names) != len(set(agent_names)):
            duplicates = [name for name in agent_names if agent_names.count(name) > 1]
            raise ValueError(f"Duplicate agents in subgraph '{self.name}': {duplicates}")
        return self


class PipelineConfig(BaseModel):
    """Complete pipeline configuration."""

    version: str = Field("1.0", description="Schema version")
    name: str = Field(..., description="Pipeline name/template identifier")
    description: str = Field("", description="Human-readable description")
    project_types: list[str] = Field(default_factory=list, description="Suitable project types (web, mobile, api, saas, etc.)")

    agents: list[AgentTaskConfig] = Field(..., description="List of agent configurations")
    edges: list[EdgeConfig] = Field(default_factory=list, description="Explicit edges (overrides auto deps)")
    subgraphs: dict[str, SubgraphDefinition] = Field(default_factory=dict, description="Named subgraph definitions for reuse")

    auto_resolve: bool = Field(True, description="Auto-add missing dependencies from global deps")
    strict_validation: bool = Field(False, description="Fail on validation warnings (vs just warn)")

    settings: dict[str, Any] = Field(default_factory=dict, description="Pipeline-level settings")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @model_validator(mode='after')
    def validate_no_duplicate_agents(self) -> PipelineConfig:
        """Ensure no regular agent appears twice (subgraph refs can duplicate)."""
        # Only check duplicates among agents that are NOT subgraph references.
        # Subgraph references may appear multiple times; they'll be expanded with unique names.
        agent_names = [
            a.agent for a in self.agents if a.enabled and a.agent not in self.subgraphs
        ]
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
# Data Structures for Pipeline Execution
# ============================================================================

@dataclass
class PipelineDAG:
    """Combined tasks and edges for pipeline execution with conditional support."""
    tasks: list[PipelineTask]
    edges: list[EdgeConfig]  # Explicit edges with optional conditions


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


def _expand_subgraphs(config: PipelineConfig) -> tuple[list[AgentTaskConfig], list[EdgeConfig]]:
    """
    Expand subgraphs in the configuration into flat lists of agents and edges.

    Args:
        config: PipelineConfig with possible subgraph references

    Returns:
        Tuple of (expanded_agents, expanded_edges)
    """
    subgraphs: dict[str, SubgraphDefinition] = config.subgraphs or {}

    # Detect circular subgraph references
    def detect_cycle(name: str, path: list[str]):
        if name in path:
            cycle = " -> ".join(path + [name])
            raise ValueError(f"Circular subgraph reference: {cycle}")
        if name in subgraphs:
            for agent in subgraphs[name].agents:
                if agent.agent in subgraphs:
                    detect_cycle(agent.agent, path + [name])

    for sg in subgraphs:
        detect_cycle(sg, [])

    def find_entry_agents(subgraph: SubgraphDefinition) -> set[str]:
        """Agents in subgraph with no incoming internal edges."""
        targets = {e.target for e in subgraph.edges}
        return {a.agent for a in subgraph.agents} - targets

    def find_exit_agents(subgraph: SubgraphDefinition) -> set[str]:
        """Agents in subgraph with no outgoing internal edges."""
        sources = {e.source for e in subgraph.edges}
        return {a.agent for a in subgraph.agents} - sources

    def expand(agent_configs: list[AgentTaskConfig], external_edges: list[EdgeConfig]) -> tuple[list[AgentTaskConfig], list[EdgeConfig]]:
        """
        Recursively expand agent list.

        Args:
            agent_configs: Agents to expand (may contain subgraph refs)
            external_edges: Edges that connect these agents to the outside context
                            (edges where source or target is an agent in agent_configs,
                            but may reference subgraph names that need expansion)
        Returns:
            (expanded_agents, expanded_edges)
        """
        result_agents: list[AgentTaskConfig] = []
        result_edges: list[EdgeConfig] = []
        seen_names: set[str] = set()

        # Build a map of agent name -> AgentTaskConfig for this level
        agent_map = {a.agent: a for a in agent_configs}

        # Process each agent in order
        for agent_cfg in agent_configs:
            name = agent_cfg.agent

            if name in subgraphs:
                # This is a subgraph reference; expand it
                subgraph = subgraphs[name]
                logger.debug("Expanding subgraph '%s'", name)

                # Recursively expand the subgraph's own agents and internal edges
                nested_agents, nested_edges = expand(subgraph.agents, subgraph.edges)

                # Determine entry and exit agents of the subgraph (based on original names)
                entry_orig = find_entry_agents(subgraph)
                exit_orig = find_exit_agents(subgraph)

                # We'll need to map original names to expanded names, considering possible renaming due to collisions
                # Collect mapping from original to final expanded name(s)
                orig_to_expanded: dict[str, list[str]] = {}
                for na in nested_agents:
                    # Determine original name: if prefixed, get part after ::
                    if "::" in na.agent:
                        # This agent came from a nested subgraph that had a prefix from that subgraph's name.
                        # But here we need to map against the direct subgraph's defined agent names.
                        # We need to see if the original agent name (without any prefix) is in entry_orig or exit_orig.
                        # The agent.agent may be like "nested_sub::build" when subgraph name is "ci" and it contains nested_sub.
                        # That's not directly matching entry_orig. Actually entry_orig are the names defined directly inside this subgraph.
                        # So we need to reconstruct mapping: if the agent's name doesn't contain "::", then it's direct.
                        # If it contains "::", then the original name is the suffix. But careful: The prefix used is the subgraph name of the nested subgraph.
                        # For our purpose, we need to know which expanded agents correspond to which direct subgraph agents.
                        # Actually nested_agents may have prefixed names only if there were collisions within the nested expansion.
                        # They will not be prefixed with current subgraph name, but with deeper subgraph name.
                        # The direct agents from this subgraph (i.e., first-level nested) will retain their original names (no prefix), unless there is a name collision among them.
                        # So we can handle: if na.agent in entry_orig (direct match), then that's an entry expansion.
                        # Also if na.agent starts with something else, we check suffix after last "::" if it matches an entry_orig? But that would be nested deeper.
                        # However entry/exit agents are only for this subgraph's direct interface. So we only care about direct child agents (no prefix from a deeper subgraph) OR prefixed versions of direct agents if collision forced renaming.
                        # The agent_cfg in subgraph.agents has agent names. Those directly appear in nested_agents, unless collision caused prefixed with this subgraph's name.
                        # In our expansion algorithm, we only prefix with current subgraph name when a duplicate is detected within the same expansion level (i.e., two agents from the same subgraph or from multiple references). So a direct agent from this subgraph can be either original name or prefixed with this subgraph's name (if name collision with another agent in the same expanded set). But entry_orig contains the original names (as defined in subgraph). So we need to check if na.agent == orig, or na.agent == f"{name}::{orig}".
                        # We'll map each original agent to a set of expanded names.
                        pass  # We'll handle more robustly below
                    else:
                        # No prefix, original name is na.agent
                        if na.agent in entry_orig:
                            orig_to_expanded.setdefault(na.agent, []).append(na.agent)
                        if na.agent in exit_orig:
                            orig_to_expanded.setdefault(na.agent, []).append(na.agent)
                # Additionally, we might have prefixed versions: if we prefixed an agent because of duplication, the name becomes f"{name}::{orig}". So we should also consider those as matching original.
                for orig in entry_orig:
                    prefixed = f"{name}::{orig}"
                    # If prefixed is in expanded names (from nested_agents), add it
                    if any(na.agent == prefixed for na in nested_agents):
                        orig_to_expanded.setdefault(orig, []).append(prefixed)
                for orig in exit_orig:
                    prefixed = f"{name}::{orig}"
                    if any(na.agent == prefixed for na in nested_agents):
                        orig_to_expanded.setdefault(orig, []).append(prefixed)

                # Process external edges that connect to/from this subgraph
                for edge in external_edges:
                    if edge.target == name:
                        # Edge targets this subgraph -> connect source to all entry points
                        for entry_orig_name in entry_orig:
                            for exp_name in orig_to_expanded.get(entry_orig_name, [entry_orig_name]):
                                result_edges.append(EdgeConfig(
                                    source=edge.source,
                                    target=exp_name,
                                    condition=edge.condition,
                                ))
                    elif edge.source == name:
                        # Edge originates from this subgraph -> connect all exit points to target
                        for exit_orig_name in exit_orig:
                            for exp_name in orig_to_expanded.get(exit_orig_name, [exit_orig_name]):
                                result_edges.append(EdgeConfig(
                                    source=exp_name,
                                    target=edge.target,
                                    condition=edge.condition,
                                ))

                # Add nested agents (with possible prefixing) to result
                for na in nested_agents:
                    if na.agent in seen_names:
                        raise ValueError(f"Duplicate agent name after expansion: {na.agent}")
                    result_agents.append(na)
                    seen_names.add(na.agent)

                # Include the subgraph's internal edges (they reference expanded agent names)
                result_edges.extend(nested_edges)

            else:
                # Not a subgraph: just add the agent
                if name in seen_names:
                    raise ValueError(f"Duplicate agent name: {name}")
                result_agents.append(agent_cfg)
                seen_names.add(name)

        # Add internal edges from this level's subgraph expansions (they are already included in nested_edges and passed through via recursion),
        # but we also need to add edges that were in external_edges that connect agents within agent_configs (i.e., edges that are not involving a subgraph reference, but between two regular agents). Those should be added directly if both source and target are not subgraphs.
        # Actually external_edges may contain edges that are between agents in agent_configs that are both not subgraphs. Those need to be added to result_edges as-is, but careful to avoid duplicates if they were already added via parent? They weren't because we are processing them now.
        for edge in external_edges:
            src_is_subgraph = edge.source in subgraphs
            tgt_is_subgraph = edge.target in subgraphs
            if not src_is_subgraph and not tgt_is_subgraph:
                # Both are regular agents; they should be in result_agents (maybe not yet added? order may cause that)
                # Just add the edge
                result_edges.append(EdgeConfig(source=edge.source, target=edge.target, condition=edge.condition))

        return result_agents, result_edges

    # Expand root-level agents with top-level edges
    expanded_agents, expanded_edges = expand(config.agents, config.edges)

    logger.info("Expanded %d agents -> %d agents, %d edges",
                len(config.agents), len(expanded_agents), len(expanded_edges))
    return expanded_agents, expanded_edges


def build_pipeline_from_config(
    config: PipelineConfig,
    agent_deps_override: dict[str, list[str]] | None = None
) -> PipelineDAG:
    """
    Convert PipelineConfig to PipelineDAG with tasks and conditional edges.

    This function:
    1. Expands any subgraph definitions into flat agent lists and edges
    2. Builds dependency graph from explicit edges or implicit deps
    3. Topologically sorts and creates PipelineTask objects

    Args:
        config: Validated pipeline configuration
        agent_deps_override: Override global dependencies (for testing)

    Returns:
        PipelineDAG with tasks in topological order and edges (with conditions)

    Raises:
        ValueError: If dependency resolution fails or edges reference unknown agents
    """
    from agents.agent_config import create_agent
    from pipeline.orchestrator import PipelineTask

    # Step 1: Expand subgraphs if any
    if config.subgraphs:
        agent_configs, explicit_edges = _expand_subgraphs(config)
        logger.info("Subgraph expansion: %d original agents -> %d expanded",
                    len(config.agents), len(agent_configs))
    else:
        agent_configs = [a for a in config.agents if a.enabled]
        explicit_edges = config.edges

    # Now agent_configs contains only regular AgentTaskConfig (no subgraph refs)
    agent_names = [a.agent for a in agent_configs]
    agent_cfg_map = {a.agent: a for a in agent_configs}

    # Determine dependency graph and edges to use
    edges_used: list[EdgeConfig] = []
    dep_map: dict[str, set[str]] = {name: set() for name in agent_names}

    if explicit_edges:
        # Explicit edges provided: use only these (override auto deps)
        logger.info("Using explicit edges (%d edges)", len(explicit_edges))

        # Validate edges reference known agents
        for edge in explicit_edges:
            if edge.source not in agent_names:
                raise ValueError(f"Edge source '{edge.source}' not in agents. Available: {agent_names}")
            if edge.target not in agent_names:
                raise ValueError(f"Edge target '{edge.target}' not in agents. Available: {agent_names}")

        edges_used = explicit_edges

        # Build dep_map from edges
        for edge in explicit_edges:
            dep_map[edge.target].add(edge.source)
    else:
        # No explicit edges: use global deps + per-agent depends_on
        logger.info("Using implicit dependencies (global deps + per-agent)")

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

        # Add global deps to dep_map
        for agent_name in agent_names:
            if agent_name in global_deps:
                for dep in global_deps[agent_name]:
                    if dep in agent_names:
                        dep_map[agent_name].add(dep)

        # Add per-agent overrides (depends_on)
        for agent_cfg in agent_configs:
            if agent_cfg.depends_on:
                for dep in agent_cfg.depends_on:
                    if dep in agent_names:
                        dep_map[agent_cfg.agent].add(dep)

        # Auto-resolve if enabled
        if config.auto_resolve:
            added_agents = _auto_add_missing_dependencies(agent_names, global_deps, dep_map)
            if added_agents:
                logger.info("Auto-adding missing agents: %s", added_agents)
                warnings_msg = f"Would auto-add agents: {added_agents} (not yet implemented)"
                logger.warning(warnings_msg)

    # Topological sort (Kahn's algorithm)
    in_degree = {name: len(dep_map.get(name, set())) for name in agent_names}

    dependents: dict[str, list[str]] = {name: [] for name in agent_names}
    for agent, deps in dep_map.items():
        for dep in deps:
            if dep in dependents:
                dependents[dep].append(agent)

    queue = [name for name, deg in in_degree.items() if deg == 0]
    ordered: list[str] = []

    while queue:
        current = queue.pop(0)
        ordered.append(current)

        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(agent_names):
        remaining = set(agent_names) - set(ordered)
        raise ValueError(f"Circular dependency or unresolved agents: {remaining}")

    # Build PipelineTask list
    tasks: list[PipelineTask] = []

    for agent_name in ordered:
        agent_cfg = agent_cfg_map[agent_name]

        # Create agent instance
        agent = create_agent(agent_name)

        # Determine task prompt
        task_prompt = agent_cfg.task if agent_cfg.task else f"Execute {agent_name} agent for: {{feature}}"

        # Handle config overrides (model, max_tokens)
        if agent_cfg.model or agent_cfg.max_tokens:
            import dataclasses
            from agents.agent_config import AgentConfig

            cfg = agent.config
            new_cfg = dataclasses.replace(
                cfg,
                model=agent_cfg.model if agent_cfg.model else cfg.model,
                max_tokens=agent_cfg.max_tokens if agent_cfg.max_tokens else cfg.max_tokens
            )
            agent.config = new_cfg

        # Determine dependencies: all agents that appear as sources in edges_used where target == agent_name
        # If edges_used is empty, fall back to dep_map (which has the same info from implicit deps)
        deps = [t.name for t in tasks if t.name in dep_map.get(agent_name, set())]

        task = PipelineTask(
            agent=agent,
            task=task_prompt,
            depends_on=deps,
        )
        tasks.append(task)

    logger.info("Built pipeline with %d agents in order: %s (edges: %d)", len(tasks), [t.name for t in tasks], len(edges_used))
    return PipelineDAG(tasks=tasks, edges=edges_used)


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
    "PipelineDAG",
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
