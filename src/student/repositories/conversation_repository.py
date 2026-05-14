"""
Conversation Management Module

Handles all conversation-related operations including:
- Adding and retrieving conversations
- Conversation history management
- Conversation summarization
- Chat history by agent/subject
- Recent activity tracking
- Feedback updates
"""

from bson import ObjectId
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from common.db.database import DatabaseConnection
import logging
logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation operations and history.
    
    Provides functionality for conversation storage, retrieval,
    summarization, and activity tracking across different subjects/agents.
    """
    
    def __init__(self, db_connection: DatabaseConnection = None):
        """Initialize conversation manager with database connection."""
        self.db = db_connection or DatabaseConnection()
        self.students = self.db.get_students_collection()
    
    def add_conversation(
        self,
        student_id: str,
        subject: str,
        query: str,
        response: str,
        feedback: str = "neutral",
        confusion_type: str = "NO_CONFUSION",
        evaluation: Optional[Dict] = None,
        quality_scores: Optional[Dict] = None,
        additional_data: Optional[Dict] = None,
        agent_id: Optional[str] = None,
        chat_session_id: Optional[str] = None
    ) -> str:
        """
        Add a conversation entry for a student and subject.
        
        Args:
            student_id: Student identifier
            subject: Subject/agent name
            query: Student query
            response: AI response
            feedback: Feedback rating (like, dislike, neutral)
            confusion_type: Type of confusion detected
            evaluation: Optional evaluation data
            quality_scores: Optional quality assessment scores
            additional_data: Additional metadata (e.g., subject_agent_id)
            agent_id: Optional agent identifier for performance tracking
            chat_session_id: Optional chat session identifier for session management
            
        Returns:
            Conversation ID as string
        """
        if feedback not in {"like", "dislike", "neutral"}:
            feedback = "neutral"

        conversation_id = ObjectId()
        timestamp = datetime.utcnow()

        conversation_doc = {
            "_id": conversation_id,
            "conversation_id": str(conversation_id),
            "query": query,
            "response": response,
            "feedback": feedback,
            "confusion_type": confusion_type,
            "timestamp": timestamp
        }

        if chat_session_id is not None:
            conversation_doc["chat_session_id"] = chat_session_id

        if agent_id is not None:
            conversation_doc["agent_id"] = agent_id

        if evaluation is not None:
            conversation_doc["evaluation"] = evaluation
        if quality_scores is not None:
            conversation_doc["quality_scores"] = quality_scores
        if additional_data is not None:
            conversation_doc.update(additional_data)

        # Update agent performance if quality scores available
        if quality_scores is not None and additional_data and additional_data.get("subject_agent_id"):
            logger.info(f"🔥 PERFORMANCE UPDATE TRIGGERED")
            logger.info(f"   - Agent ID: {additional_data['subject_agent_id']}")
            logger.info(f"   - Quality Scores: {quality_scores}")
            logger.info(f"   - Student ID: {student_id}")
            try:
                from ..agents.vector_performance_updater import update_vector_performance
                result = update_vector_performance(
                    subject_agent_id=additional_data["subject_agent_id"],
                    quality_scores=quality_scores,
                    feedback=feedback,
                    confusion_type=confusion_type,
                    student_id=student_id
                )
                logger.info(f"   - Update Result: {result}")
            except Exception as e:
                logger.info(f"❌ Error updating agent performance: {e}")
        else:
            logger.info(f"⚠️ PERFORMANCE UPDATE SKIPPED")
            logger.info(f"   - Quality Scores Present: {quality_scores is not None}")
            logger.info(f"   - Additional Data Present: {additional_data is not None}")
            logger.info(f"   - Agent ID Present: {additional_data.get('subject_agent_id') if additional_data else False}")

        # Push conversation to history
        self.students.update_one(
            {"student_id": student_id},
            {
                "$push": {
                    f"conversation_history.{subject}": {
                        "$each": [conversation_doc],
                        "$sort": {"timestamp": -1},
                        "$slice": 50
                    }
                },
                "$set": {
                    "metadata.last_active": timestamp,
                    f"metadata.last_conversation_id.{subject}": str(conversation_id)
                }
            },
            upsert=True
        )

        # Auto-generate summary when 10 conversations reached
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"conversation_history.{subject}": 1}
        )

        history = doc.get("conversation_history", {}).get(subject, [])

        if len(history) == 10:
            try:
                self.summarize_and_store_conversation(
                    student_id=student_id,
                    subject=subject,
                    limit=10
                )
            except Exception as e:
                logger.info(f"Summary generation failed: {e}")

        return str(conversation_id)
    
    def get_conversation_history(
        self,
        student_id: str,
        subject: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a specific student and subject.
        
        Args:
            student_id: Student identifier
            subject: Subject/agent name
            limit: Optional maximum number of conversations to return
            
        Returns:
            List of conversation documents sorted by timestamp (newest first)
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"conversation_history.{subject}": 1}
        )

        if not doc:
            return []

        history = doc.get("conversation_history", {}).get(subject, [])

        # Sort by latest first
        history = sorted(
            history,
            key=lambda x: x.get("timestamp", datetime.min),
            reverse=True
        )

        # Apply limit if provided
        if limit is not None:
            history = history[:limit]

        # Serialize Mongo types
        return [
            {
                "_id": str(h["_id"]),
                "query": h.get("query", ""),
                "response": h.get("response", ""),
                "feedback": h.get("feedback", "neutral"),
                "confusion_type": h.get("confusion_type", "NO_CONFUSION"),
                "timestamp": h["timestamp"].isoformat() if h.get("timestamp") else None
            }
            for h in history
        ]
    
    def get_chat_history_by_agent(
        self,
        student_id: str,
        subject: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get chat history for a specific student and subject/agent.
        
        Args:
            student_id: Student identifier
            subject: Subject/agent name
            limit: Optional maximum number of conversations
            
        Returns:
            List of formatted chat history entries
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"conversation_history.{subject}": 1}
        )

        if not doc:
            return []

        history = doc.get("conversation_history", {}).get(subject, [])
        if not history:
            return []

        # Apply limit if provided
        if limit:
            history = history[:limit]

        # Format response
        formatted_history = []
        for convo in history:
            formatted_history.append({
                "student_id": student_id,
                "query": convo.get("query"),
                "response": convo.get("response"),
                "evaluation": convo.get("evaluation", {})
            })

        return formatted_history
    
    def get_student_recent_activity(
        self,
        student_id: str,
        limit: int = 1,
        hours_back: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get student's recent chat activity across all subjects/agents.
        
        Args:
            student_id: Student identifier
            limit: Maximum number of activities to return per agent
            hours_back: Optional filter for activities within last N hours
            
        Returns:
            Dict with recent activity list and statistics
        """
        # Fetch student document with all conversation history
        doc = self.students.find_one(
            {"student_id": student_id},
            {"conversation_history": 1}
        )
        
        if not doc:
            return {"recent_activity": [], "total_count": 0}
        
        all_conversations = []
        conversation_history = doc.get("conversation_history", {})
        
        # Iterate through all subjects
        for subject, history in conversation_history.items():
            for convo in history:
                # Apply time filter if specified
                if hours_back and convo.get("timestamp"):
                    cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
                    if convo["timestamp"] < cutoff_time:
                        continue
                
                # Create response preview
                response_text = convo.get("response", "")
                response_preview = response_text[:100] + "..." if len(response_text) > 100 else response_text
                
                # Calculate time ago
                time_ago = ""
                if convo.get("timestamp"):
                    now = datetime.utcnow()
                    convo_time = convo["timestamp"]
                    time_diff = now - convo_time
                    
                    if time_diff.total_seconds() < 60:
                        time_ago = f"{int(time_diff.total_seconds())} seconds ago"
                    elif time_diff.total_seconds() < 3600:
                        time_ago = f"{int(time_diff.total_seconds() / 60)} mins ago"
                    elif time_diff.total_seconds() < 86400:
                        time_ago = f"{int(time_diff.total_seconds() / 3600)} hours ago"
                    else:
                        time_ago = f"{int(time_diff.total_seconds() / 86400)} days ago"
                
                all_conversations.append({
                    "conversation_id": str(convo.get("_id", "")),
                    "subject": subject,
                    "agent_id": convo.get("subject_agent_id", ""),
                    "query": convo.get("query", ""),
                    "response_preview": response_preview,
                    "timestamp": convo["timestamp"].isoformat() if convo.get("timestamp") else None,
                    "time_ago": time_ago,
                    "feedback": convo.get("feedback", "neutral"),
                    "confusion_type": convo.get("confusion_type", "NO_CONFUSION")
                })
        
        # Sort by timestamp (most recent first)
        all_conversations.sort(
            key=lambda x: x.get("timestamp", ""), 
            reverse=True
        )
        
        # Get only the most recent conversation per agent
        latest_per_agent = {}
        for convo in all_conversations:
            agent_key = convo.get("subject", "")
            if agent_key not in latest_per_agent:
                latest_per_agent[agent_key] = convo
        
        # Convert to list and sort by timestamp
        recent_activity_per_agent = sorted(
            latest_per_agent.values(),
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )
        
        # Apply limit to the number of agents shown
        limited_conversations = recent_activity_per_agent[:limit]
        
        # Calculate unique agents and their conversation counts
        unique_agents = {}
        for convo in all_conversations:
            subject = convo.get("subject", "")
            if subject not in unique_agents:
                unique_agents[subject] = {
                    "subject": subject,
                    "agent_id": convo.get("agent_id", ""),
                    "conversation_count": 0
                }
            unique_agents[subject]["conversation_count"] += 1
        
        # Convert to list and sort by conversation count
        unique_agents_list = sorted(
            unique_agents.values(),
            key=lambda x: x["conversation_count"],
            reverse=True
        )
        
        return {
            "recent_activity": limited_conversations,
            "total_count": len(recent_activity_per_agent),
            "agents_used_count": len(unique_agents_list),
            "unique_agents": unique_agents_list
        }
    
    def update_conversation(
        self,
        conversation_id: str,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Update an existing conversation with additional data.
        
        Args:
            conversation_id: Conversation identifier
            additional_data: Additional data to add to the conversation
            
        Returns:
            Number of modified documents
        """
        if not additional_data:
            return 0
            
        # First, find which subject contains this conversation
        try:
            conversation_obj_id = ObjectId(conversation_id)
        except Exception:
            return 0
            
        # Get all subject keys from sample documents
        sample_docs = self.students.find(
            {"conversation_history": {"$exists": True}},
            {"conversation_history": 1}
        )
        
        subjects = set()
        for doc in sample_docs:
            subjects.update(doc.get("conversation_history", {}).keys())
        
        if not subjects:
            return 0
        
        # Search through each subject to find our conversation
        for subject in subjects:
            # Check if this subject contains the conversation
            doc = self.students.find_one(
                {f"conversation_history.{subject}._id": conversation_obj_id},
                {f"conversation_history.{subject}.$": 1}
            )
            
            if doc and doc.get("conversation_history", {}).get(subject):
                # Found the conversation in this subject
                update_doc = {"$set": {}}
                for key, value in additional_data.items():
                    # Store evaluation and subject_agent_id directly at conversation level
                    # Other fields go under additional_data
                    if key in ["evaluation", "subject_agent_id", "chat_session_id"]:
                        update_doc["$set"][f"conversation_history.{subject}.$.{key}"] = value
                    else:
                        update_doc["$set"][f"conversation_history.{subject}.$.additional_data.{key}"] = value
                
                # Update the conversation
                result = self.students.update_one(
                    {f"conversation_history.{subject}._id": conversation_obj_id},
                    update_doc
                )
                
                return result.modified_count
        
        return 0

    def get_conversations_by_chat_session(
        self,
        student_id: str,
        chat_session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a specific chat session.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            limit: Optional maximum number of conversations to return
            
        Returns:
            List of conversation documents sorted by timestamp (newest first)
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {"conversation_history": 1}
        )

        if not doc:
            return []

        conversation_history = doc.get("conversation_history", {})
        session_conversations = []

        # Collect all conversations for this chat session
        for subject, conversations in conversation_history.items():
            for conv in conversations:
                if conv.get("chat_session_id") == chat_session_id:
                    conv_copy = conv.copy()
                    conv_copy["subject"] = subject
                    session_conversations.append(conv_copy)

        # Sort by timestamp (newest first)
        session_conversations.sort(
            key=lambda x: x.get("timestamp", datetime.min),
            reverse=True
        )

        # Apply limit if provided
        if limit is not None:
            session_conversations = session_conversations[:limit]

        # Serialize Mongo types
        return [
            {
                "_id": str(conv["_id"]),
                "chat_session_id": conv.get("chat_session_id"),
                "subject": conv.get("subject"),
                "query": conv.get("query", ""),
                "response": conv.get("response", ""),
                "feedback": conv.get("feedback", "neutral"),
                # "confusion_type": conv.get("confusion_type", "NO_CONFUSION"),
                "timestamp": conv["timestamp"].isoformat() if conv.get("timestamp") else None,
                # "evaluation": conv.get("evaluation", {}),
                "agent_id": conv.get("subject_agent_id")
            }
            for conv in session_conversations
        ]

    def get_conversation_by_id(self, conversation_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific conversation by ID from existing conversation_history structure.
        
        Args:
            conversation_id: Conversation identifier
            student_id: Student identifier
            
        Returns:
            Conversation data if found and belongs to student, None otherwise
        """
        try:
            conversation_obj_id = ObjectId(conversation_id)
        except Exception:
            return None
            
        # Search across all subjects for this conversation
        doc = self.students.find_one(
            {"student_id": student_id},
            {"conversation_history": 1}
        )
        
        if not doc:
            return None
            
        conversation_history = doc.get("conversation_history", {})
        
        # Search through each subject's conversation history
        for subject, history in conversation_history.items():
            for convo in history:
                if str(convo.get("_id")) == conversation_id:
                    return {
                        "conversation_id": conversation_id,
                        "subject": subject,
                        "query": convo.get("query", ""),
                        "response": convo.get("response", ""),
                        "timestamp": convo.get("timestamp"),
                        "feedback": convo.get("feedback", "neutral"),
                        # "evaluation": convo.get("evaluation", {})
                    }
        
        return None
    
    def update_feedback_by_conversation_id(
        self,
        conversation_id: str,
        feedback: str
    ) -> int:
        """
        Update feedback for a specific conversation.
        
        Args:
            conversation_id: Conversation identifier
            feedback: New feedback rating
            
        Returns:
            Number of modified documents (1 if successful, 0 otherwise)
        """
        try:
            conversation_obj_id = ObjectId(conversation_id)
        except Exception:
            return 0

        # Get all subject keys from all documents
        sample_docs = self.students.find(
            {"conversation_history": {"$exists": True}},
            {"conversation_history": 1}
        )

        subjects = set()
        for doc in sample_docs:
            subjects.update(doc.get("conversation_history", {}).keys())
        
        if not subjects:
            return 0

        for subject in subjects:
            # Find the conversation to get quality_scores
            doc = self.students.find_one(
                {f"conversation_history.{subject}._id": conversation_obj_id},
                {f"conversation_history.{subject}.$": 1}
            )
            
            if doc and doc.get("conversation_history", {}).get(subject):
                conv = doc["conversation_history"][subject][0]
                quality_scores = conv.get("quality_scores", {})
                
                # Calculate RL Reward
                reward = 0.0
                if feedback == "like":
                    reward += 1.0
                elif feedback == "dislike":
                    reward -= 1.0
                    
                if quality_scores:
                    rag_relevance = quality_scores.get("rag_relevance", 0) / 100.0
                    completeness = quality_scores.get("answer_completeness", 0) / 100.0
                    hallucination = quality_scores.get("hallucination_risk", 0) / 100.0
                    reward += (rag_relevance * 0.2) + (completeness * 0.2) - (hallucination * 0.1)
                
                reward = round(reward, 3)

                # Update feedback and reward
                result = self.students.update_one(
                    {f"conversation_history.{subject}._id": conversation_obj_id},
                    {
                        "$set": {
                            f"conversation_history.{subject}.$.feedback": feedback,
                            f"conversation_history.{subject}.$.rl_metadata.reward": reward
                        }
                    }
                )

                if result.modified_count > 0:
                    return 1

        return 0
    
    def update_subject_summary(self, student_id: str, subject: str, summary: str) -> int:
        """
        Update subject conversation summary.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            summary: Summary text
            
        Returns:
            Number of modified documents
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {f"conversation_summary.{subject}": summary}}
        )
        return result.modified_count
    
    def get_subject_summary(self, student_id: str, subject: str) -> Optional[str]:
        """
        Get subject conversation summary.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Summary text or None if not found
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"conversation_summary.{subject}": 1}
        )
        return doc.get("conversation_summary", {}).get(subject) if doc else None
    
    def summarize_and_store_conversation(
        self,
        student_id: str,
        subject: str,
        limit: Optional[int] = None,
        prompt: str = "Summarize the conversation clearly for revision."
    ) -> str:
        """
        Generate and store conversation summary.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            limit: Optional limit of conversations to summarize
            prompt: Custom prompt for summarization
            
        Returns:
            Generated summary text
        """
        history = self.get_conversation_history(
            student_id=student_id,
            subject=subject,
            limit=limit
        )

        if not history:
            raise ValueError("No conversation history available")

        # Extract text
        text_blocks = []
        for item in history:
            if item.get("query"):
                text_blocks.append(f"Q: {item['query']}")
            if item.get("response"):
                text_blocks.append(f"A: {item['response']}")

        combined_text = "\n\n".join(text_blocks)

        # Import summarizer
        from ..summrizeStdConv import summarize_text_with_groq

        summary = summarize_text_with_groq(
            text=combined_text,
            prompt=prompt
        )

        # Store summary in MongoDB
        self.students.update_one(
            {"student_id": student_id},
            {
                "$set": {
                    f"conversation_summary.{subject}": summary,
                    "metadata.last_active": datetime.utcnow()
                }
            }
        )

        return summary
