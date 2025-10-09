"""
Password reset token model
"""
from datetime import datetime, timedelta
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class PasswordReset(Base):
    """Password Reset Token model"""
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Token details
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=24),
        nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_resets")

    def is_valid(self) -> bool:
        """Check if token is still valid"""
        return not self.is_used and datetime.utcnow() < self.expires_at

    def __repr__(self) -> str:
        return f"<PasswordReset(user_id={self.user_id}, is_used={self.is_used}, expires_at='{self.expires_at}')>"
