"""
Tests for conditional edge execution in the orchestrator.

Tests cover:
- Condition evaluation (true/false)
- Edge condition checking with result context
- Deadlock detection when conditions never met
- Integration of conditional edges into execution flow
"""
import pytest
import asyncio
from pipeline.orchestrator import Orchestrator, PipelineTask, PipelineDAG
from pipeline.config_loader import EdgeConfig
from agents.base import AgentResult


# ============================================================================
# Test Helpers
# ============================================================================

class SyncFakeAgent:
    """Simple synchronous fake agent that returns a predetermined AgentResult."""
    def __init__(self, name, result):
        self.name = name
        self.result = result

    def run(self, task, context=None):
        return self.result


def make_result(agent_name, output="", **kwargs):
    """Helper to create AgentResult with defaults.

    Any keyword arguments that are not standard AgentResult fields
    are stored in the metadata dict and accessible as attributes via __getattr__.
    """
    # Standard AgentResult fields
    known_fields = {
        'input_tokens', 'output_tokens', 'duration_seconds', 'errors',
        'model_used', 'retries', 'state', 'artifact', 'metadata'
    }
    # Separate metadata
    metadata = {}
    for key in list(kwargs.keys()):
        if key not in known_fields:
            metadata[key] = kwargs.pop(key)

    defaults = {
        "agent_name": agent_name,
        "output": output,
        "input_tokens": kwargs.get("input_tokens", 0),
        "output_tokens": kwargs.get("output_tokens", 0),
        "duration_seconds": 0.1,
        "errors": [],
        "model_used": kwargs.get("model_used", "claude-sonnet-4-5"),
        "metadata": metadata,
    }
    defaults.update(kwargs)
    return AgentResult(**defaults)


def create_dag_with_edges(edges_config, agents_results):
    """
    Helper to create a PipelineDAG with given edges and agent results.

    Args:
        edges_config: List of (source, target, condition) tuples
        agents_results: Dict mapping agent name -> AgentResult

    Returns:
        PipelineDAG
    """
    tasks = []
    # Collect all agent names from edges and standalone?
    agent_names = set()
    for src, tgt, _ in edges_config:
        agent_names.add(src)
        agent_names.add(tgt)
    # Also include any extra agents in results
    agent_names.update(agents_results.keys())

    # Create tasks for each agent, with depends_on initially empty (we'll set via edges)
    for name in sorted(agent_names):  # sorted to have deterministic order
        result = agents_results.get(name, make_result(name, f"Output from {name}"))
        agent = SyncFakeAgent(name, result)
        task = PipelineTask(agent=agent, task=f"Task for {name}", depends_on=[])
        tasks.append(task)

    # Build edges list
    edges = [
        EdgeConfig(source=src, target=tgt, condition=cond)
        for src, tgt, cond in edges_config
    ]

    # Set depends_on on tasks based on edges (target depends on source)
    task_by_name = {t.name: t for t in tasks}
    for edge in edges:
        if edge.target in task_by_name:
            task_by_name[edge.target].depends_on.append(edge.source)

    return PipelineDAG(tasks=tasks, edges=edges)


# ============================================================================
# Tests for Conditional Execution
# ============================================================================

@pytest.mark.asyncio
async def test_simple_conditional_true():
    """Test that a conditional edge that evaluates to True allows execution."""
    # A -> B with condition "True"
    result_a = make_result("a", "A output")
    result_b = make_result("b", "B output")
    agents_results = {"a": result_a, "b": result_b}

    dag = create_dag_with_edges(
        edges_config=[("a", "b", "True")],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results
    assert run.results["b"].output == "B output"


@pytest.mark.asyncio
async def test_conditional_false_skips_target():
    """Test that a conditional edge evaluating to False prevents execution of target."""
    # A -> B with condition that is False (skip_flag is 0, condition checks ==1)
    result_a = make_result("a", "A output", skip_flag=0)
    result_b = make_result("b", "B output")
    agents_results = {"a": result_a, "b": result_b}

    dag = create_dag_with_edges(
        edges_config=[("a", "b", "result.skip_flag == 1")],  # condition False
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" not in run.results  # B should not have run


@pytest.mark.asyncio
async def test_multiple_dependencies_with_mixed_conditions():
    """Test target with two conditional dependencies: one true, one false -> target not ready."""
    # A -> C (cond True), B -> C (cond False)
    result_a = make_result("a", "A output", value=5)
    result_b = make_result("b", "B output", allow=False)
    result_c = make_result("c", "C output")
    agents_results = {"a": result_a, "b": result_b, "c": result_c}

    dag = create_dag_with_edges(
        edges_config=[
            ("a", "c", "result.value > 0"),  # True
            ("b", "c", "result.allow is True"),  # False
        ],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results
    assert "c" not in run.results  # C blocked by b's false condition


@pytest.mark.asyncio
async def test_deadlock_when_condition_never_met():
    """Test that if a task's edge condition never met, deadlock is detected."""
    # A -> B condition always False
    result_a = make_result("a", "A output")
    result_b = make_result("b", "B output")
    agents_results = {"a": result_a, "b": result_b}

    dag = create_dag_with_edges(
        edges_config=[("a", "b", "False")],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    with pytest.raises(RuntimeError, match="Dependency deadlock"):
        await orch.run(dag)


@pytest.mark.asyncio
async def test_condition_can_access_output_string():
    """Test that condition can inspect result.output string."""
    # A -> B condition: " 'PASS' in result.output "
    result_a = make_result("a", "Security scan result: PASS")
    result_b = make_result("b", "B output")
    agents_results = {"a": result_a, "b": result_b}

    dag = create_dag_with_edges(
        edges_config=[("a", "b", "'PASS' in result.output")],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results


@pytest.mark.asyncio
async def test_no_edges_fallback_to_simple_dependency():
    """Test that when no explicit edges, simple all(dep in completed) logic works."""
    # A -> B with no explicit edge (dag.edges empty)
    result_a = make_result("a", "A output")
    result_b = make_result("b", "B output")
    agents_results = {"a": result_a, "b": result_b}

    tasks = [
        PipelineTask(
            agent=SyncFakeAgent("a", result_a),
            task="Task A",
            depends_on=[]
        ),
        PipelineTask(
            agent=SyncFakeAgent("b", result_b),
            task="Task B",
            depends_on=["a"]
        ),
    ]
    dag = PipelineDAG(tasks=tasks, edges=[])

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results


@pytest.mark.asyncio
async def test_root_nodes_without_dependencies_run_first():
    """Test that tasks with no incoming dependencies start immediately."""
    # A (no deps) -> B, C (both depend on A)
    result_a = make_result("a", "A output")
    result_b = make_result("b", "B output")
    result_c = make_result("c", "C output")
    agents_results = {"a": result_a, "b": result_b, "c": result_c}

    dag = create_dag_with_edges(
        edges_config=[
            ("a", "b", "True"),
            ("a", "c", "True"),
        ],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results
    assert "c" in run.results
    # All should have executed


@pytest.mark.asyncio
async def test_multiple_parallel_branches_with_conditions():
    """Test parallel branches where each target has different conditions."""
    # A -> X (cond: value>5), B -> X (cond: flag=True), A -> Y (cond: True), B -> Y (cond: False)
    result_a = make_result("a", "A output", value=10, flag=False)
    result_b = make_result("b", "B output", value=3, flag=True)
    result_x = make_result("x", "X output")
    result_y = make_result("y", "Y output")
    agents_results = {"a": result_a, "b": result_b, "x": result_x, "y": result_y}

    dag = create_dag_with_edges(
        edges_config=[
            ("a", "x", "result.value > 5"),  # True
            ("b", "x", "result.flag is True"),  # True
            ("a", "y", "True"),  # True
            ("b", "y", "False"),  # False -> blocks Y
        ],
        agents_results=agents_results
    )

    orch = Orchestrator(project_id="test")
    run = await orch.run(dag)

    assert "a" in run.results
    assert "b" in run.results
    # X needs both a and b edges satisfied? Actually X depends on both a and b. Both edges must be satisfied.
    # a->x true, b->x true => X runs
    assert "x" in run.results
    # Y depends on a and b, but b->y false => Y blocked
    assert "y" not in run.results


# ============================================================================
# Tests for build_from_config with edges
# ============================================================================

def test_build_from_config_with_explicit_edges(monkeypatch):
    """Test that build_from_config uses explicit edges and returns them in DAG."""
    from agents.agent_config import create_agent as original_create_agent

    # We'll patch create_agent to return stub agents
    class StubAgent:
        def __init__(self, name, project_id=None):
            self.name = name
            # Minimal attributes

    def fake_create_agent(name, project_id=None):
        return StubAgent(name)

    monkeypatch.setattr('agents.agent_config.create_agent', fake_create_agent)

    from pipeline.orchestrator import Orchestrator
    from pipeline.config_loader import PipelineConfig, AgentTaskConfig, EdgeConfig

    config = PipelineConfig(
        name="test_edges",
        agents=[
            AgentTaskConfig(agent="a"),
            AgentTaskConfig(agent="b"),
            AgentTaskConfig(agent="c"),
        ],
        edges=[
            EdgeConfig(source="a", target="b", condition="result.value > 0"),
            EdgeConfig(source="b", target="c", condition=None),  # unconditional
        ]
    )

    orch = Orchestrator(project_id="test")
    dag = orch.build_from_config(config)

    # Check tasks
    task_names = [t.name for t in dag.tasks]
    assert set(task_names) == {"a", "b", "c"}
    # Should be topologically sorted: a, b, c
    assert task_names == ["a", "b", "c"]

    # Check edges
    assert len(dag.edges) == 2
    assert dag.edges[0].source == "a" and dag.edges[0].target == "b"
    assert dag.edges[0].condition == "result.value > 0"
    assert dag.edges[1].source == "b" and dag.edges[1].target == "c"
    assert dag.edges[1].condition is None


def test_build_from_config_without_edges_uses_implicit_deps(monkeypatch):
    """Test that when no edges provided, dependencies come from agent depends_on."""
    from agents.agent_config import create_agent as original_create_agent

    class StubAgent:
        def __init__(self, name, project_id=None):
            self.name = name

    def fake_create_agent(name, project_id=None):
        return StubAgent(name)

    monkeypatch.setattr('agents.agent_config.create_agent', fake_create_agent)

    from pipeline.orchestrator import Orchestrator
    from pipeline.config_loader import PipelineConfig, AgentTaskConfig

    config = PipelineConfig(
        name="test_implicit",
        agents=[
            AgentTaskConfig(agent="a"),
            AgentTaskConfig(agent="b", depends_on=["a"]),
            AgentTaskConfig(agent="c", depends_on=["b"]),
        ],
        edges=[]  # no explicit edges
    )

    orch = Orchestrator(project_id="test")
    dag = orch.build_from_config(config)

    task_names = [t.name for t in dag.tasks]
    assert task_names == ["a", "b", "c"]

    # Edges should be empty because we didn't use explicit edges
    assert len(dag.edges) == 0

    # Dependencies are still encoded in task.depends_on
    assert dag.tasks[1].depends_on == ["a"]
    assert dag.tasks[2].depends_on == ["b"]
