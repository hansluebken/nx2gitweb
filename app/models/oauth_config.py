"""
OAuth Configuration model for storing OAuth provider settings
"""
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class OAuthConfig(Base, TimestampMixin):
    """OAuth provider configuration"""
    __tablename__ = "oauth_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Provider identification
    provider: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 'google'
    
    # OAuth credentials (encrypted)
    client_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_secret_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Allowed domains (comma-separated, e.g. "example.com,company.org")
    # Empty = all domains allowed
    allowed_domains: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Feature flags
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_create_users: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Optional: Redirect URI (usually auto-generated)
    redirect_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Google Drive integration
    drive_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drive_shared_folder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "ninox2git"

    def get_allowed_domains_list(self) -> list[str]:
        """Get allowed domains as a list"""
        if not self.allowed_domains:
            return []
        return [d.strip().lower() for d in self.allowed_domains.split(',') if d.strip()]
    
    def is_domain_allowed(self, email: str) -> bool:
        """Check if an email's domain is allowed"""
        allowed = self.get_allowed_domains_list()
        if not allowed:
            # No restriction - all domains allowed
            return True
        
        # Extract domain from email
        if '@' not in email:
            return False
        domain = email.split('@')[1].lower()
        return domain in allowed

    def __repr__(self) -> str:
        return f"<OAuthConfig(provider='{self.provider}', enabled={self.is_enabled})>"
