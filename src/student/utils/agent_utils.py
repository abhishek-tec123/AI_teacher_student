from config.settings import settings
import logging
logger = logging.getLogger(__name__)
"""
Agent ID Utility Functions

Dynamic agent ID resolution from database and student data.
"""

# Simple cache for agent ID lookups to avoid repeated searches
_agent_id_cache = {}

def get_dynamic_agent_id_for_subject(student_manager, student_id: str, subject: str) -> str:
    """Get agent_id dynamically from student data or database with optimized search."""
    try:
        # Create cache key
        cache_key = f"{student_id}_{subject}"
        
        # Check cache first
        if cache_key in _agent_id_cache:
            cached_agent_id = _agent_id_cache[cache_key]
            logger.info(f"✅ Found agent ID in cache: {cached_agent_id}")
            return cached_agent_id
        
        # Try different subject name variations
        subject_variations = [
            subject,
            subject.replace(" ", ""),
            subject.replace(" Science", "").strip(),
            subject.replace("Computer", "CS"),
            "CS" if "Computer" in subject else subject
        ]
        
        # First try to get from student's subject_agent array (fastest)
        student = student_manager.get_student(student_id)
        if student:
            subject_agents = student.get("student_details", {}).get("subject_agent", [])
            if isinstance(subject_agents, list):
                for item in subject_agents:
                    if isinstance(item, dict):
                        item_subject = item.get("subject", "")
                        for variation in subject_variations:
                            if item_subject == variation:
                                agent_id = item.get("subject_agent_id")
                                if agent_id:
                                    logger.info(f"✅ Found agent ID in student data: {agent_id} (matched: {variation})")
                                    _agent_id_cache[cache_key] = agent_id  # Cache the result
                                    return agent_id
                    elif isinstance(item, str):
                        for variation in subject_variations:
                            if item == variation:
                                logger.info(f"✅ Found subject string in student data: {item} (matched: {variation})")
                                break
        
        # Get student's class to prioritize their database
        student_class = student.get("student_details", {}).get("class", "12") if student else "12"
        
        # Search in student's class database first (highest priority)
        logger.info(f"🔍 Searching for agent ID in student's class database ({student_class}) for subject: {subject}")
        try:
            from teacher.repositories.collections import get_all_agents_of_class
            agents = get_all_agents_of_class(student_class)
            if isinstance(agents, list):
                for agent in agents:
                    if isinstance(agent, dict):
                        agent_subject = agent.get("subject", "")
                        for variation in subject_variations:
                            if agent_subject == variation:
                                agent_id = agent.get("subject_agent_id")
                                if agent_id:
                                    logger.info(f"✅ Found agent ID in student's class database: {agent_id} (matched: {variation})")
                                    _agent_id_cache[cache_key] = agent_id  # Cache the result
                                    return agent_id
        except Exception as e:
            logger.info(f"⚠️ Error searching student's class database: {e}")
        
        # Search in vector collections with optimized logic
        logger.info(f"🔍 Searching in vector collections for subject: {subject}")
        try:
            from student.agents.vector_performance_updater import VectorPerformanceUpdater
            updater = VectorPerformanceUpdater()
            
            # First prioritize student's class database
            class_databases = [student_class] + [db for db in updater.client.list_database_names() 
                                             if db not in ["admin", "local", "config", settings.db_name, student_class]]
            
            for db_name in class_databases:
                db = updater.client[db_name]
                logger.info(f"   - Checking database: {db_name}")
                
                for collection_name in db.list_collection_names():
                    collection = db[collection_name]
                    
                    # First try exact subject match in collection name
                    if subject.lower() == collection_name.lower():
                        sample_doc = collection.find_one()
                        if sample_doc:
                            agent_id = sample_doc.get("subject_agent_id")
                            if agent_id:
                                logger.info(f"✅ Found agent ID in vectors by exact collection match: {agent_id} (collection: {collection_name})")
                                _agent_id_cache[cache_key] = agent_id  # Cache the result
                                return agent_id
                    
                    # Then try variations with more precise matching
                    for i, variation in enumerate(subject_variations):
                        if i == 0:  # Skip first variation (original subject) as we already tried exact match
                            continue
                            
                        # Only match if variation is a significant part of collection name
                        if (variation.lower() in collection_name.lower() and 
                            len(variation) >= 3 and  # Only match if variation is at least 3 chars
                            collection_name.lower().replace(" ", "").startswith(variation.lower().replace(" ", "")[:6])):  # And collection starts with variation
                            
                            sample_doc = collection.find_one()
                            if sample_doc:
                                agent_id = sample_doc.get("subject_agent_id")
                                if agent_id:
                                    logger.info(f"✅ Found agent ID in vectors by precise collection match: {agent_id} (collection: {collection_name}, variation: {variation})")
                                    _agent_id_cache[cache_key] = agent_id  # Cache the result
                                    return agent_id
        except Exception as e:
            logger.info(f"⚠️ Error searching vectors: {e}")
        
        # If no agent found, return None instead of fallback
        logger.info(f"❌ Agent not found for subject: {subject} (tried variations: {subject_variations})")
        return None
        
    except Exception as e:
        logger.info(f"❌ Error getting dynamic agent ID: {e}")
        return None
