"""
Temporal Worker Process.
Connects to Temporal server and registers workflows and activities.
Run this as a separate process from the FastAPI server.
"""
import asyncio
import logging
from temporalio.client import Client
from temporalio.worker import Worker

# Import workflows and activities
from workflows.sprint_workflow import SprintWorkflow, StoryWorkflow
from activities.agent_activities import run_agent_activity, plan_sprint, run_standup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Connect to local Temporal server
    # Note: In production, use settings to configure the host/port and namespace
    logger.info("Connecting to Temporal server at localhost:7233...")
    client = await Client.connect("localhost:7233")
    logger.info("Connected to Temporal server.")

    # Create and start the worker
    worker = Worker(
        client,
        task_queue="agent-tasks",
        workflows=[SprintWorkflow, StoryWorkflow],
        activities=[run_agent_activity, plan_sprint, run_standup],
    )

    logger.info("Starting Temporal worker. Press Ctrl+C to exit.")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
