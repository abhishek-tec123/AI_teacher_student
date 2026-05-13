import logging
"""
Topic Extraction Agent - Extracts syllabus/topics/subtopics from subject agent content
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import concurrent.futures
import threading

from teacher.utils.topic_extraction_utils import (
    initialize_utils,
    get_embedding_model,
    call_llm_direct,
    parse_json_from_llm_response,
    get_agent_chunks_from_mongodb,
    create_topic_extraction_prompt,
    organize_topics_hierarchy
)

from teacher.services.model_cache import model_cache
from config.settings import settings
logger = logging.getLogger(__name__)


# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)



class TopicExtractionAgent:
    """
    Agent for extracting topics and subtopics from subject agent content.

    This agent analyzes document chunks stored in MongoDB Atlas and uses LLM
    to identify and structure the main topics, subtopics, and syllabus hierarchy.
    """

    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_model: Optional[Any] = None
    ):
        self.embedding_model_name = embedding_model_name
        self._embedding_model = embedding_model
        self._loaded = False
        self._llm = None  # Cache LLM instance

        # Initialize shared utils
        initialize_utils(model_cache=model_cache)

    # -----------------------------
    # Embedding Model
    # -----------------------------
    @property
    def embedding_model(self) -> Any:
        """Get embedding model (lazy load)."""
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model(self.embedding_model_name)
        return self._embedding_model

    @property
    def llm(self) -> Any:
        """Get cached LLM instance (lazy load)."""
        if self._llm is None:
            from langchain_groq import ChatGroq
            import os
            
            groq_api_key = settings.groq_api_key
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY not set")
                
            from common.llm.groq_client import sync_invoke_with_limiters
            self._llm = None  # We use centralized client; keep property for compatibility
            self._llm_model_name = settings.default_llm_model
            self._llm_api_key = groq_api_key
        return self._llm

    # -----------------------------
    # Preload Agent
    # -----------------------------
    def load(self):
        """Preload the agent."""
        if self._loaded:
            logger.info("♻️ TopicExtractionAgent already loaded")
            return

        logger.info("⚡ Loading TopicExtractionAgent...")
        _ = self.embedding_model
        _ = self.llm  # Preload LLM
        self._loaded = True
        logger.info("✅ TopicExtractionAgent ready")

    # -----------------------------
    # Main Extraction Method
    # -----------------------------
    def extract_topics_from_agent(
        self,
        subject_agent_id: str,
        db_name: str,
        collection_name: str,
        max_topics: int = 20,
        include_subtopics: bool = True
    ) -> Dict[str, Any]:

        if not self._loaded:
            self.load()

        logger.info(
            f"🔍 Extracting topics from agent {subject_agent_id} "
            f"in {db_name}.{collection_name}"
        )

        try:
            # 1️⃣ Retrieve chunks from MongoDB
            chunks = get_agent_chunks_from_mongodb(
                subject_agent_id,
                db_name,
                collection_name
            )

            if not chunks:
                return {
                    "status": "error",
                    "message": f"No content found for subject agent {subject_agent_id}"
                }

            logger.info(f"📚 Retrieved {len(chunks)} chunks")

            # 2️⃣ Analyze structure
            topics_data = self._analyze_content_structure(
                chunks,
                max_topics=max_topics,
                include_subtopics=include_subtopics
            )

            # 3️⃣ Build response
            result = {
                "status": "success",
                "subject_agent_id": subject_agent_id,
                "db_name": db_name,
                "collection_name": collection_name,
                "topics": topics_data["topics"],
                "total_chunks_analyzed": len(chunks),
                "extraction_metadata": {
                    "model_used": self.embedding_model_name,
                    "extraction_time": datetime.utcnow().isoformat(),
                    "max_topics_requested": max_topics,
                    "include_subtopics": include_subtopics
                }
            }

            logger.info(f"✅ Extracted {len(topics_data['topics'])} main topics")

            return result

        except Exception as e:
            logger.error(f"❌ Topic extraction failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    # -----------------------------
    # Analyze Content Structure
    # -----------------------------
    def _analyze_content_structure(
        self,
        chunks: List[Dict[str, Any]],
        max_topics: int = 20,
        include_subtopics: bool = True
    ) -> Dict[str, Any]:

        chunk_texts = [
            chunk["text"]
            for chunk in chunks
            if chunk.get("text", "").strip()
        ]

        if not chunk_texts:
            return {"topics": []}

        # Optimize sample size for better performance
        chunks_per_sample = 20  # Increased from 10 to reduce LLM calls
        max_samples = min(5, (len(chunk_texts) + chunks_per_sample - 1) // chunks_per_sample)  # Limit to 5 samples max
        samples = []

        for i in range(min(max_samples, (len(chunk_texts) + chunks_per_sample - 1) // chunks_per_sample)):
            start_idx = i * chunks_per_sample
            end_idx = min(start_idx + chunks_per_sample, len(chunk_texts))
            sample_chunks = chunk_texts[start_idx:end_idx]
            sample_text = "\n\n".join(sample_chunks)
            samples.append(sample_text[:2000])  # Reduced from 3000 to 2000 chars

        logger.info(
            f"📊 Processing {len(chunk_texts)} chunks "
            f"in {len(samples)} samples"
        )

        # Process samples concurrently for better performance
        all_topics = []
        max_workers = min(3, len(samples))  # Limit to 3 concurrent workers
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self._extract_topics_from_sample, sample, include_subtopics): i 
                for i, sample in enumerate(samples)
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    topics = future.result()
                    logger.info(f"🔍 Completed sample {index + 1}/{len(samples)}")
                    all_topics.extend(topics)
                except Exception as e:
                    logger.error(f"❌ Error processing sample {index + 1}: {e}")

        organized_topics = organize_topics_hierarchy(
            all_topics,
            max_topics
        )

        return {"topics": organized_topics}

    # -----------------------------
    # Extract Topics From Sample
    # -----------------------------
    def _extract_topics_from_sample(
        self,
        sample_text: str,
        include_subtopics: bool
    ) -> List[Dict[str, Any]]:

        prompt = create_topic_extraction_prompt(include_subtopics)

        try:
            from langchain_core.messages import HumanMessage
            
            if sample_text:
                full_input = f"{prompt}\n\nCONTENT:\n{sample_text[:2000]}"
            else:
                full_input = prompt

            from common.llm.groq_client import sync_invoke_with_limiters
            response = sync_invoke_with_limiters(
                messages=[HumanMessage(content=full_input)],
                model_name=self._llm_model_name,
                api_key=self._llm_api_key,
                retry_on_429=True,
            )
            response_text = getattr(response, "content", str(response)).strip()

            if not response_text:
                logger.warning("Empty LLM response")
                return []

            parsed = parse_json_from_llm_response(response_text)

            topics = parsed.get("topics", [])

            logger.info(f"✅ Extracted {len(topics)} topics")

            return topics

        except Exception as e:
            logger.error(f"LLM topic extraction error: {e}")
            return []

    # -----------------------------
    # Model Info
    # -----------------------------
    def get_embedding_model_info(self) -> Dict[str, str]:

        if self._embedding_model is None:
            return {
                "model_name": self.embedding_model_name,
                "model_type": "Not loaded"
            }

        model = self._embedding_model

        return {
            "model_name": getattr(model, "model_name", self.embedding_model_name),
            "model_type": type(model).__name__
        }