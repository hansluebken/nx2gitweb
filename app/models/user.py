"""
User model for authentication and authorization
"""
from datetime import datetime
from typing import List
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User model"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # User details
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # GitHub configuration (encrypted)
    github_token_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_organization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    github_default_repo: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    servers: Mapped[List["Server"]] = relationship(
        "Server",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    password_resets: Mapped[List["PasswordReset"]] = relationship(
        "PasswordReset",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', email='{self.email}', is_admin={self.is_admin})>"
