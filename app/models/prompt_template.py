"""
Prompt Template model for managing AI prompts
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class PromptType(enum.Enum):
    """Types of prompts"""
    DOCUMENTATION = "documentation"
    CHANGELOG = "changelog"
    CODE_REVIEW = "code_review"
    CUSTOM = "custom"


class PromptTemplate(Base, TimestampMixin):
    """AI Prompt Template model"""
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Prompt details
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # z.B. "Standard Dokumentation"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # Beschreibung des Prompts
    prompt_type: Mapped[str] = mapped_column(String(50), nullable=False, default='custom')  # Type as string
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)  # Der eigentliche Prompt

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Default für diesen Typ
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Für Versionierung

    # Author/Creator info
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Username
    last_modified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<PromptTemplate(name='{self.name}', type='{self.prompt_type}')>"

    @property
    def type_label(self) -> str:
        """Get human-readable type label"""
        labels = {
            PromptType.DOCUMENTATION.value: "Dokumentation",
            PromptType.CHANGELOG.value: "Changelog",
            PromptType.CODE_REVIEW.value: "Code Review",
            PromptType.CUSTOM.value: "Benutzerdefiniert"
        }
        return labels.get(self.prompt_type, self.prompt_type)
