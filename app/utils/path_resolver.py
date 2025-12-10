"""
Path Resolution Helper for Clean Name-Based Folder Structure
"""
from pathlib import Path

def get_server_path(server):
    from ..services.ninox_cli_service import NINOX_CLI_DATA_PATH
    from .github_utils import sanitize_name
    base = Path(NINOX_CLI_DATA_PATH)
    return base / sanitize_name(server.name)

def get_team_path(server, team):
    from .github_utils import sanitize_name
    server_path = get_server_path(server)
    return server_path / sanitize_name(team.name)

def get_database_path(server, team, database_name):
    from .github_utils import sanitize_name
    team_path = get_team_path(server, team)
    return team_path / sanitize_name(database_name)
