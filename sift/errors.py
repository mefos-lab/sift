"""Reusable error handling and rate limiting for external API calls.

Every external HTTP call should go through ``api_call()`` which provides:

- **Per-service rate limiting** based on documented API limits
- **Retries** with exponential backoff for transient errors
- **Error tracking** via ``ServiceTracker`` for surfacing warnings

When adding a new data source, add its rate limit to
``SERVICE_RATE_LIMITS`` below.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import httpx

log = logging.getLogger(__name__)

# HTTP status codes worth retrying — transient server/proxy errors and rate limits
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Per-service rate limits ─────────────────────────────────────────
#
# Minimum seconds between requests to each service.  Derived from
# documented limits with headroom to stay well within them.
#
# When adding a new service, look up its documented rate limit and
# add an entry here.  The value is 1/max_rps rounded up.
#
# Source documentation:
#   ICIJ           — undocumented; conservative 2 req/s
#   OpenSanctions  — monthly quota only, no per-second limit; 5 req/s
#   GLEIF          — 60 req/min → 1 req/s
#   SEC EDGAR      — 10 req/s (also enforced in sec_client.py)
#   Companies House— 600 per 5 min → 2 req/s
#   CourtListener  — 5,000/hr → ~1.4 req/s
#   Aleph          — ~30 req/min anonymous → 0.5 req/s
#   Wikidata       — ~50 req/s API; 5 concurrent SPARQL; 2 req/s safe
#   Land Registry  — undocumented; conservative 2 req/s

SERVICE_RATE_LIMITS: dict[str, float] = {
    "ICIJ":             0.25,   # 4 req/s   (undocumented — polite)
    "OpenSanctions":    0.20,   # 5 req/s   (monthly quota only)
    "GLEIF":            1.00,   # 1 req/s   (60/min documented)
    "SEC EDGAR":        0.12,   # ~8 req/s  (10/s documented)
    "Companies House":  0.50,   # 2 req/s   (600/5min documented)
    "CourtListener":    0.75,   # ~1.3 req/s (5000/hr documented)
    "Aleph":            2.00,   # 0.5 req/s (30/min anon documented)
    "Wikidata":         0.50,   # 2 req/s   (conservative)
    "Land Registry":    0.50,   # 2 req/s   (undocumented — conservative)
}


class _ServiceRateLimiter:
    """Per-service async rate limiter.

    Tracks the last request time for each service and sleeps the
    minimum interval before allowing the next request.  Thread-safe
    via per-service asyncio locks.
    """

    def __init__(self) -> None:
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, service: str) -> asyncio.Lock:
        if service not in self._locks:
            self._locks[service] = asyncio.Lock()
        return self._locks[service]

    async def wait(self, service: str) -> None:
        """Wait until it is safe to call *service* again."""
        min_interval = SERVICE_RATE_LIMITS.get(service)
        if min_interval is None:
            return  # unknown service — no throttle

        async with self._lock_for(service):
            now = time.monotonic()
            last = self._last_call.get(service, 0.0)
            elapsed = now - last
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_call[service] = time.monotonic()


# Module-level singleton — shared across all trackers in the process
_rate_limiter = _ServiceRateLimiter()


@dataclass
class ServiceError:
    """A single recorded error from an external service."""

    service: str
    endpoint: str
    status_code: int | None
    message: str


@dataclass
class ServiceTracker:
    """Tracks which services have encountered errors during an operation.

    Usage::

        tracker = ServiceTracker()

        result = await api_call(tracker, "icij", "/reconcile", some_coro())
        if result is None:
            # call failed — tracker already recorded it

        # At the end, check tracker.warnings for a human-readable summary
        for w in tracker.warnings:
            print(w)
    """

    errors: list[ServiceError] = field(default_factory=list)
    # track per-service error counts to avoid flooding with repeated messages
    _counts: dict[str, int] = field(default_factory=dict)

    def record(self, service: str, endpoint: str, exc: Exception) -> None:
        """Record an error from *service* at *endpoint*."""
        status_code = None
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            message = f"HTTP {status_code}"
            try:
                body = exc.response.text[:200]
                message = f"HTTP {status_code} — {body}"
            except Exception:
                pass
        elif isinstance(exc, httpx.TimeoutException):
            message = "request timed out"
        elif isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            message = "connection failed"
        else:
            message = f"{type(exc).__name__}: {exc}"

        self.errors.append(ServiceError(
            service=service, endpoint=endpoint,
            status_code=status_code, message=message,
        ))
        key = f"{service}:{endpoint}"
        self._counts[key] = self._counts.get(key, 0) + 1
        log.warning("Service error: %s %s — %s", service, endpoint, message)

    @property
    def warnings(self) -> list[str]:
        """Human-readable warning strings, one per service/endpoint combo."""
        seen: dict[str, ServiceError] = {}
        for err in self.errors:
            key = f"{err.service}:{err.endpoint}"
            if key not in seen:
                seen[key] = err
        lines = []
        for key, err in seen.items():
            count = self._counts.get(key, 1)
            suffix = f" ({count} failures)" if count > 1 else ""
            lines.append(
                f"{err.service} ({err.endpoint}) is returning errors, "
                f"skipping for now{suffix} — {err.message}"
            )
        return lines

    @property
    def failed_services(self) -> list[str]:
        """Unique service names that had at least one error."""
        return sorted({e.service for e in self.errors})

    def to_dict(self) -> dict[str, Any]:
        """Serializable summary for inclusion in API responses."""
        return {
            "warnings": self.warnings,
            "failed_services": self.failed_services,
            "error_count": len(self.errors),
            "errors": [
                {
                    "service": e.service,
                    "endpoint": e.endpoint,
                    "status_code": e.status_code,
                    "message": e.message,
                }
                for e in self.errors
            ],
        }


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception is worth retrying."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    # Timeouts and connection errors are always worth retrying
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError,
                            httpx.NetworkError))


async def api_call(
    tracker: ServiceTracker,
    service: str,
    endpoint: str,
    coro_or_factory: Any,
    *,
    max_retries: int = 2,
) -> Any | None:
    """Await an async call with retries, or ``None`` on failure.

    Accepts either:
    - A coroutine (single attempt only — coroutines can't be re-awaited)
    - A zero-arg callable returning a coroutine (enables retries)

    On transient errors (HTTP 429/500/502/503/504, timeouts, connection
    failures), retries up to *max_retries* times with exponential
    backoff (0.5s, 1.0s). Non-retryable errors fail immediately.

    All failures are recorded in *tracker* with the *service* name and
    *endpoint* so callers can surface warnings like:
    "ICIJ (/reconcile) is returning errors, skipping for now"

    Usage::

        # With a factory (retryable — preferred):
        result = await api_call(tracker, "ICIJ", "/reconcile",
                                lambda: icij_client.reconcile(query=name))

        # With a coroutine (single attempt, backwards compatible):
        result = await api_call(tracker, "ICIJ", "/reconcile",
                                icij_client.reconcile(query=name))
    """
    is_factory = callable(coro_or_factory) and not asyncio.iscoroutine(coro_or_factory)
    attempts = (1 + max_retries) if is_factory else 1

    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            await _rate_limiter.wait(service)
            coro = coro_or_factory() if is_factory else coro_or_factory
            return await coro
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1 and _is_retryable(exc):
                delay = 0.5 * (2 ** attempt)  # 0.5s, 1.0s
                log.info("Retrying %s %s (attempt %d/%d) after %.1fs — %s",
                         service, endpoint, attempt + 2, attempts, delay,
                         type(exc).__name__)
                await asyncio.sleep(delay)
            else:
                break

    # All attempts exhausted or non-retryable error
    if last_exc is not None:
        tracker.record(service, endpoint, last_exc)
    return None
