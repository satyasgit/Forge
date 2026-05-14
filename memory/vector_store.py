"""
Vector Store wrapper for Supabase pgvector.
Handles embeddings and semantic search for agent memories.

v2: Added deduplication, embedding failure safety, and structured metadata.
"""
from dataclasses import dataclass
import json
import logging
from typing import Any

from config.database import AsyncSessionLocal
from sqlalchemy import text
from litellm import aembedding
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    id: str
    content: str
    metadata: dict[str, Any]
    similarity: float


class VectorMemory:
    """Wrapper for pgvector semantic search with quality controls."""
    
    # Threshold above which two memories are considered duplicates
    DEDUP_SIMILARITY_THRESHOLD = 0.92
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.embedding_model = "text-embedding-3-small"  # OpenAI embedding model (LiteLLM translates if needed)
    
    async def _get_embedding(self, text_content: str) -> list[float] | None:
        """
        Generate embedding using LiteLLM.
        Returns None on failure instead of a zero vector to prevent memory pollution.
        """
        try:
            response = await aembedding(model=self.embedding_model, input=[text_content])
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # CRITICAL: Return None, NOT a zero vector.
            # Zero vectors cluster together and poison similarity search.
            return None

    async def store(self, content: str, memory_type: str, metadata: dict[str, Any] = None) -> bool:
        """
        Store a new memory with its embedding in pgvector.
        
        Quality controls:
        1. Refuses to store if embedding generation fails.
        2. Checks for semantic duplicates before inserting.
        """
        if not content or not content.strip():
            logger.warning("Attempted to store empty memory. Skipping.")
            return False

        embedding = await self._get_embedding(content)
        if embedding is None:
            logger.error("Cannot store memory: embedding generation failed. Skipping to prevent corruption.")
            return False
        
        try:
            async with AsyncSessionLocal() as session:
                # Deduplication: Check for semantically similar existing memories
                is_duplicate = await self._check_duplicate(session, embedding, memory_type)
                if is_duplicate:
                    logger.info(
                        "[%s] Skipping duplicate memory (similarity > %.2f): %s...",
                        self.agent_name, self.DEDUP_SIMILARITY_THRESHOLD, content[:60]
                    )
                    return False

                query = text("""
                    INSERT INTO agent_memory_vectors (agent_name, content, memory_type, embedding, metadata)
                    VALUES (:agent_name, :content, :memory_type, :embedding, :metadata)
                """)
                await session.execute(query, {
                    "agent_name": self.agent_name,
                    "content": content,
                    "memory_type": memory_type,
                    "embedding": f"[{','.join(map(str, embedding))}]",
                    "metadata": json.dumps(metadata or {})
                })
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False

    async def _check_duplicate(self, session, embedding: list[float], memory_type: str) -> bool:
        """Check if a semantically similar memory already exists."""
        try:
            sql = """
                SELECT 1 - (embedding <=> :query_embedding::vector) as similarity
                FROM agent_memory_vectors
                WHERE agent_name = :agent_name
                AND memory_type = :memory_type
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT 1
            """
            result = await session.execute(text(sql), {
                "query_embedding": f"[{','.join(map(str, embedding))}]",
                "agent_name": self.agent_name,
                "memory_type": memory_type,
            })
            row = result.fetchone()
            if row and float(row.similarity) > self.DEDUP_SIMILARITY_THRESHOLD:
                return True
        except Exception as e:
            # If dedup check fails, allow the insert (fail-open for availability)
            logger.warning(f"Deduplication check failed: {e}. Allowing insert.")
        return False

    async def search(self, query: str, memory_type: str = None, top_k: int = 5) -> list[MemoryResult]:
        """Search for similar past memories."""
        query_embedding = await self._get_embedding(query)
        if query_embedding is None:
            logger.error("Cannot search memories: embedding generation failed.")
            return []

        try:
            async with AsyncSessionLocal() as session:
                # Use vector_cosine_ops for distance (<=>)
                sql = """
                    SELECT id, content, metadata, 1 - (embedding <=> :query_embedding::vector) as similarity
                    FROM agent_memory_vectors
                    WHERE agent_name = :agent_name
                """
                params = {
                    "query_embedding": f"[{','.join(map(str, query_embedding))}]",
                    "agent_name": self.agent_name
                }
                
                if memory_type:
                    sql += " AND memory_type = :memory_type"
                    params["memory_type"] = memory_type
                    
                sql += " ORDER BY embedding <=> :query_embedding::vector LIMIT :top_k"
                params["top_k"] = top_k
                
                result = await session.execute(text(sql), params)
                rows = result.fetchall()
                
                return [
                    MemoryResult(
                        id=str(row.id),
                        content=row.content,
                        metadata=row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata or '{}'),
                        similarity=float(row.similarity)
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
