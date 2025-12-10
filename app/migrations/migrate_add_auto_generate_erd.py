#!/usr/bin/env python3
"""
Migration script to add auto_generate_erd column to databases table

This migration adds the 'auto_generate_erd' column to databases table
to allow per-database control of ERD generation.

Run this script to add the new column.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import inspect, text
from app.database import engine


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_auto_generate_erd_column():
    """Add auto_generate_erd column to databases table"""
    if column_exists('databases', 'auto_generate_erd'):
        print("  Column 'auto_generate_erd' already exists, skipping")
        return False

    with engine.connect() as conn:
        # Add the column with default value TRUE (enabled by default)
        conn.execute(text("""
            ALTER TABLE databases
            ADD COLUMN auto_generate_erd BOOLEAN NOT NULL DEFAULT TRUE
        """))

        conn.commit()
        print("  Added column: auto_generate_erd (default: TRUE)")
        return True


def run_migration():
    """Run the complete migration"""
    print("\n" + "=" * 60)
    print("Auto-Generate ERD Column Migration")
    print("=" * 60)

    print("\nAdding auto_generate_erd column to databases table...")
    added = add_auto_generate_erd_column()

    print("\n" + "=" * 60)
    if added:
        print("Migration completed! Column 'auto_generate_erd' added.")
        print("\nAll existing databases now have auto_generate_erd=TRUE")
        print("You can configure this per-database in the UI.")
    else:
        print("Migration completed! No changes needed.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    run_migration()
