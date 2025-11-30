"""
Migration: Add OAuth support
- Add oauth_configs table
- Add OAuth fields to users table (auth_provider, google_id, avatar_url)
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text, inspect

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://nx2git:nx2git@localhost:5432/nx2git')


def run_migration():
    """Run the OAuth migration"""
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    
    with engine.connect() as conn:
        # Check if oauth_configs table exists
        existing_tables = inspector.get_table_names()
        
        if 'oauth_configs' not in existing_tables:
            print("Creating oauth_configs table...")
            conn.execute(text("""
                CREATE TABLE oauth_configs (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(50) UNIQUE NOT NULL,
                    client_id VARCHAR(500),
                    client_secret_encrypted VARCHAR(500),
                    allowed_domains TEXT,
                    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    auto_create_users BOOLEAN NOT NULL DEFAULT TRUE,
                    redirect_uri VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("  -> oauth_configs table created")
        else:
            print("oauth_configs table already exists")
        
        # Check and add columns to users table
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'auth_provider' not in existing_columns:
            print("Adding auth_provider column to users...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN auth_provider VARCHAR(20) NOT NULL DEFAULT 'local'
            """))
            print("  -> auth_provider column added")
        else:
            print("auth_provider column already exists")
        
        if 'google_id' not in existing_columns:
            print("Adding google_id column to users...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_id VARCHAR(100) UNIQUE
            """))
            print("  -> google_id column added")
        else:
            print("google_id column already exists")
        
        if 'avatar_url' not in existing_columns:
            print("Adding avatar_url column to users...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN avatar_url VARCHAR(500)
            """))
            print("  -> avatar_url column added")
        else:
            print("avatar_url column already exists")
        
        conn.commit()
        print("\nMigration completed successfully!")


if __name__ == '__main__':
    run_migration()
