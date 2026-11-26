"""
Resilience primitives for ELORA connectors & background validation:
  - Per-provider Circuit Breaker (closed -> open -> half_open)
  - Shared httpx.AsyncClient connection pool for TCP/TLS reuse
  - Bounded exponential backoff for transient failures
"""
import asyncio
import random
import time
import threading
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar
import httpx

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitBreaker:
    """
    Lightweight per-provider circuit breaker.
    Prevents repeatedly waiting on a failing or blocked provider.
    """

    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._state = "closed"  # closed | open | half_open
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and self._opened_at is not None:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = "half_open"
            return self._state

    def allow_request(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._state = "closed"

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold or self._state == "half_open":
                self._state = "open"
                self._opened_at = time.monotonic()
                logger.warning(f"CircuitBreaker OPEN for '{self.name}' after {self._failures} failures")

    def status_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failures": self._failures,
            "threshold": self.failure_threshold,
        }


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, source_id: str) -> CircuitBreaker:
        with self._lock:
            if source_id not in self._breakers:
                self._breakers[source_id] = CircuitBreaker(source_id)
            return self._breakers[source_id]

    def reset_all(self) -> None:
        with self._lock:
            self._breakers.clear()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: v.status_dict() for k, v in self._breakers.items()}


circuit_breakers = CircuitBreakerRegistry()


# ── Shared HTTP Client Pool ───────────────────────────────────────────────────
_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = threading.Lock()


def get_shared_http_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient for connection reuse across validation & requests."""
    global _shared_client
    with _client_lock:
        if _shared_client is None or _shared_client.is_closed:
            _shared_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
                follow_redirects=True,
                headers={"User-Agent": "ELORA-Research-Engine/1.0"},
            )
        return _shared_client


async def close_shared_http_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


async def retry_with_backoff(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 1,
    base_delay: float = 0.25,
) -> T:
    """Execute an async call with bounded exponential backoff on transient errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # pragma: no cover
