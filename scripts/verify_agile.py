"""
Verification script for Phase 3: AI Coworker Identity & Sprint Engine.
Tests Sprint creation, Story assignment, and Persona loading.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from unittest.mock import MagicMock
from agile.sprint_manager import SprintManager
from agents.base import BaseAgent
from agents.agent_config import AgentConfig
from config.settings import settings
import communication.bus
from config.database import AsyncSessionLocal, Base, async_engine

# Force SQLite for local verification
settings.database_url = ""
# Mock MessageBus to avoid Redis connection attempts
communication.bus.MessageBus = MagicMock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dummy agent for testing
class TestAgent(BaseAgent):
    name = "test_coworker"
    role = "Test Engineer"
    style = "Thorough and meticulous"
    
    @property
    def system_prompt(self) -> str:
        return "You are a test agent."

async def verify_agile():
    print("--- Verifying Phase 3: AI Coworker Identity & Sprint Engine ---")
    
    # Ensure tables exist
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as db:
        sm = SprintManager(db)
        project_id = f"test-project-{uuid.uuid4().hex[:6]}"
        
        # 1. Test Sprint Creation
        print(f"1. Creating sprint for project: {project_id}")
        sprint = await sm.create_sprint(project_id, "Sprint 1", "Verify core infrastructure")
        print(f"   ✅ Sprint created: {sprint.id}")
        
        # 2. Test Story Creation
        print("2. Adding user stories")
        story = await sm.create_story(
            sprint_id=sprint.id,
            title="Implement OAuth2",
            description="Add Google/GitHub auth",
            story_points=5,
            assigned_to="backend"
        )
        print(f"   ✅ Story created: {story.id}")
        
        # 3. Test Persona Loading
        print("3. Testing Agent Persona loading")
        agent = TestAgent(project_id)
        await agent.init_persona()
        
        if agent.persona and agent.persona.name == "test_coworker":
            print(f"   ✅ Persona loaded: {agent.persona.title} ({agent.persona.seniority})")
            print(f"   ✅ Enriched Prompt contains Identity: {'YOUR IDENTITY' in agent.effective_system_prompt}")
        else:
            print("   ❌ Persona loading failed")

        # 4. Test Standup Submission
        print("4. Submitting standup")
        report = await sm.submit_standup(
            sprint_id=sprint.id,
            agent_name="test_coworker",
            completed_yesterday=["story-123"],
            working_on_today=["story-456"],
            blockers=["Waiting on API spec"],
            mood="at_risk"
        )
        print(f"   ✅ Standup report submitted: {report.id}")

    print("--- Verification Complete ---")

if __name__ == "__main__":
    try:
        asyncio.run(verify_agile())
    except Exception as e:
        print(f"❌ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
