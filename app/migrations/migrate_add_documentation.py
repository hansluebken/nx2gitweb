#!/usr/bin/env python3
"""
Migration script to add documentation table for AI-generated application documentation

This migration adds the 'documentations' table to store generated documentation.

Run this script to add the new table.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import inspect, text
from app.database import engine


def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_documentations_table():
    """Create the documentations table"""
    if table_exists('documentations'):
        print("  Table 'documentations' already exists, skipping")
        return False
    
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE documentations (
                id SERIAL PRIMARY KEY,
                database_id INTEGER NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                model VARCHAR(100) NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                github_synced BOOLEAN NOT NULL DEFAULT FALSE,
                github_synced_at TIMESTAMP,
                github_commit_sha VARCHAR(40),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create index on database_id for faster lookups
        conn.execute(text("""
            CREATE INDEX idx_documentations_database_id ON documentations(database_id)
        """))
        
        # Create index on generated_at for ordering
        conn.execute(text("""
            CREATE INDEX idx_documentations_generated_at ON documentations(generated_at DESC)
        """))
        
        conn.commit()
        print("  Created table: documentations")
        return True


def run_migration():
    """Run the complete migration"""
    print("\n" + "=" * 60)
    print("Documentation Table Migration")
    print("=" * 60)
    
    print("\nCreating documentations table...")
    created = create_documentations_table()
    
    print("\n" + "=" * 60)
    if created:
        print("Migration completed! Table 'documentations' created.")
    else:
        print("Migration completed! No changes needed.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    run_migration()
