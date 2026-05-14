"""
Vector Performance Updater

Optimized version with targeted database search and early termination.
"""

import os
from pymongo import MongoClient
from typing import Dict, Any, List
from datetime import datetime, timedelta
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

class VectorPerformanceUpdater:
    """Updates performance data in vector documents."""
    
    def __init__(self):
        self.client = MongoClient(settings.mongodb_uri)
    
    def update_agent_performance_in_vectors(self, subject_agent_id: str, quality_scores: Dict[str, float], 
                                          feedback: str = "neutral", confusion_type: str = "NO_CONFUSION",
                                          student_id: str = None) -> bool:
        """
        Update performance data for an agent with optimized search.
        """
        import uuid
        call_id = str(uuid.uuid4())[:8]  # Short unique ID for this call
        
        logger.info(f"🚀 VECTOR PERFORMANCE UPDATE STARTED [{call_id}]")
        logger.info(f"   - Call ID: {call_id}")
        logger.info(f"   - Target Agent ID: {subject_agent_id}")
        logger.info(f"   - Quality Scores: {quality_scores}")
        logger.info(f"   - Student ID: {student_id}")
        logger.info(f"   - Feedback: {feedback}")
        logger.info(f"   - Confusion Type: {confusion_type}")
        logger.info(f"   - Timestamp: {datetime.now().isoformat()}")

        try:
            # First, find which database contains this agent (optimized search)
            target_database = None
            target_collection = None
            
            for db_name in self.client.list_database_names():
                if db_name in ["admin", "local", "config", settings.db_name]:
                    continue
                    
                db = self.client[db_name]
                logger.info(f"   - Scanning database: {db_name}")
                
                for collection_name in db.list_collection_names():
                    collection = db[collection_name]
                    
                    # Check if this collection has the agent
                    sample_doc = collection.find_one({"subject_agent_id": subject_agent_id})
                    if sample_doc:
                        target_database = db_name
                        target_collection = collection_name
                        logger.info(f"   ✅ Found agent in collection: {db_name}.{collection_name}")
                        break  # Found it, no need to search more collections
                
                if target_database:
                    break  # Found it, no need to search more databases
            
            if not target_database:
                logger.info(f"⚠️ No documents found for agent {subject_agent_id}")
                return False
            
            # Now update only the target database and collection
            db = self.client[target_database]
            collection = db[target_collection]
            
            # Check how many documents exist for this agent
            doc_count = collection.count_documents({"subject_agent_id": subject_agent_id})
            logger.info(f"   📊 Found {doc_count} documents for agent {subject_agent_id}")
            
            # Update ALL documents for this agent in this collection only
            # But first, get the current performance from any one document to avoid double counting
            current_doc = collection.find_one({"subject_agent_id": subject_agent_id})
            if current_doc and "performance" in current_doc:
                # Use the existing performance data as base to avoid double counting
                current_perf = current_doc["performance"]
                current_conv_count = current_perf.get("total_conversations", 0)
                logger.info(f"   📈 Current conversation count: {current_conv_count}")
                
                updated_performance = self._calculate_updated_performance(
                    current_perf, quality_scores, feedback, confusion_type, student_id, call_id
                )
                
                new_conv_count = updated_performance.get("total_conversations", 0)
                logger.info(f"   📈 New conversation count: {new_conv_count}")
                logger.info(f"   📈 Increment: {new_conv_count - current_conv_count}")
            else:
                # Use default performance if no existing data
                logger.info(f"   ⚠️ No existing performance data found, using default")
                updated_performance = self._calculate_updated_performance(
                    self._get_default_performance(), quality_scores, feedback, confusion_type, student_id, call_id
                )
            
            logger.info(f"   🔄 Updating {doc_count} documents with new performance data...")
            
            # Instead of update_many, let's update all documents individually to avoid any issues
            # This ensures we don't have any race conditions or inconsistent updates
            all_docs = collection.find({"subject_agent_id": subject_agent_id})
            total_updated = 0
            
            for doc in all_docs:
                result = collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"performance": updated_performance}}
                )
                if result.modified_count > 0:
                    total_updated += 1
            
            logger.info(f"   ✅ Updated {total_updated} documents in {target_database}.{target_collection}")
            logger.info(f"   🎯 PERFORMANCE UPDATE COMPLETED [{call_id}]")
            return total_updated > 0
                
        except Exception as e:
            logger.info(f"❌ Error updating vector performance: {e}")
            return False
    
    def _get_default_performance(self) -> Dict[str, Any]:
        """Get default performance structure matching expected format."""
        return {
            "performance_period": "All Time (Cumulative)",
            "total_conversations": 0,
            "unique_students": 0,
            "student_usage": {
                "total_students": 0,
                "student_ids": [],
                "conversation_per_student": {},
                "student_performance": {}
            },
            "metrics": {
                "pedagogical_value": 0,
                "critical_confidence": 0,
                "rag_relevance": 0,
                "answer_completeness": 0,
                "hallucination_risk": 0,
                "overall_score": 0,
                "satisfaction_rate": 0,
                "feedback_counts": {
                    "like": 0,
                    "dislike": 0,
                    "neutral": 0
                },
                "confusion_distribution": {}
            },
            "performance_level": "Critical",
            "health_indicators": {
                "quality_health": {"status": "No Data", "color": "gray"},
                "hallucination_health": {"status": "No Data", "color": "gray"},
                "engagement_health": {"status": "No Data", "color": "gray"}
            },
            "trend_analysis": {},
            "recommendations": [],
            "last_updated": datetime.now().isoformat()
        }
    
    def _calculate_updated_performance(self, current_performance: Dict[str, Any], 
                                   quality_scores: Dict[str, float], feedback: str, 
                                   confusion_type: str, student_id: str, call_id: str = "unknown") -> Dict[str, Any]:
        """Calculate updated performance metrics while preserving original structure."""
        try:
            logger.info(f"🔧 CALCULATING UPDATED PERFORMANCE [{call_id}]")
            logger.info(f"   - Input total_conversations: {current_performance.get('total_conversations', 0)}")
            
            # Copy current performance to preserve structure
            updated = current_performance.copy()
            
            # Update conversation count
            current_total = current_performance.get("total_conversations", 0)
            updated["total_conversations"] = current_total + 1
            
            logger.info(f"   - Updated total_conversations: {updated['total_conversations']} (incremented by 1)")
            
            # Update student_usage structure (preserve existing format)
            student_usage = updated.get("student_usage", {})
            
            # Ensure student_usage has the correct structure
            if "total_students" not in student_usage:
                student_usage["total_students"] = 0
            if "student_ids" not in student_usage:
                student_usage["student_ids"] = []
            if "conversation_per_student" not in student_usage:
                student_usage["conversation_per_student"] = {}
            if "student_performance" not in student_usage:
                student_usage["student_performance"] = {}
            
            # Add new student if not already present
            if student_id and student_id not in student_usage.get("student_ids", []):
                student_usage["student_ids"].append(student_id)
                student_usage["total_students"] = len(student_usage["student_ids"])
                logger.info(f"   - Added new student {student_id}, total students: {student_usage['total_students']}")
            
            # Update conversation count per student
            if student_id:
                conv_per_student = student_usage.get("conversation_per_student", {})
                current_student_conv = conv_per_student.get(student_id, 0)
                conv_per_student[student_id] = current_student_conv + 1
                student_usage["conversation_per_student"] = conv_per_student
                logger.info(f"   - Student {student_id} conversations: {current_student_conv} -> {conv_per_student[student_id]}")
                
                # Update student performance
                student_perf = student_usage.get("student_performance", {})
                if student_id not in student_perf:
                    student_perf[student_id] = {
                        "conversations": 0,
                        "average_score": 0,
                        "feedback_counts": {"like": 0, "dislike": 0, "neutral": 0},
                        "last_interaction": datetime.now().isoformat()
                    }
                
                student_perf[student_id]["conversations"] += 1
                student_perf[student_id]["last_interaction"] = datetime.now().isoformat()
                
                # Update feedback counts
                if feedback in student_perf[student_id]["feedback_counts"]:
                    student_perf[student_id]["feedback_counts"][feedback] += 1
                
                # Calculate average score from quality scores
                if quality_scores:
                    overall_score = quality_scores.get("overall_score", 0)
                    current_avg = student_perf[student_id].get("average_score", 0)
                    conv_count = student_perf[student_id]["conversations"]
                    new_avg = ((current_avg * (conv_count - 1)) + overall_score) / conv_count
                    student_perf[student_id]["average_score"] = round(new_avg, 2)
                
                student_usage["student_performance"] = student_perf
            
            updated["student_usage"] = student_usage
            
            # Fix unique_students calculation - it should match the actual count of unique student IDs
            updated["unique_students"] = len(student_usage.get("student_ids", []))
            logger.info(f"   - Final unique_students count: {updated['unique_students']}")
            
            # Update metrics structure (preserve existing format)
            metrics = updated.get("metrics", {})
            
            # Update quality scores (weighted average)
            for metric, value in quality_scores.items():
                if metric in metrics:
                    current_value = metrics.get(metric, 0)
                    count = updated["total_conversations"]
                    new_value = ((current_value * (count - 1)) + value) / count
                    metrics[metric] = round(new_value, 2)
                else:
                    metrics[metric] = value
            
            updated["metrics"] = metrics
            
            # Update performance level
            overall_score = metrics.get("overall_score", 0)
            if overall_score >= 80:
                performance_level = "Excellent"
            elif overall_score >= 60:
                performance_level = "Good"
            elif overall_score >= 40:
                performance_level = "Fair"
            else:
                performance_level = "Critical"
            
            # Update health indicators (preserve existing structure)
            health_indicators = updated.get("health_indicators", {})
            health_indicators["quality_health"] = {
                "status": performance_level,
                "color": "green" if overall_score >= 60 else "yellow" if overall_score >= 40 else "red"
            }
            health_indicators["hallucination_health"] = {
                "status": "Low Risk" if metrics.get("hallucination_risk", 0) <= 10 else "Medium Risk" if metrics.get("hallucination_risk", 0) <= 25 else "High Risk",
                "color": "green" if metrics.get("hallucination_risk", 0) <= 10 else "yellow" if metrics.get("hallucination_risk", 0) <= 25 else "red"
            }
            health_indicators["engagement_health"] = {
                "status": "Active" if updated["total_conversations"] >= 10 else "Low Activity",
                "color": "green" if updated["total_conversations"] >= 10 else "yellow"
            }
            updated["health_indicators"] = health_indicators
            
            # Update trend analysis (preserve existing structure)
            trend_analysis = updated.get("trend_analysis", {})
            trend_analysis["performance_trend"] = "improving" if overall_score >= 60 else "stable"
            updated["trend_analysis"] = trend_analysis
            
            # Update recommendations (preserve existing structure)
            recommendations = updated.get("recommendations", [])
            if overall_score < 60:
                recommendations.append("Consider improving response quality and engagement")
            elif overall_score >= 80:
                recommendations.append("Maintain excellent performance standards")
            updated["recommendations"] = recommendations
            
            # Update last_updated
            updated["last_updated"] = datetime.now().isoformat()
            
            logger.info(f"   ✅ PERFORMANCE CALCULATION COMPLETED [{call_id}]")
            return updated
            
        except Exception as e:
            logger.info(f"❌ Error calculating updated performance: {e}")
            return current_performance
    
    def get_agent_performance_from_vectors(self, subject_agent_id: str) -> Dict[str, Any]:
        """
        Get agent performance data from vector documents.
        
        Args:
            subject_agent_id: The agent ID
            
        Returns:
            Dict containing performance data or empty structure if not found
        """
        try:
            # Find which database contains this agent
            target_database = None
            target_collection = None
            
            for db_name in self.client.list_database_names():
                if db_name in ["admin", "local", "config", settings.db_name]:
                    continue
                    
                db = self.client[db_name]
                
                for collection_name in db.list_collection_names():
                    collection = db[collection_name]
                    
                    # Check if this collection has the agent
                    sample_doc = collection.find_one({"subject_agent_id": subject_agent_id})
                    if sample_doc:
                        target_database = db_name
                        target_collection = collection_name
                        break
                
                if target_database:
                    break
            
            if not target_database:
                logger.info(f"⚠️ No documents found for agent {subject_agent_id}")
                return self._get_empty_performance_data(subject_agent_id)
            
            # Get performance data from first document found
            db = self.client[target_database]
            collection = db[target_collection]
            
            agent_doc = collection.find_one({"subject_agent_id": subject_agent_id})
            if not agent_doc:
                return self._get_empty_performance_data(subject_agent_id)
            
            performance = agent_doc.get("performance", {})
            
            # Ensure unique_students is calculated correctly
            student_usage = performance.get("student_usage", {})
            student_ids = student_usage.get("student_ids", [])
            
            # Fix unique_students calculation
            if "unique_students" not in performance or performance["unique_students"] != len(student_ids):
                performance["unique_students"] = len(student_ids)
                
                # Update the document if we fixed the count
                collection.update_many(
                    {"subject_agent_id": subject_agent_id},
                    {"$set": {"performance.unique_students": len(student_ids)}}
                )
            
            # Build complete performance report
            return {
                "agent_id": subject_agent_id,
                "agent_metadata": agent_doc.get("agent_metadata", {}),
                **performance  # Include all performance data
            }
            
        except Exception as e:
            logger.info(f"❌ Error getting agent performance from vectors: {e}")
            return self._get_empty_performance_data(subject_agent_id)
    
    def _get_empty_performance_data(self, subject_agent_id: str) -> Dict[str, Any]:
        """Return empty performance data structure."""
        return {
            "agent_id": subject_agent_id,
            "agent_metadata": {},
            "performance_period": "All Time (Cumulative)",
            "total_conversations": 0,
            "unique_students": 0,
            "student_usage": {
                "total_students": 0,
                "student_ids": [],
                "conversation_per_student": {},
                "student_performance": {}
            },
            "metrics": {
                "pedagogical_value": 0,
                "critical_confidence": 0,
                "rag_relevance": 0,
                "answer_completeness": 0,
                "hallucination_risk": 0,
                "overall_score": 0,
                "satisfaction_rate": 0,
                "feedback_counts": {
                    "like": 0,
                    "dislike": 0,
                    "neutral": 0
                },
                "confusion_distribution": {}
            },
            "performance_level": "Critical",
            "health_indicators": {
                "quality_health": {"status": "No Data", "color": "gray"},
                "hallucination_health": {"status": "No Data", "color": "gray"},
                "engagement_health": {"status": "No Data", "color": "gray"}
            },
            "trend_analysis": {},
            "recommendations": [],
            "last_updated": datetime.now().isoformat()
        }

# Convenience function for easy usage
def update_vector_performance(subject_agent_id: str, quality_scores: Dict[str, float], 
                         feedback: str = "neutral", confusion_type: str = "NO_CONFUSION",
                         student_id: str = None) -> bool:
    """
    Update agent performance in vector documents after each conversation.
    
    Call this function after each agent query to maintain performance tracking.
    
    Args:
        subject_agent_id: The agent ID
        quality_scores: Dictionary with pedagogical_value, critical_confidence, etc.
        feedback: Student feedback (like/dislike/neutral)
        confusion_type: Detected confusion type
        student_id: Student ID (optional, for tracking unique students)
    
    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        updater = VectorPerformanceUpdater()
        return updater.update_agent_performance_in_vectors(
            subject_agent_id=subject_agent_id,
            quality_scores=quality_scores,
            feedback=feedback,
            confusion_type=confusion_type,
            student_id=student_id
        )
    except Exception as e:
        logger.info(f"❌ Error updating vector performance: {e}")
        return False

def get_vector_performance(subject_agent_id: str) -> Dict[str, Any]:
    """
    Get agent performance from vector documents.
    
    Args:
        subject_agent_id: The agent ID
        
    Returns:
        Dict containing performance data
    """
    try:
        updater = VectorPerformanceUpdater()
        return updater.get_agent_performance_from_vectors(subject_agent_id)
    except Exception as e:
        logger.info(f"❌ Error getting vector performance: {e}")
        return {
            "agent_id": subject_agent_id,
            "agent_metadata": {},
            "performance_period": "Last 30 days",
            "total_conversations": 0,
            "unique_students": 0,
            "student_usage": {},
            "metrics": {
                "pedagogical_value": 0,
                "critical_confidence": 0,
                "rag_relevance": 0,
                "answer_completeness": 0,
                "hallucination_risk": 0,
                "overall_score": 0,
                "satisfaction_rate": 0,
                "feedback_counts": {
                    "like": 0,
                    "dislike": 0,
                    "neutral": 0
                },
                "confusion_distribution": {}
            },
            "performance_level": "Critical",
            "health_indicators": {
                "quality_health": {"status": "No Data", "color": "gray"},
                "hallucination_health": {"status": "No Data", "color": "gray"},
                "engagement_health": {"status": "No Data", "color": "gray"}
            },
            "trend_analysis": {},
            "recommendations": [],
            "last_updated": datetime.now().isoformat()
        }
