#!/usr/bin/env python3
"""
Add performance tracking to existing vector documents
"""

import os
import sys
from datetime import datetime
from pymongo import MongoClient
from typing import Dict, Any
# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def add_performance_to_existing_documents():
    """Add performance tracking to all existing vector documents."""
    print("🔧 Adding Performance Tracking to Existing Vector Documents")
    print("=" * 60)
    
    try:
        client = MongoClient(os.environ.get("MONGODB_URI"))
        
        # Performance data structure to add
        performance_data = {
            "performance_period": "Last 30 days",
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
                "quality_health": {
                    "status": "No Data",
                    "color": "gray"
                },
                "hallucination_health": {
                    "status": "No Data",
                    "color": "gray"
                },
                "satisfaction_health": {
                    "status": "No Data",
                    "color": "gray"
                }
            },
            "trend_analysis": {
                "trend": "No Data",
                "direction": "neutral"
            },
            "recommendations": [
                "Agent has no conversation data - needs testing and deployment"
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        total_updated = 0
        total_documents = 0
        
        # Scan all databases
        for db_name in client.list_database_names():
            if db_name in ["admin", "local", "config", os.environ.get("DB_NAME", "tutor_ai")]:
                continue
                
            print(f"\n🗄️ Scanning database: {db_name}")
            db = client[db_name]
            
            for collection_name in db.list_collection_names():
                collection = db[collection_name]
                
                # Find documents with subject_agent_id but no performance key
                query = {
                    "subject_agent_id": {"$exists": True},
                    "performance": {"$exists": False}
                }
                
                documents_to_update = list(collection.find(query))
                
                if documents_to_update:
                    print(f"   📝 Found {len(documents_to_update)} documents in collection '{collection_name}' to update")
                    
                    # Update each document
                    for doc in documents_to_update:
                        result = collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"performance": performance_data}}
                        )
                        
                        if result.modified_count > 0:
                            total_updated += 1
                            print(f"     ✅ Updated document: {doc['_id']}")
                
                total_documents += len(documents_to_update)
        
        print(f"\n📊 Summary:")
        print(f"   Total documents found without performance: {total_documents}")
        print(f"   Total documents updated: {total_updated}")
        print(f"   Documents failed: {total_documents - total_updated}")
        
        if total_updated > 0:
            print(f"\n✅ Performance tracking added to {total_updated} existing documents!")
            print(f"🎯 Now your existing agent_K3GVB will have performance tracking!")
        else:
            print(f"\nℹ️ No documents needed updating - all already have performance tracking")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def update_specific_agent(agent_id: str = "agent_K3GVB"):
    """Update performance tracking for a specific agent only."""
    print(f"🎯 Adding Performance Tracking to Agent: {agent_id}")
    print("=" * 50)
    
    try:
        client = MongoClient(os.environ.get("MONGODB_URI"))
        
        # Performance data structure
        performance_data = {
            "performance_period": "Last 30 days",
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
                "satisfaction_health": {"status": "No Data", "color": "gray"}
            },
            "trend_analysis": {"trend": "No Data", "direction": "neutral"},
            "recommendations": ["Agent has no conversation data - needs testing and deployment"],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        total_updated = 0
        
        # Scan all databases for this specific agent
        for db_name in client.list_database_names():
            if db_name in ["admin", "local", "config", os.environ.get("DB_NAME", "tutor_ai")]:
                continue
                
            print(f"\n🗄️ Scanning database: {db_name}")
            db = client[db_name]
            
            for collection_name in db.list_collection_names():
                collection = db[collection_name]
                
                # Find documents for this agent without performance key
                query = {
                    "subject_agent_id": agent_id,
                    "performance": {"$exists": False}
                }
                
                documents_to_update = list(collection.find(query))
                
                if documents_to_update:
                    print(f"   📝 Found {len(documents_to_update)} documents for {agent_id} in '{collection_name}'")
                    
                    # Update each document
                    for doc in documents_to_update:
                        result = collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"performance": performance_data}}
                        )
                        
                        if result.modified_count > 0:
                            total_updated += 1
                            print(f"     ✅ Updated document: {doc['_id']}")
        
        print(f"\n📊 Summary for {agent_id}:")
        print(f"   Documents updated: {total_updated}")
        
        if total_updated > 0:
            print(f"\n✅ Performance tracking added to {agent_id}!")
            print(f"🎯 Your agent now has the performance key!")
        else:
            print(f"\nℹ️ {agent_id} already has performance tracking or no documents found")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def check_agent_performance(agent_id: str = "agent_K3GVB"):
    """Check if agent has performance tracking."""
    print(f"🔍 Checking Performance Tracking for: {agent_id}")
    print("=" * 50)
    
    try:
        client = MongoClient(os.environ.get("MONGODB_URI"))
        
        found_documents = 0
        documents_with_performance = 0
        documents_without_performance = 0
        
        # Scan all databases
        for db_name in client.list_database_names():
            if db_name in ["admin", "local", "config", os.environ.get("DB_NAME", "tutor_ai")]:
                continue
                
            print(f"\n🗄️ Database: {db_name}")
            db = client[db_name]
            
            for collection_name in db.list_collection_names():
                collection = db[collection_name]
                
                # Find documents for this agent
                documents = list(collection.find({"subject_agent_id": agent_id}))
                
                if documents:
                    print(f"   📄 Collection '{collection_name}': {len(documents)} documents")
                    found_documents += len(documents)
                    
                    for doc in documents:
                        if doc.get("performance"):
                            documents_with_performance += 1
                        else:
                            documents_without_performance += 1
                            
                            # Show document structure
                            print(f"     ❌ Document {doc['_id']} missing performance key")
                            print(f"        Keys: {list(doc.keys())}")
        
        print(f"\n📊 Summary for {agent_id}:")
        print(f"   Total documents found: {found_documents}")
        print(f"   Documents with performance: {documents_with_performance}")
        print(f"   Documents without performance: {documents_without_performance}")
        
        if documents_without_performance > 0:
            print(f"\n⚠️ {documents_without_performance} documents need performance tracking added!")
            print(f"🔧 Run: python3 add_performance_to_existing.py --agent {agent_id}")
        else:
            print(f"\n✅ All documents have performance tracking!")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Add performance tracking to existing vector documents")
    parser.add_argument("--agent", type=str, help="Update specific agent only")
    parser.add_argument("--check", type=str, help="Check if agent has performance tracking")
    parser.add_argument("--all", action="store_true", help="Update all agents")
    
    args = parser.parse_args()
    
    if args.check:
        check_agent_performance(args.check)
    elif args.agent:
        update_specific_agent(args.agent)
    elif args.all:
        add_performance_to_existing_documents()
    else:
        print("🚀 Performance Tracking Migration Tool")
        print("=" * 40)
        print("\nOptions:")
        print("  --agent agent_K3GVB    Update specific agent")
        print("  --check agent_K3GVB    Check agent status")
        print("  --all                  Update all agents")
        print("\nExamples:")
        print("  python3 add_performance_to_existing.py --agent agent_K3GVB")
        print("  python3 add_performance_to_existing.py --check agent_K3GVB")
        print("  python3 add_performance_to_existing.py --all")

if __name__ == "__main__":
    main()
