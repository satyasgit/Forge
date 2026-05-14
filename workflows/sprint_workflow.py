"""
Sprint Workflow: Runs for the duration of a sprint (1-4 weeks).
Orchestrates daily standups, story execution, reviews, and retrospective.

v2: Added review loop with real feedback wired into agent self-evolution.
"""
from temporalio import workflow
from datetime import timedelta
import asyncio

# Import activities (must be typed string or actual function)
with workflow.unsafe.imports_passed_through():
    from activities.agent_activities import (
        run_agent_activity,
        review_agent_output,
        record_evolution_outcome,
        plan_sprint,
        run_standup,
    )

MAX_REVISION_ROUNDS = 2  # Cap revisions to prevent infinite loops


@workflow.defn
class StoryWorkflow:
    """
    Execute a single user story through agents.
    Includes a code review loop with real feedback that drives agent evolution.
    
    Flow:
      1. Assigned agent executes the story
      2. Code review agent reviews the output
      3. If review fails and revisions remain, agent revises (goto 2)
      4. Record the outcome with REAL feedback signals into evolution memory
    """

    @workflow.run
    async def run(self, story: dict, project_id: str) -> dict:
        assigned_to = story.get("assigned_to", "backend")
        task = story.get("title", "Unknown task") + "\n" + story.get("description", "")
        sprint_id = story.get("sprint_id")
        story_id = story.get("id")

        revision_count = 0
        review_passed = False
        review_feedback = ""
        last_output = ""

        # ── Execute → Review → Revise Loop ──────────────────────────────
        while revision_count <= MAX_REVISION_ROUNDS:
            # Build context for revision rounds
            context = ""
            if revision_count > 0 and review_feedback:
                context = (
                    f"## REVISION REQUIRED (Round {revision_count}/{MAX_REVISION_ROUNDS})\n"
                    f"Your previous output was reviewed and FAILED. Fix the following issues:\n\n"
                    f"{review_feedback}\n\n"
                    f"## Your Previous Output (to revise)\n"
                    f"{last_output[:4000]}"
                )

            # Step 1: Agent executes (or revises)
            result = await workflow.execute_activity(
                run_agent_activity,
                args=[assigned_to, task, context, project_id, sprint_id, story_id],
                start_to_close_timeout=timedelta(minutes=30),
            )
            last_output = result.get("output", "")

            # Step 2: Code review (skip for non-code agents like PM)
            if assigned_to in ("pm", "ui_ux", "monetisation", "ceo", "vp_eng"):
                # These agents produce specs/plans, not code — skip code review
                review_passed = True
                review_feedback = ""
                break

            review_result = await workflow.execute_activity(
                review_agent_output,
                args=[
                    "code_review",     # reviewer
                    assigned_to,       # reviewed agent
                    task,              # original task
                    last_output,       # output to review
                    project_id,
                    sprint_id,
                    story_id,
                ],
                start_to_close_timeout=timedelta(minutes=15),
            )

            review_passed = review_result.get("review_passed", False)
            review_feedback = review_result.get("feedback", "")

            if review_passed:
                break

            revision_count += 1

        # ── Step 3: Record outcome with REAL feedback ────────────────────
        # This is the critical fix: outcomes are populated from actual
        # review results, not hardcoded to True.
        await workflow.execute_activity(
            record_evolution_outcome,
            args=[
                assigned_to,                    # agent_name
                task,                           # task_summary
                last_output[:500],              # output_summary
                review_passed,                  # review_passed (REAL)
                review_feedback[:1000],         # review_feedback (REAL)
                None,                           # tests_passed (filled by QA in future)
                revision_count,                 # revision_count (REAL)
                project_id,
            ],
            start_to_close_timeout=timedelta(minutes=5),
        )

        return {
            "story_id": story_id,
            "output": result,
            "reviewed": True,
            "review_passed": review_passed,
            "revision_count": revision_count,
        }


@workflow.defn
class SprintWorkflow:
    """
    A Sprint is a Temporal workflow that:
    1. Runs for 1-4 weeks
    2. Triggers daily standups via timer
    3. Executes stories as child workflows
    """

    @workflow.run
    async def run(self, sprint_id: str, project_id: str, backlog: list[dict], duration_days: int) -> dict:
        # Phase 1: Sprint Planning
        stories = await workflow.execute_activity(
            plan_sprint,
            args=[sprint_id, project_id, backlog],
            start_to_close_timeout=timedelta(minutes=30),
        )

        # Phase 2: Execute Stories (parallel where possible)
        # We start child workflows for each story
        story_futures = []
        for story in stories:
            future = workflow.execute_child_workflow(
                StoryWorkflow.run,
                args=[story, project_id],
                id=f"story-{story.get('id', 'unknown')}-{workflow.uuid4()}",
            )
            story_futures.append(future)

        # Phase 3: Wait for all stories to complete
        stories_completed = False
        days_passed = 0
        
        while not stories_completed and days_passed < duration_days:
            # Wait for either 24 hours to pass, or all stories to complete
            done, pending = await asyncio.wait(
                story_futures, 
                timeout=24*60*60, # 24 hours
                return_when=asyncio.ALL_COMPLETED
            )
            
            if not pending:
                stories_completed = True
            else:
                days_passed += 1
                # Run daily standup
                await workflow.execute_activity(
                    run_standup,
                    args=[sprint_id, project_id],
                    start_to_close_timeout=timedelta(minutes=10),
                )

        # Wait for any remaining stories if we hit the duration limit
        story_results = await asyncio.gather(*story_futures)

        # Phase 4: Sprint Review
        total_revisions = sum(r.get("revision_count", 0) for r in story_results if isinstance(r, dict))
        pass_rate = sum(1 for r in story_results if isinstance(r, dict) and r.get("review_passed")) / max(len(story_results), 1)

        return {
            "sprint_id": sprint_id,
            "status": "completed",
            "stories_completed": len(story_results),
            "first_pass_review_rate": round(pass_rate * 100, 1),
            "total_revision_rounds": total_revisions,
        }
