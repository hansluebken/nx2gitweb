"""
AI Configuration model for KI-Provider settings
Supports: Claude (Anthropic), OpenAI, Google Gemini
"""
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .prompt_template import PromptTemplate


class AIProvider(str, Enum):
    """Supported AI providers"""
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


# Default models for each provider (cost-effective defaults)
DEFAULT_MODELS = {
    AIProvider.CLAUDE: "claude-haiku-4-5",
    AIProvider.OPENAI: "gpt-4.1-mini",
    AIProvider.GEMINI: "gemini-2.5-flash",
}

# Available models per provider (sorted by capability: newest/best first)
AVAILABLE_MODELS = {
    AIProvider.CLAUDE: [
        # Claude 4.5 Familie (aktuell)
        "claude-opus-4-5",              # Höchste Qualität
        "claude-sonnet-4-5",            # Bestes Preis-Leistungs-Verhältnis
        "claude-haiku-4-5",             # Schnell & günstig
        # Claude 4.1 Familie
        "claude-opus-4-1",              # Opus 4.1
        # Claude 4 Familie
        "claude-opus-4-0",              # Opus 4
        "claude-sonnet-4-0",            # Sonnet 4
        # Claude 3.7 Familie
        "claude-3-7-sonnet-latest",     # Sonnet 3.7
        # Claude 3.5 Familie (legacy)
        "claude-3-5-haiku-latest",      # Haiku 3.5
    ],
    AIProvider.OPENAI: [
        # GPT-5 Familie (aktuell)
        "gpt-5",                        # Flagship
        "gpt-5-mini",                   # Schneller
        "gpt-5-nano",                   # Am schnellsten
        "gpt-5-chat-latest",            # Chat-optimiert
        # GPT-5.1 Familie
        "gpt-5.1",                      # Neueste Version
        "gpt-5.1-codex",                # Codex-Max für Code
        # GPT-4.1 Familie
        "gpt-4.1",                      # GPT-4.1
        "gpt-4.1-mini",                 # Schnell & günstig
        "gpt-4.1-nano",                 # Am schnellsten
        # GPT-4o Familie
        "gpt-4o",                       # Multimodal
        # O-Serie (Reasoning)
        "o4-mini",                      # Reasoning mini
        "o3",                           # Reasoning
        "o3-mini",                      # Reasoning mini
    ],
    AIProvider.GEMINI: [
        # Gemini 3 Familie (Preview)
        "gemini-3-pro-preview",         # Gemini 3 Pro (Preview)
        # Gemini 2.5 Familie (aktuell)
        "gemini-2.5-pro",               # Höchste Qualität
        "gemini-2.5-flash",             # Schnell & günstig
        "gemini-2.5-flash-lite",        # Noch schneller
        "gemini-2.5-flash-image",       # Bildgenerierung
        # Gemini 2.0 Familie
        "gemini-2.0-flash",             # Flash 2.0
        "gemini-2.0-flash-lite",        # Flash 2.0 Lite
    ],
}


class AIConfig(Base, TimestampMixin):
    """
    AI Provider Configuration
    
    Stores API keys and settings for each AI provider.
    Only one provider can be set as default at a time.
    """
    __tablename__ = "ai_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Provider identification (unique per provider)
    provider: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # API Key (encrypted)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Model selection
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Status flags
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Model parameters
    max_tokens: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)

    # Prompt template for documentation generation
    doc_prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True
    )

    # Connection test status
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    doc_prompt_template: Mapped["PromptTemplate | None"] = relationship(
        "PromptTemplate",
        foreign_keys=[doc_prompt_template_id]
    )

    def __repr__(self) -> str:
        default_str = " [DEFAULT]" if self.is_default else ""
        active_str = "" if self.is_active else " (inactive)"
        return f"<AIConfig(provider='{self.provider}', model='{self.model}'{default_str}{active_str})>"
    
    @property
    def is_configured(self) -> bool:
        """Check if the provider has an API key configured"""
        return self.api_key_encrypted is not None and len(self.api_key_encrypted) > 0
    
    @property
    def display_name(self) -> str:
        """Human-readable provider name"""
        names = {
            AIProvider.CLAUDE.value: "Claude (Anthropic)",
            AIProvider.OPENAI.value: "OpenAI",
            AIProvider.GEMINI.value: "Google Gemini",
        }
        return names.get(self.provider, self.provider)
    
    @classmethod
    def get_provider_choices(cls) -> list:
        """Get list of available providers for UI dropdowns"""
        return [
            {"value": AIProvider.CLAUDE.value, "label": "Claude (Anthropic)"},
            {"value": AIProvider.OPENAI.value, "label": "OpenAI"},
            {"value": AIProvider.GEMINI.value, "label": "Google Gemini"},
        ]
    
    @classmethod
    def get_model_choices(cls, provider: str) -> list:
        """Get list of available models for a provider"""
        try:
            provider_enum = AIProvider(provider)
            return AVAILABLE_MODELS.get(provider_enum, [])
        except ValueError:
            return []
    
    @classmethod
    def get_default_model(cls, provider: str) -> str:
        """Get the default model for a provider"""
        try:
            provider_enum = AIProvider(provider)
            model = DEFAULT_MODELS.get(provider_enum)
            return model if model else ""
        except ValueError:
            return ""
