"""
Verification script for Phase 4: Temporal Workflow Orchestration.
Requires a running Temporal server (`temporal server start-dev`) and worker (`python api/worker.py`).
"""
import asyncio
import logging
from pipeline.orchestrator import run_sprint_with_temporal

logging.basicConfig(level=logging.INFO)

async def verify_temporal():
    print("--- Verifying Phase 4: Temporal Orchestration ---")
    
    backlog = [
        {"id": "story-1", "title": "Setup database", "description": "backend postgres setup"},
        {"id": "story-2", "title": "Create login page", "description": "frontend react login page"},
    ]
    
    try:
        workflow_id = await run_sprint_with_temporal(
            sprint_id="sprint-123",
            project_id="test-project",
            backlog=backlog,
            duration_days=2
        )
        print(f"✅ Successfully started Temporal SprintWorkflow with ID: {workflow_id}")
        print("Check the Temporal UI at http://localhost:8233 to see the workflow progress.")
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_temporal())
