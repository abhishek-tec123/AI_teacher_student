import logging
import os
import sys
import asyncio
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from teacher.services.retriever_agent import RetrievalOrchestratorAgent
from student.services.run_single_query import run_query
logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


class StudentAgent:
    """
    High-level async-enabled agent wrapper for running queries
    with optional student personalization.
    """

    def __init__(self):
        self.retriever_agent = RetrievalOrchestratorAgent()
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=3)

    def load(self):
        """
        Load retriever resources once (embeddings, vector DB, etc.)
        """
        if not self._loaded:
            logger.info("Loading RetrieverAgent...")
            self.retriever_agent.load()
            self._loaded = True

    async def ask_async(
        self,
        query: str,
        class_name: str,
        subject: str,
        student_profile: Optional[Dict] = None,
        subject_agent_id: Optional[str] = None,  # for shared knowledge
        top_k: int = 5,
        is_deep_dive: bool = False,
        chunk_context: Optional[str] = None,
    ):
        """
        Async version of ask method for better performance.
        """
        if not self._loaded:
            self.load()

        logger.info("Running async query for class=%s subject=%s deep_dive=%s", class_name, subject, is_deep_dive)

        def _run_query():
            return run_query(
                retriever_agent=self.retriever_agent,
                query=query,
                db_name=class_name,
                collection_name=subject,
                student_profile=student_profile,
                subject_agent_id=subject_agent_id,  # Pass for shared knowledge
                top_k=top_k,
                is_deep_dive=is_deep_dive,
                chunk_context=chunk_context,
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _run_query)

    def ask(
        self,
        query: str,
        class_name: str,
        subject: str,
        student_profile: Optional[Dict] = None,
        subject_agent_id: Optional[str] = None,  # for shared knowledge
        top_k: int = 5,
        is_deep_dive: bool = False,
        chunk_context: Optional[str] = None,
    ):
        """
        Run a query with optional student profile.
        Uses async version internally for better performance.

        Args:
            query (str): Student question
            class_name (str): Class/grade (e.g., '10th')
            subject (str): Subject (e.g., 'Science')
            student_profile (dict, optional): Personalization config
            is_deep_dive (bool): If True, bypass retriever and reuse chunk_context
            chunk_context (str, optional): Pre-built chunk context for deep-dive
        """
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread
                return asyncio.run(
                    self.ask_async(
                        query, class_name, subject, student_profile, subject_agent_id, top_k,
                        is_deep_dive, chunk_context,
                    )
                )

            if loop.is_running():
                # If already in an event loop, use a separate thread to run the async task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.ask_async(
                            query, class_name, subject, student_profile, subject_agent_id, top_k,
                            is_deep_dive, chunk_context,
                        )
                    )
                    return future.result(timeout=60)
            else:
                # Loop exists but not running
                return asyncio.run(
                    self.ask_async(
                        query, class_name, subject, student_profile, subject_agent_id, top_k,
                        is_deep_dive, chunk_context,
                    )
                )
        except Exception as e:
            logger.error(f"Error in async wrapper: {e}")
            # Fallback to synchronous behavior
            return self._ask_sync_fallback(query, class_name, subject, student_profile, subject_agent_id, top_k, is_deep_dive, chunk_context)

    def _ask_sync_fallback(
        self,
        query: str,
        class_name: str,
        subject: str,
        student_profile: Optional[Dict] = None,
        subject_agent_id: Optional[str] = None,
        top_k: int = 5,
        is_deep_dive: bool = False,
        chunk_context: Optional[str] = None,
    ):
        """
        Fallback synchronous ask method.
        """
        if not self._loaded:
            self.load()

        logger.info("Running sync query for class=%s subject=%s deep_dive=%s", class_name, subject, is_deep_dive)

        return run_query(
            retriever_agent=self.retriever_agent,
            query=query,
            db_name=class_name,
            collection_name=subject,
            student_profile=student_profile,
            subject_agent_id=subject_agent_id,  # Pass for shared knowledge
            top_k=top_k,
            is_deep_dive=is_deep_dive,
            chunk_context=chunk_context,
        )
