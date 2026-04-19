"""
LLM abstraction layer.
All agent-to-LLM communication goes through this module.
Supports Anthropic, OpenAI, Google, local models via LiteLLM.
"""
import logging
import litellm
from typing import Any
from dataclasses import dataclass, field
from config.settings import settings

logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """Model routing configuration."""
    # Planning/Architecture (highest quality)
    planning_model: str = "claude-3-5-sonnet"
    # Code generation (fast + good)
    coding_model: str = "claude-3-5-sonnet"
    # Cheap tasks (summaries, routing, classification)
    fast_model: str = "claude-3-5-haiku"
    # Vision tasks (screenshots, UI mockups)
    vision_model: str = "gpt-4o"
    # Search-grounded tasks (research, docs lookup)
    search_model: str = "gemini-1.5-flash"
    
    # Fallback chain
    fallback_models: list[str] = field(default_factory=lambda: [
        "claude-3-5-sonnet",
        "gpt-4o",
        "gemini-1.5-flash",
    ])

class LLMClient:
    """Unified LLM client with routing, fallback, and cost tracking."""

    def __init__(self, config: LLMConfig = None, proxy_url: str = None):
        self.config = config or LLMConfig()
        self.api_base = proxy_url or settings.litellm_proxy_url
        
        # Configure litellm to use the proxy if available
        if self.api_base:
            litellm.api_base = self.api_base
            logger.info(f"LLMClient initialized with proxy: {self.api_base}")
        else:
            logger.info("LLMClient initialized (no proxy, direct mode)")

    async def create_message(
        self,
        model: str,
        messages: list[dict],
        system: str = "",
        tools: list[dict] = None,
        max_tokens: int = 4096,
        **kwargs
    ) -> Any:
        """
        Send a message to any LLM provider.
        
        Uses LiteLLM under the hood.
        """
        # If system is provided separately, prepend it to messages
        full_messages = messages.copy()
        if system:
            # Check if there's already a system message
            if not any(m.get("role") == "system" for m in full_messages):
                full_messages.insert(0, {"role": "system", "content": system})

        params = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        if tools:
            params["tools"] = tools
            
        try:
            # LiteLLM handles provider-specific translation
            response = await litellm.acompletion(**params)
            return response
        except Exception as e:
            logger.error(f"LiteLLM completion error: {e}")
            raise

    async def create_with_fallback(self, **kwargs) -> Any:
        """Try primary model, fall back to alternatives on failure."""
        primary_model = kwargs.pop("model")
        models_to_try = [primary_model] + self.config.fallback_models
        
        # Remove duplicates while preserving order
        models_to_try = list(dict.fromkeys(models_to_try))

        last_error = None
        for model in models_to_try:
            try:
                return await self.create_message(model=model, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed: {e}, trying next...")
                continue

        raise last_error
