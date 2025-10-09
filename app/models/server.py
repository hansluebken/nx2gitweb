"""
Server model for Ninox servers
"""
from typing import List
from sqlalchemy import String, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class Server(Base, TimestampMixin):
    """Ninox Server model"""
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Server details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted API key
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # GitHub Configuration (encrypted)
    github_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="servers")
    teams: Mapped[List["Team"]] = relationship(
        "Team",
        back_populates="server",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Server(name='{self.name}', url='{self.url}', user_id={self.user_id})>"
