"""
Background Sync Manager
Handles database syncs in a server-side thread pool, independent of browser connections.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncTask:
    """Represents a sync task"""
    database_id: int
    user_id: int
    server_id: int
    team_id: int
    started_at: datetime
    

class BackgroundSyncManager:
    """
    Manages background sync operations that continue even if the user leaves the page.
    Uses a thread pool to run syncs independently of the NiceGUI event loop.
    """
    
    _instance: Optional["BackgroundSyncManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        # Reduce max_workers to 2 to minimize SHA conflicts during parallel syncs
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sync_")
        self._active_syncs: Dict[int, SyncTask] = {}  # database_id -> SyncTask
        self._sync_lock = threading.Lock()
        self._bulk_sync_active: bool = False
        self._bulk_sync_team_id: Optional[int] = None
        self._bulk_sync_total: int = 0
        self._bulk_sync_completed: int = 0
        logger.info("BackgroundSyncManager initialized")
    
    def is_syncing(self, database_id: int) -> bool:
        """Check if a database is currently being synced"""
        with self._sync_lock:
            return database_id in self._active_syncs
    
    def is_bulk_sync_active(self, team_id: Optional[int] = None) -> bool:
        """Check if a bulk sync is currently active, optionally for a specific team"""
        with self._sync_lock:
            if team_id is not None:
                return self._bulk_sync_active and self._bulk_sync_team_id == team_id
            return self._bulk_sync_active
    
    def get_bulk_sync_progress(self) -> tuple:
        """Get bulk sync progress (completed, total)"""
        with self._sync_lock:
            return (self._bulk_sync_completed, self._bulk_sync_total)
    
    def start_bulk_sync(self, team_id: int, total_count: int):
        """Mark the start of a bulk sync operation"""
        with self._sync_lock:
            self._bulk_sync_active = True
            self._bulk_sync_team_id = team_id
            self._bulk_sync_total = total_count
            self._bulk_sync_completed = 0
        logger.info(f"Bulk sync started for team {team_id} with {total_count} databases")
    
    def end_bulk_sync(self):
        """Mark the end of a bulk sync operation"""
        with self._sync_lock:
            self._bulk_sync_active = False
            self._bulk_sync_team_id = None
            self._bulk_sync_total = 0
            self._bulk_sync_completed = 0
        logger.info("Bulk sync ended")
    
    def increment_bulk_sync_progress(self):
        """Increment bulk sync completed count"""
        with self._sync_lock:
            self._bulk_sync_completed += 1
            completed = self._bulk_sync_completed
            total = self._bulk_sync_total
            # Auto-end bulk sync when all done
            if completed >= total and total > 0:
                self._bulk_sync_active = False
                self._bulk_sync_team_id = None
                logger.info(f"Bulk sync auto-completed: {completed}/{total}")
    
    def get_active_syncs(self) -> Dict[int, SyncTask]:
        """Get all active sync tasks"""
        with self._sync_lock:
            return dict(self._active_syncs)
    
    def start_sync(
        self,
        user,
        server,
        team,
        database,
        already_syncing: Optional[Set[str]] = None
    ) -> bool:
        """
        Start a background sync for a database.
        Returns True if sync was started, False if already syncing.
        """
        from ..database import get_db
        from ..models.database import Database, SyncStatus
        
        # Check if already syncing
        with self._sync_lock:
            if database.id in self._active_syncs:
                logger.info(f"Database {database.name} is already syncing")
                return False
            
            # Register sync task
            task = SyncTask(
                database_id=database.id,
                user_id=user.id,
                server_id=server.id,
                team_id=team.id,
                started_at=datetime.utcnow()
            )
            self._active_syncs[database.id] = task
        
        # Update database status
        db = get_db()
        try:
            db_obj = db.query(Database).filter(Database.id == database.id).first()
            if db_obj:
                db_obj.sync_status = SyncStatus.SYNCING.value
                db_obj.sync_started_at = datetime.utcnow()
                db_obj.sync_error = None
                db.commit()
        finally:
            db.close()
        
        # Submit to thread pool
        self._executor.submit(
            self._run_sync,
            user.id,
            server.id,
            team.id,
            database.id,
            already_syncing or set()
        )
        
        logger.info(f"Started background sync for {database.name}")
        return True
    
    def _run_sync(
        self,
        user_id: int,
        server_id: int,
        team_id: int,
        database_id: int,
        already_syncing: Set[str]
    ):
        """
        Run sync in background thread.
        Creates its own event loop for async operations.
        """
        from ..database import get_db
        from ..models.database import Database, SyncStatus
        from ..models.user import User
        from ..models.server import Server
        from ..models.team import Team
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        database_name = None
        
        try:
            # Load models fresh in this thread
            db = get_db()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                server = db.query(Server).filter(Server.id == server_id).first()
                team = db.query(Team).filter(Team.id == team_id).first()
                database = db.query(Database).filter(Database.id == database_id).first()
                
                if not all([user, server, team, database]):
                    raise ValueError("Could not load required models")
                
                database_name = database.name
                
                # Copy needed attributes (detach from session)
                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'github_token_encrypted': user.github_token_encrypted,
                    'github_organization': user.github_organization,
                }
                server_data = {
                    'id': server.id,
                    'name': server.name,
                    'url': server.url,
                    'api_key_encrypted': server.api_key_encrypted,
                    'github_repo_name': server.github_repo_name,
                }
                team_data = {
                    'id': team.id,
                    'name': team.name,
                    'team_id': team.team_id,
                }
                database_data = {
                    'id': database.id,
                    'name': database.name,
                    'database_id': database.database_id,
                    'github_path': database.github_path,
                }
            finally:
                db.close()
            
            # Run the actual sync
            loop.run_until_complete(
                self._async_sync(
                    user_data,
                    server_data,
                    team_data,
                    database_data,
                    already_syncing
                )
            )
            
            logger.info(f"Background sync completed for {database_name} (ID {database_id})")
            
        except Exception as e:
            logger.error(f"Background sync failed for database ID {database_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Update status to error
            db = get_db()
            try:
                db_obj = db.query(Database).filter(Database.id == database_id).first()
                if db_obj:
                    db_obj.sync_status = SyncStatus.ERROR.value
                    db_obj.sync_error = str(e)[:1000]
                    db.commit()
            finally:
                db.close()
        
        finally:
            # Always update status to idle/success when done
            db = get_db()
            try:
                db_obj = db.query(Database).filter(Database.id == database_id).first()
                if db_obj and db_obj.sync_status == SyncStatus.SYNCING.value:
                    # Only set to idle if still syncing (not error)
                    db_obj.sync_status = SyncStatus.IDLE.value
                    db_obj.last_modified = datetime.utcnow()
                    db.commit()
                    logger.info(f"Reset sync status to idle for {database_name or database_id}")
            except Exception as e:
                logger.error(f"Failed to reset sync status: {e}")
            finally:
                db.close()
            
            # Remove from active syncs and update bulk progress
            with self._sync_lock:
                self._active_syncs.pop(database_id, None)
                
                # Update bulk sync progress if active
                if self._bulk_sync_active:
                    self._bulk_sync_completed += 1
                    if self._bulk_sync_completed >= self._bulk_sync_total and self._bulk_sync_total > 0:
                        self._bulk_sync_active = False
                        self._bulk_sync_team_id = None
                        logger.info(f"Bulk sync auto-completed: {self._bulk_sync_completed}/{self._bulk_sync_total}")
            
            loop.close()
    
    async def _async_sync(
        self,
        user_data: dict,
        server_data: dict,
        team_data: dict,
        database_data: dict,
        already_syncing: Set[str]
    ):
        """
        Async sync implementation - mirrors sync.py logic but uses data dicts.
        """
        from ..database import get_db
        from ..models.database import Database, SyncStatus
        from ..utils.encryption import get_encryption_manager
        from ..utils.github_utils import sanitize_name, get_repo_name_from_server
        from ..utils.svg_erd_generator import generate_svg_erd
        from ..utils.ninox_code_extractor import extract_and_generate as extract_ninox_code
        from ..utils.ninox_md_generator import generate_markdown_from_backup
        from ..api.ninox_client import NinoxClient
        from ..api.github_manager import GitHubManager
        from ..auth import create_audit_log
        import json
        import os
        
        database_id = database_data['id']
        database_ninox_id = database_data['database_id']
        database_name = database_data['name']
        
        # Check loop protection
        if database_ninox_id in already_syncing:
            logger.info(f"Skipping {database_name} - already syncing (loop protection)")
            return
        
        already_syncing.add(database_ninox_id)
        
        logger.info(f"Background sync starting for {database_name}")
        
        # Decrypt credentials
        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server_data['api_key_encrypted'])
        
        # Connect to Ninox
        client = NinoxClient(server_data['url'], api_key)
        
        # Fetch database structure
        loop = asyncio.get_event_loop()
        db_structure = await loop.run_in_executor(
            None,
            client.get_database_structure,
            team_data['team_id'],
            database_ninox_id
        )
        
        # Check for linked databases and sync them first
        # SKIP cascade syncs during bulk sync - all DBs are synced anyway
        # Full cascade is enabled - loop protection via already_syncing set
        known_dbs = db_structure.get('schema', {}).get('knownDatabases', [])
        
        if known_dbs and not self._bulk_sync_active:
            logger.info(f"Found {len(known_dbs)} linked databases for {database_name}")
            
            db = get_db()
            try:
                team_databases = db.query(Database).filter(
                    Database.team_id == team_data['id']
                ).all()
                db_by_ninox_id = {d.database_id: d for d in team_databases}
            finally:
                db.close()
            
            for ext_db_info in known_dbs:
                ext_db_id = ext_db_info.get('dbId')
                ext_db_name = ext_db_info.get('name', ext_db_id)
                
                if ext_db_id and ext_db_id not in already_syncing:
                    linked_db = db_by_ninox_id.get(ext_db_id)
                    if linked_db:
                        logger.info(f"Cascade syncing linked DB: {ext_db_name}")
                        try:
                            # Set sync_status for cascade DB
                            db_session = get_db()
                            try:
                                cascade_db = db_session.query(Database).filter(Database.id == linked_db.id).first()
                                if cascade_db:
                                    cascade_db.sync_status = SyncStatus.SYNCING.value
                                    cascade_db.sync_started_at = datetime.utcnow()
                                    db_session.commit()
                            finally:
                                db_session.close()
                            
                            linked_db_data = {
                                'id': linked_db.id,
                                'name': linked_db.name,
                                'database_id': linked_db.database_id,
                                'github_path': linked_db.github_path,
                            }
                            await self._async_sync(
                                user_data,
                                server_data,
                                team_data,
                                linked_db_data,
                                already_syncing
                            )
                            
                            # Reset sync_status after cascade sync
                            db_session = get_db()
                            try:
                                cascade_db = db_session.query(Database).filter(Database.id == linked_db.id).first()
                                if cascade_db:
                                    cascade_db.sync_status = SyncStatus.IDLE.value
                                    cascade_db.last_modified = datetime.utcnow()
                                    db_session.commit()
                            finally:
                                db_session.close()
                                
                        except Exception as link_err:
                            logger.warning(f"Could not cascade sync {ext_db_name}: {link_err}")
                            # Reset status on error
                            try:
                                db_session = get_db()
                                cascade_db = db_session.query(Database).filter(Database.id == linked_db.id).first()
                                if cascade_db:
                                    cascade_db.sync_status = SyncStatus.IDLE.value
                                    db_session.commit()
                                db_session.close()
                            except:
                                pass
        elif known_dbs and self._bulk_sync_active:
            logger.info(f"Skipping cascade sync for {database_name} - bulk sync active")
        
        # Fetch views and reports
        views_data = []
        reports_data = []
        report_files_data = {}
        
        try:
            views_data = await loop.run_in_executor(
                None, client.get_views, team_data['team_id'], database_ninox_id, True
            )
            logger.info(f"Fetched {len(views_data)} views")
        except Exception as e:
            logger.warning(f"Could not fetch views: {e}")
        
        try:
            reports_data = await loop.run_in_executor(
                None, client.get_reports, team_data['team_id'], database_ninox_id, True
            )
            logger.info(f"Fetched {len(reports_data)} reports")
        except Exception as e:
            logger.warning(f"Could not fetch reports: {e}")
        
        # Check if GitHub is configured
        if not user_data['github_token_encrypted'] or not user_data['github_organization']:
            logger.warning(f"GitHub not configured for {database_name}")
            return
        
        github_token = encryption.decrypt(user_data['github_token_encrypted'])
        
        # Get repo name using the helper function
        # Create a mock server object for get_repo_name_from_server
        class MockServer:
            def __init__(self, url, github_repo_name=None):
                self.url = url
                self.github_repo_name = github_repo_name
        
        mock_server = MockServer(server_data['url'], server_data.get('github_repo_name'))
        repo_name = get_repo_name_from_server(mock_server)
        
        github_mgr = GitHubManager(
            access_token=github_token,
            organization=user_data['github_organization']
        )
        
        # Ensure repository exists
        repo = github_mgr.ensure_repository(
            repo_name=repo_name,
            description=f"Ninox database backups from {server_data['name']} ({server_data['url']})"
        )
        
        # Create paths - new structure:
        # - team-name/db-name.md (MD directly visible under team)
        # - team-name/db-name/structure.json (details in subfolder)
        team_name = sanitize_name(team_data['name'])
        db_name = sanitize_name(database_name)
        server_name = sanitize_name(server_data['name'])
        github_path = f'{team_name}/{db_name}'  # Subfolder for details
        
        # Create complete backup
        complete_backup = {
            'schema': db_structure,
            'views': views_data,
            'reports': reports_data,
            'report_files': report_files_data,
            '_metadata': {
                'synced_at': datetime.utcnow().isoformat(),
                'database_name': database_name,
                'database_id': database_ninox_id,
                'team_name': team_data['name'],
                'team_id': team_data['team_id'],
                'server_name': server_data['name'],
            }
        }
        
        structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)
        backup_json = json.dumps(complete_backup, indent=2, ensure_ascii=False)
        
        # Upload structure (into subfolder)
        full_path = f'{github_path}/structure.json'
        await loop.run_in_executor(
            None,
            github_mgr.update_file,
            repo,
            full_path,
            structure_json,
            f'Update {database_name} structure from {team_data["name"]}'
        )
        
        # Upload complete backup (into subfolder)
        backup_path = f'{github_path}/complete-backup.json'
        await loop.run_in_executor(
            None,
            github_mgr.update_file,
            repo,
            backup_path,
            backup_json,
            f'Update {database_name} complete backup'
        )
        
        # Save locally
        local_base_path = f'/app/data/code/{server_name}/{team_name}/{db_name}'
        os.makedirs(local_base_path, exist_ok=True)
        
        with open(f'{local_base_path}/structure.json', 'w', encoding='utf-8') as f:
            json.dump(db_structure, f, indent=2, ensure_ascii=False)
        
        with open(f'{local_base_path}/complete-backup.json', 'w', encoding='utf-8') as f:
            json.dump(complete_backup, f, indent=2, ensure_ascii=False)
        
        # Load external DB structures for MD generation
        external_db_structures = {}
        if known_dbs:
            db = get_db()
            try:
                team_databases = db.query(Database).filter(
                    Database.team_id == team_data['id']
                ).all()
                db_by_ninox_id = {d.database_id: d for d in team_databases}
            finally:
                db.close()
            
            for ext_db in known_dbs:
                ext_db_id = ext_db.get('dbId')
                if ext_db_id:
                    linked_db = db_by_ninox_id.get(ext_db_id)
                    if linked_db:
                        ext_db_name_safe = sanitize_name(linked_db.name)
                        ext_local_path = f'/app/data/code/{server_name}/{team_name}/{ext_db_name_safe}/complete-backup.json'
                        if os.path.exists(ext_local_path):
                            try:
                                with open(ext_local_path, 'r', encoding='utf-8') as f:
                                    external_db_structures[ext_db_id] = json.load(f)
                            except Exception:
                                pass
        
        # Generate and upload Markdown (directly under team folder, not in subfolder)
        try:
            md_content = generate_markdown_from_backup(complete_backup, database_name, external_db_structures)
            if md_content:
                md_path = f'{team_name}/{db_name}.md'  # MD directly visible under team
                await loop.run_in_executor(
                    None,
                    github_mgr.update_file,
                    repo,
                    md_path,
                    md_content,
                    f'Update {database_name} Markdown documentation'
                )
                
                with open(f'{local_base_path}/complete-backup.md', 'w', encoding='utf-8') as f:
                    f.write(md_content)
        except Exception as e:
            logger.warning(f"Failed to generate Markdown: {e}")
        
        # Generate and upload SVG ERD (into subfolder)
        try:
            svg_content = generate_svg_erd(db_structure)
            if svg_content:
                erd_path = f'{github_path}/erd.svg'
                await loop.run_in_executor(
                    None,
                    github_mgr.update_file,
                    repo,
                    erd_path,
                    svg_content,
                    f'Update {database_name} ERD diagram'
                )
        except Exception as e:
            logger.warning(f"Failed to generate ERD: {e}")
        
        # Extract and save code files
        try:
            code_files = extract_ninox_code(db_structure, database_name)
            if code_files:
                for file_path, file_content in code_files.items():
                    full_local_path = f'{local_base_path}/{file_path}'
                    os.makedirs(os.path.dirname(full_local_path), exist_ok=True)
                    with open(full_local_path, 'w', encoding='utf-8') as f:
                        f.write(file_content)
        except Exception as e:
            logger.warning(f"Failed to extract code: {e}")
        
        # Update database record
        db = get_db()
        try:
            db_obj = db.query(Database).filter(Database.id == database_id).first()
            if db_obj:
                db_obj.github_path = github_path
                db_obj.last_modified = datetime.utcnow()
                db.commit()
            
            # Create audit log
            create_audit_log(
                db=db,
                user_id=user_data['id'],
                action='database_synced',
                resource_type='database',
                resource_id=database_id,
                details=f'Background sync: {database_name}',
                auto_commit=True
            )
        finally:
            db.close()
        
        logger.info(f"Background sync completed for {database_name}")


# Global instance
_sync_manager: Optional[BackgroundSyncManager] = None


def get_sync_manager() -> BackgroundSyncManager:
    """Get or create the global sync manager"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = BackgroundSyncManager()
    return _sync_manager
