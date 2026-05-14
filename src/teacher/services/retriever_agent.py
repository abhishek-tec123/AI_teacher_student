import logging
"""
RetrieverAgent - Student-adaptive Retriever Agent
Handles:
- Embedding model loading (cached)
- Vector similarity search
- LLM response generation
- Optional dynamic student profile
"""

import os
import asyncio
from typing import Optional, Dict
from langchain_huggingface import HuggingFaceEmbeddings
import sys
from concurrent.futures import ThreadPoolExecutor

from teacher.services.structured_response import StudentProfile
from teacher.services.model_cache import model_cache
from teacher.services.enhanced_similarity_search import retrieve_chunk_for_query_send_to_llm_enhanced
logger = logging.getLogger(__name__)

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class RetrievalOrchestratorAgent:
    """
    Async-enabled Passive Retriever Agent with optional student-adaptive prompts.
    """

    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_model: Optional[HuggingFaceEmbeddings] = None
    ):
        self.embedding_model_name = embedding_model_name
        self._embedding_model = embedding_model
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=5)

    # -----------------------------
    # Embedding model (lazy + cached)
    # -----------------------------
    @property
    def embedding_model(self) -> HuggingFaceEmbeddings:
        if self._embedding_model is None:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self._embedding_model = model_cache.get_embedding_model(self.embedding_model_name)
            logger.info("✅ Embedding model loaded successfully")
        return self._embedding_model

    # -----------------------------
    # Preload (NO LLM CALL)
    # -----------------------------
    def load(self):
        if self._loaded:
            logger.info("♻️ RetrieverAgent already loaded")
            return
        logger.info("⚡ Preloading RetrieverAgent...")
        _ = self.embedding_model
        self._loaded = True
        logger.info("✅ RetrieverAgent preload complete")

    # -----------------------------
    # Async Retrieval + LLM with optional student profile
    # -----------------------------
    async def orchestrate_retrieval_and_response_async(
        self,
        query: str,
        db_name: str,
        collection_name: str,
        student_profile: Optional[dict] = None,  # user can pass dict or None
        subject_agent_id: Optional[str] = None,  # for shared knowledge
        top_k: int = 10
    ) -> str:
        """
        Async version of retrieval and response orchestration.
        """
        
        # Validate profile
        if isinstance(student_profile, dict):
            profile = StudentProfile(**student_profile)  # convert dict to Pydantic
        elif isinstance(student_profile, StudentProfile):
            profile = student_profile  # already validated
        else:
            profile = StudentProfile()  # default

        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if not self._loaded:
            self.load()

        logger.info(f"🔍 Processing async query in {db_name}.{collection_name}")
        
        def _run_retrieval():
            try:
                # Check if this is a shared document query - disable RL for shared docs
                disable_rl = bool(subject_agent_id)
                
                result = retrieve_chunk_for_query_send_to_llm_enhanced(
                    query=query,
                    db_name=db_name,
                    collection_name=collection_name,
                    subject_agent_id=subject_agent_id,
                    embedding_model=self.embedding_model,
                    student_profile=profile.dict(),  # send as dict to similarity_search/groq
                    top_k=top_k,
                    disable_rl=disable_rl
                )
                return result  # {"response": str, "quality_scores": dict, "sources": list}
            except Exception as e:
                logger.error(f"❌ Error during retrieval: {e}")
                raise
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _run_retrieval)

    # -----------------------------
    # Synchronous wrapper for backward compatibility
    # -----------------------------
    def orchestrate_retrieval_and_response(
        self,
        query: str,
        db_name: str,
        collection_name: str,
        student_profile: Optional[dict] = None,  # user can pass dict or None
        subject_agent_id: Optional[str] = None,  # for shared knowledge
        top_k: int = 10
    ) -> str:
        """
        Synchronous wrapper for backward compatibility.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in an event loop, use run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        self.orchestrate_retrieval_and_response_async(
                            query, db_name, collection_name, student_profile, subject_agent_id, top_k
                        )
                    )
                    return future.result(timeout=60)
            else:
                # If no event loop running, run directly
                return asyncio.run(
                    self.orchestrate_retrieval_and_response_async(
                        query, db_name, collection_name, student_profile, subject_agent_id, top_k
                    )
                )
        except Exception as e:
            logger.error(f"Error in async wrapper: {e}")
            # Fallback to synchronous behavior
            return self._orchestrate_sync_fallback(query, db_name, collection_name, student_profile, subject_agent_id, top_k)

    def _orchestrate_sync_fallback(
        self,
        query: str,
        db_name: str,
        collection_name: str,
        student_profile: Optional[dict] = None,
        subject_agent_id: Optional[str] = None,
        top_k: int = 10
    ) -> str:
        """
        Fallback synchronous orchestration.
        """
        # Validate profile
        if isinstance(student_profile, dict):
            profile = StudentProfile(**student_profile)  # convert dict to Pydantic
        elif isinstance(student_profile, StudentProfile):
            profile = student_profile  # already validated
        else:
            profile = StudentProfile()  # default

        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if not self._loaded:
            self.load()

        logger.info(f"🔍 Processing sync query in {db_name}.{collection_name}")
        
        try:
            # Check if this is a shared document query - disable RL for shared docs
            disable_rl = bool(subject_agent_id)
            
            result = retrieve_chunk_for_query_send_to_llm_enhanced(
                query=query,
                db_name=db_name,
                collection_name=collection_name,
                subject_agent_id=subject_agent_id,
                embedding_model=self.embedding_model,
                student_profile=profile.dict(),  # send as dict to similarity_search/groq
                top_k=top_k,
                disable_rl=disable_rl
            )
            return result  # {"response": str, "quality_scores": dict, "sources": list}
        except Exception as e:
            logger.error(f"❌ Error during retrieval: {e}")
            raise


    # -----------------------------
    # Info helper
    # -----------------------------
    def get_embedding_model_info(self) -> Dict[str, str]:
        model = self.embedding_model
        return {
            "model_name": getattr(model, "model_name", self.embedding_model_name),
            "model_type": type(model).__name__
        }
