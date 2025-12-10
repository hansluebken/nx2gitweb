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


@dataclass
class DocsSyncTask:
    """Represents a docs sync task"""
    job_id: int
    user_id: int
    started_at: datetime
    current: int = 0
    total: int = 0
    phase: str = "init"  # init, scraping, creating, uploading, done
    message: str = ""
    

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
        # Docs sync state
        self._docs_sync_task: Optional[DocsSyncTask] = None
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

            # Scan and save dependencies after successful sync
            try:
                logger.info(f"Scanning dependencies for {database_name}...")
                from ..ui.sync import save_database_dependencies
                from ..models.team import Team

                db = get_db()
                try:
                    team = db.query(Team).filter(Team.id == team_data['id']).first()
                    if team:
                        # Use database_data dict to get ninox_id
                        save_database_dependencies(team, database_data['database_id'])
                finally:
                    db.close()
            except Exception as dep_err:
                logger.warning(f"Could not scan dependencies for {database_name}: {dep_err}")

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
                    # Sync completed successfully - clear error and set to idle
                    db_obj.sync_status = SyncStatus.IDLE.value
                    db_obj.sync_error = None  # Clear any previous errors
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
        Async sync implementation using ninox_sync_service (team-specific paths).
        """
        from ..database import get_db
        from ..models.database import Database
        from ..models.server import Server
        from ..models.team import Team
        from ..models.user import User
        from .ninox_sync_service import get_ninox_sync_service

        database_id = database_data['id']
        database_ninox_id = database_data['database_id']
        database_name = database_data['name']

        # Check loop protection
        if database_ninox_id in already_syncing:
            logger.info(f"Skipping {database_name} - already syncing (loop protection)")
            return

        already_syncing.add(database_ninox_id)

        logger.info(f"Background sync starting for {database_name} using ninox_sync_service")

        # Reload models from database for this thread
        db = get_db()
        try:
            user = db.query(User).filter(User.id == user_data['id']).first()
            server = db.query(Server).filter(Server.id == server_data['id']).first()
            team = db.query(Team).filter(Team.id == team_data['id']).first()
            database = db.query(Database).filter(Database.id == database_id).first()

            if not all([user, server, team, database]):
                raise ValueError("Could not load required models")
        finally:
            db.close()

        # Use ninox_sync_service which already handles team-specific paths
        sync_service = get_ninox_sync_service()

        # Don't pass generate_erd/generate_docs - let the service read from database settings
        result = await sync_service.sync_database_async(
            server,
            team,
            database_ninox_id,
            user=user
        )

        if not result.success:
            raise Exception(result.error)

        logger.info(f"✓ Background sync completed for {database_name} using ninox_sync_service")

        # Rest of the function is replaced by simplified logic
        return
    def is_docs_sync_active(self) -> bool:
        """Check if a docs sync is currently running"""
        with self._sync_lock:
            return self._docs_sync_task is not None
    
    def get_docs_sync_progress(self) -> Optional[DocsSyncTask]:
        """Get current docs sync progress"""
        with self._sync_lock:
            return self._docs_sync_task
    
    def start_docs_sync(self, user_id: int, job_id: int) -> bool:
        """
        Start a background docs sync.
        Returns True if started, False if already running.
        """
        with self._sync_lock:
            if self._docs_sync_task is not None:
                logger.info("Docs sync already running")
                return False
            
            self._docs_sync_task = DocsSyncTask(
                job_id=job_id,
                user_id=user_id,
                started_at=datetime.utcnow(),
                phase="init",
                message="Starting..."
            )
        
        # Submit to thread pool
        self._executor.submit(self._run_docs_sync, user_id, job_id)
        logger.info(f"Started background docs sync for job {job_id}")
        return True
    
    def _run_docs_sync(self, user_id: int, job_id: int):
        """Run docs sync in background thread"""
        from ..database import get_db
        from ..models.user import User
        from ..models.cronjob import Cronjob
        from .ninox_docs_service import NinoxDocsService
        from ..utils.encryption import get_encryption_manager
        from ..auth import create_audit_log
        
        try:
            # Get user credentials
            db = get_db()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user or not user.github_token_encrypted:
                    raise ValueError("GitHub not configured")
                
                github_token_encrypted = user.github_token_encrypted
                github_org = user.github_organization
            finally:
                db.close()
            
            service = NinoxDocsService()
            
            # Progress callback
            def on_progress(progress):
                with self._sync_lock:
                    if self._docs_sync_task:
                        self._docs_sync_task.phase = "scraping"
                        self._docs_sync_task.current = progress.current
                        self._docs_sync_task.total = progress.total
                        self._docs_sync_task.message = f"Downloading: {progress.current_function}"
            
            # Phase 1: Scrape
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.phase = "scraping"
                    self._docs_sync_task.message = "Downloading documentation..."
            
            all_docs = service.scrape_all_documentation(
                progress_callback=on_progress,
                delay=0.3
            )
            
            func_count = len(all_docs.get('functions', {}))
            api_count = len(all_docs.get('api', {}))
            print_count = len(all_docs.get('print', {}))
            total_docs = func_count + api_count + print_count
            
            logger.info(f"Docs sync: scraped {total_docs} docs")
            
            # Phase 2: Create Markdown
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.phase = "creating"
                    self._docs_sync_task.current = 0
                    self._docs_sync_task.total = 3
                    self._docs_sync_task.message = "Creating Markdown files..."
            
            functions_md = service.create_functions_markdown(all_docs.get('functions', {}))
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.current = 1
            
            api_md = service.create_api_markdown(all_docs.get('api', {}))
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.current = 2
            
            print_md = service.create_print_markdown(all_docs.get('print', {}))
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.current = 3
            
            # Phase 3: Upload
            with self._sync_lock:
                if self._docs_sync_task:
                    self._docs_sync_task.phase = "uploading"
                    self._docs_sync_task.message = "Uploading to GitHub..."
            
            encryption = get_encryption_manager()
            github_token = encryption.decrypt(github_token_encrypted)
            
            result = service.upload_separate_files_to_github(
                functions_md,
                api_md,
                print_md,
                github_token,
                github_org,
                "ninox-docs"
            )
            
            # Update job status
            db = get_db()
            try:
                job = db.query(Cronjob).filter(Cronjob.id == job_id).first()
                if job:
                    job.last_run = datetime.utcnow()
                    if result.get('success'):
                        job.last_status = 'success'
                        job.last_error = None
                        logger.info(f"Docs sync completed: {result.get('url')}")
                    else:
                        job.last_status = 'error'
                        job.last_error = result.get('error', 'Unknown error')
                        logger.error(f"Docs sync failed: {result.get('error')}")
                    db.commit()
                
                # Audit log
                create_audit_log(
                    db=db,
                    user_id=user_id,
                    action='docs_sync_completed',
                    resource_type='cronjob',
                    resource_id=job_id,
                    details=f'Docs sync: {func_count} functions, {api_count} API, {print_count} print',
                    auto_commit=True
                )
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"Docs sync failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Update job status
            db = get_db()
            try:
                job = db.query(Cronjob).filter(Cronjob.id == job_id).first()
                if job:
                    job.last_run = datetime.utcnow()
                    job.last_status = 'error'
                    job.last_error = str(e)[:1000]
                    db.commit()
            finally:
                db.close()
        
        finally:
            # Clear docs sync task
            with self._sync_lock:
                self._docs_sync_task = None
            logger.info("Docs sync task cleared")


# Global instance
_sync_manager: Optional[BackgroundSyncManager] = None


def get_sync_manager() -> BackgroundSyncManager:
    """Get or create the global sync manager"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = BackgroundSyncManager()
    return _sync_manager
