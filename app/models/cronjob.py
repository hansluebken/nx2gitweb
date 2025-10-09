"""
Cronjob model for scheduled database synchronization
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin
import enum


class CronjobType(enum.Enum):
    """Cronjob execution type"""
    INTERVAL = "interval"  # Run every X hours/days/weeks
    DAILY_TIME = "daily_time"  # Run daily at specific time


class IntervalUnit(enum.Enum):
    """Interval unit for interval-based cronjobs"""
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


class Cronjob(Base, TimestampMixin):
    """Cronjob model for scheduled synchronization"""
    __tablename__ = "cronjobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Reference to team
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    # Cronjob configuration
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Type: interval or daily_time
    job_type: Mapped[CronjobType] = mapped_column(SQLEnum(CronjobType), nullable=False)

    # For interval jobs: run every X hours/days/weeks
    interval_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_unit: Mapped[IntervalUnit | None] = mapped_column(SQLEnum(IntervalUnit), nullable=True)

    # For daily_time jobs: run at specific time (HH:MM format)
    daily_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # e.g. "14:30"

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Execution tracking
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # success, error, running
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="cronjobs")

    def __repr__(self) -> str:
        try:
            return f"<Cronjob(name='{self.name}', team='{self.team.name}', type={self.job_type.value}, active={self.is_active})>"
        except:
            return f"<Cronjob(id={getattr(self, 'id', 'unknown')})>"

    def get_schedule_description(self) -> str:
        """Get human-readable schedule description"""
        if self.job_type == CronjobType.INTERVAL:
            return f"Every {self.interval_value} {self.interval_unit.value}"
        elif self.job_type == CronjobType.DAILY_TIME:
            return f"Daily at {self.daily_time}"
        return "Unknown"
