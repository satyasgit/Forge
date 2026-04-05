"""
Tests for Pipeline Config Loader.

Tests YAML loading, validation, and conversion to PipelineTask.
"""
import pytest
from pathlib import Path
from pipeline.config_loader import (
    load_pipeline_from_yaml,
    load_pipeline_from_dict,
    validate_pipeline,
    PipelineConfig,
    AgentTaskConfig,
    PipelineValidationError,
    build_pipeline_from_config,
    load_all_templates,
    load_template,
    build_dag_dict,
    estimate_cost,
    estimate_duration,
)


class TestLoadPipelineFromYAML:
    """Test loading pipeline from YAML files."""

    def test_load_valid_template(self, tmp_path):
        """Test loading a valid template YAML."""
        yaml_content = """
version: "1.0"
name: "test_pipeline"
description: "Test pipeline"
agents:
  - agent: "pm"
    enabled: true
  - agent: "backend"
    enabled: true
    depends_on: ["pm"]
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        config = load_pipeline_from_yaml(yaml_file)

        assert config.name == "test_pipeline"
        assert len(config.agents) == 2
        assert config.agents[0].agent == "pm"
        assert config.agents[1].agent == "backend"

    def test_load_missing_file_raises(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_pipeline_from_yaml("/nonexistent/file.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path):
        """Test that invalid YAML raises error."""
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("invalid: yaml: content: [")

        with pytest.raises(ValueError, match="Invalid YAML"):
            load_pipeline_from_yaml(yaml_file)


class TestLoadPipelineFromDict:
    """Test loading pipeline from dictionary."""

    def test_valid_dict(self):
        data = {
            "name": "dict_pipeline",
            "agents": [
                {"agent": "pm", "enabled": True},
                {"agent": "backend", "enabled": True},
            ]
        }
        config = load_pipeline_from_dict(data)
        assert config.name == "dict_pipeline"
        assert len(config.agents) == 2

    def test_invalid_duplicate_agents_raises(self):
        """Test that duplicate agents fail validation."""
        data = {
            "name": "bad_pipeline",
            "agents": [
                {"agent": "pm", "enabled": True},
                {"agent": "pm", "enabled": True},
            ]
        }
        with pytest.raises(PipelineValidationError, match="Duplicate agents"):
            load_pipeline_from_dict(data)


class TestValidatePipeline:
    """Test pipeline validation logic."""

    def test_valid_pipeline(self):
        config = PipelineConfig(
            name="valid",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
            ]
        )
        result = validate_pipeline(config, agent_registry={"pm", "backend"})

        assert result.valid is True
        assert len(result.errors) == 0

    def test_unknown_agent_raises_error(self):
        config = PipelineConfig(
            name="bad",
            agents=[
                AgentTaskConfig(agent="nonexistent_agent"),
            ]
        )
        result = validate_pipeline(config, agent_registry={"pm", "backend"})

        assert result.valid is False
        assert any("Unknown agent" in err for err in result.errors)

    def test_circular_dependency_detected(self):
        """Test that circular dependencies are caught."""
        config = PipelineConfig(
            name="cycle_test",
            agents=[
                AgentTaskConfig(agent="agent1", depends_on=["agent2"]),
                AgentTaskConfig(agent="agent2", depends_on=["agent1"]),
            ],
            auto_resolve=False,
        )
        result = validate_pipeline(config, agent_registry={"agent1", "agent2"})

        assert result.valid is False
        assert any("Circular dependency" in err for err in result.errors)


class TestBuildPipelineFromConfig:
    """Test converting config to PipelineTask list."""

    def test_build_creates_tasks_in_order(self):
        """Test that build_from_config creates tasks topologically sorted."""
        from agents.agent_config import create_agent, get_registered_agents

        # Ensure agents are registered
        from agents.pm_agent import PMAgent
        from agents.backend_agent import BackendAgent
        from agents.agent_config import register_agent
        register_agent(PMAgent)
        register_agent(BackendAgent)

        config = PipelineConfig(
            name="test_build",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
            ]
        )

        # We'll need an orchestrator instance
        from pipeline.orchestrator import Orchestrator
        orch = Orchestrator(project_id="test_project")
        dag = orch.build_from_config(config)
        tasks = dag.tasks

        assert len(tasks) == 2
        assert tasks[0].name == "pm"
        assert tasks[1].name == "backend"
        assert tasks[1].depends_on == ["pm"]

    def test_build_with_task_override(self):
        """Test that custom task prompt is used."""
        from agents.agent_config import register_agent
        from agents.pm_agent import PMAgent
        from pipeline.orchestrator import Orchestrator
        register_agent(PMAgent)

        config = PipelineConfig(
            name="custom_task",
            agents=[
                AgentTaskConfig(
                    agent="pm",
                    task="Custom prompt for: {feature}"
                )
            ]
        )

        orch = Orchestrator(project_id="test_project")
        dag = orch.build_from_config(config)
        tasks = dag.tasks

        assert tasks[0].task == "Custom prompt for: {feature}"


class TestLoadAllTemplates:
    """Test template discovery."""

    def test_load_all_templates_from_config_dir(self):
        """Test that load_all_templates finds templates in config/pipelines/."""
        templates = load_all_templates()

        # Should find at least the templates we created
        names = [t["name"] for t in templates]
        assert "full_stack_web" in names
        assert "api_only" in names
        assert "security_audit_only" in names
        assert "mvp" in names

    def test_templates_have_required_fields(self):
        """Test that each template has required metadata."""
        templates = load_all_templates()
        for t in templates:
            assert "name" in t
            assert "description" in t
            assert "agent_count" in t
            assert "project_types" in t


class TestLoadTemplate:
    """Test loading specific template by name."""

    def test_load_existing_template(self):
        config = load_template("api_only")
        assert config is not None
        assert config.name == "api_only"
        assert len(config.agents) > 0

    def test_load_nonexistent_template_returns_none(self):
        config = load_template("does_not_exist_xyz")
        assert config is None


class TestDagAndEstimation:
    """Test DAG generation and cost/duration estimation."""

    def test_build_dag_dict(self):
        """Test DAG dict generation for React Flow."""
        from pipeline.orchestrator import PipelineTask, Orchestrator
        from agents.agent_config import register_agent
        from agents.pm_agent import PMAgent
        from agents.backend_agent import BackendAgent
        register_agent(PMAgent)
        register_agent(BackendAgent)

        config = PipelineConfig(
            name="dag_test",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
            ]
        )

        orch = Orchestrator(project_id="test")
        dag_result = orch.build_from_config(config)
        tasks = dag_result.tasks

        dag = build_dag_dict(tasks)

        assert "nodes" in dag
        assert "edges" in dag
        assert len(dag["nodes"]) == 2
        assert len(dag["edges"]) == 1
        assert dag["edges"][0]["source"] == "pm"
        assert dag["edges"][0]["target"] == "backend"

    def test_estimate_cost(self):
        """Test cost estimation."""
        from pipeline.orchestrator import PipelineTask, Orchestrator
        from agents.agent_config import register_agent
        from agents.pm_agent import PMAgent
        from agents.backend_agent import BackendAgent
        register_agent(PMAgent)
        register_agent(BackendAgent)

        config = PipelineConfig(
            name="cost_test",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="backend"),
            ]
        )

        orch = Orchestrator(project_id="test")
        dag_result = orch.build_from_config(config)
        tasks = dag_result.tasks

        cost = estimate_cost(tasks)
        assert cost > 0
        assert cost < 10.0  # Rough estimate for 2 agents

    def test_estimate_duration(self):
        """Test duration estimation."""
        from pipeline.orchestrator import PipelineTask, Orchestrator
        from agents.agent_config import register_agent
        from agents.pm_agent import PMAgent
        from agents.backend_agent import BackendAgent
        register_agent(PMAgent)
        register_agent(BackendAgent)

        config = PipelineConfig(
            name="duration_test",
            agents=[
                AgentTaskConfig(agent="pm"),
                AgentTaskConfig(agent="backend", depends_on=["pm"]),
            ]
        )

        orch = Orchestrator(project_id="test")
        dag_result = orch.build_from_config(config)
        tasks = dag_result.tasks

        duration = estimate_duration(tasks)
        assert duration > 0
        # Backend depends on PM, so duration should sum them (sequential)
        # If they were parallel, duration would be max