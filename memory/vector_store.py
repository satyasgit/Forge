"""
Vector Store wrapper for Supabase pgvector.
Handles embeddings and semantic search for agent memories.
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
    """Wrapper for pgvector semantic search."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.embedding_model = "text-embedding-3-small" # OpenAI embedding model (LiteLLM translates if needed)
    
    async def _get_embedding(self, text_content: str) -> list[float]:
        """Generate embedding using LiteLLM."""
        try:
            response = await aembedding(model=self.embedding_model, input=[text_content])
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return dummy embedding for fallback/local testing if no API keys
            return [0.0] * 1536

    async def store(self, content: str, memory_type: str, metadata: dict[str, Any] = None) -> bool:
        """Store a new memory with its embedding in pgvector."""
        try:
            embedding = await self._get_embedding(content)
            
            async with AsyncSessionLocal() as session:
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

    async def search(self, query: str, memory_type: str = None, top_k: int = 5) -> list[MemoryResult]:
        """Search for similar past memories."""
        try:
            query_embedding = await self._get_embedding(query)
            
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
