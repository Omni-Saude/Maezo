"""Rate limiting middleware for multi-tenant API protection.

This module implements a token bucket rate limiter with per-tenant isolation
to prevent abuse and ensure fair resource allocation across hospital tenants.

Architecture Decision Record (ADR-027): Token Bucket Algorithm
- Default: 100 requests/minute per tenant
- Burst capacity: 20 requests
- Thread-safe with asyncio lock
- In-memory state (production should use Redis)
"""

import asyncio
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Dict, Optional


class RateLimitExceededError(Exception):
    """Raised when a tenant exceeds their rate limit."""

    def __init__(self, tenant_id: str, retry_after: float):
        self.tenant_id = tenant_id
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for tenant {tenant_id}. "
            f"Retry after {retry_after:.2f} seconds"
        )


@dataclass
class TokenBucket:
    """Token bucket for rate limiting using the leaky bucket algorithm.

    Attributes:
        capacity: Maximum number of tokens (burst size)
        refill_rate: Tokens added per second
        tokens: Current number of available tokens
        last_refill: Timestamp of last token refill
    """

    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill

        # Add tokens based on refill rate
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def time_until_available(self, tokens: int = 1) -> float:
        """Calculate time until requested tokens will be available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens available (0 if already available)
        """
        self._refill()

        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


class TenantRateLimiter:
    """Per-tenant rate limiter using token bucket algorithm.

    This implementation provides isolated rate limiting for each tenant
    to prevent noisy neighbors and ensure fair resource allocation.

    Attributes:
        _rate: Requests per minute per tenant
        _burst: Burst capacity (max tokens in bucket)
        _buckets: Per-tenant token buckets
        _lock: Async lock for thread safety

    Example:
        >>> limiter = TenantRateLimiter(rate=100, burst=20)
        >>> if limiter.check_limit("hospital-123"):
        ...     # Process request
        ...     pass
        ... else:
        ...     raise RateLimitExceededError(...)
    """

    def __init__(self, rate: int = 100, burst: int = 20):
        """Initialize rate limiter.

        Args:
            rate: Maximum requests per minute per tenant
            burst: Maximum burst size (tokens in bucket)
        """
        self._rate = rate  # requests per minute
        self._burst = burst
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    def get_bucket(self, tenant_id: str) -> TokenBucket:
        """Get or create token bucket for a tenant.

        Args:
            tenant_id: Unique tenant identifier

        Returns:
            TokenBucket for the tenant
        """
        if tenant_id not in self._buckets:
            # Convert rate from requests/minute to tokens/second
            refill_rate = self._rate / 60.0
            self._buckets[tenant_id] = TokenBucket(
                capacity=self._burst,
                refill_rate=refill_rate
            )
        return self._buckets[tenant_id]

    def check_limit(self, tenant_id: str) -> bool:
        """Check if request is within rate limit.

        Args:
            tenant_id: Tenant making the request

        Returns:
            True if allowed, False if rate limited
        """
        bucket = self.get_bucket(tenant_id)
        return bucket.consume(1)

    def get_retry_after(self, tenant_id: str) -> float:
        """Get time until tenant can make another request.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Seconds until next request allowed
        """
        bucket = self.get_bucket(tenant_id)
        return bucket.time_until_available(1)

    async def check_limit_async(self, tenant_id: str) -> bool:
        """Async version of check_limit with proper locking.

        Args:
            tenant_id: Tenant making the request

        Returns:
            True if allowed, False if rate limited
        """
        async with self._lock:
            return self.check_limit(tenant_id)


# Global rate limiter instance
_default_limiter: Optional[TenantRateLimiter] = None


def get_rate_limiter() -> TenantRateLimiter:
    """Get or create the default rate limiter instance.

    Returns:
        Global TenantRateLimiter instance
    """
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = TenantRateLimiter()
    return _default_limiter


def rate_limited(func: Callable) -> Callable:
    """Decorator to apply rate limiting to a function.

    The decorated function must accept 'tenant_id' as a keyword argument.
    Raises RateLimitExceededError if rate limit is exceeded.

    Example:
        >>> @rate_limited
        ... async def process_claim(claim_id: str, tenant_id: str):
        ...     # Process claim
        ...     pass

    Args:
        func: Function to decorate (must accept tenant_id kwarg)

    Returns:
        Decorated function with rate limiting

    Raises:
        RateLimitExceededError: If rate limit exceeded for tenant
    """
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tenant_id = kwargs.get('tenant_id')
            if not tenant_id:
                raise ValueError("tenant_id required for rate limiting")

            limiter = get_rate_limiter()

            if not await limiter.check_limit_async(tenant_id):
                retry_after = limiter.get_retry_after(tenant_id)
                raise RateLimitExceededError(tenant_id, retry_after)

            return await func(*args, **kwargs)
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tenant_id = kwargs.get('tenant_id')
            if not tenant_id:
                raise ValueError("tenant_id required for rate limiting")

            limiter = get_rate_limiter()

            if not limiter.check_limit(tenant_id):
                retry_after = limiter.get_retry_after(tenant_id)
                raise RateLimitExceededError(tenant_id, retry_after)

            return func(*args, **kwargs)
        return sync_wrapper
