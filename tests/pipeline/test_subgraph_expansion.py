"""
Tests for subgraph expansion in config_loader.

Tests cover:
- Simple subgraph expansion (non-nested)
- Nested subgraphs (subgraph inside subgraph)
- Dependency preservation with edges to/from subgraph
- Expansion with explicit edges
- Subgraph name collision handling (prefixing)
"""
import pytest
from pipeline.config_loader import (
    PipelineConfig,
    AgentTaskConfig,
    EdgeConfig,
    SubgraphDefinition,
    build_pipeline_from_config,
    _expand_subgraphs,
)


# ============================================================================
# Test Helpers
# ============================================================================

def simple_agent(name, **kwargs):
    """Helper to create AgentTaskConfig with defaults."""
    defaults = {"agent": name, "enabled": True}
    defaults.update(kwargs)
    return AgentTaskConfig(**defaults)


def simple_edge(source, target, condition=None):
    """Helper to create EdgeConfig."""
    return EdgeConfig(source=source, target=target, condition=condition)


def simple_subgraph(name, agents, edges=None, description=""):
    """Helper to create SubgraphDefinition."""
    return SubgraphDefinition(name=name, description=description, agents=agents, edges=edges or [])


# ============================================================================
# Tests for _expand_subgraphs
# ============================================================================

def test_expand_simple_subgraph():
    """Test basic subgraph expansion: agent -> subgraph -> other."""
    config = PipelineConfig(
        name="test_simple",
        agents=[
            simple_agent("pm"),
            simple_agent("ci_cd_pipeline"),  # Subgraph reference
            simple_agent("monetisation"),
        ],
        subgraphs={
            "ci_cd_pipeline": simple_subgraph(
                name="ci_cd_pipeline",
                agents=[
                    simple_agent("build"),
                    simple_agent("test"),
                    simple_agent("deploy"),
                ],
                edges=[
                    simple_edge("build", "test"),
                    simple_edge("test", "deploy"),
                ]
            )
        },
        edges=[
            simple_edge("pm", "ci_cd_pipeline"),
            simple_edge("ci_cd_pipeline", "monetisation"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    # Should have: pm, build, test, deploy, monetisation = 5 agents
    agent_names = [a.agent for a in expanded_agents]
    assert set(agent_names) == {"pm", "build", "test", "deploy", "monetisation"}
    # Order should preserve: pm first (source of edge), then subgraph agents, then monetisation
    # The order within subgraph should be as defined: build, test, deploy
    assert agent_names == ["pm", "build", "test", "deploy", "monetisation"]

    # Edges: pm->build, build->test, test->deploy, deploy->monetisation
    edge_tuples = [(e.source, e.target) for e in expanded_edges]
    assert ("pm", "build") in edge_tuples
    assert ("build", "test") in edge_tuples
    assert ("test", "deploy") in edge_tuples
    assert ("deploy", "monetisation") in edge_tuples
    assert len(expanded_edges) == 4


def test_expand_nested_subgraphs():
    """Test subgraph containing another subgraph reference."""
    config = PipelineConfig(
        name="test_nested",
        agents=[
            simple_agent("pm"),
            simple_agent("full_ci"),  # References nested_sub which contains another subgraph
        ],
        subgraphs={
            "full_ci": simple_subgraph(
                name="full_ci",
                agents=[
                    simple_agent("build"),
                    simple_agent("nested_sub"),  # This is a nested subgraph
                    simple_agent("deploy"),
                ],
                edges=[
                    simple_edge("build", "nested_sub"),
                    simple_edge("nested_sub", "deploy"),
                ]
            ),
            "nested_sub": simple_subgraph(
                name="nested_sub",
                agents=[
                    simple_agent("test"),
                    simple_agent("security_scan"),
                ],
                edges=[
                    simple_edge("test", "security_scan"),
                ]
            ),
        },
        edges=[
            simple_edge("pm", "full_ci"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    # Expected agents: pm, build, test, security_scan, deploy
    agent_names = [a.agent for a in expanded_agents]
    assert set(agent_names) == {"pm", "build", "test", "security_scan", "deploy"}
    # Order should be: pm, build, test, security_scan, deploy
    # Because full_ci: build->nested_sub->deploy, and nested_sub: test->security_scan, so build->test->security_scan->deploy
    assert agent_names == ["pm", "build", "test", "security_scan", "deploy"]

    # Edges: pm->build, build->test, test->security_scan, security_scan->deploy
    edge_tuples = [(e.source, e.target) for e in expanded_edges]
    assert ("pm", "build") in edge_tuples
    assert ("build", "test") in edge_tuples
    assert ("test", "security_scan") in edge_tuples
    assert ("security_scan", "deploy") in edge_tuples
    assert len(expanded_edges) == 4


def test_expand_subgraph_with_multiple_references():
    """Test same subgraph used in multiple places (should be duplicated)."""
    config = PipelineConfig(
        name="test_multiple_refs",
        agents=[
            simple_agent("pm"),
            simple_agent("ci"),  # First use of ci_cd
            simple_agent("backend"),
            simple_agent("ci"),  # Second use of ci_cd (should duplicate)
        ],
        subgraphs={
            "ci": simple_subgraph(
                name="ci",
                agents=[
                    simple_agent("build"),
                    simple_agent("test"),
                ],
                edges=[
                    simple_edge("build", "test"),
                ]
            )
        },
        edges=[
            simple_edge("pm", "ci"),
            simple_edge("ci", "backend"),
            simple_edge("backend", "ci"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    # Agents: pm, build, test, backend, build2, test2
    # The two "ci" references each expand to build+test. Second instance should be prefixed.
    agent_names = [a.agent for a in expanded_agents]
    assert "pm" in agent_names
    assert "backend" in agent_names
    # First ci (unprefixed if no collision) - actually first instance: build, test
    # Second instance: ci::build, ci::test (prefixed)
    assert "build" in agent_names
    assert "test" in agent_names
    assert "ci::build" in agent_names
    assert "ci::test" in agent_names
    assert len(expanded_agents) == 6

    # Edges: pm->build, build->test, test->backend, backend->ci::build, ci::build->ci::test
    edge_tuples = [(e.source, e.target) for e in expanded_edges]
    assert ("pm", "build") in edge_tuples
    assert ("build", "test") in edge_tuples
    assert ("test", "backend") in edge_tuples
    assert ("backend", "ci::build") in edge_tuples
    assert ("ci::build", "ci::test") in edge_tuples


def test_expand_subgraph_with_conditions_on_edges():
    """Test that edge conditions are preserved through expansion."""
    config = PipelineConfig(
        name="test_conditions",
        agents=[
            simple_agent("backend"),
            simple_agent("ci"),
        ],
        subgraphs={
            "ci": simple_subgraph(
                name="ci",
                agents=[
                    simple_agent("build"),
                    simple_agent("deploy", task="Deploy if secure"),
                ],
                edges=[
                    simple_edge("build", "deploy", condition="result.build_score >= 80"),
                ]
            )
        },
        edges=[
            simple_edge("backend", "ci"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    # Check that condition made it through
    deploy_edges = [e for e in expanded_edges if e.target == "deploy"]
    assert len(deploy_edges) == 1
    assert deploy_edges[0].source == "build"
    assert deploy_edges[0].condition == "result.build_score >= 80"


def test_build_from_config_with_subgraph():
    """Test full build_from_config with subgraph produces correct tasks."""
    from agents.agent_config import create_agent as original_create_agent
    from pipeline.orchestrator import PipelineTask

    class StubAgent:
        def __init__(self, name, project_id=None):
            self.name = name
            self.config = None
        def run(self, task, context=None):
            pass

    def fake_create_agent(name, project_id=None):
        return StubAgent(name)

    # Temporarily patch create_agent
    import agents.agent_config
    original = agents.agent_config.create_agent
    agents.agent_config.create_agent = fake_create_agent

    try:
        config = PipelineConfig(
            name="test_build",
            agents=[
                simple_agent("a"),
                simple_agent("my_sub"),
                simple_agent("c"),
            ],
            subgraphs={
                "my_sub": simple_subgraph(
                    name="my_sub",
                    agents=[
                        simple_agent("b1"),
                        simple_agent("b2"),
                    ],
                    edges=[
                        simple_edge("b1", "b2"),
                    ]
                )
            },
            edges=[
                simple_edge("a", "my_sub"),
                simple_edge("my_sub", "c"),
            ],
        )

        # Build with orchestrator
        from pipeline.orchestrator import Orchestrator
        orch = Orchestrator(project_id="test")
        dag = orch.build_from_config(config)

        task_names = [t.name for t in dag.tasks]
        assert task_names == ["a", "b1", "b2", "c"]

        # Check edges in dag
        edge_tuples = [(e.source, e.target) for e in dag.edges]
        # Edges should be: a->b1, b1->b2, b2->c
        assert ("a", "b1") in edge_tuples
        assert ("b1", "b2") in edge_tuples
        assert ("b2", "c") in edge_tuples

    finally:
        agents.agent_config.create_agent = original


def test_circular_subgraph_reference_raises():
    """Test that circular subgraph references are detected."""
    config = PipelineConfig(
        name="test_circular",
        agents=[
            simple_agent("a"),
            simple_agent("b"),
        ],
        subgraphs={
            "a": simple_subgraph(
                name="a",
                agents=[
                    simple_agent("c"),
                ],
            ),
            "c": simple_subgraph(
                name="c",
                agents=[
                    simple_agent("a"),  # Circular!
                ],
            ),
        },
    )

    with pytest.raises(ValueError, match="Circular subgraph reference"):
        _expand_subgraphs(config)


def test_subgraph_with_no_internal_edges():
    """Test subgraph that has no internal edges (all agents run in parallel)."""
    config = PipelineConfig(
        name="test_parallel",
        agents=[
            simple_agent("pm"),
            simple_agent("ci"),
        ],
        subgraphs={
            "ci": simple_subgraph(
                name="ci",
                agents=[
                    simple_agent("build"),
                    simple_agent("test"),
                    simple_agent("lint"),
                ],
                edges=[]  # No internal edges => build, test, lint can run in parallel
            )
        },
        edges=[
            simple_edge("pm", "ci"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    agent_names = [a.agent for a in expanded_agents]
    assert set(agent_names) == {"pm", "build", "test", "lint"}
    # Since ci is a group with all parallel, edges should be: pm->build, pm->test, pm->lint
    edge_tuples = [(e.source, e.target) for e in expanded_edges]
    # All agents in ci get an edge from pm
    assert ("pm", "build") in edge_tuples
    assert ("pm", "test") in edge_tuples
    assert ("pm", "lint") in edge_tuples
    assert len(expanded_edges) == 3


def test_subgraph_entry_exit_detection():
    """Test that entry/exit agents are correctly identified."""
    # Subgraph: A -> B -> C, and D with no edges
    config = PipelineConfig(
        name="test_entry_exit",
        agents=[
            simple_agent("start"),
            simple_agent("my_sub"),
        ],
        subgraphs={
            "my_sub": simple_subgraph(
                name="my_sub",
                agents=[
                    simple_agent("A"),
                    simple_agent("B"),
                    simple_agent("C"),
                    simple_agent("D"),  # No edges in or out
                ],
                edges=[
                    simple_edge("A", "B"),
                    simple_edge("B", "C"),
                ]
            )
        },
        edges=[
            simple_edge("start", "my_sub"),
        ],
    )

    expanded_agents, expanded_edges = _expand_subgraphs(config)

    # Entry: A (no one points to A inside subgraph), D (also no incoming) --> both should connect to start
    # Exit: C (B->C but C points to nothing), D (no outgoing) --> both should connect to downstream if any

    edge_tuples = [(e.source, e.target) for e in expanded_edges]
    # start connects to entry agents
    assert ("start", "A") in edge_tuples
    assert ("start", "D") in edge_tuples
    # B is not an entry (A->B), so start->B should NOT be present
    assert ("start", "B") not in edge_tuples
    assert ("start", "C") not in edge_tuples
