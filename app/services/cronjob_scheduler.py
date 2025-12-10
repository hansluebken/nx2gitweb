"""
Cronjob Scheduler Service
Automatically executes scheduled database sync jobs using BackgroundSyncManager
Also handles Ninox Documentation sync jobs
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from ..database import get_db
from ..models.cronjob import Cronjob, CronjobType, SyncType
from ..models.team import Team
from ..models.server import Server
from ..models.database import Database
from ..models.user import User
from ..auth import create_audit_log
from .background_sync import get_sync_manager

logger = logging.getLogger(__name__)


class CronjobScheduler:
    """Scheduler for automatic database synchronization"""

    def __init__(self):
        self.running = False
        self.check_interval = 30  # Check every 30 seconds

    async def start(self):
        """Start the scheduler"""
        self.running = True
        logger.info("🚀 Cronjob Scheduler started")

        while self.running:
            try:
                await self.check_and_run_jobs()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(self.check_interval)

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("🛑 Cronjob Scheduler stopped")

    async def check_and_run_jobs(self):
        """Check for jobs that need to run and execute them"""
        db = get_db()
        try:
            now = datetime.utcnow()

            # Find active jobs where next_run is in the past or now
            jobs = db.query(Cronjob).filter(
                Cronjob.is_active == True,
                Cronjob.next_run <= now
            ).all()

            if jobs:
                logger.info(f"Found {len(jobs)} jobs to run")

            for job in jobs:
                try:
                    logger.info(f"Executing cronjob: {job.name} (ID: {job.id})")
                    await self.execute_job(job)
                except Exception as e:
                    logger.error(f"Error executing job {job.name}: {e}")

        finally:
            db.close()

    async def execute_job(self, job: Cronjob, progress_callback=None):
        """
        Execute a single cronjob.
        Routes to appropriate handler based on sync_type.

        Args:
            job: The cronjob to execute
            progress_callback: Optional callback function(status, message) to report progress
        """
        db = get_db()
        try:
            # Update status to running
            job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
            job_obj.last_status = 'running'
            job_obj.last_run = datetime.utcnow()
            db.commit()
            
            # Get sync_type (default to DATABASE for old jobs)
            sync_type = getattr(job_obj, 'sync_type', None) or SyncType.DATABASE
        finally:
            db.close()

        # Route to appropriate handler
        if sync_type == SyncType.NINOX_DOCS:
            logger.info(f"  Executing docs sync cronjob: {job.name}")
            await self.execute_docs_sync(job, progress_callback)
        else:
            logger.info(f"  Executing database sync cronjob: {job.name} (Team ID: {job.team_id})")
            await self.execute_database_sync(job, progress_callback)

    async def execute_database_sync(self, job: Cronjob, progress_callback=None):
        """
        Execute a database sync cronjob using the BackgroundSyncManager.
        This mirrors the "Sync All" behavior from the sync UI.
        """

        try:
            # Get team, server and user info
            db = get_db()
            try:
                team = db.query(Team).filter(Team.id == job.team_id).first()
                if not team:
                    raise ValueError(f"Team {job.team_id} not found")
                    
                server = db.query(Server).filter(Server.id == team.server_id).first()
                if not server:
                    raise ValueError(f"Server for team {team.name} not found")

                # Get all non-excluded databases for this team
                databases = db.query(Database).filter(
                    Database.team_id == job.team_id,
                    Database.is_excluded == False
                ).all()

                # Get user (server owner) for GitHub credentials
                user = db.query(User).filter(User.id == server.user_id).first()
                if not user:
                    raise ValueError(f"User for server {server.name} not found")

                total_count = len(databases)
                logger.info(f"  Found {total_count} databases to sync")

                if total_count == 0:
                    logger.info(f"  No databases to sync (all excluded)")
                    # Update job status
                    job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                    job_obj.last_status = 'success'
                    job_obj.last_error = 'No databases to sync (all excluded)'
                    job_obj.run_count += 1
                    job_obj.next_run = self.calculate_next_run(job_obj)
                    db.commit()
                    return

                # Store database info for background sync
                db_infos = [(d.id, d.name) for d in databases]
                
            finally:
                db.close()

            # Get sync manager (same as used by "Sync All")
            sync_manager = get_sync_manager()

            # Check if bulk sync is already running for this team
            if sync_manager.is_bulk_sync_active(team.id):
                logger.warning(f"  Bulk sync already in progress for team {team.name}")
                db = get_db()
                job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                job_obj.last_status = 'skipped'
                job_obj.last_error = 'Bulk sync already in progress'
                job_obj.next_run = self.calculate_next_run(job_obj)
                db.commit()
                db.close()
                return

            # Start bulk sync mode (same as "Sync All")
            sync_manager.start_bulk_sync(team.id, total_count)

            if progress_callback:
                progress_callback('running', f'Starting bulk sync for {total_count} databases')

            # Start background syncs for all databases (same as "Sync All")
            started_count = 0
            skipped_count = 0

            # Reload models fresh for background sync
            db = get_db()
            try:
                user = db.query(User).filter(User.id == user.id).first()
                server = db.query(Server).filter(Server.id == server.id).first()
                team = db.query(Team).filter(Team.id == team.id).first()
                
                for db_id, db_name in db_infos:
                    database = db.query(Database).filter(Database.id == db_id).first()
                    if not database:
                        continue
                        
                    if sync_manager.is_syncing(database.id):
                        skipped_count += 1
                        logger.info(f"    Skipping {db_name} - already syncing")
                    else:
                        started = sync_manager.start_sync(user, server, team, database)
                        if started:
                            started_count += 1
                            logger.info(f"    Started background sync for {db_name}")
                            if progress_callback:
                                progress_callback('running', f'Started sync {started_count}/{total_count}: {db_name}')
                        else:
                            skipped_count += 1
            finally:
                db.close()

            logger.info(f"  Started {started_count} syncs, skipped {skipped_count}")

            # If no syncs started, end bulk sync mode
            if started_count == 0:
                sync_manager.end_bulk_sync()

            # Wait for all syncs to complete (poll bulk sync status)
            max_wait_seconds = 3600  # Max 1 hour
            poll_interval = 5  # Check every 5 seconds
            waited = 0

            while sync_manager.is_bulk_sync_active(team.id) and waited < max_wait_seconds:
                await asyncio.sleep(poll_interval)
                waited += poll_interval
                completed, total = sync_manager.get_bulk_sync_progress()
                logger.info(f"  Sync progress: {completed}/{total}")
                if progress_callback:
                    progress_callback('running', f'Syncing: {completed}/{total} completed')

            # Determine final status
            if waited >= max_wait_seconds:
                final_status = 'timeout'
                error_msg = f'Timeout after {max_wait_seconds}s - syncs may still be running'
            else:
                final_status = 'success'
                error_msg = None

            # Update job status
            db = get_db()
            try:
                job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                job_obj.last_status = final_status
                job_obj.last_error = error_msg
                job_obj.run_count += 1
                job_obj.next_run = self.calculate_next_run(job_obj)
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='cronjob_executed',
                    resource_type='cronjob',
                    resource_id=job.id,
                    details=f'Cronjob "{job.name}" executed: {started_count} databases synced',
                    auto_commit=True
                )
            finally:
                db.close()

            logger.info(f"  ✓ Cronjob completed: {started_count} syncs started")
            if progress_callback:
                progress_callback('completed', f'Completed: {started_count} databases synced')

        except Exception as e:
            logger.error(f"  ✗ Job execution failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Mark as error
            db = get_db()
            try:
                job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                job_obj.last_status = 'error'
                job_obj.last_error = str(e)[:1000]
                job_obj.run_count += 1
                job_obj.next_run = self.calculate_next_run(job_obj)
                db.commit()
            finally:
                db.close()
            
            if progress_callback:
                progress_callback('error', str(e))

    async def execute_docs_sync(self, job: Cronjob, progress_callback=None):
        """
        Execute a Ninox documentation sync cronjob.
        Downloads docs from forum.ninox.de and uploads to GitHub.
        """
        from .ninox_docs_service import NinoxDocsService
        from ..utils.encryption import get_encryption_manager
        
        try:
            # Get user for GitHub credentials
            db = get_db()
            try:
                user = db.query(User).filter(User.id == job.user_id).first()
                if not user:
                    raise ValueError(f"User {job.user_id} not found")
                
                if not user.github_token_encrypted or not user.github_organization:
                    raise ValueError("GitHub not configured for user")
                
                user_id = user.id
                github_token_encrypted = user.github_token_encrypted
                github_org = user.github_organization
            finally:
                db.close()

            if progress_callback:
                progress_callback('running', 'Downloading Ninox documentation...')

            # Create docs service and scrape
            service = NinoxDocsService()
            
            # Run scraping in thread pool (blocking operation)
            loop = asyncio.get_event_loop()
            
            def scrape_docs():
                return service.scrape_all_documentation(delay=0.5)
            
            all_docs = await loop.run_in_executor(None, scrape_docs)
            
            func_count = len(all_docs.get('functions', {}))
            api_count = len(all_docs.get('api', {}))
            print_count = len(all_docs.get('print', {}))
            
            logger.info(f"  Scraped {func_count} functions, {api_count} API docs, {print_count} print docs")

            if progress_callback:
                progress_callback('running', f'Scraped {func_count + api_count + print_count} docs, uploading to GitHub...')

            # Create markdown files
            functions_md = service.create_functions_markdown(all_docs.get('functions', {}))
            api_md = service.create_api_markdown(all_docs.get('api', {}))
            print_md = service.create_print_markdown(all_docs.get('print', {}))

            # Decrypt GitHub token
            encryption = get_encryption_manager()
            github_token = encryption.decrypt(github_token_encrypted)

            # Upload to GitHub in thread pool
            def upload_docs():
                return service.upload_separate_files_to_github(
                    functions_md,
                    api_md,
                    print_md,
                    github_token,
                    github_org,
                    "ninox-docs"
                )
            
            result = await loop.run_in_executor(None, upload_docs)

            if result.get('success'):
                final_status = 'success'
                error_msg = None
                logger.info(f"  ✓ Docs sync completed: {result.get('url')}")
            else:
                final_status = 'error'
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"  ✗ Docs sync failed: {error_msg}")

            # Update job status
            db = get_db()
            try:
                job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                job_obj.last_status = final_status
                job_obj.last_error = error_msg
                job_obj.run_count += 1
                job_obj.next_run = self.calculate_next_run(job_obj)
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user_id,
                    action='cronjob_docs_sync',
                    resource_type='cronjob',
                    resource_id=job.id,
                    details=f'Docs sync "{job.name}": {func_count} functions, {api_count} API, {print_count} print docs',
                    auto_commit=True
                )
            finally:
                db.close()

            if progress_callback:
                progress_callback('completed', f'Completed: {func_count + api_count + print_count} docs synced')

        except Exception as e:
            logger.error(f"  ✗ Docs sync failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Mark as error
            db = get_db()
            try:
                job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
                job_obj.last_status = 'error'
                job_obj.last_error = str(e)[:1000]
                job_obj.run_count += 1
                job_obj.next_run = self.calculate_next_run(job_obj)
                db.commit()
            finally:
                db.close()
            
            if progress_callback:
                progress_callback('error', str(e))

    def calculate_next_run(self, job: Cronjob) -> datetime:
        """Calculate next run time for a cronjob"""
        now = datetime.utcnow()

        if job.job_type == CronjobType.INTERVAL:
            interval_value = job.interval_value

            if job.interval_unit.value == 'minutes':
                return now + timedelta(minutes=interval_value)
            elif job.interval_unit.value == 'hours':
                return now + timedelta(hours=interval_value)
            elif job.interval_unit.value == 'days':
                return now + timedelta(days=interval_value)
            elif job.interval_unit.value == 'weeks':
                return now + timedelta(weeks=interval_value)

        elif job.job_type == CronjobType.DAILY_TIME:
            hour, minute = map(int, job.daily_time.split(':'))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # If time has passed today, schedule for tomorrow
            if next_run <= now:
                next_run += timedelta(days=1)

            return next_run

        # Default: 1 day
        return now + timedelta(days=1)


# Global scheduler instance
_scheduler = None


def get_scheduler() -> CronjobScheduler:
    """Get or create the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = CronjobScheduler()
    return _scheduler


async def start_scheduler():
    """Start the global scheduler"""
    scheduler = get_scheduler()
    await scheduler.start()


def stop_scheduler():
    """Stop the global scheduler"""
    scheduler = get_scheduler()
    scheduler.stop()
