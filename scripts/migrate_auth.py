#!/usr/bin/env python3
"""
Database migration script to add authentication fields to existing students.
This script should be run once to update the database schema for authentication.
"""

import sys
import os
from datetime import datetime
from pymongo import MongoClient
# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.auth.password_utils import get_password_hash, generate_default_password

MONGO_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("DB_NAME", "tutor_ai")
COLLECTION_NAME = "students"

def migrate_students_to_auth():
    """Add authentication fields to existing student documents."""
    
    print("Starting authentication migration for existing students...")
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    students = db[COLLECTION_NAME]
    
    # Find students without auth field
    students_without_auth = students.find({"auth": {"$exists": False}})
    
    migrated_count = 0
    failed_count = 0
# using bycrypt methods for one way password hashing------------------------------------------------------------
    # for student in students_without_auth:
    #     try:
    #         # Generate default password
    #         default_password = generate_default_password()
    #         password_hash = get_password_hash(default_password)
            
    #         # Update student document with auth fields
    #         result = students.update_one(
    #             {"_id": student["_id"]},
    #             {
    #                 "$set": {
    #                     "auth": {
    #                         "password_hash": password_hash,
    #                         "is_active": True,
    #                         "last_login": None,
    #                         "role": "student"
    #                     }
    #                 }
    #             }
    #         )
# using AES methods for encrypt password------------------------------------------------------------
    for student in students_without_auth:
        try:
            # Generate default password
            default_password = generate_default_password()
            password_hash = encrypt_password(default_password)  # <- updated

            # Update student document with auth fields
            result = students.update_one(
                {"_id": student["_id"]},
                {
                    "$set": {
                        "auth": {
                            "password_hash": password_hash,
                            "is_active": True,
                            "last_login": None,
                            "role": "student"
                        }
                    }
                }
            )
# using AES methods for encrypt password------------------------------------------------------------
            if result.modified_count > 0:
                migrated_count += 1
                print(f"✅ Migrated student: {student.get('student_details', {}).get('name', 'Unknown')} ({student.get('student_id', 'Unknown')})")
                print(f"   Temporary password: {default_password}")
                print("   Please save this password and provide it to the student.")
                print()
            else:
                failed_count += 1
                print(f"❌ Failed to migrate student: {student.get('student_id', 'Unknown')}")
                
        except Exception as e:
            failed_count += 1
            print(f"❌ Error migrating student {student.get('student_id', 'Unknown')}: {str(e)}")
    
    print(f"\nMigration completed:")
    print(f"✅ Successfully migrated: {migrated_count} students")
    print(f"❌ Failed to migrate: {failed_count} students")
    
    client.close()

def create_default_admin():
    """Create a default admin user if none exists."""
    
    print("\nCreating default admin user...")
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    admins = db["admins"]
    
    # Check if admin collection exists and has any users
    if admins.count_documents({}) > 0:
        print("ℹ️  Admin users already exist. Skipping default admin creation.")
        client.close()
        return
    
    from admin.repositories.admin_repository import AdminManager
    
    admin_manager = AdminManager()
    
    try:
        # Create default admin
        admin_email = "admin@teacherai.com"
        admin_password = "Admin123!"  # Shorter password to fit bcrypt limit
        
        admin_id, password = admin_manager.create_admin(
            name="Default Admin",
            email=admin_email,
            password=admin_password,
            permissions=["all"]
        )
        
        print(f"✅ Default admin created successfully:")
        print(f"   Email: {admin_email}")
        print(f"   Password: {admin_password}")
        print(f"   Admin ID: {admin_id}")
        print("⚠️  IMPORTANT: Change the default admin password immediately after first login!")
        
    except Exception as e:
        print(f"❌ Error creating default admin: {str(e)}")
    
    admin_manager.close()
    client.close()

def backup_database():
    """Create a backup of the database before migration."""
    
    print("Creating database backup...")
    
    # This is a simple backup - in production, use mongodump or similar
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    backup_collection_name = f"students_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Copy students collection to backup
    students = db[COLLECTION_NAME]
    backup_students = db[backup_collection_name]
    
    # Insert all documents into backup collection
    all_students = list(students.find({}))
    if all_students:
        backup_students.insert_many(all_students)
        print(f"✅ Backup created: {backup_collection_name} ({len(all_students)} documents)")
    else:
        print("ℹ️  No students found to backup")
    
    client.close()

def main():
    """Main migration function."""
    
    print("=" * 60)
    print("STUDENT LEARNING SYSTEM - AUTHENTICATION MIGRATION")
    print("=" * 60)
    print()
    
    # Check MongoDB connection
    try:
        client = MongoClient(MONGO_URI)
        client.server_info()
        print("✅ MongoDB connection successful")
        client.close()
    except Exception as e:
        print(f"❌ MongoDB connection failed: {str(e)}")
        return
    
    # Ask for confirmation
    print("This script will:")
    print("1. Create a backup of existing student data")
    print("2. Add authentication fields to existing students")
    print("3. Generate temporary passwords for existing students")
    print("4. Create a default admin user")
    print()
    
    confirm = input("Do you want to proceed? (y/N): ").lower().strip()
    if confirm != 'y':
        print("Migration cancelled.")
        return
    
    try:
        # Step 1: Backup
        backup_database()
        
        # Step 2: Migrate students
        migrate_students_to_auth()
        
        # Step 3: Create default admin
        create_default_admin()
        
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Save the temporary passwords shown above")
        print("2. Distribute passwords to respective students")
        print("3. Login as admin and change the default password")
        print("4. Test the authentication system")
        print()
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        print("Please check the error above and try again.")

if __name__ == "__main__":
    main()
