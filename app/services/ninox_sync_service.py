"""
Ninox Sync Service
Provides high-level sync operations for ninox-dev-cli integration.

This service can be used by:
- The NiceGUI web application
- Cronjobs for automatic synchronization
- External CLI tools (opencode, claude code)
"""
import os
import logging
import asyncio
import subprocess
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from .ninox_cli_service import (
    get_ninox_cli_service,
    NinoxCLIService,
    NinoxEnvironment,
    DownloadResult,
    DatabaseInfo
)
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database

logger = logging.getLogger(__name__)


class NinoxSyncService:
    """
    High-level service for synchronizing Ninox databases.
    
    Provides methods for:
    - Syncing all databases from a server
    - Syncing specific databases
    - Scheduled/cronjob sync
    - CLI-triggered sync
    """
    
    def __init__(self):
        self.cli_service = get_ninox_cli_service()
        # Ensure git repo is initialized
        init_git_repo(self.cli_service.project_path)

    def _generate_and_save_docs(self, team: Team, database_id: str, team_path, db_model_id: int):
        """
        Generate AI documentation and save in database.

        Args:
            team: Team model
            database_id: Ninox database ID
            team_path: Path to team folder
            db_model_id: Database model ID for Documentation relationship
        """
        try:
            from ..utils.ninox_yaml_parser import NinoxYAMLParser
            from ..services.doc_generator import get_documentation_generator
            from ..models.documentation import Documentation

            # Check if AI is configured
            generator = get_documentation_generator()
            if not generator:
                logger.info(f"Skipping docs for {database_id} - AI not configured")
                return

            # Load database from YAML
            parser = NinoxYAMLParser(str(team_path))
            databases = parser.get_all_databases()

            yaml_db = None
            for db in databases:
                if db.database_id == database_id:
                    yaml_db = db
                    break

            if not yaml_db:
                logger.warning(f"Database {database_id} not found for docs generation")
                return

            # Generate documentation using AI (convert YAML to dict format)
            logger.info(f"Calling AI to generate documentation for {yaml_db.name}...")
            structure_dict = yaml_db.to_dict_for_docs()
            result = generator.generate(structure_dict, yaml_db.name)

            if result.success:
                # Save to database
                db_conn = get_db()
                try:
                    doc = Documentation(
                        database_id=db_model_id,
                        content=result.content,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens
                    )
                    db_conn.add(doc)
                    db_conn.commit()
                    logger.info(f"✓ AI documentation saved to database for {yaml_db.name} ({result.input_tokens + result.output_tokens} tokens)")
                finally:
                    db_conn.close()

                # Save to local file and commit to git
                try:
                    # Save docs directly at database root (old structure - deprecated)
                    database_path = team_path / 'src' / 'Objects' / f'database_{database_id}'
                    docs_file = database_path / 'APPLICATION_DOCS.md'
                    docs_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(docs_file, 'w', encoding='utf-8') as f:
                        f.write(result.content)

                    logger.info(f"✓ AI documentation saved to file: {docs_file}")

                    # Commit documentation to git
                    commit_message = f"Update AI documentation for {yaml_db.name}"
                    commit_changes(team_path, commit_message)
                    logger.info(f"✓ Documentation committed to git")

                except Exception as e:
                    logger.error(f"Failed to save documentation file: {e}")

            else:
                logger.warning(f"Documentation generation failed: {result.error}")

        except Exception as e:
            logger.error(f"Error generating docs for {database_id}: {e}")

    def _generate_and_save_erd_new_structure(
        self,
        server: Server,
        team: Team,
        database_name: str,
        database_id: str,
        db_path: Path
    ):
        """
        Generate ERD and save as SVG file (NEW structure with clear names).

        Args:
            server: Server model
            team: Team model
            database_name: Database display name
            database_id: Ninox database ID
            db_path: Path to database directory (with clear names)
        """
        try:
            from ..utils.ninox_yaml_parser import NinoxYAMLParser
            from ..utils.svg_erd_generator import generate_svg_erd

            # Parser on DATABASE level (db_path contains src/Objects/)
            parser = NinoxYAMLParser(str(db_path))
            databases = parser.get_all_databases()

            # Should find exactly one database
            if not databases:
                logger.warning(f"No databases found in {db_path} for ERD generation")
                return

            yaml_db = databases[0]  # Take first (should be only one)
            logger.info(f"Found database for ERD: {yaml_db.name}")

            # Generate SVG directly from YAML
            svg_content = generate_svg_erd(yaml_db)

            if svg_content and '<svg' in svg_content:
                # Save ERD as SVG file in database subfolder
                from ..utils.github_utils import sanitize_name
                db_subfolder = f"database_{sanitize_name(database_name)}"
                erd_file = db_path / 'src' / 'Objects' / db_subfolder / 'erd.svg'
                erd_file.parent.mkdir(parents=True, exist_ok=True)

                with open(erd_file, 'w', encoding='utf-8') as f:
                    f.write(svg_content)

                logger.info(f"✓ ERD saved: {erd_file} ({len(svg_content)} bytes)")
            else:
                logger.warning(f"ERD generation failed for {database_name} - no valid SVG")

        except Exception as e:
            logger.error(f"Error generating ERD for {database_name}: {e}")

    def _generate_and_save_docs_new_structure(
        self,
        server: Server,
        team: Team,
        database_name: str,
        database_id: str,
        db_path: Path,
        db_model_id: int
    ):
        """
        Generate AI documentation and save (NEW structure with clear names).

        Args:
            server: Server model
            team: Team model
            database_name: Database display name
            database_id: Ninox database ID
            db_path: Path to database directory (with clear names)
            db_model_id: Database model ID for Documentation relationship
        """
        try:
            from ..utils.ninox_yaml_parser import NinoxYAMLParser
            from ..services.doc_generator import get_documentation_generator
            from ..models.documentation import Documentation

            # Check if AI is configured
            generator = get_documentation_generator()
            if not generator:
                logger.info(f"Skipping docs for {database_name} - AI not configured")
                return

            # Parser on DATABASE level (db_path contains src/Objects/)
            parser = NinoxYAMLParser(str(db_path))
            databases = parser.get_all_databases()

            # Should find exactly one database
            if not databases:
                logger.warning(f"No databases found in {db_path} for docs generation")
                return

            yaml_db = databases[0]
            logger.info(f"Found database for docs: {yaml_db.name}")

            # Generate documentation using AI (convert YAML to dict format)
            logger.info(f"Calling AI to generate documentation for {yaml_db.name}...")
            structure_dict = yaml_db.to_dict_for_docs()
            result = generator.generate(structure_dict, yaml_db.name)

            if result.success:
                # Save to database
                db_conn = get_db()
                try:
                    doc = Documentation(
                        database_id=db_model_id,
                        content=result.content,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens
                    )
                    db_conn.add(doc)
                    db_conn.commit()
                    logger.info(f"✓ AI documentation saved to database for {yaml_db.name} ({result.input_tokens + result.output_tokens} tokens)")
                finally:
                    db_conn.close()

                # Save to local file and commit to git
                try:
                    # Save docs directly at database root for better visibility in GitHub
                    docs_file = db_path / 'APPLICATION_DOCS.md'
                    docs_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(docs_file, 'w', encoding='utf-8') as f:
                        f.write(result.content)

                    logger.info(f"✓ AI documentation saved to file: {docs_file}")

                    # Commit documentation to git (server level)
                    server_path = db_path.parent.parent
                    commit_message = f"Update AI documentation for {yaml_db.name}"
                    commit_changes(server_path, commit_message)
                    logger.info(f"✓ Documentation committed to git")

                except Exception as e:
                    logger.error(f"Failed to save documentation file: {e}")

            else:
                logger.warning(f"Documentation generation failed: {result.error}")

        except Exception as e:
            logger.error(f"Error generating docs for {database_name}: {e}")

    def _generate_and_save_scripts_new_structure(
        self,
        server: Server,
        team: Team,
        database_name: str,
        database_id: str,
        db_path: Path
    ):
        """
        Generate scripts.md file with all code from the database (NEW structure).

        Args:
            server: Server model
            team: Team model
            database_name: Database display name
            database_id: Ninox database ID
            db_path: Path to database directory (with clear names)
        """
        try:
            from ..utils.ninox_yaml_parser import NinoxYAMLParser
            from ..utils.scripts_md_generator import generate_scripts_md

            # Parser on DATABASE level (db_path contains src/Objects/)
            parser = NinoxYAMLParser(str(db_path))
            databases = parser.get_all_databases()

            # Should find exactly one database
            if not databases:
                logger.warning(f"No databases found in {db_path} for scripts generation")
                return

            yaml_db = databases[0]
            logger.info(f"Generating scripts.md for {yaml_db.name}...")

            # Generate scripts markdown
            scripts_content = generate_scripts_md(yaml_db)

            # Save to local file
            try:
                # Save scripts directly at database root (same level as APPLICATION_DOCS.md)
                scripts_file = db_path / 'SCRIPTS.md'
                scripts_file.parent.mkdir(parents=True, exist_ok=True)

                with open(scripts_file, 'w', encoding='utf-8') as f:
                    f.write(scripts_content)

                logger.info(f"✓ Scripts saved to file: {scripts_file}")

                # Commit scripts to git (server level)
                server_path = db_path.parent.parent
                commit_message = f"Update scripts for {yaml_db.name}"
                commit_changes(server_path, commit_message)
                logger.info(f"✓ Scripts committed to git")

            except Exception as e:
                logger.error(f"Failed to save scripts file: {e}")

        except Exception as e:
            logger.error(f"Error generating scripts for {database_name}: {e}")

    def _generate_and_save_erd(self, team: Team, database_id: str, team_path):
        """
        Generate ERD and save as SVG file in team folder.

        Args:
            team: Team model
            database_id: Ninox database ID
            team_path: Path to team folder
        """
        try:
            from ..utils.ninox_yaml_parser import NinoxYAMLParser
            from ..utils.svg_erd_generator import generate_svg_erd

            # Load database from YAML
            parser = NinoxYAMLParser(str(team_path))
            databases = parser.get_all_databases()

            yaml_db = None
            for db in databases:
                if db.database_id == database_id:
                    yaml_db = db
                    break

            if not yaml_db:
                logger.warning(f"Database {database_id} not found in YAML for ERD generation")
                return

            # Generate SVG directly from YAML (no JSON conversion needed!)
            svg_content = generate_svg_erd(yaml_db)

            if svg_content and '<svg' in svg_content:
                # Save ERD as SVG file
                erd_file = team_path / 'src' / 'Objects' / f'database_{database_id}' / 'erd.svg'
                erd_file.parent.mkdir(parents=True, exist_ok=True)

                with open(erd_file, 'w', encoding='utf-8') as f:
                    f.write(svg_content)

                logger.info(f"✓ ERD saved: {erd_file} ({len(svg_content)} bytes)")
            else:
                logger.warning(f"ERD generation failed for {database_id} - no valid SVG")

        except Exception as e:
            logger.error(f"Error generating ERD for {database_id}: {e}")

    def _setup_github_remote_on_first_sync(
        self,
        team_path: Path,
        server: Server,
        user
    ) -> bool:
        """
        Setup GitHub remote and do initial push (only on first sync).

        This is called after the first YAML download to:
        1. Create GitHub repository if needed
        2. Configure git remote with token
        3. Push initial YAML structure to GitHub

        Args:
            team_path: Path to team folder with git repo
            server: Server model
            user: User object with GitHub credentials

        Returns:
            True if this was the first sync and setup was done, False otherwise
        """
        from ..api.github_manager import GitHubManager
        from ..utils.encryption import get_encryption_manager
        from ..utils.github_utils import get_repo_name_from_server

        # Check if remote already configured
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=team_path,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info(f"Git remote already configured: {result.stdout.strip()}")
            logger.info("ℹ️  YAML committed locally. Push manually when ready: cd /app/data/ninox-cli/team_<id> && git push")
            return False  # Not first sync

        # Check if user has GitHub configured
        if not user.github_token_encrypted or not user.github_organization:
            logger.info("GitHub not configured in user profile - skipping remote setup")
            return False

        # First sync - setup GitHub
        logger.info("🚀 First sync detected - setting up GitHub remote...")

        try:
            # Decrypt GitHub token
            enc_manager = get_encryption_manager()
            github_token = enc_manager.decrypt(user.github_token_encrypted)
            github_org = user.github_organization

            # Get repository name from server
            repo_name = get_repo_name_from_server(server)

            logger.info(f"📦 Repository: {github_org}/{repo_name}")

            # 1. Ensure repository exists on GitHub
            github_mgr = GitHubManager(access_token=github_token, organization=github_org)
            repo = github_mgr.ensure_repository(
                repo_name,
                description=f"Ninox YAML backups from {server.name}"
            )
            logger.info(f"✓ GitHub repository ready: {repo.html_url}")

            # 2. Configure git remote with token
            remote_url = f"https://{github_token}@github.com/{github_org}/{repo_name}.git"
            subprocess.run(
                ['git', 'remote', 'add', 'origin', remote_url],
                cwd=team_path,
                check=True,
                capture_output=True
            )
            logger.info("✓ Git remote configured")

            # 3. Ensure we're on main branch
            subprocess.run(
                ['git', 'branch', '-M', 'main'],
                cwd=team_path,
                capture_output=True
            )

            # 4. Initial push to GitHub (force push to overwrite any initial commits)
            logger.info("📤 Pushing initial YAML structure to GitHub...")
            push_result = subprocess.run(
                ['git', 'push', '-u', 'origin', 'main', '--force'],
                cwd=team_path,
                capture_output=True,
                text=True
            )

            if push_result.returncode == 0:
                logger.info(f"✅ Initial push completed to {github_org}/{repo_name}")
                logger.info(f"🔗 Repository URL: {repo.html_url}")
                return True
            else:
                logger.error(f"❌ Push failed: {push_result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to setup GitHub remote: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _restructure_download(
        self,
        temp_cli_path: Path,
        server: Server,
        team: Team,
        database_name: str,
        database_id: str
    ) -> Path:
        """
        Reorganize ninox-cli output from ID-based to NAME-based structure.

        FROM (ninox-cli temp):
            _temp_team_{id}/src/Objects/database_{id}/

        TO (clean structure):
            {server_name}/{team_name}/{database_name}/src/Objects/

        Args:
            temp_cli_path: Temporary ninox-cli download path
            server: Server model
            team: Team model
            database_name: Database display name
            database_id: Database ID (from Ninox)

        Returns:
            Path to final database directory
        """
        import shutil
        import json
        from ..utils.github_utils import sanitize_name

        # Source: ninox-cli output with IDs (Objects and Files)
        source_objects = temp_cli_path / 'src' / 'Objects' / f'database_{database_id}'
        source_files = temp_cli_path / 'src' / 'Files' / f'database_{database_id}'

        if not source_objects.exists():
            raise ValueError(f"ninox-cli download not found: {source_objects}")

        # Target: Clean name-based structure
        target_server_path = self.cli_service.project_path / sanitize_name(server.name)
        target_team_path = target_server_path / sanitize_name(team.name)
        target_db_path = target_team_path / sanitize_name(database_name)

        # Create target directories
        target_db_path.mkdir(parents=True, exist_ok=True)

        # Parser expects: base/src/Objects/database_*/
        # So we need to create a database subfolder in Objects
        db_subfolder = f"database_{sanitize_name(database_name)}"
        target_objects = target_db_path / 'src' / 'Objects' / db_subfolder

        # Remove if exists (clean re-sync)
        if target_objects.exists():
            shutil.rmtree(target_objects)

        # Copy Objects to target (into database subfolder)
        shutil.copytree(source_objects, target_objects)
        logger.info(f"✓ Copied Objects: {source_objects} → {target_objects}")

        # Copy Files if they exist (also into database subfolder)
        if source_files.exists():
            target_files = target_db_path / 'src' / 'Files' / db_subfolder
            if target_files.exists():
                shutil.rmtree(target_files)
            shutil.copytree(source_files, target_files)
            logger.info(f"✓ Copied Files: {source_files} → {target_files}")
        else:
            logger.info(f"No Files folder found for {database_name}")

        # Create metadata file for ID tracking
        from ..utils.metadata_helper import create_database_metadata
        create_database_metadata(target_db_path, server, team, database_id, database_name)

        logger.info(f"✓ Restructured: {source_objects} → {target_db_path}")

        # Clean up temp folder
        try:
            if temp_cli_path.name.startswith('_temp_'):
                shutil.rmtree(temp_cli_path)
                logger.info(f"✓ Temp folder cleaned: {temp_cli_path}")
        except Exception as e:
            logger.warning(f"Could not clean temp folder: {e}")

        return target_db_path

    def get_server_team_path(self, server: Server, team: Team) -> Path:
        """
        Get the working path for a server/team combination using CLEAR NAMES.

        Structure: /app/data/ninox-cli/{server_name}/{team_name}/

        Args:
            server: Server model instance
            team: Team model instance

        Returns:
            Path to team working directory
        """
        from ..utils.github_utils import sanitize_name

        base_path = self.cli_service.project_path
        server_folder = sanitize_name(server.name)
        team_folder = sanitize_name(team.name)

        return base_path / server_folder / team_folder

    def get_team_cli_service(self, team: Team, database_id: str = None) -> NinoxCLIService:
        """
        Get or create a team-specific CLI service.

        DEPRECATED: This method still uses old ID-based paths for ninox-cli temp download.
        The actual working directory uses clear names via get_server_team_path().

        Args:
            team: Team model instance
            database_id: Optional database ID for unique temp directory

        Returns:
            NinoxCLIService configured for this team
        """
        # Temp folder for ninox-cli download (will be restructured)
        # Use database_id to create unique temp folder for each DB in parallel syncs
        base_path = self.cli_service.project_path
        if database_id:
            team_path = base_path / f'_temp_team_{team.team_id}_db_{database_id}'
        else:
            team_path = base_path / f'_temp_team_{team.team_id}'

        # Create team-specific CLI service
        team_cli_service = NinoxCLIService(str(team_path))

        # Initialize project and git repo for this team
        team_cli_service.init_project()
        init_git_repo(team_path)

        logger.info(f"Created team-specific CLI service for team {team.name} (ID: {team.team_id}) at {team_path}")

        return team_cli_service
    
    def configure_server_environment(self, server: Server, team: Team, team_cli_service: NinoxCLIService) -> str:
        """
        Configure ninox-cli environment for a server/team combination.

        Args:
            server: Server model instance
            team: Team model instance
            team_cli_service: Team-specific CLI service

        Returns:
            Environment name
        """
        from ..utils.encryption import get_encryption_manager

        env_name = f"{server.name.lower().replace(' ', '_')}_{team.name.lower().replace(' ', '_')}"

        # Ensure domain has protocol
        domain = server.url
        if not domain.startswith('http'):
            domain = f"https://{domain}"

        # Decrypt API key
        enc_manager = get_encryption_manager()
        api_key = enc_manager.decrypt(server.api_key_encrypted)

        env = NinoxEnvironment(
            name=env_name,
            domain=domain,
            api_key=api_key,
            workspace_id=team.team_id
        )

        team_cli_service.init_project()
        team_cli_service.configure_environment(env)

        return env_name
    
    def sync_database(
        self,
        server: Server,
        team: Team,
        database_id: str,
        timeout: int = 300
    ) -> DownloadResult:
        """
        Synchronously download a single database to team-specific folder.

        Args:
            server: Server model
            team: Team model
            database_id: Ninox database ID
            timeout: Download timeout

        Returns:
            DownloadResult
        """
        # Get team-specific CLI service
        team_cli_service = self.get_team_cli_service(team)

        # Configure environment for this team
        env_name = self.configure_server_environment(server, team, team_cli_service)

        # Download database to team-specific folder
        result = team_cli_service.download_database(env_name, database_id, timeout)

        # Auto-commit changes if sync was successful
        if result.success:
            db_name = result.path.parent.name if result.path else database_id
            commit_message = f"Sync: {db_name} ({database_id})"
            commit_changes(team_cli_service.project_path, commit_message)

        return result
    
    async def sync_database_async(
        self,
        server: Server,
        team: Team,
        database_id: str,
        timeout: int = 300,
        user = None,
        generate_erd: bool = None,
        generate_docs: bool = None
    ) -> DownloadResult:
        """
        Asynchronously download a single database and restructure to name-based paths.

        Workflow:
        1. Download with ninox-cli to temp folder (ID-based)
        2. Get database name from DB
        3. Restructure to: {server_name}/{team_name}/{database_name}/
        4. Commit to git (name-based structure)
        5. GitHub setup on first sync
        6. Generate ERD and docs

        Args:
            server: Server model
            team: Team model
            database_id: Ninox database ID
            timeout: Download timeout
            user: Optional User object for GitHub setup
            generate_erd: Whether to generate ERD (None = auto-detect based on first sync)
            generate_docs: Whether to generate documentation (None = auto-detect based on first sync)
        """
        import shutil

        # Get database name from database model
        db_conn = get_db()
        try:
            db_obj = db_conn.query(Database).filter(
                Database.team_id == team.id,
                Database.database_id == database_id
            ).first()

            if not db_obj:
                logger.error(f"Database {database_id} not found in DB")
                return DownloadResult(success=False, database_id=database_id, error="Database not found in system")

            database_name = db_obj.name
        finally:
            db_conn.close()

        logger.info(f"Syncing: {database_name} (ID: {database_id})")

        # Get temp CLI service for download (unique per database for parallel syncs)
        team_cli_service = self.get_team_cli_service(team, database_id)

        # Configure environment
        env_name = self.configure_server_environment(server, team, team_cli_service)

        # Download to TEMP folder (ninox-cli standard structure with IDs)
        result = await team_cli_service.download_database_async(env_name, database_id, timeout)

        if not result.success:
            return result

        # ============================================================
        # RESTRUCTURE: ID-based → NAME-based
        # ============================================================
        try:
            final_db_path = self._restructure_download(
                temp_cli_path=team_cli_service.project_path,
                server=server,
                team=team,
                database_name=database_name,
                database_id=database_id
            )

            logger.info(f"✓ Restructured to: {final_db_path}")

        except Exception as e:
            logger.error(f"Restructuring failed: {e}")
            return DownloadResult(success=False, database_id=database_id, error=f"Restructuring failed: {e}")

        # ============================================================
        # GIT OPERATIONS (on name-based structure)
        # ============================================================

        # Get server-level path for git operations
        server_path = self.get_server_team_path(server, team).parent  # Go up to server level

        # Initialize git if needed
        init_git_repo(server_path)

        # Commit changes
        commit_message = f"Sync: {database_name}"
        commit_changes(server_path, commit_message)
        logger.info(f"✓ Committed: {database_name}")

        # ============================================================
        # DETECT FIRST SYNC FOR THIS DATABASE (not based on git remote)
        # ============================================================
        # Check if this database has ever been synced before
        was_first_sync_for_db = False
        db_conn = get_db()
        try:
            db_obj = db_conn.query(Database).filter(
                Database.team_id == team.id,
                Database.database_id == database_id
            ).first()

            if db_obj and not db_obj.last_modified:
                # Database exists but has never been synced (last_modified is None)
                was_first_sync_for_db = True
                logger.info(f"First sync detected for database: {database_name}")
            elif db_obj:
                logger.info(f"Subsequent sync for database: {database_name} (last synced: {db_obj.last_modified})")
        finally:
            db_conn.close()

        # Setup GitHub remote on first sync, then push on every sync (if user provided)
        was_first_sync_for_server = False
        if user:
            try:
                was_first_sync_for_server = self._setup_github_remote_on_first_sync(
                    server_path,
                    server,
                    user
                )
                if was_first_sync_for_server:
                    logger.info("✅ GitHub remote configured and initial push completed")
                else:
                    # Not first sync - but still push to GitHub
                    logger.info("📤 Pushing changes to GitHub...")
                    import subprocess
                    push_result = subprocess.run(
                        ['git', 'push'],
                        cwd=server_path,
                        capture_output=True,
                        text=True
                    )
                    if push_result.returncode == 0:
                        logger.info("✅ Changes pushed to GitHub")
                    else:
                        logger.warning(f"Push failed: {push_result.stderr}")
            except Exception as e:
                logger.warning(f"GitHub operation failed (non-critical): {e}")

        # ============================================================
        # AUTO-DETECT: Initial sync = ALWAYS generate everything
        # ============================================================
        if was_first_sync_for_db:
            # INITIAL SYNC: Always generate ERD (DOCS only if enabled by user)
            generate_erd = True
            generate_docs = None  # Will be read from database settings
            logger.info(f"Sync mode: INITIAL - Force generating ERD only")
        else:
            # SUBSEQUENT SYNC: Read settings from database
            if generate_erd is None or generate_docs is None:
                db_conn = get_db()
                try:
                    db_obj = db_conn.query(Database).filter(
                        Database.team_id == team.id,
                        Database.database_id == database_id
                    ).first()

                    if db_obj:
                        if generate_erd is None:
                            generate_erd = getattr(db_obj, 'auto_generate_erd', True)
                        if generate_docs is None:
                            generate_docs = db_obj.auto_generate_docs
                    else:
                        # Fallback if DB not found
                        if generate_erd is None:
                            generate_erd = True
                        if generate_docs is None:
                            generate_docs = True
                finally:
                    db_conn.close()

            logger.info(f"Sync mode: SUBSEQUENT | ERD: {generate_erd} | DOCS: {generate_docs}")

        # ============================================================
        # POST-SYNC TASKS (ERD, Docs, Dependencies)
        # ============================================================

        logger.info(f"Running post-sync tasks for {database_name}...")

        # 1. Generate and save ERD as SVG file (if enabled)
        if generate_erd:
            try:
                # ERD will be saved in the new structure
                self._generate_and_save_erd_new_structure(
                    server, team, database_name, database_id, final_db_path
                )
            except Exception as e:
                logger.warning(f"ERD generation failed for {database_name}: {e}")
        else:
            logger.info(f"Skipping ERD generation for {database_name} (user disabled)")

        # 2. Generate AI documentation (if enabled)
        if generate_docs:
            try:
                from ..services.background_sync import get_sync_manager
                sync_manager = get_sync_manager()
                skip_docs_for_bulk = getattr(sync_manager, '_skip_docs_for_bulk', False)

                if skip_docs_for_bulk:
                    logger.info(f"Skipping auto-docs for {database_name} (user disabled for this sync)")
                else:
                    db_conn = get_db()
                    try:
                        db_obj = db_conn.query(Database).filter(
                            Database.team_id == team.id,
                            Database.database_id == database_id
                        ).first()

                        if db_obj and db_obj.auto_generate_docs:
                            logger.info(f"Auto-generating documentation for {database_name} (enabled)...")
                            self._generate_and_save_docs_new_structure(
                                server, team, database_name, database_id, final_db_path, db_obj.id
                            )
                            # Also generate scripts.md with all code
                            logger.info(f"Auto-generating scripts.md for {database_name}...")
                            self._generate_and_save_scripts_new_structure(
                                server, team, database_name, database_id, final_db_path
                            )
                        else:
                            logger.info(f"Skipping auto-docs for {database_name} (disabled in DB settings)")
                    finally:
                        db_conn.close()
            except Exception as e:
                logger.warning(f"Documentation generation failed for {database_name}: {e}")
        else:
            logger.info(f"Skipping documentation generation for {database_name} (user disabled)")

        # ============================================================
        # FINAL PUSH - Push all commits (sync + ERD + docs) to GitHub
        # ============================================================
        if user and user.github_token_encrypted:
            try:
                logger.info("📤 Final push: Pushing all changes (sync + ERD + docs) to GitHub...")
                import subprocess
                push_result = subprocess.run(
                    ['git', 'push'],
                    cwd=server_path,
                    capture_output=True,
                    text=True
                )
                if push_result.returncode == 0:
                    logger.info("✅ All changes pushed to GitHub successfully")
                else:
                    logger.warning(f"Final push failed: {push_result.stderr}")
            except Exception as e:
                logger.warning(f"Final push failed (non-critical): {e}")

        # ============================================================
        # UPDATE last_modified after sync
        # ============================================================
        if was_first_sync_for_db:
            # Mark database as synced
            db_conn = get_db()
            try:
                db_obj = db_conn.query(Database).filter(
                    Database.team_id == team.id,
                    Database.database_id == database_id
                ).first()

                if db_obj:
                    db_obj.last_modified = datetime.utcnow()  # Mark as synced
                    # Note: Auto-flags remain as user configured them (default: ERD=TRUE, DOCS=FALSE)
                    db_conn.commit()
                    logger.info(f"✓ Marked database as synced (last_modified updated)")
            finally:
                db_conn.close()

        # Return success with new path
        return DownloadResult(
            success=True,
            database_id=database_id,
            path=final_db_path
        )
    def sync_all_databases(
        self,
        server: Server,
        team: Team,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, DownloadResult]:
        """
        Download all databases from a server/team.
        
        Args:
            server: Server model
            team: Team model
            progress_callback: Optional callback(current, total, db_name)
            
        Returns:
            Dict mapping database_id to DownloadResult
        """
        results = {}
        
        # Get list of databases
        databases = self.list_remote_databases(server, team)
        total = len(databases)
        
        # Temporarily disable auto-commit for individual syncs
        for i, db_info in enumerate(databases):
            db_id = db_info.get('id', '')
            db_name = db_info.get('name', db_id)
            
            if progress_callback:
                progress_callback(i + 1, total, db_name)
            
            logger.info(f"Syncing database {i+1}/{total}: {db_name} ({db_id})")
            
            # Call CLI service directly to avoid individual commits
            env_name = self.configure_server_environment(server, team)
            result = self.cli_service.download_database(env_name, db_id)
            results[db_id] = result
            
            if result.success:
                logger.info(f"  Success in {result.duration_seconds:.1f}s")
            else:
                logger.error(f"  Failed: {result.error}")
        
        # Commit all changes at once
        success_count = sum(1 for r in results.values() if r.success)
        if success_count > 0:
            commit_message = f"Bulk sync: {success_count} database(s) from {server.name}/{team.name}"
            commit_changes(self.cli_service.project_path, commit_message)
        
        return results
    
    async def sync_all_databases_async(
        self,
        server: Server,
        team: Team,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, DownloadResult]:
        """Async version of sync_all_databases"""
        results = {}
        
        databases = await self.list_remote_databases_async(server, team)
        total = len(databases)
        
        # Temporarily disable auto-commit for individual syncs
        for i, db_info in enumerate(databases):
            db_id = db_info.get('id', '')
            db_name = db_info.get('name', db_id)
            
            if progress_callback:
                progress_callback(i + 1, total, db_name)
            
            logger.info(f"Syncing database {i+1}/{total}: {db_name} ({db_id})")
            
            # Call CLI service directly to avoid individual commits
            env_name = self.configure_server_environment(server, team)
            result = await self.cli_service.download_database_async(env_name, db_id)
            results[db_id] = result
            
            if result.success:
                logger.info(f"  Success in {result.duration_seconds:.1f}s")
            else:
                logger.error(f"  Failed: {result.error}")
        
        # Commit all changes at once
        success_count = sum(1 for r in results.values() if r.success)
        if success_count > 0:
            commit_message = f"Bulk sync: {success_count} database(s) from {server.name}/{team.name}"
            commit_changes(self.cli_service.project_path, commit_message)
        
        return results
    
    def get_local_databases(self) -> List[DatabaseInfo]:
        """Get list of locally downloaded databases"""
        return self.cli_service.get_downloaded_databases()


# Singleton instance
_sync_service: Optional[NinoxSyncService] = None


def get_ninox_sync_service() -> NinoxSyncService:
    """Get or create singleton sync service"""
    global _sync_service
    if _sync_service is None:
        _sync_service = NinoxSyncService()
    return _sync_service


# ============================================================================
# CLI Entry Points
# ============================================================================

def cli_sync_database(server_id: int, database_id: str) -> bool:
    """
    CLI entry point to sync a single database.
    
    This can be called from external tools like opencode or claude code.
    
    Args:
        server_id: Database server ID
        database_id: Ninox database ID
        
    Returns:
        True if sync was successful
    """
    db = get_db()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            logger.error(f"Server {server_id} not found")
            return False
        
        team = db.query(Team).filter(
            Team.server_id == server_id,
            Team.is_active == True
        ).first()
        if not team:
            logger.error(f"No active team found for server {server_id}")
            return False
        
        service = get_ninox_sync_service()
        result = service.sync_database(server, team, database_id)
        
        return result.success
    finally:
        db.close()


def cli_sync_all(server_id: int) -> Dict[str, bool]:
    """
    CLI entry point to sync all databases from a server.
    
    Args:
        server_id: Database server ID
        
    Returns:
        Dict mapping database_id to success status
    """
    db = get_db()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            logger.error(f"Server {server_id} not found")
            return {}
        
        team = db.query(Team).filter(
            Team.server_id == server_id,
            Team.is_active == True
        ).first()
        if not team:
            logger.error(f"No active team found for server {server_id}")
            return {}
        
        service = get_ninox_sync_service()
        results = service.sync_all_databases(server, team)
        
        return {db_id: result.success for db_id, result in results.items()}
    finally:
        db.close()


def cli_list_servers() -> List[Dict[str, Any]]:
    """
    CLI entry point to list available servers.
    
    Returns:
        List of server info dicts
    """
    db = get_db()
    try:
        servers = db.query(Server).filter(Server.is_active == True).all()
        return [
            {
                'id': s.id,
                'name': s.name,
                'url': s.url,
            }
            for s in servers
        ]
    finally:
        db.close()


def cli_list_local_databases() -> List[Dict[str, Any]]:
    """
    CLI entry point to list locally downloaded databases.
    
    Returns:
        List of database info dicts
    """
    service = get_ninox_sync_service()
    databases = service.get_local_databases()
    
    return [
        {
            'id': db.database_id,
            'name': db.name,
            'path': str(db.path),
            'table_count': db.table_count,
            'has_global_code': db.has_global_code,
            'download_date': db.download_date.isoformat(),
        }
        for db in databases
    ]


# ============================================================================
# Cronjob Integration
# ============================================================================

async def cronjob_sync_server(server_id: int) -> Dict[str, Any]:
    """
    Cronjob entry point to sync all databases from a server.
    
    This is called by the cronjob scheduler.
    
    Args:
        server_id: Database server ID
        
    Returns:
        Dict with sync results and statistics
    """
    start_time = datetime.now()
    
    db = get_db()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return {
                'success': False,
                'error': f"Server {server_id} not found",
                'databases_synced': 0
            }
        
        team = db.query(Team).filter(
            Team.server_id == server_id,
            Team.is_active == True
        ).first()
        if not team:
            return {
                'success': False,
                'error': f"No active team for server {server_id}",
                'databases_synced': 0
            }
        
        service = get_ninox_sync_service()
        results = await service.sync_all_databases_async(server, team)
        
        duration = (datetime.now() - start_time).total_seconds()
        success_count = sum(1 for r in results.values() if r.success)
        fail_count = len(results) - success_count
        
        return {
            'success': fail_count == 0,
            'server_name': server.name,
            'team_name': team.name,
            'databases_synced': success_count,
            'databases_failed': fail_count,
            'total_databases': len(results),
            'duration_seconds': duration,
            'results': {
                db_id: {
                    'success': r.success,
                    'error': r.error,
                    'duration': r.duration_seconds
                }
                for db_id, r in results.items()
            }
        }
    finally:
        db.close()


async def cronjob_sync_database(server_id: int, database_id: str) -> Dict[str, Any]:
    """
    Cronjob entry point to sync a specific database.
    
    Args:
        server_id: Database server ID
        database_id: Ninox database ID
        
    Returns:
        Dict with sync result
    """
    db = get_db()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            return {
                'success': False,
                'error': f"Server {server_id} not found"
            }
        
        team = db.query(Team).filter(
            Team.server_id == server_id,
            Team.is_active == True
        ).first()
        if not team:
            return {
                'success': False,
                'error': f"No active team for server {server_id}"
            }
        
        service = get_ninox_sync_service()
        result = await service.sync_database_async(server, team, database_id)
        
        return {
            'success': result.success,
            'database_id': database_id,
            'path': str(result.path) if result.path else None,
            'duration_seconds': result.duration_seconds,
            'error': result.error
        }
    finally:
        db.close()


def init_git_repo(repo_path: Path) -> bool:
    """
    Initialize git repository if not exists and configure it.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        True if successful
    """
    try:
        git_dir = repo_path / '.git'
        
        if not git_dir.exists():
            logger.info(f"Initializing git repository in {repo_path}")
            
            # Git init with main as default branch
            subprocess.run(['git', 'init', '-b', 'main'], cwd=str(repo_path), check=True, capture_output=True)

            # Configure git
            subprocess.run(
                ['git', 'config', 'user.name', 'Ninox2Git'],
                cwd=str(repo_path),
                check=True,
                capture_output=True
            )
            subprocess.run(
                ['git', 'config', 'user.email', 'ninox2git@automated.local'],
                cwd=str(repo_path),
                check=True,
                capture_output=True
            )
            
            # Create .gitignore
            gitignore_path = repo_path / '.gitignore'
            if not gitignore_path.exists():
                with open(gitignore_path, 'w') as f:
                    f.write("node_modules/\n")
                    f.write("package-lock.json\n")
                    f.write(".DS_Store\n")
            
            # Initial commit
            subprocess.run(['git', 'add', '.'], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(
                ['git', 'commit', '-m', 'Initial commit - Ninox YAML structure'],
                cwd=str(repo_path),
                check=True,
                capture_output=True
            )
            
            logger.info(f"Git repository initialized successfully in {repo_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize git repository: {e}")
        return False


def commit_changes(repo_path: Path, message: str) -> bool:
    """
    Commit all changes in the repository.
    
    Args:
        repo_path: Path to the repository
        message: Commit message
        
    Returns:
        True if successful
    """
    try:
        # Check if there are changes
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout.strip():
            logger.info("No changes to commit")
            return True
        
        # Add all changes
        subprocess.run(
            ['git', 'add', '.'],
            cwd=str(repo_path),
            check=True,
            capture_output=True
        )
        
        # Commit
        subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=str(repo_path),
            check=True,
            capture_output=True
        )
        
        logger.info(f"Changes committed: {message}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Git commit failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Error committing changes: {e}")
        return False


def get_git_log(repo_path: Path, database_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get Git commit history for a specific database.
    
    Args:
        repo_path: Path to the repository
        database_id: Database ID to filter commits
        limit: Maximum number of commits to return
        
    Returns:
        List of commit dictionaries with sha, date, message, author
    """
    try:
        # Get commits that affected this database
        # Filter by database directory: src/Objects/database_{db_id}/
        db_pattern = f"src/Objects/database_{database_id}/"
        
        # Git log format: %H = commit hash, %aI = author date (ISO), %s = subject, %an = author name
        result = subprocess.run(
            ['git', 'log', f'--max-count={limit}', '--format=%H|%aI|%s|%an', '--', db_pattern],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        
        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split('|', 3)
            if len(parts) == 4:
                sha, date_str, message, author = parts
                
                # Parse date
                try:
                    from datetime import datetime
                    commit_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    commit_date = None
                
                commits.append({
                    'sha': sha,
                    'date': commit_date,
                    'message': message,
                    'author': author
                })
        
        return commits
        
    except Exception as e:
        logger.error(f"Error getting git log: {e}")
        return []


def get_commit_diff(repo_path: Path, commit_sha: str, database_id: str) -> Dict[str, Any]:
    """
    Get diff for a specific commit filtered by database.
    
    Args:
        repo_path: Path to the repository
        commit_sha: Commit SHA
        database_id: Database ID to filter diff
        
    Returns:
        Dict with patch, files, and statistics
    """
    try:
        db_pattern = f"src/Objects/database_{database_id}/"
        
        # Get diff for this commit (compared to parent)
        result = subprocess.run(
            ['git', 'show', '--format=', commit_sha, '--', db_pattern],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        
        patch = result.stdout
        
        # Get stats
        stats_result = subprocess.run(
            ['git', 'show', '--stat', '--format=', commit_sha, '--', db_pattern],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse changed files
        changed_files = []
        for line in stats_result.stdout.strip().split('\n'):
            if '|' in line and ('+' in line or '-' in line):
                parts = line.split('|')
                if len(parts) >= 2:
                    file_path = parts[0].strip()
                    changed_files.append(file_path)
        
        return {
            'patch': patch,
            'files': changed_files,
            'file_count': len(changed_files)
        }
        
    except Exception as e:
        logger.error(f"Error getting commit diff: {e}")
        return {
            'patch': '',
            'files': [],
            'file_count': 0
        }


def get_changed_files(repo_path: Path) -> List[str]:
    """
    Get list of changed files (modified, added, deleted).
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        List of file paths relative to repo root
    """
    try:
        # Get status
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        
        changed_files = []
        for line in result.stdout.strip().split('\n'):
            if line:
                # Format: "XY filename" where XY is status code
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    changed_files.append(parts[1])
        
        return changed_files
        
    except Exception as e:
        logger.error(f"Error getting changed files: {e}")
        return []
