"""
Outcome Tracker for Agent Self-Evolution.
Records task outcomes, analyzes successes/failures, and extracts lessons learned.
"""
from dataclasses import dataclass, field
import logging
from typing import Any

from llm.client import LLMClient

logger = logging.getLogger(__name__)

@dataclass
class TaskOutcome:
    """Records what happened AFTER an agent's output was produced."""
    agent_name: str
    task_summary: str
    output_summary: str          # What the agent produced (truncated)
    
    # Outcome signals (filled in post-execution)
    review_passed: bool | None = None       # Did code review approve?
    review_feedback: str = ""               # What did the reviewer say?
    tests_passed: bool | None = None        # Did QA tests pass?
    test_failures: list[str] = field(default_factory=list)
    security_issues: list[str] = field(default_factory=list)
    human_feedback: str = ""                # Did a human give feedback?
    cost_usd: float = 0.0
    revision_count: int = 0                 # How many revision rounds?
    
    # Derived learning
    lesson_learned: str = ""                # Auto-generated reflection
    patterns_to_repeat: list[str] = field(default_factory=list)
    patterns_to_avoid: list[str] = field(default_factory=list)

class OutcomeTracker:
    """Tracks outcomes and extracts learnings for agent evolution."""
    
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
    
    async def extract_lesson(self, outcome: TaskOutcome) -> str:
        """Use a fast LLM to extract a concise lesson from an outcome."""
        prompt = f"""
        Analyze this task outcome and extract a concise lesson learned for future execution.
        
        Agent: {outcome.agent_name}
        Task: {outcome.task_summary}
        Output Summary: {outcome.output_summary}
        
        Feedback & Signals:
        - Review Passed: {outcome.review_passed}
        - Review Feedback: {outcome.review_feedback}
        - Tests Passed: {outcome.tests_passed}
        - Human Feedback: {outcome.human_feedback}
        
        Provide a 1-3 sentence specific, actionable rule the agent should follow next time to avoid these mistakes or repeat this success.
        If the task was successful, identify the pattern to repeat. If it failed, identify the pattern to avoid.
        """
        
        try:
            response = await self.llm.create_message(
                model="anthropic/claude-haiku-4-5-20251001",
                messages=[{"role": "user", "content": prompt}]
            )
            return response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Failed to extract lesson: {e}")
            return "Task completed. No specific lesson extracted."
