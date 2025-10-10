#!/usr/bin/env python3
"""
Test script to debug GitHub content loading issue
"""
import sys
sys.path.append('/home/nx2git-go/webapp')

from app.database import get_db
from app.models.server import Server
from app.models.team import Team
from app.models.database import Database
from app.models.user import User
from app.utils.encryption import get_encryption_manager
from app.utils.github_utils import sanitize_name, get_repo_name_from_server
from app.api.github_manager import GitHubManager

def test_github_content():
    db = get_db()
    try:
        # Get user
        user = db.query(User).filter(User.username == 'user500').first()
        if not user:
            print("User not found")
            return

        # Get a database with github_path
        database = db.query(Database).filter(
            Database.github_path.isnot(None),
            Database.name == "00 - ERP - Solution"
        ).first()

        if not database:
            print("Database not found")
            return

        print(f"Database: {database.name}")
        print(f"GitHub Path: {database.github_path}")

        # Get team and server
        team = db.query(Team).filter(Team.id == database.team_id).first()
        server = db.query(Server).filter(Server.id == team.server_id).first()

        print(f"Team: {team.name}")
        print(f"Server: {server.name}")

        # Decrypt tokens
        encryption = get_encryption_manager()
        github_token = encryption.decrypt(user.github_token_encrypted)

        # Get repo name
        repo_name = get_repo_name_from_server(server)
        print(f"Repo name: {repo_name}")
        print(f"Organization: {user.github_organization}")

        # Create GitHub manager
        github_mgr = GitHubManager(
            access_token=github_token,
            organization=user.github_organization
        )

        # Get repository
        repo = github_mgr.get_repository(repo_name)
        if not repo:
            print("Repository not found")
            return

        print(f"Repository found: {repo.name}")

        # Build file path
        db_name = sanitize_name(database.name)
        file_path = f'{database.github_path}/{db_name}-structure.json'
        print(f"File path: {file_path}")

        # Get file metadata first
        try:
            file_obj = repo.get_contents(file_path)
            print(f"File size: {file_obj.size} bytes")
            print(f"File encoding: {file_obj.encoding}")
            print(f"Download URL: {file_obj.download_url}")
        except Exception as e:
            print(f"Error getting file metadata: {e}")
            return

        # Try to get content
        print("\n=== Testing get_file_content ===")
        content = github_mgr.get_file_content(repo, file_path)

        if content:
            print(f"Content loaded successfully!")
            print(f"Content length: {len(content)} characters")
            print(f"First 200 chars: {content[:200]}...")

            # Try to parse as JSON
            import json
            try:
                json_data = json.loads(content)
                print(f"JSON parsed successfully!")
                print(f"JSON has {len(json_data)} top-level keys")
                if isinstance(json_data, dict):
                    print(f"Top-level keys: {list(json_data.keys())[:5]}...")
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
        else:
            print("No content returned!")

    finally:
        db.close()

if __name__ == "__main__":
    test_github_content()