"""
Cross-Agent Knowledge Transfer.

When one agent learns something valuable, it can be shared across the team.
The BE agent's lesson about webhook idempotency should be available to any
agent that encounters a similar pattern.
"""
import logging
from typing import Any

from communication.bus import MessageBus, AgentMessage
from memory.vector_store import VectorMemory

logger = logging.getLogger(__name__)


class KnowledgeTransfer:
    """Share learnings across agents to accelerate team-wide improvement."""
    
    # Shared agent name for team-wide knowledge
    SHARED_AGENT = "shared_team"
    
    def __init__(self):
        self.bus = MessageBus()
        self.shared_memory = VectorMemory(self.SHARED_AGENT)
    
    async def broadcast_learning(
        self,
        source_agent: str,
        lesson: str,
        applicable_to: list[str] | None = None,
    ) -> bool:
        """
        Share a lesson learned by one agent with the team.
        
        Stored in a shared vector memory accessible by all agents,
        and broadcast via the message bus to relevant agents.
        """
        if not lesson or not lesson.strip():
            return False

        # 1. Store in shared vector memory (accessible by all agents)
        stored = await self.shared_memory.store(
            content=f"[Learned by {source_agent}]: {lesson}",
            memory_type="team_lesson",
            metadata={
                "source_agent": source_agent,
                "applicable_to": applicable_to or [],
            },
        )
        
        if not stored:
            logger.warning("Failed to store team learning from %s", source_agent)
            return False

        # 2. Notify relevant agents via message bus
        if applicable_to:
            for agent in applicable_to:
                try:
                    await self.bus.publish(AgentMessage(
                        sender="evolution_engine",
                        recipient=agent,
                        channel="general",
                        message_type="broadcast",
                        content=f"📚 Team learning from {source_agent}: {lesson}",
                        metadata={"source_agent": source_agent, "type": "team_lesson"},
                    ))
                except Exception as e:
                    logger.warning("Failed to notify %s of team learning: %s", agent, e)

        logger.info(
            "[KnowledgeTransfer] %s shared lesson with team: %s...",
            source_agent, lesson[:60]
        )
        return True

    async def get_team_knowledge(
        self,
        agent_name: str,
        task: str,
        top_k: int = 3,
        min_similarity: float = 0.6,
    ) -> list[str]:
        """
        Retrieve relevant team learnings for a task.
        Combines agent-specific + shared knowledge.
        """
        results = []
        
        try:
            # Shared team knowledge
            shared = await self.shared_memory.search(
                query=task,
                memory_type="team_lesson",
                top_k=top_k,
            )
            results.extend([
                m.content for m in shared
                if m.similarity > min_similarity
            ])
        except Exception as e:
            logger.warning("Failed to search team knowledge: %s", e)

        return results
