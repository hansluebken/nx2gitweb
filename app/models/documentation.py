"""
Documentation model for storing AI-generated application documentation
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin


class Documentation(Base, TimestampMixin):
    """
    Stores AI-generated documentation for databases
    
    Each database can have multiple documentation versions,
    with the latest being the current one.
    """
    __tablename__ = "documentations"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Link to database
    database_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("databases.id", ondelete="CASCADE"), 
        nullable=False
    )
    
    # Documentation content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    """The generated Markdown documentation"""
    
    # Generation metadata
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    """When the documentation was generated"""
    
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    """AI model used for generation (e.g., gemini-2.5-pro)"""
    
    # Token tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Number of input tokens used"""
    
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Number of output tokens generated"""
    
    # GitHub sync status
    github_synced: Mapped[bool] = mapped_column(default=False, nullable=False)
    """Whether the documentation was synced to GitHub"""
    
    github_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """When the documentation was synced to GitHub"""
    
    github_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    """GitHub commit SHA if synced"""
    
    # Relationship to database
    database = relationship("Database", back_populates="documentations")
    
    def __repr__(self) -> str:
        return f"<Documentation(database_id={self.database_id}, generated_at={self.generated_at}, model={self.model})>"
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)"""
        return (self.input_tokens or 0) + (self.output_tokens or 0)
    
    @property
    def content_preview(self) -> str:
        """First 200 characters of content for preview"""
        if not self.content:
            return ""
        return self.content[:200] + "..." if len(self.content) > 200 else self.content
