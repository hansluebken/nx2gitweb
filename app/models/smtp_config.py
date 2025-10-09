"""
SMTP Configuration Model
Stores SMTP server settings for email functionality
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from .base import Base


class SmtpConfig(Base):
    """Model for SMTP server configuration"""
    __tablename__ = 'smtp_configs'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=587)
    username = Column(String(255), nullable=False)
    password_encrypted = Column(String(500), nullable=False)  # Encrypted password
    from_email = Column(String(255), nullable=False)
    from_name = Column(String(100), default='Ninox2Git')
    use_tls = Column(Boolean, default=True)
    use_ssl = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)  # Only one can be active
    is_tested = Column(Boolean, default=False)  # Has been successfully tested
    last_test_date = Column(DateTime(timezone=True))
    last_test_result = Column(String(500))  # Success or error message
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<SmtpConfig(name='{self.name}', host='{self.host}:{self.port}', active={self.is_active})>"