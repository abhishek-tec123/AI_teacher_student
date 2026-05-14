from typing import List, Optional

from teacher.services.vector_store_atlas import get_mongo_collection
import logging
logger = logging.getLogger(__name__)

def get_student_agent_ids(student_id: str) -> List[str]:
    """
    Get list of agent IDs that a student has access to
    This would typically come from student profile or enrollment data
    """
    try:
        # For now, we'll implement a simple check
        # In a real implementation, this would check student enrollments
        from student.repositories.student_repository import StudentManager
        from teacher.repositories.collections import get_all_agents_of_class

        student_manager = StudentManager()
        student_data = student_manager.get_student(student_id)

        if not student_data:
            return []

        accessible_agents: List[str] = []

        # Get basic student details
        student_details = student_data.get("student_details", {}) or {}
        student_class = student_details.get("class", "")

        # Get subject_agent from root level first (current schema), fallback to student_details for legacy
        subject_agent = student_data.get("subject_agent", "")
        if not subject_agent:
            subject_agent = student_details.get("subject_agent", "")

        # Helper to extract an agent ID from a dict entry
        def _extract_agent_id(agent_dict: dict) -> Optional[str]:
            # 1) Direct ID fields (preferred)
            agent_id = (
                agent_dict.get("subject_agent_id")
                or agent_dict.get("agent_id")
                or agent_dict.get("id")
            )
            if agent_id:
                return agent_id

            # 2) Fallback: resolve by subject name using class agents
            subject_name = agent_dict.get("subject") or agent_dict.get("name")
            if subject_name and student_class:
                try:
                    agents_response = get_all_agents_of_class(student_class)
                    # agents_response may be a dict or direct list depending on implementation
                    agents = agents_response.get("agents") if isinstance(agents_response, dict) else agents_response
                    if isinstance(agents, list):
                        for agent in agents:
                            if isinstance(agent, dict) and (agent.get("subject") == subject_name or agent.get("name") == subject_name):
                                resolved_id = agent.get("subject_agent_id")
                                if resolved_id:
                                    print(
                                        f"Resolved agent ID '{resolved_id}' for student {student_id} "
                                        f"from subject '{subject_name}' and class '{student_class}'"
                                    )
                                    return resolved_id
                except Exception as e:
                    logger.info(f"Error resolving agent_id by subject for student {student_id}: {e}")

            # 3) No ID could be resolved
            if subject_name:
                print(
                    f"Warning: subject_agent entry for student {student_id} "
                    f"has subject '{subject_name}' but no agent ID field and could not be resolved"
                )
            return None

        # Handle different data structures from student_details.subject_agent
        if subject_agent:
            if isinstance(subject_agent, str):
                # Treat plain strings as direct agent IDs
                accessible_agents.append(subject_agent)
            elif isinstance(subject_agent, dict):
                agent_id = _extract_agent_id(subject_agent)
                if agent_id:
                    accessible_agents.append(agent_id)
            elif isinstance(subject_agent, list):
                for agent in subject_agent:
                    if isinstance(agent, str):
                        # Treat plain strings as direct agent IDs
                        accessible_agents.append(agent)
                    elif isinstance(agent, dict):
                        agent_id = _extract_agent_id(agent)
                        if agent_id:
                            accessible_agents.append(agent_id)

        # Also derive accessible agents from conversation history (where subject_agent_id is stored)
        conversation_history = student_data.get("conversation_history", {})
        if isinstance(conversation_history, dict):
            for subject_conversations in conversation_history.values():
                if isinstance(subject_conversations, list):
                    for conv in subject_conversations:
                        if isinstance(conv, dict):
                            additional_data = conv.get("additional_data", {}) or {}
                            conv_agent_id = (
                                additional_data.get("subject_agent_id")
                                or additional_data.get("agent_id")
                                or additional_data.get("id")
                            )
                            if conv_agent_id and conv_agent_id not in accessible_agents:
                                accessible_agents.append(conv_agent_id)

        # Optional debug log to see what we resolved
        logger.info(f"Resolved accessible agents for student {student_id}: {accessible_agents}")

        return accessible_agents

    except Exception as e:
        logger.info(f"Error getting student agents: {e}")
        return []

def validate_student_agent_access(student_id: str, agent_id: str) -> bool:
    """
    Validate that a student has access to a specific agent
    """
    student_agents = get_student_agent_ids(student_id)
    return agent_id in student_agents

def get_agent_documents_from_db(agent_id: str) -> List[dict]:
    """
    Get unique documents for an agent from the database
    """
    try:
        # We need to find which database/collection contains this agent
        # Use central collections utilities to resolve the correct location
        from teacher.repositories.collections import list_all_collections

        agent_location = None
        try:
            all_agents = list_all_collections()
            if isinstance(all_agents, dict):
                for agent in all_agents.get("agents", []):
                    if (
                        isinstance(agent, dict)
                        and agent.get("subject_agent_id") == agent_id
                    ):
                        agent_location = {
                            "class": agent.get("class"),
                            "subject": agent.get("subject"),
                        }
                        break
        except Exception as e:
            logger.info(f"Error resolving agent location for {agent_id}: {e}")

        if not agent_location:
            # Fallback: try generic 'general' database as before
            possible_locations = [("general", "general")]
        else:
            possible_locations = [
                (agent_location["class"], agent_location["subject"])
            ]

        for db_name, collection_name in possible_locations:
            try:
                collection, used_collection_name = get_mongo_collection(
                    db_name, collection_name
                )

                # Find all unique documents for this agent
                pipeline = [
                    {"$match": {"subject_agent_id": agent_id}},
                    {
                        "$group": {
                            "_id": "$document.doc_unique_id",
                            "file_name": {"$first": "$document.file_name"},
                            "file_type": {"$first": "$document.file_type"},
                            "storage_path": {"$first": "$document.storage_path"},
                            "preview_available": {
                                "$first": "$document.preview_available"
                            },
                            "file_size": {"$first": "$document.file_size"},
                            "upload_date": {"$first": "$document.upload_date"},
                            "chunk_count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"upload_date": -1}},
                ]

                documents = list(collection.aggregate(pipeline))

                if documents:
                    # Convert _id to document_id
                    for doc in documents:
                        doc["document_id"] = doc.pop("_id")

                    return documents

            except Exception as e:
                logger.info(f"Error checking collection {db_name}.{collection_name}: {e}")
                continue

        return []
        
    except Exception as e:
        logger.info(f"Error getting agent documents: {e}")
        return []
