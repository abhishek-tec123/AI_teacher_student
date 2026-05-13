import logging
import time
from typing import List, Optional, Any

from langchain_core.messages import BaseMessage, AIMessage
from config.settings import settings

logger = logging.getLogger(__name__)

# Cached OpenAI client instances
_ollama_client_cache: dict = {}


def _get_ollama_client(api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 30.0):
    """Get or create a cached OpenAI client for Ollama."""
    cache_key = (api_key, base_url, timeout)
    if cache_key not in _ollama_client_cache:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("The 'openai' package is required for Ollama integration. Install it with: pip install openai")

        _ollama_client_cache[cache_key] = OpenAI(
            api_key=api_key or settings.ollama_api_key or "dummy",
            base_url=base_url or settings.ollama_base_url,
            timeout=timeout,
        )
        logger.info(f"Created Ollama client: base_url={base_url or settings.ollama_base_url}")
    return _ollama_client_cache[cache_key]


def _convert_messages_to_openai(messages: List[BaseMessage]) -> List[dict]:
    """Convert LangChain messages to OpenAI chat format."""
    openai_messages = []
    for m in messages:
        role = "user"
        if hasattr(m, "type"):
            if m.type == "human":
                role = "user"
            elif m.type == "ai":
                role = "assistant"
            elif m.type == "system":
                role = "system"
        content = getattr(m, "content", str(m))
        openai_messages.append({"role": role, "content": content})
    return openai_messages


def sync_invoke_ollama(
    messages: List[BaseMessage],
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    retry_on_429: bool = True,
    retry_max_attempts: int = 3,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Synchronous Ollama LLM invocation using OpenAI-compatible API.
    Returns an AIMessage-like object with a .content attribute.
    """
    _model_name = model_name or settings.default_llm_model.replace("ollama/", "")
    _api_key = api_key or settings.ollama_api_key
    if not _api_key:
        raise ValueError("OLLAMA_API_KEY is not set in environment variables.")

    client = _get_ollama_client(api_key=_api_key, base_url=base_url, timeout=timeout)
    openai_messages = _convert_messages_to_openai(messages)

    last_exception = None
    attempt = 0

    while attempt < retry_max_attempts:
        try:
            response = client.chat.completions.create(
                model=_model_name,
                messages=openai_messages,
                temperature=temperature if temperature is not None else 0.7,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            content = response.choices[0].message.content
            logger.info(f"Ollama call succeeded on attempt {attempt + 1}")
            # Return an object with .content to match ChatGroq.invoke() behavior
            return AIMessage(content=content)
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            is_rate_limit = (
                "429" in str(e)
                or "rate_limit_exceeded" in error_str
                or "too many requests" in error_str
            )

            if not is_rate_limit or not retry_on_429:
                logger.error(f"Ollama call failed (not retryable): {e}")
                raise

            attempt += 1
            if attempt >= retry_max_attempts:
                break

            delay = retry_base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Ollama rate limit hit (attempt {attempt}/{retry_max_attempts}). "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise last_exception or RuntimeError("Ollama call failed after all retries")


async def async_invoke_ollama(
    messages: List[BaseMessage],
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    retry_on_429: bool = True,
    retry_max_attempts: int = 3,
    retry_base_delay: float = 2.0,
) -> Any:
    """
    Async Ollama LLM invocation (runs sync call in thread pool).
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        sync_invoke_ollama,
        messages,
        model_name,
        api_key,
        base_url,
        temperature,
        max_tokens,
        timeout,
        max_retries,
        retry_on_429,
        retry_max_attempts,
        retry_base_delay,
    )
