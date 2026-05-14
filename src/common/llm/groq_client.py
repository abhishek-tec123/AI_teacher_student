import asyncio
import inspect
import logging
import threading
import time
from typing import List, Optional, Any

from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage

from config.settings import settings
from common.llm.groq_rate_limiter import (
    get_rate_limiter,
    get_concurrency_limiter,
    estimate_tokens,
    increment_daily_tokens,
    is_daily_budget_low,
)

logger = logging.getLogger(__name__)

# Cached ChatGroq instances by (model_name, temperature, max_tokens, max_retries, streaming)
_llm_cache: dict = {}

# Global LLM call tracker
_llm_call_log: list = []
_llm_call_lock = threading.Lock()


def _record_llm_call(model_name: str, estimated_tokens: int):
    """Record an LLM invocation for per-request auditing."""
    global _llm_call_log
    caller_frame = inspect.currentframe().f_back.f_back
    caller_file = inspect.getfile(caller_frame) if caller_frame else "unknown"
    caller_func = caller_frame.f_code.co_name if caller_frame else "unknown"
    # Shorten path
    caller_file = caller_file.split("/src/")[-1] if "/src/" in caller_file else caller_file.split("\\src\\")[-1]
    entry = {
        "timestamp": time.time(),
        "model": model_name,
        "tokens": estimated_tokens,
        "caller_file": caller_file,
        "caller_func": caller_func,
    }
    with _llm_call_lock:
        _llm_call_log.append(entry)
        # Keep only last 500 entries
        if len(_llm_call_log) > 500:
            _llm_call_log = _llm_call_log[-500:]


def get_recent_llm_calls(seconds: float = 10.0) -> list:
    """Return LLM calls within the last N seconds."""
    now = time.time()
    with _llm_call_lock:
        return [c for c in _llm_call_log if now - c["timestamp"] <= seconds]


def _get_cached_llm(
    model_name: str,
    api_key: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    streaming: bool = False,
) -> ChatGroq:
    """Get or create a cached ChatGroq instance."""
    cache_key = (model_name, temperature, max_tokens, max_retries, streaming)
    if cache_key not in _llm_cache:
        kwargs = {
            "model_name": model_name,
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": max_retries,
            "streaming": streaming,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        _llm_cache[cache_key] = ChatGroq(**kwargs)
        logger.info(f"Created cached ChatGroq instance: model={model_name}, temp={temperature}")
    return _llm_cache[cache_key]


def _invoke_llm_sync(
    llm: ChatGroq,
    messages: List[BaseMessage],
    retry_on_429: bool = True,
    retry_max_attempts: int = 5,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Synchronous LLM invoke with retry logic.
    """
    last_exception = None
    attempt = 0

    while attempt < retry_max_attempts:
        try:
            result = llm.invoke(messages)
            logger.info(f"Groq call succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            is_rate_limit = (
                "429" in str(e)
                or "rate_limit_exceeded" in error_str
                or "too many requests" in error_str
                or "rate limit" in error_str
            )

            if not is_rate_limit or not retry_on_429:
                logger.error(f"Groq call failed (not retryable): {e}")
                raise

            attempt += 1
            if attempt >= retry_max_attempts:
                break

            delay = retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Groq rate limit hit (attempt {attempt}/{retry_max_attempts}). "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise last_exception or RuntimeError("Groq call failed after all retries")


async def _invoke_llm_async(
    llm: ChatGroq,
    messages: List[BaseMessage],
    retry_on_429: bool = True,
    retry_max_attempts: int = 5,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Async LLM invoke with retry logic.
    Runs blocking invoke in thread pool to avoid blocking the event loop.
    """
    last_exception = None
    attempt = 0
    loop = asyncio.get_running_loop()

    while attempt < retry_max_attempts:
        try:
            result = await loop.run_in_executor(None, llm.invoke, messages)
            logger.info(f"Groq call succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            is_rate_limit = (
                "429" in str(e)
                or "rate_limit_exceeded" in error_str
                or "too many requests" in error_str
                or "rate limit" in error_str
            )

            if not is_rate_limit or not retry_on_429:
                logger.error(f"Groq call failed (not retryable): {e}")
                raise

            attempt += 1
            if attempt >= retry_max_attempts:
                break

            delay = retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Groq rate limit hit (attempt {attempt}/{retry_max_attempts}). "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

    raise last_exception or RuntimeError("Groq call failed after all retries")


def sync_invoke_with_limiters(
    messages: List[BaseMessage],
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    streaming: bool = False,
    retry_on_429: bool = True,
    retry_max_attempts: int = 5,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Synchronous Groq LLM invocation with centralized rate limiting and retry logic.
    Safe to call from any thread, including FastAPI's run_in_threadpool worker threads.
    """
    _model_name = model_name or getattr(settings, "groq_llm", "llama-3.1-8b-instant")
    _api_key = api_key or getattr(settings, "groq_api_key", None)
    if not _api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    total_text = "\n".join(
        getattr(m, "content", str(m)) for m in messages
    )
    estimated_input_tokens = estimate_tokens(total_text)
    estimated_output_tokens = max_tokens or 1000
    estimated_total = estimated_input_tokens + estimated_output_tokens

    tpm_limit = getattr(settings, "groq_tpm_limit", 7000)
    reserve_tokens = getattr(settings, "groq_tpm_reserve", 500)
    max_concurrent = getattr(settings, "groq_max_concurrent", 2)

    rate_limiter = get_rate_limiter(tpm_limit=tpm_limit, reserve_tokens=reserve_tokens)
    concurrency_limiter = get_concurrency_limiter(max_concurrent=max_concurrent)

    # Acquire rate limit tokens (blocking)
    rate_limiter.acquire_sync(estimated_total)

    llm = _get_cached_llm(
        model_name=_model_name,
        api_key=_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
        streaming=streaming,
    )

    # Acquire concurrency slot and make the call
    with concurrency_limiter:
        result = _invoke_llm_sync(
            llm=llm,
            messages=messages,
            retry_on_429=retry_on_429,
            retry_max_attempts=retry_max_attempts,
            retry_base_delay=retry_base_delay,
        )
    _record_llm_call(_model_name, estimated_total)
    increment_daily_tokens(estimated_total)
    return result


async def async_invoke_with_limiters(
    messages: List[BaseMessage],
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    streaming: bool = False,
    retry_on_429: bool = True,
    retry_max_attempts: int = 5,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Async Groq LLM invocation with centralized rate limiting and retry logic.
    """
    _model_name = model_name or getattr(settings, "groq_llm", "llama-3.1-8b-instant")
    _api_key = api_key or getattr(settings, "groq_api_key", None)
    if not _api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    total_text = "\n".join(
        getattr(m, "content", str(m)) for m in messages
    )
    estimated_input_tokens = estimate_tokens(total_text)
    estimated_output_tokens = max_tokens or 1000
    estimated_total = estimated_input_tokens + estimated_output_tokens

    tpm_limit = getattr(settings, "groq_tpm_limit", 7000)
    reserve_tokens = getattr(settings, "groq_tpm_reserve", 500)
    max_concurrent = getattr(settings, "groq_max_concurrent", 2)

    rate_limiter = get_rate_limiter(tpm_limit=tpm_limit, reserve_tokens=reserve_tokens)
    concurrency_limiter = get_concurrency_limiter(max_concurrent=max_concurrent)

    # Acquire rate limit tokens (async)
    await rate_limiter.acquire_async(estimated_total)

    llm = _get_cached_llm(
        model_name=_model_name,
        api_key=_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
        streaming=streaming,
    )

    async with concurrency_limiter:
        result = await _invoke_llm_async(
            llm=llm,
            messages=messages,
            retry_on_429=retry_on_429,
            retry_max_attempts=retry_max_attempts,
            retry_base_delay=retry_base_delay,
        )
    _record_llm_call(_model_name, estimated_total)
    increment_daily_tokens(estimated_total)
    return result
