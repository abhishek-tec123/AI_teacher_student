import os
import asyncio
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from concurrent.futures import ThreadPoolExecutor
from config.settings import settings
import logging
logger = logging.getLogger(__name__)


# -----------------------------
# Async LLM with Connection Pooling
# -----------------------------
_llm_executor = ThreadPoolExecutor(max_workers=5)
_llm_cache = {}
_cache_ttl = 600  # 10 minutes for LLM responses

def _get_llm_cache_key(query: str, context: str, system_prompt: str) -> str:
    """Generate cache key for LLM responses."""
    import hashlib
    content = f"{query}_{context[:200]}_{system_prompt[:100]}"
    return hashlib.md5(content.encode()).hexdigest()

def _get_cached_llm_response(cache_key: str):
    """Get cached LLM response if valid."""
    import time
    if cache_key in _llm_cache:
        cached_data, timestamp = _llm_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            logger.info(f"🎯 Using cached LLM response for key: {cache_key[:8]}...")
            return cached_data
        else:
            del _llm_cache[cache_key]
    return None

def _cache_llm_response(cache_key: str, response):
    """Cache LLM response."""
    import time
    _llm_cache[cache_key] = (response, time.time())
    # Limit cache size
    if len(_llm_cache) > 50:
        oldest_key = min(_llm_cache.keys(), key=lambda k: _llm_cache[k][1])
        del _llm_cache[oldest_key]

async def _generate_response_async(
    query: str,
    context: str = None,
    system_prompt: str = "Provide a clear, short, and simple response."
) -> str:
    """Async version of LLM response generation."""
    
    # Check cache first
    cache_key = _get_llm_cache_key(query, context or "", system_prompt)
    cached_response = _get_cached_llm_response(cache_key)
    if cached_response:
        return cached_response
    
    def _generate():
        try:
            groq_api_key = settings.groq_api_key
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY is not set in environment variables.")

            # Build input for LLM
            if context:
                full_input = f"""
{system_prompt}

QUESTION:
{query}

CONTEXT:
{context}
""".strip()
            else:
                full_input = f"""
{system_prompt}

QUESTION:
{query}
""".strip()

            from common.llm.groq_client import sync_invoke_with_limiters

            response = sync_invoke_with_limiters(
                messages=[HumanMessage(content=full_input)],
                model_name=settings.default_llm_model,
                api_key=groq_api_key,
                timeout=30.0,
                max_retries=2,
                retry_on_429=True,
            )
            result = getattr(response, "content", str(response)).strip()
            
            # Cache the response
            _cache_llm_response(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in LLM generation: {e}")
            raise
    
    loop = asyncio.get_event_loop()
    if loop is None or loop.is_closed():
        # If no event loop or it's closed, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return await loop.run_in_executor(_llm_executor, _generate)
        finally:
            loop.close()
    else:
        return await loop.run_in_executor(_llm_executor, _generate)

async def generate_response_stream_async(
    query: str,
    context: str = None,
    system_prompt: str = "Provide a clear, short, and simple response."
):
    """Async streaming version of LLM response generation."""
    
    def _generate_stream():
        try:
            groq_api_key = settings.groq_api_key
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY is not set in environment variables.")

            # Build input for LLM
            if context:
                full_input = f"""
{system_prompt}

QUESTION:
{query}

CONTEXT:
{context}
""".strip()
            else:
                full_input = f"""
{system_prompt}

QUESTION:
{query}
""".strip()

            from common.llm.groq_client import sync_invoke_with_limiters

            # Note: streaming via centralized client uses invoke for simplicity
            # If true streaming is needed, use ChatGroq directly with caution
            response = sync_invoke_with_limiters(
                messages=[HumanMessage(content=full_input)],
                model_name=settings.default_llm_model,
                api_key=groq_api_key,
                timeout=30.0,
                max_retries=2,
                retry_on_429=True,
            )
            content = getattr(response, 'content', '')
            if content:
                yield content
                    
        except Exception as e:
            logger.error(f"Error in LLM streaming: {e}")
            yield f"Error: {str(e)}"
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_llm_executor, _generate_stream)


def generate_response_with_groq(
    query: str,
    context: str | None = None,
    system_prompt: str = "Provide a clear, short, and simple response."
) -> str:
    """
    Generates a simple response for a general query.
    Optionally uses context (e.g., text to summarize or reference).
    """

    if not query.strip():
        raise ValueError("Query cannot be empty")

    try:
        # Try to run async version for better performance
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already in an event loop, use run_in_executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    _generate_response_async(query, context, system_prompt)
                )
                return future.result(timeout=30)
        else:
            # If no event loop running, run directly
            return asyncio.run(_generate_response_async(query, context, system_prompt))
    except Exception as e:
        logger.error(f"Error in async wrapper: {e}")
        # Fallback to synchronous behavior
        return _generate_sync_fallback(query, context, system_prompt)

def _generate_sync_fallback(
    query: str,
    context: str = None,
    system_prompt: str = "Provide a clear, short, and simple response."
) -> str:
    """
    Fallback synchronous LLM generation.
    """
    try:
        groq_api_key = settings.groq_api_key
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in environment variables.")

        # Build input for LLM
        if context:
            full_input = f"""
{system_prompt}

QUESTION:
{query}

CONTEXT:
{context}
""".strip()
        else:
            full_input = f"""
{system_prompt}

QUESTION:
{query}
""".strip()

        from common.llm.groq_client import sync_invoke_with_limiters

        response = sync_invoke_with_limiters(
            messages=[HumanMessage(content=full_input)],
            model_name=settings.default_llm_model,
            api_key=groq_api_key,
            retry_on_429=True,
        )

        result = getattr(response, "content", str(response)).strip()

        logger.info("Response generated successfully")

        return result
        
    except Exception as e:
        logger.error(f"Error in synchronous LLM generation: {e}")
        raise
