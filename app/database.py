"""
Database configuration and session management
"""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import Pool
from .models.base import Base


# Database URL from environment - MUST be set in environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
    echo=os.getenv('SQL_ECHO', 'false').lower() == 'true'
)

# Session factory
# expire_on_commit=False prevents "Instance not bound to Session" errors
# when accessing attributes after commit
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


# Enable foreign key constraints for SQLite (if used for testing)
@event.listens_for(Pool, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign keys for SQLite"""
    if 'sqlite' in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db():
    """Initialize database - create all tables"""
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")
    
    # Run migrations for new columns
    run_migrations()


def run_migrations():
    """Run manual migrations for new columns in existing tables"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Migration: Add sync_status, sync_started_at, sync_error to databases table
    if 'databases' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('databases')]
        
        with engine.connect() as conn:
            # Add sync_status column
            if 'sync_status' not in columns:
                print("  → Adding 'sync_status' column to databases table...")
                conn.execute(text(
                    "ALTER TABLE databases ADD COLUMN sync_status VARCHAR(20) DEFAULT 'idle' NOT NULL"
                ))
                conn.commit()
                print("    ✓ Added sync_status column")
            
            # Add sync_started_at column
            if 'sync_started_at' not in columns:
                print("  → Adding 'sync_started_at' column to databases table...")
                conn.execute(text(
                    "ALTER TABLE databases ADD COLUMN sync_started_at TIMESTAMP NULL"
                ))
                conn.commit()
                print("    ✓ Added sync_started_at column")
            
            # Add sync_error column
            if 'sync_error' not in columns:
                print("  → Adding 'sync_error' column to databases table...")
                conn.execute(text(
                    "ALTER TABLE databases ADD COLUMN sync_error TEXT NULL"
                ))
                conn.commit()
                print("    ✓ Added sync_error column")


def get_db() -> Session:
    """
    Get database session

    Usage:
        db = get_db()
        try:
            # ... use db
        finally:
            db.close()
    """
    return SessionLocal()


@contextmanager
def get_db_context():
    """
    Get database session as context manager

    Usage:
        with get_db_context() as db:
            # ... use db
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
