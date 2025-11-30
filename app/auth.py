"""
Authentication module with JWT token support

This module provides complete authentication functionality including:
- Password hashing with bcrypt
- JWT token generation and validation
- User login/logout
- User registration with email validation
- Password reset token generation
- Session management
- Audit logging for all authentication actions
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
import jwt
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .models.user import User
from .models.audit_log import AuditLog
from .models.password_reset import PasswordReset
from .utils.validators import validate_email, validate_password, validate_username
from .dto import UserDTO


# JWT Configuration from environment
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))


class AuthError(Exception):
    """Base exception for authentication errors"""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when login credentials are invalid"""
    pass


class UserNotFoundError(AuthError):
    """Raised when user is not found"""
    pass


class UserExistsError(AuthError):
    """Raised when attempting to create a user that already exists"""
    pass


class InvalidTokenError(AuthError):
    """Raised when JWT token is invalid or expired"""
    pass


class InactiveUserError(AuthError):
    """Raised when user account is inactive"""
    pass


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password as string
    """
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash

    Args:
        password: Plain text password
        password_hash: Hashed password

    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def generate_jwt_token(user) -> str:
    """
    Generate JWT token for user

    Args:
        user: User object or UserDTO

    Returns:
        JWT token string
    """
    # Token expiration time
    expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)

    # Token payload - works with both User model and UserDTO
    payload = {
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin,
        'exp': expiration,
        'iat': datetime.utcnow(),
        'type': 'access'
    }

    # Generate token
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def validate_jwt_token(token: str) -> Dict[str, Any]:
    """
    Validate and decode JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        InvalidTokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Verify token type
        if payload.get('type') != 'access':
            raise InvalidTokenError("Invalid token type")

        return payload
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Invalid token: {str(e)}")


def create_audit_log(
    db: Session,
    user_id: int,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    auto_commit: bool = False
) -> AuditLog:
    """
    Create audit log entry

    Args:
        db: Database session (can be None if auto_commit=True, will create own session)
        user_id: User ID
        action: Action performed (e.g., 'login', 'logout', 'password_reset_request')
        resource_type: Type of resource affected
        resource_id: ID of resource affected
        details: Additional details
        ip_address: Client IP address
        user_agent: Client user agent
        auto_commit: If True, creates own session and commits. If False (default),
                     uses provided session and caller must commit.

    Returns:
        Created AuditLog object
    """
    # If auto_commit, use a separate session to avoid conflicts
    if auto_commit:
        from .database import get_db
        own_db = get_db()
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
            own_db.add(audit_log)
            own_db.commit()
            own_db.close()
            return audit_log
        finally:
            own_db.close()
    else:
        # Use provided session
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(audit_log)
        return audit_log


def register_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    is_admin: bool = False,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> User:
    """
    Register a new user

    Args:
        db: Database session
        username: Username
        email: Email address
        password: Plain text password
        full_name: Full name (optional)
        is_admin: Whether user is admin
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        Created User object

    Raises:
        UserExistsError: If username or email already exists
        ValueError: If validation fails
    """
    # Validate username
    is_valid, error = validate_username(username)
    if not is_valid:
        raise ValueError(f"Invalid username: {error}")

    # Validate email
    is_valid, error = validate_email(email)
    if not is_valid:
        raise ValueError(f"Invalid email: {error}")

    # Validate password
    is_valid, error = validate_password(password)
    if not is_valid:
        raise ValueError(f"Invalid password: {error}")

    # Check if user already exists
    existing_user = db.query(User).filter(
        or_(User.username == username, User.email == email)
    ).first()

    if existing_user:
        if existing_user.username == username:
            raise UserExistsError("Username already exists")
        else:
            raise UserExistsError("Email already exists")

    # Create new user
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        is_admin=is_admin,
        is_active=True
    )

    db.add(user)
    db.commit()
    # Note: db.refresh() removed - user.id is already available after commit

    # Create audit log (with auto_commit since user already committed)
    create_audit_log(
        db=db,
        user_id=user.id,
        action='user_registered',
        resource_type='user',
        resource_id=user.id,
        details=f"User {username} registered",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user


def login_user(
    db: Session,
    username_or_email: str,
    password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> tuple[UserDTO, str]:
    """
    Login user and generate JWT token - SIMPLIFIED VERSION FOR DEBUGGING
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info("=== LOGIN START ===")

        # Find user by username or email
        user = db.query(User).filter(
            or_(User.username == username_or_email, User.email == username_or_email)
        ).first()
        logger.info(f"Step 1: Found user")

        if not user:
            raise InvalidCredentialsError("Invalid username/email or password")

        # Capture IMMEDIATELY after query
        user_id = user.id
        logger.info(f"Step 2: Captured user_id={user_id}")

        username = user.username
        logger.info(f"Step 3: Captured username={username}")

        email = user.email
        full_name = user.full_name
        is_admin = user.is_admin
        is_active = user.is_active
        password_hash = user.password_hash
        github_token_encrypted = user.github_token_encrypted
        github_organization = user.github_organization
        github_default_repo = user.github_default_repo
        logger.info(f"Step 4: ALL attributes captured")

        # Verify password
        if not verify_password(password, password_hash):
            raise InvalidCredentialsError("Invalid username/email or password")
        logger.info(f"Step 5: Password verified")

        if not is_active:
            raise InactiveUserError("User account is inactive")
        logger.info(f"Step 6: Active check passed")

        # DONT touch user object anymore! Just commit
        last_login_time = datetime.utcnow()
        logger.info(f"Step 7: About to update last_login - user object state: {db.is_modified(user)}")

        user.last_login = last_login_time
        logger.info(f"Step 8: Set last_login")

        # NO audit log for now - just commit
        logger.info(f"Step 9: About to commit")
        db.commit()
        logger.info(f"Step 10: COMMITTED - user is now detached")

        # Create DTO from captured values
        user_dto = UserDTO(
            id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            is_admin=is_admin,
            is_active=is_active,
            last_login=last_login_time,
            github_token_encrypted=github_token_encrypted,
            github_organization=github_organization,
            github_default_repo=github_default_repo
        )
        logger.info(f"Step 11: Created UserDTO")

        # Generate token
        token = generate_jwt_token(user_dto)
        logger.info(f"Step 12: Generated token")

        logger.info(f"Step 13: About to return")
        return user_dto, token

    except Exception as e:
        logger.error(f"EXCEPTION in login_user: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        import traceback
        logger.error(traceback.format_exc())
        raise


def logout_user(
    db: Session,
    user_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    Logout user (creates audit log entry)

    Note: JWT tokens are stateless, so actual invalidation requires
    a token blacklist or short expiration times

    Args:
        db: Database session
        user_id: User ID
        ip_address: Client IP address
        user_agent: Client user agent
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Capture username BEFORE auto_commit
        username = user.username
        create_audit_log(
            db=db,
            user_id=user_id,
            action='logout',
            details=f"User {username} logged out",
            ip_address=ip_address,
            user_agent=user_agent,
            auto_commit=True
        )


def get_user_from_token(db: Session, token: str) -> UserDTO:
    """
    Get user from JWT token

    Args:
        db: Database session
        token: JWT token

    Returns:
        UserDTO object

    Raises:
        InvalidTokenError: If token is invalid
        UserNotFoundError: If user not found
        InactiveUserError: If user is inactive
    """
    # Validate token
    payload = validate_jwt_token(token)

    # Get user from database
    user = db.query(User).filter(User.id == payload['user_id']).first()

    if not user:
        raise UserNotFoundError("User not found")

    if not user.is_active:
        raise InactiveUserError("User account is inactive")

    # Create UserDTO from the user model while still in session
    user_dto = UserDTO.from_model(user)

    return user_dto


def generate_password_reset_token(
    db: Session,
    email: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> tuple[User, str]:
    """
    Generate password reset token for user

    Args:
        db: Database session
        email: User email address
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        Tuple of (User object, reset token)

    Raises:
        UserNotFoundError: If user not found
    """
    # Find user by email
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise UserNotFoundError("User not found")

    # Capture user data BEFORE commit
    user_id = user.id
    user_email = user.email

    # Generate secure random token
    token = secrets.token_urlsafe(32)

    # Create password reset record
    password_reset = PasswordReset(
        user_id=user_id,
        token=token
    )
    db.add(password_reset)
    db.commit()

    # Create audit log (with auto_commit since password_reset already committed)
    create_audit_log(
        db=db,
        user_id=user_id,
        action='password_reset_request',
        details=f"Password reset requested for {user_email}",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user, token


def validate_password_reset_token(db: Session, token: str) -> PasswordReset:
    """
    Validate password reset token

    Args:
        db: Database session
        token: Password reset token

    Returns:
        PasswordReset object

    Raises:
        InvalidTokenError: If token is invalid or expired
    """
    # Find token in database
    password_reset = db.query(PasswordReset).filter(
        PasswordReset.token == token
    ).first()

    if not password_reset:
        raise InvalidTokenError("Invalid password reset token")

    # Check if token is valid
    if not password_reset.is_valid():
        raise InvalidTokenError("Password reset token has expired or been used")

    return password_reset


def reset_password(
    db: Session,
    token: str,
    new_password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> User:
    """
    Reset user password using reset token

    Args:
        db: Database session
        token: Password reset token
        new_password: New password
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        User object

    Raises:
        InvalidTokenError: If token is invalid
        ValueError: If password validation fails
    """
    # Validate token
    password_reset = validate_password_reset_token(db, token)

    # Validate new password
    is_valid, error = validate_password(new_password)
    if not is_valid:
        raise ValueError(f"Invalid password: {error}")

    # Get user
    user = db.query(User).filter(User.id == password_reset.user_id).first()
    if not user:
        raise UserNotFoundError("User not found")

    # Capture user data BEFORE commit
    user_id = user.id
    user_email = user.email

    # Update password
    user.password_hash = hash_password(new_password)

    # Mark token as used
    password_reset.is_used = True
    password_reset.used_at = datetime.utcnow()

    db.commit()

    # Create audit log (with auto_commit since password already committed)
    create_audit_log(
        db=db,
        user_id=user_id,
        action='password_reset',
        details=f"Password reset for {user_email}",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user


def change_password(
    db: Session,
    user_id: int,
    current_password: str,
    new_password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> User:
    """
    Change user password (requires current password)

    Args:
        db: Database session
        user_id: User ID
        current_password: Current password
        new_password: New password
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        User object

    Raises:
        UserNotFoundError: If user not found
        InvalidCredentialsError: If current password is incorrect
        ValueError: If new password validation fails
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise UserNotFoundError("User not found")

    # Capture user data BEFORE commit
    username = user.username

    # Verify current password
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("Current password is incorrect")

    # Validate new password
    is_valid, error = validate_password(new_password)
    if not is_valid:
        raise ValueError(f"Invalid password: {error}")

    # Update password
    user.password_hash = hash_password(new_password)
    db.commit()

    # Create audit log (with auto_commit since password already committed)
    create_audit_log(
        db=db,
        user_id=user_id,
        action='password_changed',
        details=f"Password changed for {username}",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user


def create_admin_user(db: Session) -> User:
    """
    Create the default admin user if it doesn't exist

    Username: user500
    Password: Quaternion1234____

    Args:
        db: Database session

    Returns:
        User object (existing or newly created)
    """
    # Check if admin user already exists
    admin_user = db.query(User).filter(User.username == 'user500').first()

    if admin_user:
        print("Admin user 'user500' already exists")
        return admin_user

    # Create admin user
    admin_user = User(
        username='user500',
        email='admin@nx2git.local',
        password_hash=hash_password('Quaternion1234____'),
        full_name='Administrator',
        is_admin=True,
        is_active=True
    )

    db.add(admin_user)
    db.commit()
    # Note: db.refresh() removed - admin_user.id is already available after commit

    # Create audit log (with auto_commit since admin_user already committed)
    create_audit_log(
        db=db,
        user_id=admin_user.id,
        action='admin_user_created',
        resource_type='user',
        resource_id=admin_user.id,
        details='Default admin user created',
        auto_commit=True
    )

    print(f"Admin user created: username='user500', password='Quaternion1234____'")
    return admin_user


def require_admin(user: User) -> None:
    """
    Check if user is admin, raise error if not

    Args:
        user: User object

    Raises:
        AuthError: If user is not admin
    """
    if not user.is_admin:
        raise AuthError("Admin privileges required")


def deactivate_user(
    db: Session,
    user_id: int,
    admin_user_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> User:
    """
    Deactivate a user account (admin only)

    Args:
        db: Database session
        user_id: User ID to deactivate
        admin_user_id: Admin user ID performing the action
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        User object

    Raises:
        UserNotFoundError: If user not found
        AuthError: If admin user is not actually an admin
    """
    # Verify admin user
    admin_user = db.query(User).filter(User.id == admin_user_id).first()
    if not admin_user:
        raise UserNotFoundError("Admin user not found")
    require_admin(admin_user)

    # Get target user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise UserNotFoundError("User not found")

    # Capture usernames BEFORE commit
    username = user.username
    admin_username = admin_user.username

    # Deactivate user
    user.is_active = False
    db.commit()

    # Create audit log (with auto_commit since user already committed)
    create_audit_log(
        db=db,
        user_id=admin_user_id,
        action='user_deactivated',
        resource_type='user',
        resource_id=user.id,
        details=f"User {username} deactivated by admin {admin_username}",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user


def activate_user(
    db: Session,
    user_id: int,
    admin_user_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> User:
    """
    Activate a user account (admin only)

    Args:
        db: Database session
        user_id: User ID to activate
        admin_user_id: Admin user ID performing the action
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        User object

    Raises:
        UserNotFoundError: If user not found
        AuthError: If admin user is not actually an admin
    """
    # Verify admin user
    admin_user = db.query(User).filter(User.id == admin_user_id).first()
    if not admin_user:
        raise UserNotFoundError("Admin user not found")
    require_admin(admin_user)

    # Get target user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise UserNotFoundError("User not found")

    # Capture usernames BEFORE commit
    username = user.username
    admin_username = admin_user.username

    # Activate user
    user.is_active = True
    db.commit()

    # Create audit log (with auto_commit since user already committed)
    create_audit_log(
        db=db,
        user_id=admin_user_id,
        action='user_activated',
        resource_type='user',
        resource_id=user.id,
        details=f"User {username} activated by admin {admin_username}",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )

    return user


# ============================================================================
# OAuth Authentication Functions
# ============================================================================

class OAuthDomainNotAllowedError(AuthError):
    """Raised when user's email domain is not allowed for OAuth"""
    pass


def login_or_create_oauth_user(
    db: Session,
    google_id: str,
    email: str,
    full_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> tuple[UserDTO, str]:
    """
    Login or create a user via Google OAuth
    
    - If user with google_id exists: update and login
    - If user with email exists: link Google account and login
    - If auto_create enabled and domain allowed: create new user
    
    Args:
        db: Database session
        google_id: Google user ID
        email: User's email from Google
        full_name: User's full name from Google
        avatar_url: User's avatar URL from Google
        ip_address: Client IP address
        user_agent: Client user agent
        
    Returns:
        Tuple of (UserDTO, JWT token)
        
    Raises:
        OAuthDomainNotAllowedError: If email domain is not allowed
        InactiveUserError: If user account is inactive
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from .models.oauth_config import OAuthConfig
    
    logger.info(f"OAuth login attempt for: {email}")
    
    # Get OAuth config
    oauth_config = db.query(OAuthConfig).filter(
        OAuthConfig.provider == 'google',
        OAuthConfig.is_enabled == True
    ).first()
    
    if not oauth_config:
        raise AuthError("Google OAuth is not configured")
    
    # Check domain restriction
    if not oauth_config.is_domain_allowed(email):
        allowed = oauth_config.get_allowed_domains_list()
        logger.warning(f"OAuth domain not allowed for {email}. Allowed: {allowed}")
        raise OAuthDomainNotAllowedError(
            f"Die Domain Ihrer E-Mail-Adresse ist nicht erlaubt. "
            f"Erlaubte Domains: {', '.join(allowed)}"
        )
    
    # Try to find existing user by google_id
    user = db.query(User).filter(User.google_id == google_id).first()
    
    if user:
        logger.info(f"Found existing user by google_id: {user.username}")
    else:
        # Try to find by email (link existing account)
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            logger.info(f"Linking Google account to existing user: {user.username}")
            user.google_id = google_id
            user.auth_provider = 'google'
        elif oauth_config.auto_create_users:
            # Create new user
            logger.info(f"Creating new user via OAuth: {email}")
            
            # Generate username from email
            username = email.split('@')[0]
            base_username = username
            counter = 1
            
            # Ensure unique username
            while db.query(User).filter(User.username == username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email,
                password_hash="",  # No password for OAuth users
                full_name=full_name,
                is_admin=False,
                is_active=True,
                auth_provider='google',
                google_id=google_id,
                avatar_url=avatar_url,
            )
            db.add(user)
            logger.info(f"Created new OAuth user: {username}")
        else:
            logger.warning(f"Auto-create disabled, user not found: {email}")
            raise UserNotFoundError(
                "Kein Benutzer mit dieser E-Mail-Adresse gefunden. "
                "Automatische Registrierung ist deaktiviert."
            )
    
    # Check if user is active
    if not user.is_active:
        raise InactiveUserError("Ihr Benutzerkonto ist deaktiviert")
    
    # Update user info from Google
    if avatar_url and avatar_url != user.avatar_url:
        user.avatar_url = avatar_url
    if full_name and full_name != user.full_name:
        user.full_name = full_name
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    # Capture user data before commit
    user_id = user.id if user.id else None
    username = user.username
    user_email = user.email
    user_full_name = user.full_name
    user_is_admin = user.is_admin
    user_is_active = user.is_active
    user_last_login = user.last_login
    user_github_token = user.github_token_encrypted
    user_github_org = user.github_organization
    user_github_repo = user.github_default_repo
    user_auth_provider = user.auth_provider
    user_google_id = user.google_id
    user_avatar_url = user.avatar_url
    
    # Commit changes
    db.commit()
    
    # Get user_id after commit for new users
    if not user_id:
        user_id = user.id
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=user_id,
        action='oauth_login',
        details=f"User {username} logged in via Google OAuth",
        ip_address=ip_address,
        user_agent=user_agent,
        auto_commit=True
    )
    
    # Create UserDTO
    user_dto = UserDTO(
        id=user_id,
        username=username,
        email=user_email,
        full_name=user_full_name,
        is_admin=user_is_admin,
        is_active=user_is_active,
        last_login=user_last_login,
        github_token_encrypted=user_github_token,
        github_organization=user_github_org,
        github_default_repo=user_github_repo,
        auth_provider=user_auth_provider,
        google_id=user_google_id,
        avatar_url=user_avatar_url,
    )
    
    # Generate JWT token
    token = generate_jwt_token(user_dto)
    
    logger.info(f"OAuth login successful for: {username}")
    return user_dto, token
