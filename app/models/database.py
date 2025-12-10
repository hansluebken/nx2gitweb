"""
Database model for Ninox databases
"""
import enum
from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Enum as SQLEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class SyncStatus(enum.Enum):
    """Sync status for databases"""
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


if TYPE_CHECKING:
    from .changelog import ChangeLog
    from .documentation import Documentation
    from .database_dependency import DatabaseDependency


class Database(Base, TimestampMixin):
    """Ninox Database model"""
    __tablename__ = "databases"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)

    # Database details
    database_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Ninox database ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_generate_docs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Auto-generate AI documentation (default: OFF)
    auto_generate_erd: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # Auto-generate ERD diagrams
    last_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # BookStack integration
    bookstack_shelf_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # BookStack shelf ID
    bookstack_book_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # BookStack book ID
    auto_sync_to_bookstack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Auto-sync after doc generation
    last_bookstack_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # Last sync to BookStack
    
    # Sync status (for background sync tracking)
    sync_status: Mapped[str] = mapped_column(
        String(20), 
        default=SyncStatus.IDLE.value, 
        nullable=False
    )
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="databases")
    changelogs: Mapped[List["ChangeLog"]] = relationship(
        "ChangeLog",
        back_populates="database",
        cascade="all, delete-orphan",
        order_by="desc(ChangeLog.commit_date)"
    )
    documentations: Mapped[List["Documentation"]] = relationship(
        "Documentation",
        back_populates="database",
        cascade="all, delete-orphan",
        order_by="desc(Documentation.generated_at)"
    )
    dependencies_as_source: Mapped[List["DatabaseDependency"]] = relationship(
        "DatabaseDependency",
        foreign_keys="DatabaseDependency.source_database_id",
        back_populates="source_database",
        cascade="all, delete-orphan"
    )
    dependencies_as_target: Mapped[List["DatabaseDependency"]] = relationship(
        "DatabaseDependency",
        foreign_keys="DatabaseDependency.target_database_id",
        back_populates="target_database",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Database(name='{self.name}', database_id='{self.database_id}', team_id={self.team_id})>"
    
    @property
    def latest_documentation(self):
        """Get the most recent documentation"""
        if self.documentations:
            return self.documentations[0]
        return None
    
    @property
    def is_syncing(self) -> bool:
        """Check if database is currently syncing"""
        return self.sync_status == SyncStatus.SYNCING.value
