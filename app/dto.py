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
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info("UserDTO.from_model: Starting...")
            # IMPORTANT: Access ALL attributes while the session is still active!
            # This triggers SQLAlchemy to load them from the database

            # Force load all attributes - even if None
            logger.info("UserDTO.from_model: Loading id...")
            user_id = user.id
            logger.info(f"UserDTO.from_model: id={user_id}")

            logger.info("UserDTO.from_model: Loading username...")
            username = user.username
            logger.info(f"UserDTO.from_model: username={username}")

            logger.info("UserDTO.from_model: Loading email...")
            email = user.email

            logger.info("UserDTO.from_model: Loading full_name...")
            full_name = user.full_name

            logger.info("UserDTO.from_model: Loading is_admin...")
            is_admin = user.is_admin

            logger.info("UserDTO.from_model: Loading is_active...")
            is_active = user.is_active

            logger.info("UserDTO.from_model: Loading last_login...")
            last_login = user.last_login

            logger.info("UserDTO.from_model: Loading github_token_encrypted...")
            github_token_encrypted = user.github_token_encrypted

            logger.info("UserDTO.from_model: Loading github_organization...")
            github_organization = user.github_organization

            logger.info("UserDTO.from_model: Loading github_default_repo...")
            github_default_repo = user.github_default_repo

            logger.info("UserDTO.from_model: Creating DTO object...")
            # Now safely copy the values
            return cls(
                id=user_id,
                username=username,
                email=email,
                full_name=full_name,
                is_admin=is_admin,
                is_active=is_active,
                last_login=last_login,
                github_token_encrypted=github_token_encrypted,
                github_organization=github_organization,
                github_default_repo=github_default_repo
            )
        except Exception as e:
            logger.error(f"UserDTO.from_model ERROR: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise