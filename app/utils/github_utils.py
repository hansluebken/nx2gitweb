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
    return sanitize_name(server_hostname)