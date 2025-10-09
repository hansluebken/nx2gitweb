"""
Helper utilities for the application
"""
import re
import secrets
from typing import Optional


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as filename or directory name

    Args:
        name: String to sanitize

    Returns:
        Sanitized string safe for filenames
    """
    # Remove problematic characters
    # Keep: letters, numbers, hyphen, dot, underscore
    name = re.sub(r'[^a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùû\-._]', '_', name)

    # Remove multiple dots
    name = re.sub(r'\.{2,}', '.', name)

    # Remove multiple underscores
    name = re.sub(r'_{2,}', '_', name)

    # Remove leading/trailing dots, underscores, hyphens
    name = name.strip('._-')

    # Handle empty result
    if not name:
        name = 'unnamed'

    # Limit length (with room for extensions)
    if len(name) > 200:
        if '.' in name[-10:]:
            parts = name.rsplit('.', 1)
            base = parts[0][:190]
            name = f"{base}.{parts[1]}"
        else:
            name = name[:200]

    return name


def generate_random_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token

    Args:
        length: Length of the token in bytes (default 32)

    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(length)


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes to human-readable string

    Args:
        bytes_value: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def truncate_string(text: str, max_length: int = 50, suffix: str = '...') -> str:
    """
    Truncate a string to a maximum length

    Args:
        text: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
