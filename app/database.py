"""
Database configuration and session management
"""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import Pool
from .models.base import Base


# Database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://nx2git:changeme@postgres:5432/nx2git')

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
    echo=os.getenv('SQL_ECHO', 'false').lower() == 'true'
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
