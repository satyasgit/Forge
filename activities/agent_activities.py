"""
Temporal Activities wrapping agent execution.
Each activity is a self-contained unit of work that Temporal can:
  - Retry on failure
  - Time out gracefully
  - Execute on any worker
  - Track with full observability
"""
from temporalio import activity
import textwrap
import logging
import asyncio

logger = logging.getLogger(__name__)

@activity.defn
async def run_agent_activity(
    agent_name: str,
    task: str,
    context: str = "",
    project_id: str = "default",
    sprint_id: str | None = None,
    story_id: str | None = None,
) -> dict:
    """Execute an agent as a Temporal activity."""
    from agents.agent_config import create_agent
    from communication.bus import MessageBus, AgentMessage
    from config.database import AsyncSessionLocal
    
    logger.info(f"Starting agent activity: {agent_name} for task: {task[:50]}")

    # 1. Create the agent with full context
    agent = create_agent(agent_name, project_id=project_id)
    bus = MessageBus()

    # 2. Retrieve semantic memories (Simulated for now, as VectorMemory is not fully implemented in base yet)
    # similar = await agent.recall_similar(task)
    similar = ""

    # 3. Check inbox for relevant messages (Mocked for now, pending full MessageBus implementation for inbox)
    # inbox = await bus.get_inbox(agent_name)
    # message_context = "\n".join([f"[{m.sender}] {m.content}" for m in inbox if m.sprint_id == sprint_id])
    message_context = ""

    # 4. Build enriched context
    full_context = "\n\n".join(filter(None, [
        context,
        f"## Relevant past experience:\n{similar}" if similar else None,
        f"## Team messages:\n{message_context}" if message_context else None,
    ]))

    # 5. Execute
    result = await agent.run(task, context=full_context)

    # 6. Post status update
    status_msg = AgentMessage(
        sender=agent_name,
        channel=f"sprint-{sprint_id}" if sprint_id else "general",
        message_type="status",
        content=f"Completed: {task[:100]}...",
        metadata={"story_id": story_id, "result": result.to_dict()}
    )
    await bus.publish(status_msg)

    # 7. Self-Evolution: Track outcome and remember lesson
    from evolution.outcome_tracker import TaskOutcome
    
    # In a full flow, review_passed would be populated by the QA agent's step.
    # For now, we assume success if no exceptions were thrown.
    outcome = TaskOutcome(
        agent_name=agent_name,
        task_summary=task,
        output_summary=result.output[:500],
        review_passed=True,
        tests_passed=True
    )
    await agent.remember_outcome(outcome)

    return result.to_dict()

@activity.defn
async def plan_sprint(sprint_id: str, project_id: str, backlog: list[dict]) -> list[dict]:
    """Execute VP Eng agent to plan a sprint."""
    from agents.agent_config import create_agent
    
    agent = create_agent("vp_eng", project_id=project_id)
    result = await agent.plan_sprint(sprint_id, backlog)
    
    # Simple parse of result to get assignments (in a real system, this would be structured data)
    # For now, return a mocked up list of stories based on backlog
    stories = []
    for item in backlog:
        story = item.copy()
        story["sprint_id"] = sprint_id
        # Simplistic parsing/assignment
        if "frontend" in item.get("description", "").lower():
            story["assigned_to"] = "frontend"
        elif "backend" in item.get("description", "").lower():
            story["assigned_to"] = "backend"
        else:
            story["assigned_to"] = "pm"
        stories.append(story)
        
    return stories

@activity.defn
async def run_standup(sprint_id: str, project_id: str) -> dict:
    """Execute VP Eng agent to summarize a daily standup."""
    from agents.agent_config import create_agent
    
    agent = create_agent("vp_eng", project_id=project_id)
    result = await agent.summarize_standup(sprint_id)
    return result.to_dict()
