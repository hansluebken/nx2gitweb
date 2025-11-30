#!/usr/bin/env python3
"""
Migration script to add AI Configuration and ChangeLog tables

This migration adds:
1. ai_configs table - For storing AI provider settings (Claude, OpenAI, Gemini)
2. changelogs table - For storing change history with AI-generated descriptions

Run this script after updating the models to create the new tables.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import inspect, text
from app.database import engine, get_db
from app.models.base import Base
from app.models.ai_config import AIConfig, AIProvider, DEFAULT_MODELS
from app.models.changelog import ChangeLog


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_tables():
    """Create the new tables if they don't exist"""
    created = []
    
    # Check and create ai_configs table
    if not table_exists('ai_configs'):
        AIConfig.__table__.create(engine)
        created.append('ai_configs')
        print("  Created table: ai_configs")
    else:
        print("  Table ai_configs already exists, skipping")
    
    # Check and create changelogs table
    if not table_exists('changelogs'):
        ChangeLog.__table__.create(engine)
        created.append('changelogs')
        print("  Created table: changelogs")
    else:
        print("  Table changelogs already exists, skipping")
    
    return created


def initialize_default_ai_configs():
    """Initialize default AI provider configurations"""
    db = get_db()
    
    try:
        # Check if any AI configs exist
        existing = db.query(AIConfig).count()
        if existing > 0:
            print(f"  AI configurations already exist ({existing} entries), skipping initialization")
            return
        
        # Create default configurations for each provider
        providers = [
            (AIProvider.CLAUDE, True),   # Claude as default
            (AIProvider.OPENAI, False),
            (AIProvider.GEMINI, False),
        ]
        
        for provider, is_default in providers:
            config = AIConfig(
                provider=provider.value,
                model=DEFAULT_MODELS[provider],
                is_default=is_default,
                is_active=True,
                max_tokens=1000,
                temperature=0.3,
                api_key_encrypted=None,  # No API key yet
            )
            db.add(config)
            print(f"  Created AI config for {provider.value} (default: {is_default})")
        
        db.commit()
        print("  Initialized default AI provider configurations")
        
    except Exception as e:
        print(f"  Error initializing AI configs: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def run_migration():
    """Run the complete migration"""
    print("\n" + "=" * 60)
    print("AI Configuration and ChangeLog Migration")
    print("=" * 60)
    
    print("\nStep 1: Creating tables...")
    created = create_tables()
    
    if 'ai_configs' in created:
        print("\nStep 2: Initializing default AI configurations...")
        initialize_default_ai_configs()
    else:
        print("\nStep 2: Skipping AI config initialization (table already existed)")
    
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    
    print("\nNext steps:")
    print("1. Go to Admin Panel -> KI-Konfiguration")
    print("2. Configure API keys for your preferred AI provider(s)")
    print("3. Set your default provider")
    print()


if __name__ == "__main__":
    run_migration()
