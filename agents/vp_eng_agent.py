"""
VP Engineering Agent — operational management and sprint execution.
"""
import textwrap
from typing import List, Dict, Any
from agents.base import BaseAgent, AgentResult
from agents.agent_config import register_agent
from agile.sprint_manager import SprintManager
from config.database import AsyncSessionLocal

@register_agent
class VPEngAgent(BaseAgent):
    name = "vp_eng"
    role = "VP Engineering"
    style = "Execution-focused, data-driven, and supportive of team velocity"
    enabled_tools = ["slack_send_message"]

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are the VP of Engineering in an AI engineering organization.
            Your goal is to manage the sprint lifecycle, track team velocity, 
            and ensure that blockers are removed.

            ## Your Responsibilities:
            1. Sprint Planning: Assign user stories to agents based on their roles.
            2. Daily Standups: Aggregate status updates and highlight blockers.
            3. Velocity Tracking: Monitor progress and adjust scope if needed.
            4. Team Health: Ensure agents have what they need to succeed.

            ## Communication Style:
            - Professional, efficient, and direct.
            - Focus on timelines, blockers, and status.
            - Use Gherkin acceptance criteria to verify progress.

            ## Output Format:
            When summarizing a standup, use the following structure:
            ### STANDUP SUMMARY: [Date]
            - **On Track**: Agents who are progressing as planned.
            - **At Risk**: Stories that might miss the sprint end.
            - **Blockers**: Immediate issues requiring resolution.
            - **Velocity Note**: Summary of points completed vs total.
        """).strip()

    async def summarize_standup(self, sprint_id: str) -> AgentResult:
        """Aggregate daily standup reports into a summary."""
        async with AsyncSessionLocal() as db:
            sm = SprintManager(db)
            reports = await sm.get_daily_standup_summary(sprint_id)
            
            reports_text = []
            for r in reports:
                reports_text.append(textwrap.dedent(f"""
                    - **Agent**: {r.agent_name}
                      **Yesterday**: {r.completed_yesterday}
                      **Today**: {r.working_on_today}
                      **Blockers**: {r.blockers}
                      **Mood**: {r.mood}
                """))
            
            task = textwrap.dedent(f"""
                Summarize today's standup for Sprint {sprint_id}. 
                Identify cross-agent blockers and highlight any at-risk stories.

                ## Individual Reports
                {"".join(reports_text) if reports_text else "No reports submitted today."}
            """)
            return await self.run(task)

    async def plan_sprint(self, sprint_id: str, backlog: List[Dict[str, Any]]) -> AgentResult:
        """Assign backlog items to agents."""
        task = textwrap.dedent(f"""
            Plan the assignments for Sprint {sprint_id}. 
            Assign each user story to the most appropriate agent role (pm, frontend, backend, security, etc.).

            ## Backlog
            {backlog}

            Provide a table of Story ID → Assigned Agent.
        """)
        return await self.run(task)
