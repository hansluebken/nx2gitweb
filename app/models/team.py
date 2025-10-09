"""
Team model for Ninox teams
"""
from datetime import datetime
from typing import List
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class Team(Base, TimestampMixin):
    """Ninox Team model"""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"), nullable=False, index=True)

    # Team details
    team_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Ninox team ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    server: Mapped["Server"] = relationship("Server", back_populates="teams")
    databases: Mapped[List["Database"]] = relationship(
        "Database",
        back_populates="team",
        cascade="all, delete-orphan"
    )
    cronjobs: Mapped[List["Cronjob"]] = relationship(
        "Cronjob",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Team(name='{self.name}', team_id='{self.team_id}', server_id={self.server_id})>"
