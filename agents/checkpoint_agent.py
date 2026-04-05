"""
Checkpoint Agent - pauses pipeline execution for human approval or external input.

Supports checkpoint types:
- human_approval: Wait for manual approval/rejection
- manual_qa: Wait for QA completion
- budget_approval: Wait for cost threshold approval
- data_input: Wait for external data to be provided

The checkpoint agent creates a checkpoint record and signals the orchestrator
to pause. The pipeline can be resumed via the resume API endpoint.
"""
from __future__ import annotations

import logging
from agents.base import BaseAgent, AgentResult
from agents.agent_config import AgentConfig, register_agent
from memory.store import ProjectMemory

logger = logging.getLogger(__name__)


@register_agent
class CheckpointAgent(BaseAgent):
    """
    Special agent that creates a checkpoint and triggers pipeline pause.

    Configuration (via AgentConfig.meta or .checkpoint_config):
      - checkpoint_type: str (required) - human_approval, manual_qa, budget_approval, data_input
      - message: str (optional) - Message to display to approvers
      - approvers: list[str] (optional) - Email/IDs of required approvers
      - timeout_minutes: int (optional) - Auto-timeout after N minutes (default: 1440 = 24h)
      - required_approvers: int (optional) - Minimum number of approvals needed (default: 1)
    """
    name = "checkpoint"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Extract checkpoint config from meta
        cp_config = self.config.meta.get("checkpoint", {})
        self.checkpoint_type = cp_config.get("checkpoint_type", "human_approval")
        self.message = cp_config.get("message", "Action required: review this pipeline step.")
        self.approvers = cp_config.get("approvers", [])
        self.timeout_minutes = cp_config.get("timeout_minutes", 1440)  # 24 hours default
        self.required_approvers = cp_config.get("required_approvers", 1)
        self.required_context = cp_config.get("required_context", [])  # Keys that must be in context

    @property
    def system_prompt(self) -> str:
        return f"""You are a Checkpoint Agent for {self.project_id}.

Your purpose is to pause the pipeline and request human intervention.

Checkpoint type: {self.checkpoint_type}
Message to approvers: {self.message}
Required approvers: {self.required_approvers}
Timeout: {self.timeout_minutes} minutes

When executed, you will create a checkpoint record and the pipeline will pause.
Approvers will be notified (via email/Slack - not yet implemented) to review.

You do not perform any analysis or generate output. You simply trigger the pause.
"""

    def run(self, task: str, context: str = "", use_memory: bool = True) -> AgentResult:
        """
        Execute the checkpoint agent.

        Args:
            task: Task description (unused but kept for interface)
            context: Context from previous agents

        Returns:
            AgentResult with special `is_checkpoint` flag set to True.
            The orchestrator will detect this and pause the pipeline.
        """
        result = AgentResult(agent_name=self.name, model_used=self.config.model)
        result.state = "checkpoint_created"
        result.output = f"Checkpoint created: {self.message}"

        # Create checkpoint record in database
        try:
            checkpoint_id = self.memory.create_checkpoint(
                pipeline_run_id=self.project_id,  # Using project_id as run_id for now
                agent_name=self.name,
                checkpoint_type=self.checkpoint_type,
                message=self.message,
                metadata={
                    "approvers": self.approvers,
                    "timeout_minutes": self.timeout_minutes,
                    "required_approvers": self.required_approvers,
                    "context_snapshot": context[:500] if context else "",  # Store partial context
                }
            )
            result.checkpoint_id = checkpoint_id  # Add custom attribute
            result.checkpoint_type = self.checkpoint_type
            logger.info("[%s] Checkpoint created: id=%s type=%s message=%s",
                        self.name, checkpoint_id[:8], self.checkpoint_type, self.message)
        except Exception as e:
            logger.error("[%s] Failed to create checkpoint: %s", self.name, e)
            result.errors.append(f"Failed to create checkpoint: {e}")
            result.state = "error"

        return result
