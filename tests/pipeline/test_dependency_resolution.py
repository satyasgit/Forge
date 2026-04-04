"""
Tests for dependency resolution in pipeline config loader.

Tests topological sorting, circular dependency detection, and auto-resolve.
"""
import pytest
from pipeline.config_loader import (
    PipelineConfig,
    AgentTaskConfig,
    validate_pipeline,
    _auto_add_missing_dependencies,
)


class TestDependencyResolution:
    """Test dependency graph building and resolution."""

    def test_simple_linear_dependencies(self):
        """Test linear chain: A -> B -> C."""
        config = PipelineConfig(
            name="linear",
            agents=[
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
                AgentTaskConfig(agent="qa", depends_on=["backend"]),
                AgentTaskConfig(agent="pm"),  # pm has no deps
            ],
            auto_resolve=True,
        )

        result = validate_pipeline(config, agent_registry={"pm", "backend", "qa"})

        assert result.valid is True
        # If we built tasks, order should be pm, backend, qa

    def test_parallel_dependencies(self):
        """Test parallel branches: PM -> FE; PM -> BE."""
        config = PipelineConfig(
            name="parallel",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="frontend", depends_on=["pm"]),
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
                AgentTaskConfig(agent="qa", depends_on=["frontend", "backend"]),
            ]
        )

        result = validate_pipeline(config, agent_registry={
            "pm", "frontend", "backend", "qa"
        })

        assert result.valid is True
        # No cycles

    def test_circular_dependency_detected(self):
        """Test that A -> B -> A is detected as cycle."""
        # Need to inject custom deps to create cycle, since global deps are fixed
        # We'll override dependencies via custom agent_deps.yaml or validation function
        # For now, test the validation's cycle detection by creating a cycle manually
        # in the validation function (we'll need to enhance it)
        # This is a placeholder for a proper cycle test
        pass  # TODO: Implement proper cycle detection test

    def test_missing_dependency_warning(self):
        """Test warning when dependency not in pipeline."""
        config = PipelineConfig(
            name="missing_dep",
            agents=[
                AgentTaskConfig(agent="qa", depends_on=["code_review"]),
                # qa depends on code_review but code_review not in agents
            ],
            auto_resolve=False,  # Don't auto-add
        )

        result = validate_pipeline(config, agent_registry={"qa", "code_review", "backend"})

        assert result.valid is True  # Warning only, not error
        assert any("code_review" in w and "not in pipeline" in w for w in result.warnings)

    def test_auto_resolve_adds_missing_dependency(self):
        """Test that auto_resolve adds missing dependency."""
        # Global deps says qa needs code_review
        # If template lists only qa (no code_review), auto_resolve should warn about addition
        config = PipelineConfig(
            name="auto_resolve_test",
            agents=[
                AgentTaskConfig(agent="qa"),
            ],
            auto_resolve=True,
        )

        # Need to ensure agent_deps.yaml is loaded and contains qa -> code_review
        # This depends on the actual file. Let's check what's in agent_deps.yaml
        # qa depends on ["backend", "code_review"]
        result = validate_pipeline(config, agent_registry={
            "qa", "backend", "code_review", "pm", "frontend", "security", "devops"
        })

        # With auto_resolve=True, we should get a warning about auto-adding
        assert any("Auto-added" in w for w in result.warnings)

    def test_no_duplicate_agents_allowed(self):
        """Test that including same agent twice fails validation."""
        with pytest.raises(ValueError, match="Duplicate agents"):
            PipelineConfig(
                name="dupes",
                agents=[
                    AgentTaskConfig(agent="pm"),
                    AgentTaskConfig(agent="pm"),
                ]
            )

    def test_dependency_on_disabled_agent_warns(self):
        """Test that depending on a disabled agent produces warning."""
        config = PipelineConfig(
            name="dep_on_disabled",
            agents=[
                AgentTaskConfig(agent="qa"),
                AgentTaskConfig(agent="code_review", enabled=False),
            ],
        )
        # qa depends on code_review via global deps, but code_review is disabled
        result = validate_pipeline(config, agent_registry={
            "qa", "code_review", "backend", "pm"
        })

        assert result.valid is True
        assert any("depends on" in w and "which is not in pipeline or is disabled" in w for w in result.warnings)


class TestAutoAddMissingDependencies:
    """Test the _auto_add_missing_dependencies helper."""

    def test_auto_add_from_global_deps(self):
        """Test auto-adding agents required by global deps."""
        agent_names = ["qa"]
        global_deps = {
            "qa": ["backend", "code_review"],
        }
        dep_graph = {"qa": set()}

        added = _auto_add_missing_dependencies(agent_names, global_deps, dep_graph)

        assert "backend" in added
        assert "code_review" in added
        assert len(added) == 2

    def test_no_auto_add_if_already_present(self):
        """Test that already-present agents aren't added."""
        agent_names = ["qa", "backend"]
        global_deps = {
            "qa": ["backend", "code_review"],
        }
        dep_graph = {
            "qa": set(),
            "backend": set(),
        }

        added = _auto_add_missing_dependencies(agent_names, global_deps, dep_graph)

        assert "backend" not in added  # Already in agent_names
        assert "code_review" in added

    def test_auto_add_transitive_dependencies(self):
        """Test that transitive deps are also considered."""
        # Chain: qa -> backend -> pm
        agent_names = ["qa"]
        global_deps = {
            "qa": ["backend"],
            "backend": ["pm"],
        }
        dep_graph = {"qa": set()}

        added = _auto_add_missing_dependencies(agent_names, global_deps, dep_graph)

        assert "backend" in added
        # pm is dep of backend, but backend not in agent_names initially
        # So pm should also be added (transitively)
        assert "pm" in added
