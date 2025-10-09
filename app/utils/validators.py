"""
Validation utilities
"""
import re
from email_validator import validate_email as email_validator_validate, EmailNotValidError


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email address

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Validate and normalize email
        validation = email_validator_validate(email)
        return True, ""
    except EmailNotValidError as e:
        return False, str(e)


def validate_password(password: str, min_length: int = 8) -> tuple[bool, str]:
    """
    Validate password strength

    Requirements:
    - Minimum length (default 8)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate
        min_length: Minimum password length

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters long"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        return False, "Password must contain at least one special character"

    return True, ""


def validate_username(username: str) -> tuple[bool, str]:
    """
    Validate username

    Requirements:
    - 3-50 characters
    - Only alphanumeric, underscore, hyphen
    - Must start with alphanumeric

    Args:
        username: Username to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"

    if len(username) > 50:
        return False, "Username must be at most 50 characters long"

    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', username):
        return False, "Username must start with a letter or number and contain only letters, numbers, underscore, or hyphen"

    return True, ""


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate URL format

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Simple URL validation regex
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if not url_pattern.match(url):
        return False, "Invalid URL format. Must start with http:// or https://"

    return True, ""
