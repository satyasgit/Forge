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

    # 2. Build enriched context from team messages (if available)
    message_context = ""
    full_context = "\n\n".join(filter(None, [
        context,
        f"## Team messages:\n{message_context}" if message_context else None,
    ]))

    # 3. Execute (BaseAgent.run handles memory recall internally)
    result = await agent.run(task, context=full_context)

    # 4. Post status update
    status_msg = AgentMessage(
        sender=agent_name,
        channel=f"sprint-{sprint_id}" if sprint_id else "general",
        message_type="status",
        content=f"Completed: {task[:100]}...",
        metadata={"story_id": story_id, "result": result.to_dict()}
    )
    await bus.publish(status_msg)

    # NOTE: Outcome recording is NOT done here anymore.
    # It is done in the StoryWorkflow AFTER the review phase,
    # so that real feedback signals (review_passed, tests_passed)
    # can be wired into the TaskOutcome.

    return result.to_dict()


@activity.defn
async def review_agent_output(
    reviewer_agent: str,
    original_agent: str,
    original_task: str,
    output_to_review: str,
    project_id: str = "default",
    sprint_id: str | None = None,
    story_id: str | None = None,
) -> dict:
    """
    Run a review agent (code_review, qa, security) on another agent's output.
    Returns structured feedback including pass/fail verdict.
    """
    from agents.agent_config import create_agent
    from communication.bus import MessageBus, AgentMessage

    logger.info(f"Starting review: {reviewer_agent} reviewing {original_agent}'s output")

    agent = create_agent(reviewer_agent, project_id=project_id)
    bus = MessageBus()

    review_task = (
        f"## Review Request\n"
        f"You are reviewing the output of the **{original_agent}** agent.\n\n"
        f"### Original Task\n{original_task}\n\n"
        f"### Output to Review\n{output_to_review[:8000]}\n\n"
        f"### Instructions\n"
        f"1. Evaluate the output against the original task requirements.\n"
        f"2. Check for correctness, security, error handling, and best practices.\n"
        f"3. At the END of your review, you MUST include a verdict line:\n"
        f"   `VERDICT: PASS` or `VERDICT: FAIL`\n"
        f"4. If FAIL, list the specific issues that must be fixed.\n"
    )

    result = await agent.run(review_task)

    # Parse verdict from output
    output_upper = result.output.upper()
    review_passed = "VERDICT: PASS" in output_upper
    
    # Extract feedback (everything that's not the verdict line)
    feedback_lines = [
        line for line in result.output.split("\n")
        if "VERDICT:" not in line.upper()
    ]
    feedback = "\n".join(feedback_lines).strip()

    # Broadcast review result
    verdict_emoji = "✅" if review_passed else "❌"
    await bus.publish(AgentMessage(
        sender=reviewer_agent,
        channel=f"sprint-{sprint_id}" if sprint_id else "general",
        message_type="decision",
        content=f"{verdict_emoji} Review of {original_agent}'s work: {'PASS' if review_passed else 'FAIL'}",
        metadata={"story_id": story_id, "review_passed": review_passed}
    ))

    return {
        "reviewer": reviewer_agent,
        "reviewed_agent": original_agent,
        "review_passed": review_passed,
        "feedback": feedback,
        "result": result.to_dict(),
    }


@activity.defn
async def record_evolution_outcome(
    agent_name: str,
    task_summary: str,
    output_summary: str,
    review_passed: bool | None = None,
    review_feedback: str = "",
    tests_passed: bool | None = None,
    revision_count: int = 0,
    project_id: str = "default",
) -> dict:
    """
    Record an outcome and extract a lesson AFTER real feedback has been collected.
    This is the correct place for evolution — not inside run_agent_activity.
    """
    from agents.agent_config import create_agent
    from evolution.outcome_tracker import TaskOutcome

    logger.info(
        f"Recording evolution outcome for {agent_name}: "
        f"review_passed={review_passed}, tests_passed={tests_passed}, revisions={revision_count}"
    )

    agent = create_agent(agent_name, project_id=project_id)

    outcome = TaskOutcome(
        agent_name=agent_name,
        task_summary=task_summary,
        output_summary=output_summary[:500],
        review_passed=review_passed,
        review_feedback=review_feedback,
        tests_passed=tests_passed,
        revision_count=revision_count,
    )

    await agent.remember_outcome(outcome)

    return {
        "agent_name": agent_name,
        "lesson_recorded": True,
        "review_passed": review_passed,
        "revision_count": revision_count,
    }


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
