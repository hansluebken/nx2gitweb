"""
Data Transfer Objects (DTOs) for passing data without SQLAlchemy session dependencies
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserDTO:
    """
    Plain data object for User information.
    Used to pass user data around without SQLAlchemy session dependencies.
    """
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_admin: bool
    is_active: bool
    last_login: Optional[datetime]
    github_token_encrypted: Optional[str] = None
    github_organization: Optional[str] = None
    github_default_repo: Optional[str] = None

    @classmethod
    def from_model(cls, user):
        """Create UserDTO from SQLAlchemy User model"""
        # IMPORTANT: Access ALL attributes while the session is still active!
        # This triggers SQLAlchemy to load them from the database

        # Force load all attributes - even if None
        _ = user.id
        _ = user.username
        _ = user.email
        _ = user.full_name
        _ = user.is_admin
        _ = user.is_active
        _ = user.last_login
        _ = user.github_token_encrypted
        _ = user.github_organization
        _ = user.github_default_repo

        # Now safely copy the values
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_admin=user.is_admin,
            is_active=user.is_active,
            last_login=user.last_login,
            github_token_encrypted=user.github_token_encrypted,
            github_organization=user.github_organization,
            github_default_repo=user.github_default_repo
        )