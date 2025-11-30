"""
Database model for Ninox databases
"""
from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .changelog import ChangeLog
    from .documentation import Documentation


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
    last_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Google Drive integration
    drive_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Google Docs document ID
    drive_last_upload: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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

    def __repr__(self) -> str:
        return f"<Database(name='{self.name}', database_id='{self.database_id}', team_id={self.team_id})>"
    
    @property
    def latest_documentation(self):
        """Get the most recent documentation"""
        if self.documentations:
            return self.documentations[0]
        return None
