#!/usr/bin/env python3
"""
Migration script to move GitHub configuration from Server to User model
This is a one-time migration to support the new architecture where GitHub
tokens are stored at the user level instead of server level.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.models.server import Server
from app.models.user import User


def migrate_github_config():
    """
    Migrate GitHub configuration from servers to users.
    Takes the first server's GitHub config for each user and moves it to the user model.
    """
    db = get_db()

    try:
        # Get all servers with GitHub configuration
        servers_with_github = db.query(Server).filter(
            (Server.github_token_encrypted != None) |
            (Server.github_organization != None) |
            (Server.github_repo_name != None)
        ).all()

        if not servers_with_github:
            print("No servers with GitHub configuration found. Migration not needed.")
            return

        print(f"Found {len(servers_with_github)} servers with GitHub configuration")

        # Group servers by user
        user_configs = {}
        for server in servers_with_github:
            if server.user_id not in user_configs:
                user_configs[server.user_id] = server

        # Migrate configuration to users
        migrated_count = 0
        for user_id, server in user_configs.items():
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # Only migrate if user doesn't already have GitHub config
                if not user.github_token_encrypted:
                    print(f"Migrating GitHub config for user {user.username} from server {server.name}")
                    user.github_token_encrypted = server.github_token_encrypted
                    user.github_organization = server.github_organization
                    user.github_default_repo = server.github_repo_name
                    migrated_count += 1
                else:
                    print(f"User {user.username} already has GitHub configuration, skipping")

        if migrated_count > 0:
            db.commit()
            print(f"Successfully migrated GitHub configuration for {migrated_count} users")

            # Clear GitHub config from servers
            for server in servers_with_github:
                server.github_token_encrypted = None
                server.github_organization = None
                server.github_repo_name = None

            db.commit()
            print("Cleared GitHub configuration from servers (kept for backward compatibility)")
        else:
            print("No users needed GitHub configuration migration")

    except Exception as e:
        print(f"Error during migration: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting GitHub configuration migration...")
    migrate_github_config()
    print("Migration completed successfully!")