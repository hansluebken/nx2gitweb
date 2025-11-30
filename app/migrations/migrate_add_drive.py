"""
Migration: Add Google Drive integration fields
- Add drive fields to oauth_configs table
- Add drive fields to databases table  
- Add refresh token to users table
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://nx2git:nx2git@localhost:5432/nx2git')


def run_migration():
    """Run the Google Drive migration"""
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    
    with engine.connect() as conn:
        # oauth_configs table - add drive fields
        oauth_columns = [col['name'] for col in inspector.get_columns('oauth_configs')]
        
        if 'drive_enabled' not in oauth_columns:
            print("Adding drive_enabled column to oauth_configs...")
            conn.execute(text("""
                ALTER TABLE oauth_configs 
                ADD COLUMN drive_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """))
            print("  -> drive_enabled column added")
        else:
            print("drive_enabled column already exists")
        
        if 'drive_shared_folder_name' not in oauth_columns:
            print("Adding drive_shared_folder_name column to oauth_configs...")
            conn.execute(text("""
                ALTER TABLE oauth_configs 
                ADD COLUMN drive_shared_folder_name VARCHAR(255)
            """))
            print("  -> drive_shared_folder_name column added")
        else:
            print("drive_shared_folder_name column already exists")
        
        # databases table - add drive fields
        db_columns = [col['name'] for col in inspector.get_columns('databases')]
        
        if 'drive_document_id' not in db_columns:
            print("Adding drive_document_id column to databases...")
            conn.execute(text("""
                ALTER TABLE databases 
                ADD COLUMN drive_document_id VARCHAR(100)
            """))
            print("  -> drive_document_id column added")
        else:
            print("drive_document_id column already exists")
        
        if 'drive_last_upload' not in db_columns:
            print("Adding drive_last_upload column to databases...")
            conn.execute(text("""
                ALTER TABLE databases 
                ADD COLUMN drive_last_upload TIMESTAMP
            """))
            print("  -> drive_last_upload column added")
        else:
            print("drive_last_upload column already exists")
        
        # users table - add refresh token field
        user_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'google_refresh_token_encrypted' not in user_columns:
            print("Adding google_refresh_token_encrypted column to users...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_refresh_token_encrypted VARCHAR(1000)
            """))
            print("  -> google_refresh_token_encrypted column added")
        else:
            print("google_refresh_token_encrypted column already exists")
        
        conn.commit()
        print("\nMigration completed successfully!")


if __name__ == '__main__':
    run_migration()
