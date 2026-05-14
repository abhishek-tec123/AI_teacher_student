from fastapi import APIRouter, HTTPException, Query, Depends, status
from typing import List
from pydantic import BaseModel, Field, validator
from datetime import datetime
from student.agents.agent_performance_monitor import AgentPerformanceMonitor
from common.auth.dependencies import get_current_user, require_role, require_any_role, require_permission
from student.agents.vector_performance_updater import get_vector_performance
from .analytics import get_all_agent_performance  # reuse shared helper
import logging
logger = logging.getLogger(__name__)


router = APIRouter(tags=["agent-performance"])


# ================================
# RESPONSE MODELS
# ================================

class PerformanceResponse(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=100)
    agent_metadata: dict
    performance_period: str
    total_conversations: int = Field(..., ge=0)
    metrics: dict
    performance_level: str
    health_indicators: dict
    trend_analysis: dict
    recommendations: List[str]
    last_updated: str
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        if not v or v.strip() == '':
            raise ValueError('Agent ID cannot be empty')
        return v.strip()
    
    @validator('performance_level')
    def validate_performance_level(cls, v):
        valid_levels = ['Excellent', 'Good', 'Average', 'Poor', 'Critical']
        if v not in valid_levels:
            raise ValueError(f'Performance level must be one of: {valid_levels}')
        return v


class AgentOverviewResponse(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=100)
    agent_name: str = Field(..., min_length=1, max_length=200)
    class_name: str = Field(..., min_length=1, max_length=100)
    subject: str = Field(..., min_length=1, max_length=100)
    overall_score: float = Field(..., ge=0, le=100)
    performance_level: str
    total_conversations: int = Field(..., ge=0)
    health_status: str
    last_updated: str
    
    @validator('agent_id', 'agent_name', 'class_name', 'subject')
    def validate_non_empty_fields(cls, v):
        if not v or v.strip() == '':
            raise ValueError('Field cannot be empty')
        return v.strip()


class AgentOverviewWithCountResponse(BaseModel):
    agents: List[AgentOverviewResponse]
    total_agents: int

class HealthCheckResponse(BaseModel):
    critical_agents: List[AgentOverviewResponse]
    total_agents: int
    critical_count: int
    alert_summary: dict
    last_checked: str


# ================================
# STATIC ROUTES FIRST
# ================================

@router.get("/overview", response_model=AgentOverviewWithCountResponse)
async def get_all_agents_overview(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back for performance data"),
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """Get performance overview for all agents.
    
    Args:
        days: Number of days to look back for performance data (1-365)
        current_user: Authenticated user with admin or teacher role
        
    Returns:
        List of agents with their performance overview
    
    Raises:
        HTTPException: If authentication fails or data retrieval fails
    """
    try:
        logger.info(f"User {current_user.get('user_id')} requesting agent overview for {days} days")
        
        monitor = AgentPerformanceMonitor()
        overview_data = monitor.get_all_agents_overview(days)
        
        if not overview_data:
            logger.warning("No agent data found")
            return AgentOverviewWithCountResponse(
                agents=[],
                total_agents=0
            )
        
        agents = [AgentOverviewResponse(**agent) for agent in overview_data]
        logger.info(f"Retrieved {len(agents)} agents overview")
        
        return AgentOverviewWithCountResponse(
            agents=agents,
            total_agents=len(agents)
        )
        
    except ValueError as e:
        logger.error(f"Validation error in get_all_agents_overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request parameters: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_all_agents_overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve agent performance overview"
        )


@router.get("/health-check", response_model=HealthCheckResponse)
async def get_health_check(
    threshold_score: float = Query(default=60, ge=0, le=100),
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    try:
        monitor = AgentPerformanceMonitor()
        critical_agents = monitor.get_agents_needing_attention(threshold_score)
        all_agents = monitor.get_all_agents_overview()

        alert_summary = {}
        for agent in all_agents:
            level = agent["performance_level"]
            alert_summary[level] = alert_summary.get(level, 0) + 1

        return HealthCheckResponse(
            critical_agents=[AgentOverviewResponse(**a) for a in critical_agents],
            total_agents=len(all_agents),
            critical_count=len(critical_agents),
            alert_summary=alert_summary,
            last_checked=datetime.utcnow().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/summary")
async def get_metrics_summary(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    try:
        monitor = AgentPerformanceMonitor()
        all_agents = monitor.get_all_agents_overview(days)

        if not all_agents:
            return {
                "message": "No agent data available",
                "period": f"Last {days} days",
                "total_agents": 0
            }

        total_conversations = sum(a["total_conversations"] for a in all_agents)
        avg_score = sum(a["overall_score"] for a in all_agents) / len(all_agents)

        performance_levels = {}
        for agent in all_agents:
            level = agent["performance_level"]
            performance_levels[level] = performance_levels.get(level, 0) + 1

        health_distribution = {}
        for agent in all_agents:
            health = agent["health_status"]
            health_distribution[health] = health_distribution.get(health, 0) + 1

        return {
            "period": f"Last {days} days",
            "total_agents": len(all_agents),
            "total_conversations": total_conversations,
            "average_score": round(avg_score, 1),
            "performance_distribution": performance_levels,
            "health_distribution": health_distribution,
            "top_performers": all_agents[:5],
            "agents_needing_attention": len([a for a in all_agents if a["overall_score"] < 60])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# LEGACY / BACKWARDS-COMPAT ROUTES
# ================================

@router.get("/all-agents-performance")
async def legacy_all_agents_performance(
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """
    Backwards-compatible alias for /api/v1/performance/analytics/all-agents-performance.
    Keeps existing frontend route /api/v1/performance/all-agents-performance working.
    """
    try:
        logger.info(
            f"User {current_user.get('user_id')} requesting LEGACY full agents performance"
        )
        agents = get_all_agent_performance()

        return {
            "success": True,
            "message": f"Found {len(agents)} agents with detailed performance",
            "total_agents": len(agents),
            "agents": agents,
        }
    except Exception as e:
        logger.error(f"Error in legacy_all_agents_performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving detailed agents performance: {str(e)}",
        )


@router.get("/agent-performance/{agent_id}")
async def legacy_agent_performance(
    agent_id: str,
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """
    Backwards-compatible alias for /api/v1/performance/analytics/agent-performance/{agent_id}.
    Keeps existing frontend route /api/v1/performance/agent-performance/{agent_id} working.
    """
    try:
        logger.info(
            f"User {current_user.get('user_id')} requesting LEGACY performance for agent {agent_id}"
        )

        # Reuse logic from analytics.get_single_agent_performance
        vector_performance = get_vector_performance(agent_id)

        if not vector_performance or vector_performance.get("total_conversations", 0) == 0:
            monitor = AgentPerformanceMonitor()
            summary = monitor.get_agent_performance_summary(agent_id)

            if summary:
                return {
                    "success": True,
                    "message": f"Performance data for {agent_id}",
                    "agent_id": agent_id,
                    "source": "summary_collection",
                    "performance": summary,
                }

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        return {
            "success": True,
            "message": f"Performance data for {agent_id}",
            "agent_id": agent_id,
            "source": "vector_documents",
            "performance": vector_performance,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in legacy_agent_performance for {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving agent performance for {agent_id}: {str(e)}",
        )


# ================================
# DYNAMIC ROUTES (NAMESPACED)
# ================================

@router.get("/agent/{agent_id}", response_model=PerformanceResponse)
async def get_agent_performance(
    agent_id: str,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back for performance data"),
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """Get detailed performance metrics for a specific agent.
    
    Args:
        agent_id: Unique identifier for the agent
        days: Number of days to look back for performance data (1-365)
        current_user: Authenticated user with admin or teacher role
        
    Returns:
        Detailed performance metrics for the specified agent
        
    Raises:
        HTTPException: If agent not found, authentication fails, or data retrieval fails
    """
    try:
        # Validate agent_id
        if not agent_id or agent_id.strip() == '':
            raise ValueError("Agent ID cannot be empty")
        
        agent_id = agent_id.strip()
        logger.info(f"User {current_user.get('user_id')} requesting performance for agent {agent_id}")
        
        monitor = AgentPerformanceMonitor()
        performance_data = monitor.get_agent_performance_metrics(agent_id, days)
        
        if not performance_data:
            logger.warning(f"No performance data found for agent {agent_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No performance data found for agent {agent_id}"
            )
        
        logger.info(f"Retrieved performance data for agent {agent_id}")
        return PerformanceResponse(**performance_data)
        
    except ValueError as e:
        logger.error(f"Validation error in get_agent_performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request parameters: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_agent_performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve agent performance data"
        )


@router.get("/agent/{agent_id}/trends")
async def get_agent_trends(
    agent_id: str,
    days: int = Query(default=30, ge=7, le=365),
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    try:
        monitor = AgentPerformanceMonitor()
        performance_data = monitor.get_agent_performance_metrics(agent_id, days)

        return {
            "agent_id": agent_id,
            "trend_analysis": performance_data["trend_analysis"],
            "performance_history": performance_data["metrics"],
            "recommendations": performance_data["recommendations"],
            "analysis_period": f"Last {days} days"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))