#!/usr/bin/env python3
"""
Quick script to enable global RAG for agent_YXA00
"""

import os
import sys
from pymongo import MongoClient

def load_env():
    """Load environment variables from .env file"""
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    os.environ[key] = value
    except FileNotFoundError:
        print("⚠️ .env file not found")
    except Exception as e:
        print(f"⚠️ Error loading .env: {e}")

def enable_global_rag_for_agent():
    """Enable global_rag_enabled for agent_YXA00"""
    
    MONGODB_URI = os.environ.get("MONGODB_URI")
    if not MONGODB_URI:
        print("❌ MONGODB_URI environment variable not set")
        return False
    
    client = MongoClient(MONGODB_URI)
    agent_id = "agent_YXA00"
    
    # Search for the agent across all databases
    found_collection = None
    found_db_name = None
    found_collection_name = None
    
    for db_name in client.list_database_names():
        if db_name in ["admin", "local", "config"]:
            continue
        
        db = client[db_name]
        for collection_name in db.list_collection_names():
            collection = db[collection_name]
            existing = collection.find_one({"subject_agent_id": agent_id})
            if existing is not None:
                found_collection = collection
                found_db_name = db_name
                found_collection_name = collection_name
                print(f"✅ Found agent {agent_id} in {db_name}.{collection_name}")
                break
        
        if found_collection is not None:
            break
    
    if found_collection is None:
        print(f"❌ Agent {agent_id} not found")
        return False
    
    # Update the agent metadata to enable global RAG
    try:
        result = found_collection.update_many(
            {"subject_agent_id": agent_id},
            {"$set": {"agent_metadata.global_rag_enabled": True}}
        )
        
        print(f"✅ Updated {result.modified_count} documents for agent {agent_id}")
        print(f"✅ global_rag_enabled set to True")
        
        # Verify the update
        updated_doc = found_collection.find_one({"subject_agent_id": agent_id})
        if updated_doc:
            global_rag = updated_doc.get("agent_metadata", {}).get("global_rag_enabled")
            print(f"✅ Verification: global_rag_enabled = {global_rag}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to update agent: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Enabling global RAG for agent_YXA00...")
    load_env()  # Load environment variables from .env
    success = enable_global_rag_for_agent()
    if success:
        print("🎉 Global RAG enabled successfully!")
        print("📝 Now try your query again - shared documents should be searchable")
    else:
        print("❌ Failed to enable global RAG")
        sys.exit(1)
