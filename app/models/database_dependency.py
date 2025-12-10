"""
Database Dependency model for tracking dependencies between databases
"""
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class DatabaseDependency(Base, TimestampMixin):
    """
    Tracks dependencies between databases.

    If database A references database B, then:
    - source_database_id = A
    - target_database_id = B

    This means A depends on B, or A → B
    """
    __tablename__ = "database_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Source database (the one that has the reference)
    source_database_id: Mapped[int] = mapped_column(
        ForeignKey("databases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Target database (the one being referenced)
    target_database_id: Mapped[int] = mapped_column(
        ForeignKey("databases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Ninox database IDs (for easier querying)
    source_ninox_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_ninox_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Relationships
    source_database: Mapped["Database"] = relationship(
        "Database",
        foreign_keys=[source_database_id],
        back_populates="dependencies_as_source"
    )

    target_database: Mapped["Database"] = relationship(
        "Database",
        foreign_keys=[target_database_id],
        back_populates="dependencies_as_target"
    )

    # Ensure no duplicate dependencies
    __table_args__ = (
        UniqueConstraint('source_database_id', 'target_database_id', name='uq_db_dependency'),
    )

    def __repr__(self) -> str:
        return f"<DatabaseDependency(source={self.source_ninox_id}, target={self.target_ninox_id})>"
