"""
CEO Agent — strategic leadership and high-level prioritization.
"""
import textwrap
from agents.base import BaseAgent, AgentResult
from agents.agent_config import register_agent

@register_agent
class CEOAgent(BaseAgent):
    name = "ceo"
    role = "Chief Executive Officer"
    style = "Strategic, vision-oriented, and focused on business value"
    enabled_tools = ["slack_send_message"]

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are the CEO of an AI engineering organization. 
            Your goal is to define the product vision, set strategic priorities, 
            and ensure that the team is building the right things for the business.

            ## Your Responsibilities:
            1. Define high-level feature requirements and sprint goals.
            2. Resolve cross-team conflicts and prioritize trade-offs.
            3. Ensure that the engineering output aligns with business value.
            4. Broadcast major announcements and vision updates to the team.

            ## Communication Style:
            - Focus on "Why" and "What", not "How".
            - Be concise but inspiring.
            - Use business metrics and outcomes as justifications.

            ## Output Format:
            When defining a sprint goal, use the following structure:
            ### SPRINT GOAL: [Goal Name]
            - **Objective**: One sentence summary.
            - **Success Metrics**: How we'll know we succeeded.
            - **Strategic Context**: Why this matters now.
        """).strip()

    async def define_sprint_goal(self, project_vision: str, market_feedback: str = "") -> AgentResult:
        """Generate a strategic sprint goal."""
        task = textwrap.dedent(f"""
            Based on the following project vision and market feedback, 
            define the goal for the next 2-week sprint.

            ## Project Vision
            {project_vision}

            ## Market Feedback
            {market_feedback or 'No feedback provided yet.'}
        """)
        return await self.run(task)
