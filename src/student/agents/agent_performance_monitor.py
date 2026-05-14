import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from bson import ObjectId
import statistics
from enum import Enum

# Import cache
from common.cache.performance_cache import performance_cache
from config.settings import settings
import logging
logger = logging.getLogger(__name__)


class PerformanceLevel(Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good" 
    AVERAGE = "Average"
    POOR = "Poor"
    CRITICAL = "Critical"

class AgentPerformanceMonitor:
    def __init__(self):
        self.client = MongoClient(
            settings.mongodb_uri,
            maxPoolSize=50,  # Connection pooling
            minPoolSize=5,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            retryWrites=True,
            w="majority"
        )
        self.db = self.client[settings.db_name]
        self.students_collection = self.db["students"]
        self.performance_collection = self.db["agent_performance_logs"]
        self.agent_performance_collection = self.db["agent_performance_summary"]
        
        # Import vector performance updater
        from .vector_performance_updater import VectorPerformanceUpdater
        self.vector_updater = VectorPerformanceUpdater()
        
        # Cache for agent registry to avoid repeated database scans
        self._agent_registry_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minutes cache
    
    def _build_agent_registry(self) -> Dict[str, Dict[str, Any]]:
        """Build and cache agent registry from vector databases."""
        current_time = datetime.utcnow().timestamp()
        
        # Try to get from Redis cache first
        cached_registry = performance_cache.get_agent_registry()
        if cached_registry:
            return cached_registry
        
        # Return cached data if still valid
        if (self._agent_registry_cache and self._cache_timestamp and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._agent_registry_cache
        
        # Build fresh registry with optimized queries
        agent_registry = {}
        
        try:
            # Get all databases at once
            db_names = [db for db in self.client.list_database_names() 
                       if db not in ["admin", "local", "config", settings.db_name]]
            
            for db_name in db_names:
                db = self.client[db_name]
                
                # Get all collections at once
                collection_names = db.list_collection_names()
                
                for collection_name in collection_names:
                    collection = db[collection_name]
                    
                    # Use optimized aggregation with indexes
                    pipeline = [
                        {"$match": {"subject_agent_id": {"$exists": True, "$ne": None}}},
                        {"$group": {
                            "_id": "$subject_agent_id",
                            "db_name": {"$first": db_name},
                            "collection_name": {"$first": collection_name},
                            "agent_metadata": {"$first": "$agent_metadata"},
                            "performance": {"$first": "$performance"},
                            "doc_count": {"$sum": 1}
                        }},
                        {"$sort": {"doc_count": -1}}  # Most active agents first
                    ]
                    
                    results = list(collection.aggregate(pipeline, allowDiskUse=True))
                    
                    for result in results:
                        agent_id = result["_id"]
                        if agent_id and isinstance(agent_id, str):
                            agent_registry[agent_id] = {
                                "db_name": result["db_name"],
                                "collection_name": result["collection_name"],
                                "agent_metadata": result["agent_metadata"],
                                "performance": result["performance"],
                                "document_count": result["doc_count"]
                            }
            
            # Update both local cache and Redis
            self._agent_registry_cache = agent_registry
            self._cache_timestamp = current_time
            performance_cache.set_agent_registry(agent_registry, ttl=self._cache_ttl)
            
            logger.info(f"Built agent registry with {len(agent_registry)} agents")
            
        except Exception as e:
            logger.error(f"Error building agent registry: {e}")
            # Return cached data if available, even if expired
            if self._agent_registry_cache:
                return self._agent_registry_cache
        
        return agent_registry
        
    def create_agent_performance_summary(self, subject_agent_id: str, agent_metadata: dict) -> bool:
        """Create initial performance summary for a new agent."""
        try:
            summary = {
                "subject_agent_id": subject_agent_id,
                "agent_metadata": agent_metadata,
                "total_conversations": 0,
                "cumulative_metrics": {
                    "pedagogical_value": 0.0,
                    "critical_confidence": 0.0,
                    "rag_relevance": 0.0,
                    "answer_completeness": 0.0,
                    "hallucination_risk": 0.0,
                    "overall_score": 0.0
                },
                "feedback_counts": {
                    "like": 0,
                    "dislike": 0,
                    "neutral": 0
                },
                "confusion_distribution": {},
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow()
            }
            
            result = self.agent_performance_collection.update_one(
                {"subject_agent_id": subject_agent_id},
                {"$setOnInsert": summary},
                upsert=True
            )
            
            return result.acknowledged
            
        except Exception as e:
            logger.info(f"Error creating agent performance summary: {e}")
            return False
    
    def update_agent_performance(self, subject_agent_id: str, quality_scores: dict, feedback: str = "neutral", confusion_type: str = "NO_CONFUSION") -> bool:
        """Update agent performance after each conversation."""
        try:
            # Get current summary
            current = self.agent_performance_collection.find_one({"subject_agent_id": subject_agent_id})
            
            if not current:
                # Create new summary if doesn't exist
                agent_metadata = self._get_agent_metadata(subject_agent_id)
                self.create_agent_performance_summary(subject_agent_id, agent_metadata)
                current = self.agent_performance_collection.find_one({"subject_agent_id": subject_agent_id})
            
            if not current:
                return False
            
            # Update cumulative metrics (running average)
            total_conversations = current.get("total_conversations", 0)
            cumulative = current.get("cumulative_metrics", {})
            
            # Calculate new cumulative averages
            new_total = total_conversations + 1
            for metric in ["pedagogical_value", "critical_confidence", "rag_relevance", "answer_completeness", "hallucination_risk"]:
                current_value = cumulative.get(metric, 0.0)
                new_value = quality_scores.get(metric, 0.0)
                cumulative[metric] = ((current_value * total_conversations) + new_value) / new_total
            
            # Calculate overall score (excluding hallucination_risk from average)
            core_metrics = ["pedagogical_value", "critical_confidence", "rag_relevance", "answer_completeness"]
            core_values = [cumulative[metric] for metric in core_metrics]
            cumulative["overall_score"] = sum(core_values) / len(core_values) if core_values else 0.0
            
            # Update feedback counts
            feedback_counts = current.get("feedback_counts", {"like": 0, "dislike": 0, "neutral": 0})
            if feedback in feedback_counts:
                feedback_counts[feedback] += 1
            
            # Update confusion distribution
            confusion_dist = current.get("confusion_distribution", {})
            confusion_dist[confusion_type] = confusion_dist.get(confusion_type, 0) + 1
            
            # Update the document
            update_data = {
                "total_conversations": new_total,
                "cumulative_metrics": cumulative,
                "feedback_counts": feedback_counts,
                "confusion_distribution": confusion_dist,
                "last_updated": datetime.utcnow()
            }
            
            result = self.agent_performance_collection.update_one(
                {"subject_agent_id": subject_agent_id},
                {"$set": update_data}
            )
            
            return result.acknowledged
            
        except Exception as e:
            logger.info(f"Error updating agent performance: {e}")
            return False
    
    def get_agent_performance_summary(self, subject_agent_id: str) -> Dict[str, Any]:
        """Get agent performance summary (checks vector documents first)."""
        try:
            # First try to get performance from vector documents
            vector_performance = self.vector_updater.get_agent_performance_from_vectors(subject_agent_id)
            
            if vector_performance and vector_performance.get("total_conversations", 0) > 0:
                return vector_performance
            
            # Fall back to agent_performance_summary collection if vector has no data
            summary = self.agent_performance_collection.find_one({"subject_agent_id": subject_agent_id})
            
            if not summary:
                # Try to create from agent metadata if exists
                agent_metadata = self._get_agent_metadata(subject_agent_id)
                if agent_metadata.get("agent_metadata"):
                    self.create_agent_performance_summary(subject_agent_id, agent_metadata)
                    summary = self.agent_performance_collection.find_one({"subject_agent_id": subject_agent_id})
            
            if not summary:
                return self._get_empty_performance_report(subject_agent_id)
            
            # Calculate satisfaction rate
            feedback_counts = summary.get("feedback_counts", {"like": 0, "dislike": 0, "neutral": 0})
            total_feedback = sum(feedback_counts.values())
            satisfaction_rate = round(((feedback_counts["like"] / total_feedback) * 100), 1) if total_feedback > 0 else 0
            
            # Get metrics
            cumulative_metrics = summary.get("cumulative_metrics", {})
            metrics = {
                **cumulative_metrics,
                "satisfaction_rate": satisfaction_rate,
                "feedback_counts": feedback_counts,
                "confusion_distribution": summary.get("confusion_distribution", {})
            }
            
            # Build performance report
            performance_report = {
                "agent_id": subject_agent_id,
                "agent_metadata": summary.get("agent_metadata", self._get_agent_metadata(subject_agent_id)),
                "performance_period": "All Time (Cumulative)",
                "total_conversations": summary.get("total_conversations", 0),
                "metrics": metrics,
                "performance_level": self.calculate_performance_level(metrics.get("overall_score", 0)),
                "health_indicators": self._calculate_health_indicators(metrics),
                "trend_analysis": {"trend": "Stable", "direction": "neutral"},  # No trend for cumulative data
                "recommendations": self._generate_recommendations(metrics),
                "last_updated": summary.get("last_updated", datetime.utcnow()).isoformat()
            }
            
            return performance_report
            
        except Exception as e:
            logger.info(f"Error getting agent performance summary: {e}")
            return self._get_empty_performance_report(subject_agent_id)
    
    def calculate_performance_level(self, overall_score: float) -> PerformanceLevel:
        if overall_score >= 85:
            return PerformanceLevel.EXCELLENT
        elif overall_score >= 70:
            return PerformanceLevel.GOOD
        elif overall_score >= 55:
            return PerformanceLevel.AVERAGE
        elif overall_score >= 40:
            return PerformanceLevel.POOR
        else:
            return PerformanceLevel.CRITICAL
    
    def get_agent_performance_metrics(self, subject_agent_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive performance metrics for a specific agent."""
        # Try to get from cache first
        cached_data = performance_cache.get_agent_performance(subject_agent_id, days)
        if cached_data:
            return cached_data
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Find all conversations for this agent across all students
        agent_conversations = []
        
        try:
            # Use optimized query with proper indexing
            pipeline = [
                {"$unwind": {"path": "$conversation_history", "preserveNullAndEmptyArrays": False}},
                {"$match": {
                    "conversation_history.subject_agent_id": subject_agent_id,
                    "conversation_history.timestamp": {"$gte": start_date, "$lte": end_date}
                }},
                {"project": {
                    "conversation": "$conversation_history"
                }}
            ]
            
            results = list(self.students_collection.aggregate(pipeline, allowDiskUse=True))
            agent_conversations = [result["conversation"] for result in results]
            
        except Exception as e:
            logger.error(f"Error querying conversations for agent {subject_agent_id}: {e}")
            # Fallback to manual iteration if aggregation fails
            for subject in self.students_collection.find({
                "conversation_history": {"$exists": True}
            }):
                if "conversation_history" in subject:
                    for subj_name, conversations in subject["conversation_history"].items():
                        for conv in conversations:
                            if conv.get("subject_agent_id") == subject_agent_id:
                                if "timestamp" in conv and conv["timestamp"] >= start_date:
                                    agent_conversations.append(conv)
        
        if not agent_conversations:
            empty_report = self._get_empty_performance_report(subject_agent_id)
            # Cache empty results for shorter time
            performance_cache.set_agent_performance(subject_agent_id, days, empty_report, ttl=60)
            return empty_report
        
        # Calculate metrics
        metrics = self._calculate_metrics(agent_conversations)
        
        # Get agent metadata
        agent_metadata = self._get_agent_metadata(subject_agent_id)
        
        # Build performance report
        performance_report = {
            "agent_id": subject_agent_id,
            "agent_metadata": agent_metadata,
            "performance_period": f"Last {days} days",
            "total_conversations": len(agent_conversations),
            "metrics": metrics,
            "performance_level": self.calculate_performance_level(metrics["overall_score"]),
            "health_indicators": self._calculate_health_indicators(metrics),
            "trend_analysis": self._calculate_trends(agent_conversations),
            "recommendations": self._generate_recommendations(metrics),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        # Store performance log
        self._store_performance_log(performance_report)
        
        # Cache the results
        performance_cache.set_agent_performance(subject_agent_id, days, performance_report)
        
        return performance_report
    
    def _calculate_metrics(self, conversations: List[Dict]) -> Dict[str, Any]:
        """Calculate performance metrics from conversations."""
        quality_scores = []
        feedback_counts = {"like": 0, "dislike": 0, "neutral": 0}
        confusion_types = {}
        
        for conv in conversations:
            # Quality scores
            if "quality_scores" in conv:
                scores = conv["quality_scores"]
                quality_scores.append(scores)
            
            # Feedback
            feedback = conv.get("feedback", "neutral")
            if feedback in feedback_counts:
                feedback_counts[feedback] += 1
            
            # Confusion types
            confusion = conv.get("confusion_type", "NO_CONFUSION")
            confusion_types[confusion] = confusion_types.get(confusion, 0) + 1
        
        # Calculate averages
        if quality_scores:
            avg_scores = {}
            for key in ["pedagogical_value", "critical_confidence", "rag_relevance", 
                       "answer_completeness", "hallucination_risk", "overall_score"]:
                values = [score.get(key, 0) for score in quality_scores if key in score]
                avg_scores[key] = round(statistics.mean(values), 1) if values else 0
            
            # Calculate overall score (excluding hallucination_risk from average)
            core_metrics = ["pedagogical_value", "critical_confidence", "rag_relevance", "answer_completeness"]
            core_values = [avg_scores[metric] for metric in core_metrics if metric in avg_scores]
            overall_score = round(statistics.mean(core_values), 1) if core_values else 0
            avg_scores["overall_score"] = overall_score
        else:
            avg_scores = {
                "pedagogical_value": 0,
                "critical_confidence": 0,
                "rag_relevance": 0,
                "answer_completeness": 0,
                "hallucination_risk": 0,
                "overall_score": 0
            }
        
        # Calculate feedback satisfaction rate
        total_feedback = sum(feedback_counts.values())
        satisfaction_rate = round(((feedback_counts["like"] / total_feedback) * 100), 1) if total_feedback > 0 else 0
        
        return {
            **avg_scores,
            "feedback_counts": feedback_counts,
            "satisfaction_rate": satisfaction_rate,
            "confusion_distribution": confusion_types
        }
    
    def _get_agent_metadata(self, subject_agent_id: str) -> Dict[str, Any]:
        """Get agent metadata from the vector database."""
        try:
            # Search across all databases for the agent
            for db_name in self.client.list_database_names():
                if db_name in ["admin", "local", "config", settings.db_name]:
                    continue
                    
                db = self.client[db_name]
                for collection_name in db.list_collection_names():
                    collection = db[collection_name]
                    agent_doc = collection.find_one({"subject_agent_id": subject_agent_id})
                    if agent_doc:
                        return {
                            "class": db_name,
                            "subject": collection_name,
                            "agent_metadata": agent_doc.get("agent_metadata", {}),
                            "document_count": collection.count_documents({"subject_agent_id": subject_agent_id})
                        }
        except Exception as e:
            logger.info(f"Error fetching agent metadata: {e}")
        
        return {"class": "Unknown", "subject": "Unknown", "agent_metadata": {}}
    
    def _calculate_health_indicators(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate health indicators for the agent."""
        indicators = {}
        
        # Quality health
        overall = metrics.get("overall_score", 0)
        if overall >= 80:
            indicators["quality_health"] = {"status": "Healthy", "color": "green"}
        elif overall >= 60:
            indicators["quality_health"] = {"status": "Warning", "color": "yellow"}
        else:
            indicators["quality_health"] = {"status": "Critical", "color": "red"}
        
        # Hallucination risk
        hallucination = metrics.get("hallucination_risk", 0)
        if hallucination >= 80:
            indicators["hallucination_health"] = {"status": "Safe", "color": "green"}
        elif hallucination >= 60:
            indicators["hallucination_health"] = {"status": "Moderate", "color": "yellow"}
        else:
            indicators["hallucination_health"] = {"status": "High Risk", "color": "red"}
        
        # Student satisfaction
        satisfaction = metrics.get("satisfaction_rate", 0)
        if satisfaction >= 80:
            indicators["satisfaction_health"] = {"status": "Excellent", "color": "green"}
        elif satisfaction >= 60:
            indicators["satisfaction_health"] = {"status": "Good", "color": "yellow"}
        else:
            indicators["satisfaction_health"] = {"status": "Poor", "color": "red"}
        
        return indicators
    
    def _calculate_trends(self, conversations: List[Dict]) -> Dict[str, Any]:
        """Calculate performance trends over time."""
        if len(conversations) < 2:
            return {"trend": "Insufficient data", "direction": "neutral"}
        
        # Sort by timestamp
        conversations.sort(key=lambda x: x.get("timestamp", datetime.min))
        
        # Split into two halves for trend analysis
        mid_point = len(conversations) // 2
        first_half = conversations[:mid_point]
        second_half = conversations[mid_point:]
        
        # Calculate average scores for each half
        first_avg = self._calculate_metrics(first_half)
        second_avg = self._calculate_metrics(second_half)
        
        # Determine trend
        score_diff = second_avg["overall_score"] - first_avg["overall_score"]
        
        if score_diff > 5:
            trend = "Improving"
            direction = "up"
        elif score_diff < -5:
            trend = "Declining"
            direction = "down"
        else:
            trend = "Stable"
            direction = "neutral"
        
        return {
            "trend": trend,
            "direction": direction,
            "score_change": round(score_diff, 1),
            "recent_avg": second_avg["overall_score"],
            "earlier_avg": first_avg["overall_score"]
        }
    
    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on performance metrics."""
        recommendations = []
        
        overall = metrics.get("overall_score", 0)
        hallucination = metrics.get("hallucination_risk", 0)
        satisfaction = metrics.get("satisfaction_rate", 0)
        
        if overall < 60:
            recommendations.append("Consider updating training materials to improve response quality")
        
        if hallucination < 70:
            recommendations.append("Review and update knowledge base to reduce hallucination risk")
        
        if satisfaction < 60:
            recommendations.append("Analyze student feedback to identify areas for improvement")
        
        if metrics.get("critical_confidence", 0) < 50:
            recommendations.append("Improve confidence in responses by enhancing knowledge coverage")
        
        if metrics.get("rag_relevance", 0) < 60:
            recommendations.append("Optimize retrieval system for better context relevance")
        
        if not recommendations:
            recommendations.append("Agent is performing well - continue current configuration")
        
        return recommendations
    
    def _store_performance_log(self, performance_report: Dict[str, Any]):
        """Store performance log in database."""
        try:
            log_entry = {
                "agent_id": performance_report["agent_id"],
                "timestamp": datetime.utcnow(),
                "overall_score": performance_report["metrics"]["overall_score"],
                "performance_level": performance_report["performance_level"].value,
                "total_conversations": performance_report["total_conversations"],
                "health_indicators": performance_report["health_indicators"],
                "metrics_summary": {
                    "pedagogical_value": performance_report["metrics"]["pedagogical_value"],
                    "critical_confidence": performance_report["metrics"]["critical_confidence"],
                    "rag_relevance": performance_report["metrics"]["rag_relevance"],
                    "answer_completeness": performance_report["metrics"]["answer_completeness"],
                    "hallucination_risk": performance_report["metrics"]["hallucination_risk"],
                    "satisfaction_rate": performance_report["metrics"]["satisfaction_rate"]
                }
            }
            
            self.performance_collection.insert_one(log_entry)
        except Exception as e:
            logger.info(f"Error storing performance log: {e}")
    
    def _get_empty_performance_report(self, subject_agent_id: str) -> Dict[str, Any]:
        """Return empty performance report for agents with no data."""
        return {
            "agent_id": subject_agent_id,
            "agent_metadata": self._get_agent_metadata(subject_agent_id),
            "performance_period": "Last 30 days",
            "total_conversations": 0,
            "metrics": {
                "pedagogical_value": 0,
                "critical_confidence": 0,
                "rag_relevance": 0,
                "answer_completeness": 0,
                "hallucination_risk": 0,
                "overall_score": 0,
                "satisfaction_rate": 0,
                "feedback_counts": {"like": 0, "dislike": 0, "neutral": 0},
                "confusion_distribution": {}
            },
            "performance_level": PerformanceLevel.CRITICAL,
            "health_indicators": {
                "quality_health": {"status": "No Data", "color": "gray"},
                "hallucination_health": {"status": "No Data", "color": "gray"},
                "satisfaction_health": {"status": "No Data", "color": "gray"}
            },
            "trend_analysis": {"trend": "No Data", "direction": "neutral"},
            "recommendations": ["Agent has no conversation data - needs testing and deployment"],
            "last_updated": datetime.utcnow().isoformat()
        }
    
    def get_all_agents_overview(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get performance overview for all agents from cached registry."""
        import time
        start_time = time.time()
        logger.info(f"🚀 Starting get_all_agents_overview for {days} days")
        
        # Try to get from cache first
        cached_overview = performance_cache.get_agent_overview(days)
        if cached_overview:
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"⚡ Cache HIT! Returned in {elapsed:.2f}ms")
            return cached_overview
        
        logger.info("📦 Cache miss - building fresh overview...")
        cache_start = time.time()
        
        # Get agent registry from cache
        agent_registry = self._build_agent_registry()
        registry_time = (time.time() - cache_start) * 1000
        logger.info(f"📋 Agent registry built in {registry_time:.2f}ms ({len(agent_registry)} agents)")
        
        # Build overview from cached registry
        build_start = time.time()
        overview = []
        for agent_id, agent_info in agent_registry.items():
            performance = agent_info.get("performance")
            
            # Use cached performance data if available, otherwise get default
            if performance:
                metrics = performance.get("metrics", {})
                performance_level = performance.get("performance_level", "Critical")
                health_status = performance.get("health_indicators", {}).get("quality_health", {}).get("status", "Critical")
                last_updated = performance.get("last_updated", datetime.utcnow().isoformat())
            else:
                # Fallback to default values
                metrics = {
                    "overall_score": 0,
                    "pedagogical_value": 0,
                    "critical_confidence": 0,
                    "rag_relevance": 0,
                    "answer_completeness": 0,
                    "hallucination_risk": 0
                }
                performance_level = "Critical"
                health_status = "Critical"
                last_updated = datetime.utcnow().isoformat()
            
            # Handle both enum and string types
            if hasattr(performance_level, 'value'):
                performance_level = performance_level.value
            else:
                performance_level = str(performance_level)
            
            overview.append({
                "agent_id": agent_id,
                "agent_name": agent_info["agent_metadata"].get("agent_name", "Unknown"),
                "class_name": agent_info["db_name"],
                "subject": agent_info["collection_name"],
                "overall_score": metrics.get("overall_score", 0),
                "performance_level": performance_level,
                "total_conversations": performance.get("total_conversations", 0) if performance else 0,
                "health_status": health_status,
                "last_updated": last_updated,
                "document_count": agent_info.get("document_count", 0)
            })
        
        # Sort by overall score, then by document count
        overview.sort(key=lambda x: (x["overall_score"], x["document_count"]), reverse=True)
        
        build_time = (time.time() - build_start) * 1000
        logger.info(f"🏗️  Overview built in {build_time:.2f}ms")
        
        # Cache results
        cache_set_start = time.time()
        performance_cache.set_agent_overview(days, overview)
        cache_set_time = (time.time() - cache_set_start) * 1000
        logger.info(f"💾 Results cached in {cache_set_time:.2f}ms")
        
        total_time = (time.time() - start_time) * 1000
        logger.info(f"✅ Total get_all_agents_overview time: {total_time:.2f}ms")
        
        return overview
    
    def get_agents_needing_attention(self, threshold_score: float = 60) -> List[Dict[str, Any]]:
        """Get agents that need attention based on performance threshold."""
        overview = self.get_all_agents_overview()
        return [agent for agent in overview if agent["overall_score"] < threshold_score]
