"""
Cronjob Scheduler Service
Automatically executes scheduled database sync jobs
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from ..database import get_db
from ..models.cronjob import Cronjob, CronjobType
from ..models.team import Team
from ..models.server import Server
from ..models.database import Database
from ..utils.encryption import get_encryption_manager
from ..utils.github_utils import sanitize_name, get_repo_name_from_server
from ..utils.svg_erd_generator import generate_svg_erd
from ..utils.ninox_md_generator import generate_markdown_from_backup
from ..api.ninox_client import NinoxClient
from ..api.github_manager import GitHubManager
from ..auth import create_audit_log
import json
import os

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
        """Execute a single cronjob

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
            db.close()

            logger.info(f"  Team ID: {job.team_id}")

            # Get team and server info
            db = get_db()
            team = db.query(Team).filter(Team.id == job.team_id).first()
            server = db.query(Server).filter(Server.id == team.server_id).first()

            # Get all non-excluded databases for this team
            databases = db.query(Database).filter(
                Database.team_id == job.team_id,
                Database.is_excluded == False
            ).all()

            logger.info(f"  Found {len(databases)} databases to sync")

            # Get user (server owner) for GitHub credentials
            from ..models.user import User
            user = db.query(User).filter(User.id == server.user_id).first()

            db.close()

            # Sync each database
            success_count = 0
            error_count = 0
            total = len(databases)

            for idx, database in enumerate(databases, 1):
                try:
                    logger.info(f"    Syncing: {database.name}")
                    if progress_callback:
                        progress_callback('running', f'Syncing database {idx}/{total}: {database.name}')

                    await self.sync_database(user, server, team, database)
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"    Error syncing {database.name}: {e}")

            # Update job status
            db = get_db()
            job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()

            if error_count > 0:
                job_obj.last_status = 'partial'
                job_obj.last_error = f'{success_count} success, {error_count} errors'
            else:
                job_obj.last_status = 'success'
                job_obj.last_error = None

            job_obj.run_count += 1

            # Calculate next run
            job_obj.next_run = self.calculate_next_run(job_obj)

            db.commit()

            # Create audit log
            create_audit_log(
                db=db,
                user_id=user.id,
                action='cronjob_executed',
                resource_type='cronjob',
                resource_id=job.id,
                details=f'Cronjob "{job.name}" executed: {success_count} success, {error_count} errors',
                auto_commit=True
            )

            db.close()

            logger.info(f"  ✓ Cronjob completed: {success_count} success, {error_count} errors")
            logger.info(f"  Next run: {job_obj.next_run}")

        except Exception as e:
            logger.error(f"  ✗ Job execution failed: {e}")

            # Mark as error
            db = get_db()
            job_obj = db.query(Cronjob).filter(Cronjob.id == job.id).first()
            job_obj.last_status = 'error'
            job_obj.last_error = str(e)[:1000]
            job_obj.next_run = self.calculate_next_run(job_obj)
            db.commit()
            db.close()

    async def sync_database(self, user, server, team, database, already_syncing=None):
        """
        Sync a single database to GitHub with cascade sync for linked databases.
        
        Args:
            user: User model with GitHub credentials
            server: Server model
            team: Team model
            database: Database model to sync
            already_syncing: Set of database_ids being synced (loop protection)
        """
        # Initialize loop protection set
        if already_syncing is None:
            already_syncing = set()
        
        # Check if already syncing (loop protection)
        if database.database_id in already_syncing:
            logger.info(f"    Skipping {database.name} - already syncing (loop protection)")
            return
        
        # Add to syncing set
        already_syncing.add(database.database_id)
        
        # Run the synchronous operations in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        def sync_operation():
            """Synchronous operation to sync database"""
            # Decrypt API key
            encryption = get_encryption_manager()
            api_key = encryption.decrypt(server.api_key_encrypted)

            # Create Ninox client
            client = NinoxClient(server.url, api_key)

            # Fetch database structure
            db_structure = client.get_database_structure(team.team_id, database.database_id)
            
            # Return structure for cascade sync check
            return db_structure, client, encryption, api_key
        
        # Get structure first
        db_structure, client, encryption, api_key = await loop.run_in_executor(None, sync_operation)
        
        # Check for linked databases and sync them first (cascade sync)
        known_dbs = db_structure.get('schema', {}).get('knownDatabases', [])
        if known_dbs:
            logger.info(f"    Found {len(known_dbs)} linked databases")
            
            # Get all databases in this team
            db_session = get_db()
            try:
                team_databases = db_session.query(Database).filter(
                    Database.team_id == team.id
                ).all()
                db_by_ninox_id = {db.database_id: db for db in team_databases}
            finally:
                db_session.close()
            
            for ext_db_info in known_dbs:
                ext_db_id = ext_db_info.get('dbId')
                ext_db_name = ext_db_info.get('name', ext_db_id)
                
                if ext_db_id and ext_db_id not in already_syncing:
                    linked_db = db_by_ninox_id.get(ext_db_id)
                    if linked_db:
                        logger.info(f"    Cascade syncing linked DB: {ext_db_name}")
                        try:
                            await self.sync_database(user, server, team, linked_db, already_syncing)
                        except Exception as link_err:
                            logger.warning(f"    Could not cascade sync {ext_db_name}: {link_err}")
        
        # Now continue with main sync
        def complete_sync():
            """Complete the sync operation with all components"""
            # Check if GitHub is configured
            if not user.github_token_encrypted or not user.github_organization:
                logger.warning(f"    GitHub not configured for user {user.username}")
                return

            # Decrypt GitHub token
            github_token = encryption.decrypt(user.github_token_encrypted)

            # Use helper function to get repo name from server
            repo_name = get_repo_name_from_server(server)

            # Create GitHub manager
            github_mgr = GitHubManager(
                access_token=github_token,
                organization=user.github_organization
            )

            # Ensure repository exists
            repo = github_mgr.ensure_repository(
                repo_name=repo_name,
                description=f'Ninox database backups from {server.name} ({server.url})'
            )

            # Create path: team/dbname-structure.json
            team_name = sanitize_name(team.name)
            db_name = sanitize_name(database.name)
            server_name = sanitize_name(server.name)
            github_path = team_name
            full_path = f'{github_path}/{db_name}-structure.json'
            
            # Fetch views and reports
            views_data = []
            reports_data = []
            try:
                views_data = client.get_views(team.team_id, database.database_id, full_view=True)
                logger.info(f"    Fetched {len(views_data)} views")
            except Exception as e:
                logger.warning(f"    Could not fetch views: {e}")
            
            try:
                reports_data = client.get_reports(team.team_id, database.database_id, full_report=True)
                logger.info(f"    Fetched {len(reports_data)} reports")
            except Exception as e:
                logger.warning(f"    Could not fetch reports: {e}")
            
            # Create complete backup structure
            complete_backup = {
                'schema': db_structure,
                'views': views_data,
                'reports': reports_data,
                'report_files': {},
                '_metadata': {
                    'synced_at': datetime.utcnow().isoformat(),
                    'database_name': database.name,
                    'database_id': database.database_id,
                    'team_name': team.name,
                    'team_id': team.team_id,
                    'server_name': server.name,
                }
            }

            # Convert to JSON
            structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)
            backup_json = json.dumps(complete_backup, indent=2, ensure_ascii=False)

            # Upload structure to GitHub
            github_mgr.update_file(
                repo=repo,
                file_path=full_path,
                content=structure_json,
                commit_message=f'[Automated] Update {database.name} structure from {team.name}'
            )
            
            # Upload complete backup
            backup_path = f'{github_path}/{db_name}-complete-backup.json'
            github_mgr.update_file(
                repo=repo,
                file_path=backup_path,
                content=backup_json,
                commit_message=f'[Automated] Update {database.name} complete backup'
            )
            
            # Save locally for MD generation
            local_base_path = f'/app/data/code/{server_name}/{team_name}/{db_name}'
            os.makedirs(local_base_path, exist_ok=True)
            
            with open(f'{local_base_path}/structure.json', 'w', encoding='utf-8') as f:
                json.dump(db_structure, f, indent=2, ensure_ascii=False)
            
            with open(f'{local_base_path}/complete-backup.json', 'w', encoding='utf-8') as f:
                json.dump(complete_backup, f, indent=2, ensure_ascii=False)
            
            # Load external DB structures from local files for MD generation
            external_db_structures = {}
            if known_dbs:
                db_session = get_db()
                try:
                    team_databases = db_session.query(Database).filter(
                        Database.team_id == team.id
                    ).all()
                    db_by_ninox_id = {db.database_id: db for db in team_databases}
                finally:
                    db_session.close()
                
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
            
            # Generate and upload Markdown documentation
            try:
                md_content = generate_markdown_from_backup(complete_backup, database.name, external_db_structures)
                if md_content:
                    md_path = f'{github_path}/{db_name}-complete-backup.md'
                    github_mgr.update_file(
                        repo=repo,
                        file_path=md_path,
                        content=md_content,
                        commit_message=f'[Automated] Update {database.name} Markdown documentation'
                    )
                    logger.info(f"    ✓ Uploaded Markdown: {md_path}")
                    
                    # Save locally
                    with open(f'{local_base_path}/complete-backup.md', 'w', encoding='utf-8') as f:
                        f.write(md_content)
            except Exception as e:
                logger.warning(f"    Failed to generate/upload Markdown: {e}")

            # Generate and upload SVG ERD diagram
            try:
                svg_content = generate_svg_erd(db_structure)
                logger.info(f"    Generated SVG ERD: {len(svg_content)} bytes")

                # Upload SVG file
                erd_file_path = f'{github_path}/{db_name}-erd.svg'
                github_mgr.update_file(
                    repo=repo,
                    file_path=erd_file_path,
                    content=svg_content,
                    commit_message=f'[Automated] Update {database.name} ERD diagram'
                )
                logger.info(f"    ✓ Uploaded SVG ERD: {erd_file_path}")
            except Exception as e:
                logger.warning(f"    Failed to generate/upload ERD: {e}")

            # Update database record
            db_session = get_db()
            db_obj = db_session.query(Database).filter(Database.id == database.id).first()
            db_obj.github_path = team_name
            db_obj.last_modified = datetime.utcnow()
            db_session.commit()
            db_session.close()

            logger.info(f"    ✓ Synced to GitHub: {full_path}")

        # Execute the complete sync in thread pool
        await loop.run_in_executor(None, complete_sync)

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
