"""
GitHub-related utility functions
"""
import re


def sanitize_name(name):
    """Remove/replace characters that are problematic for file paths"""
    # Replace problematic characters with underscores or remove them
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Replace spaces with underscores
    safe_name = safe_name.replace(' ', '_')
    # Remove leading/trailing dots and spaces
    safe_name = safe_name.strip('. ')
    return safe_name


def sanitize_repo_name(name):
    """
    Sanitize a name for use as a GitHub repository name.
    
    GitHub repository names can only contain:
    - Alphanumeric characters (a-z, A-Z, 0-9)
    - Hyphens (-)
    - Underscores (_)
    - Dots (.)
    
    They cannot:
    - Start or end with a dot
    - Contain consecutive dots
    - Be longer than 100 characters
    """
    # Replace spaces and other invalid characters with hyphens
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', name)
    # Remove consecutive hyphens or dots
    safe_name = re.sub(r'-+', '-', safe_name)
    safe_name = re.sub(r'\.+', '.', safe_name)
    # Remove leading/trailing hyphens, dots, and underscores
    safe_name = safe_name.strip('-._')
    # Truncate to 100 characters (GitHub limit)
    safe_name = safe_name[:100]
    # Ensure it's not empty
    if not safe_name:
        safe_name = 'repository'
    return safe_name


def get_repo_name_from_server(server):
    """Get the repository name based on the server URL

    Args:
        server: Server object with url attribute

    Returns:
        Sanitized repository name based on server hostname
    """
    # Extract server hostname from URL for repository name
    # e.g. "https://hagedorn.ninoxdb.de" -> "hagedorn.ninoxdb.de"
    server_hostname = server.url.replace('https://', '').replace('http://', '').split('/')[0]
    return sanitize_repo_name(server_hostname)