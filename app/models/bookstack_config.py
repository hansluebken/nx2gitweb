"""
BookStack Configuration model for documentation export
"""
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .server import Server


class BookstackConfig(Base, TimestampMixin):
    """BookStack instance configuration per server"""
    __tablename__ = "bookstack_configs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Link to server
    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True  # One BookStack config per server
    )

    # BookStack instance details
    url: Mapped[str] = mapped_column(String(500), nullable=False)  # https://docs.company.com
    api_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted API token

    # Default shelf configuration
    default_shelf_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Ninox Datenbanken")
    default_shelf_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Stored after creation

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Connection test status
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    server: Mapped["Server"] = relationship("Server", back_populates="bookstack_config")

    def __repr__(self) -> str:
        return f"<BookstackConfig(server_id={self.server_id}, url='{self.url}')>"

    @property
    def is_configured(self) -> bool:
        """Check if BookStack is fully configured"""
        return bool(self.url and self.api_token_encrypted)
