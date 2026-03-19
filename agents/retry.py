"""
Retry logic and circuit breaker for agent API calls.

Handles transient failures (rate limits, timeouts, network errors)
with exponential backoff and prevents cascading failures via circuit breaker.
"""
from __future__ import annotations

import functools
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, TypeVar, ParamSpec

import anthropic

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ── Retryable Exceptions ─────────────────────────────────────────────────────

RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    ConnectionError,
    TimeoutError,
)

NON_RETRYABLE_EXCEPTIONS = (
    anthropic.AuthenticationError,
    anthropic.BadRequestError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
)


# ── Retry Decorator ──────────────────────────────────────────────────────────

def with_retry(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    max_wait: float = 30.0,
    jitter: bool = True,
    retryable: tuple = RETRYABLE_EXCEPTIONS,
) -> Callable:
    """
    Decorator that retries a function on transient failures.

    Uses exponential backoff with optional jitter:
        wait = min(backoff_base ** attempt + random(0, 1), max_wait)

    Usage:
        @with_retry(max_retries=3, backoff_base=2.0)
        def call_claude(messages):
            return client.messages.create(...)
    """
    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except NON_RETRYABLE_EXCEPTIONS:
                    raise  # Don't retry auth errors, bad requests, etc.
                except retryable as e:
                    last_exception = e
                    if attempt >= max_retries:
                        break

                    wait = min(backoff_base ** attempt, max_wait)
                    if jitter:
                        wait += random.uniform(0, 1)

                    logger.warning(
                        "[retry] %s failed (attempt %d/%d): %s — waiting %.1fs",
                        fn.__qualname__, attempt + 1, max_retries, e, wait,
                    )
                    time.sleep(wait)

            logger.error(
                "[retry] %s exhausted all %d retries. Last error: %s",
                fn.__qualname__, max_retries, last_exception,
            )
            raise last_exception  # type: ignore[misc]

        return wrapper
    return decorator


# ── Circuit Breaker ──────────────────────────────────────────────────────────

@dataclass
class CircuitBreaker:
    """
    Prevents cascading failures by stopping calls to a failing service.

    States:
        CLOSED  → Normal operation. Failures increment counter.
        OPEN    → All calls rejected immediately. Resets after cooldown.
        HALF_OPEN → Allows one trial call. Success → CLOSED, Failure → OPEN.

    Usage:
        breaker = CircuitBreaker(name="claude_api", failure_threshold=5, cooldown_seconds=60)

        if breaker.allow_request():
            try:
                result = call_claude(...)
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            raise CircuitBreakerOpenError("claude_api circuit is open")
    """
    name: str
    failure_threshold: int = 5        # consecutive failures before opening
    cooldown_seconds: float = 60.0    # how long to stay open
    half_open_max_calls: int = 1      # calls allowed in half-open state

    # Internal state
    _failure_count: int = field(default=0, init=False)
    _state: str = field(default="closed", init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> str:
        if self._state == "open":
            elapsed = time.time() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._state = "half_open"
                self._half_open_calls = 0
                logger.info("[circuit:%s] Transitioning to HALF_OPEN after %.0fs cooldown", self.name, elapsed)
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        current_state = self.state
        if current_state == "closed":
            return True
        if current_state == "half_open":
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False  # open

    def record_success(self) -> None:
        """Record a successful call. Resets failure counter."""
        if self._state in ("half_open", "open"):
            logger.info("[circuit:%s] Success — closing circuit", self.name)
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record a failed call. May trip the breaker open."""
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.time()
            logger.warning(
                "[circuit:%s] OPENED after %d consecutive failures — cooldown %.0fs",
                self.name, self._failure_count, self.cooldown_seconds,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._failure_count = 0
        self._state = "closed"
        self._half_open_calls = 0

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "threshold": self.failure_threshold,
            "cooldown_remaining": max(
                0, self.cooldown_seconds - (time.time() - self._opened_at)
            ) if self._state == "open" else 0,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting calls."""
    pass


# ── Global Circuit Breaker for Claude API ─────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str = "claude_api") -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=5,
            cooldown_seconds=60.0,
        )
    return _breakers[name]
