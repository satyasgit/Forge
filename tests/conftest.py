import pytest
from agents.retry import get_circuit_breaker

@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset the Claude API circuit breaker before every test."""
    get_circuit_breaker("claude_api").reset()
