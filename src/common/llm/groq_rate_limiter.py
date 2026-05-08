import asyncio
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter for Groq API TPM management.
    Works across both sync and async contexts.
    """

    def __init__(self, tpm_limit: int = 7000, reserve_tokens: int = 500):
        self.tpm_limit = tpm_limit
        self.reserve_tokens = reserve_tokens
        self.available_tokens = float(tpm_limit)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * (self.tpm_limit / 60.0)
        self.available_tokens = min(self.tpm_limit, self.available_tokens + tokens_to_add)
        self.last_refill = now

    def acquire_sync(self, tokens_needed: int) -> None:
        """Blocking synchronous acquire."""
        with self._lock:
            self._refill()
            effective_limit = self.tpm_limit - self.reserve_tokens

            if tokens_needed > effective_limit:
                logger.warning(
                    f"Request needs {tokens_needed} tokens, which exceeds "
                    f"effective limit of {effective_limit}. Allowing anyway, but expect possible 429."
                )

            while self.available_tokens < tokens_needed:
                wait_time = (tokens_needed - self.available_tokens) / self.tpm_limit * 60.0
                wait_time = max(wait_time, 0.5)
                logger.info(
                    f"Rate limiter: waiting {wait_time:.1f}s for "
                    f"{tokens_needed} tokens (available: {self.available_tokens:.0f})"
                )
                time.sleep(wait_time)
                self._refill()

            self.available_tokens -= tokens_needed
            logger.info(
                f"Rate limiter: acquired {tokens_needed} tokens, "
                f"remaining: {self.available_tokens:.0f}"
            )

    async def acquire_async(self, tokens_needed: int) -> None:
        """Async wrapper that yields control while waiting."""
        # Fast path: try non-blocking acquire
        with self._lock:
            self._refill()
            if self.available_tokens >= tokens_needed:
                self.available_tokens -= tokens_needed
                logger.info(
                    f"Rate limiter: acquired {tokens_needed} tokens, "
                    f"remaining: {self.available_tokens:.0f}"
                )
                return

            effective_limit = self.tpm_limit - self.reserve_tokens
            if tokens_needed > effective_limit:
                logger.warning(
                    f"Request needs {tokens_needed} tokens, which exceeds "
                    f"effective limit of {effective_limit}. Allowing anyway, but expect possible 429."
                )

            needed = tokens_needed

        # Slow path: poll with sleeps (releases GIL for other threads)
        while True:
            with self._lock:
                self._refill()
                if self.available_tokens >= needed:
                    self.available_tokens -= needed
                    logger.info(
                        f"Rate limiter: acquired {needed} tokens, "
                        f"remaining: {self.available_tokens:.0f}"
                    )
                    return
                wait_time = (needed - self.available_tokens) / self.tpm_limit * 60.0
                wait_time = max(wait_time, 0.5)
            logger.info(
                f"Rate limiter: waiting {wait_time:.1f}s for "
                f"{needed} tokens (available: {self.available_tokens:.0f})"
            )
            await asyncio.sleep(wait_time)


class GroqConcurrencyLimiter:
    """
    Thread-safe concurrency limiter.
    Uses threading.Semaphore so it works across any thread/loop context.
    """

    def __init__(self, max_concurrent: int = 2):
        self.semaphore = threading.Semaphore(max_concurrent)

    def acquire_sync(self) -> None:
        self.semaphore.acquire()

    def release_sync(self) -> None:
        self.semaphore.release()

    async def acquire_async(self) -> None:
        """Async wrapper that yields while waiting for the semaphore."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.semaphore.acquire)

    def release_async(self) -> None:
        self.semaphore.release()

    def __enter__(self):
        self.acquire_sync()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_sync()
        return False

    async def __aenter__(self):
        await self.acquire_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release_async()
        return False


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# Global shared limiters (singletons, thread-safe)
_rate_limiter: Optional[TokenBucketRateLimiter] = None
_concurrency_limiter: Optional[GroqConcurrencyLimiter] = None
_lock = threading.Lock()


def get_rate_limiter(tpm_limit: int = 7000, reserve_tokens: int = 500) -> TokenBucketRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        with _lock:
            if _rate_limiter is None:
                _rate_limiter = TokenBucketRateLimiter(tpm_limit=tpm_limit, reserve_tokens=reserve_tokens)
    return _rate_limiter


def get_concurrency_limiter(max_concurrent: int = 2) -> GroqConcurrencyLimiter:
    global _concurrency_limiter
    if _concurrency_limiter is None:
        with _lock:
            if _concurrency_limiter is None:
                _concurrency_limiter = GroqConcurrencyLimiter(max_concurrent=max_concurrent)
    return _concurrency_limiter


def reset_limiters() -> None:
    """Reset global limiters (useful for testing)."""
    global _rate_limiter, _concurrency_limiter
    with _lock:
        _rate_limiter = None
        _concurrency_limiter = None
