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
from ..utils.ninox_erd_generator import generate_all_diagrams
from ..api.ninox_client import NinoxClient
from ..api.github_manager import GitHubManager
from ..auth import create_audit_log
import json

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

    async def sync_database(self, user, server, team, database):
        """Sync a single database to GitHub"""
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
            full_path = f'{team_name}/{db_name}-structure.json'

            # Convert to JSON
            structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)

            # Upload to GitHub
            github_mgr.update_file(
                repo=repo,
                file_path=full_path,
                content=structure_json,
                commit_message=f'[Automated] Update {database.name} structure from {team.name}'
            )

            # Generate and upload ERD diagrams
            try:
                erd_files = generate_all_diagrams(db_structure)
                logger.info(f"    Generated {len(erd_files)} ERD files")

                # Upload each ERD file
                erd_base_path = f'{team_name}/{db_name}-erd'
                for erd_file_path, erd_content in erd_files.items():
                    erd_full_path = f'{erd_base_path}/{erd_file_path}'
                    github_mgr.update_file(
                        repo=repo,
                        file_path=erd_full_path,
                        content=erd_content,
                        commit_message=f'[Automated] Update {database.name} ERD diagrams'
                    )
                logger.info(f"    ✓ Uploaded ERD diagrams to {erd_base_path}")
            except Exception as e:
                logger.warning(f"    Failed to generate/upload ERD: {e}")

            # Update database record
            db = get_db()
            db_obj = db.query(Database).filter(Database.id == database.id).first()
            db_obj.github_path = team_name
            db_obj.last_modified = datetime.utcnow()
            db.commit()
            db.close()

            logger.info(f"    ✓ Synced to GitHub: {full_path}")

        # Execute the synchronous operation in a thread pool
        await loop.run_in_executor(None, sync_operation)

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
