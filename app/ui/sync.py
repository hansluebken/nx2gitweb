"""
Synchronization page for Ninox2Git
"""
from nicegui import ui, background_tasks
from datetime import datetime
import asyncio
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.audit_log import AuditLog
from ..models.user_preference import UserPreference
from ..models.changelog import ChangeLog
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from ..utils.github_utils import sanitize_name, get_repo_name_from_server
from ..utils.svg_erd_generator import generate_svg_erd
from ..utils.ninox_code_extractor import extract_and_generate as extract_ninox_code
from ..api.ninox_client import NinoxClient
from ..api.github_manager import GitHubManager
from .components import (
    NavHeader, Card, FormField, Toast, EmptyState,
    StatusBadge, format_datetime, PRIMARY_COLOR, SUCCESS_COLOR
)
from .database_timeline import show_database_timeline_dialog
import json


def render(user):
    """
    Render the synchronization page

    Args:
        user: Current user object
    """
    import logging
    logger = logging.getLogger(__name__)

    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'sync').render()

    # Get team parameter from URL if present
    from urllib.parse import parse_qs, urlparse
    try:
        query_params = parse_qs(urlparse(ui.page.url).query)
        team_id_param = query_params.get('team', [None])[0]
        if team_id_param:
            team_id_param = int(team_id_param)
            logger.info(f"Team ID from URL parameter: {team_id_param}")
    except:
        team_id_param = None
        logger.info("No team ID parameter in URL")

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Synchronization').classes('text-h4 font-bold mb-4')

        # Server and team selectors
        selector_container = ui.column().classes('w-full')
        databases_container = ui.column().classes('w-full gap-4 mt-4')
        history_container = ui.column().classes('w-full gap-4 mt-4')

        with selector_container:
            render_selectors(user, databases_container, history_container, team_id_param)


def render_selectors(user, databases_container, history_container, team_id_param=None):
    """Render server and team selectors"""
    import logging
    logger = logging.getLogger(__name__)

    db = get_db()
    try:
        # Get or create user preferences
        preferences = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
        if not preferences:
            preferences = UserPreference(user_id=user.id)
            db.add(preferences)
            db.commit()

        # If team_id_param is provided, find the team and its server
        override_server = None
        override_team = None
        if team_id_param:
            logger.info(f"Looking for team with ID: {team_id_param}")
            team = db.query(Team).filter(Team.id == team_id_param).first()
            if team:
                logger.info(f"Found team: {team.name}, server_id: {team.server_id}")
                override_team = team
                override_server = db.query(Server).filter(Server.id == team.server_id).first()
                # Also update preferences to remember this selection
                preferences.last_selected_team_id = team.id
                preferences.last_selected_server_id = team.server_id
                db.commit()

        # Get user's servers
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()

        if not servers:
            with databases_container:
                databases_container.clear()
                EmptyState.render(
                    icon='storage',
                    title='No Active Servers',
                    message='You need to add an active server before synchronizing.',
                    action_label='Add Server',
                    on_action=lambda: ui.navigate.to('/servers')
                )
            return

        # Create server options
        server_options = {server.name: server for server in servers}

        # Determine initial server selection
        initial_server = None
        if override_server:
            # Use the server from the team parameter
            initial_server = override_server.name
            logger.info(f"Using override server: {initial_server}")
        elif preferences.last_selected_server_id:
            # Try to find the last selected server
            for server in servers:
                if server.id == preferences.last_selected_server_id:
                    initial_server = server.name
                    break

        # If no saved preference or server not found, use the first one
        if not initial_server:
            initial_server = list(server_options.keys())[0] if server_options else None

        with ui.row().classes('w-full items-center gap-4'):
            server_select = ui.select(
                label='Select Server',
                options=list(server_options.keys()),
                value=initial_server
            ).classes('flex-1')

            team_select = ui.select(
                label='Select Team',
                options=[],
                value=None
            ).classes('flex-1')

        # Update teams when server changes
        def on_server_change(e=None):
            import logging
            logger = logging.getLogger(__name__)

            # Get current value from server_select directly, not from event
            current_server_name = server_select.value
            logger.info(f"=== SERVER CHANGE === Current server_select.value: {current_server_name}")

            if current_server_name and current_server_name in server_options:
                # Use a NEW db session for this event
                event_db = get_db()
                try:
                    server = server_options[current_server_name]
                    logger.info(f"Selected server: {server.name} (id={server.id})")

                    # Save server selection to preferences
                    pref = event_db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if pref:
                        pref.last_selected_server_id = server.id
                        event_db.commit()

                    teams = event_db.query(Team).filter(
                        Team.server_id == server.id,
                        Team.is_active == True
                    ).all()
                    logger.info(f"Found {len(teams)} teams for server {server.name}")

                    team_options = {team.name: team for team in teams}
                    team_select.options = list(team_options.keys())
                    logger.info(f"Set team_select.options to {len(team_select.options)} teams")

                    # Check if there's a saved team preference for this server or override
                    initial_team = None

                    # Check for override team first (when coming from Teams page)
                    if hasattr(e, 'is_initial_load') and e.is_initial_load and override_team and override_team.server_id == server.id:
                        initial_team = override_team.name
                        logger.info(f"Using override team: {initial_team}")
                    elif pref and pref.last_selected_team_id:
                        for team in teams:
                            if team.id == pref.last_selected_team_id and team.server_id == server.id:
                                initial_team = team.name
                                break

                    # Use saved team or first available
                    team_select.value = initial_team if initial_team else (list(team_options.keys())[0] if team_options else None)
                    logger.info(f"Set team_select.value to: {team_select.value}")

                    team_select.update()
                    logger.info("Called team_select.update()")

                    # Store team options for later use
                    team_select.team_options = team_options

                    # Load databases if team is selected
                    if team_select.value:
                        load_databases(
                            user,
                            server,
                            team_options[team_select.value],
                            databases_container
                        )
                        load_sync_history(
                            user,
                            team_options[team_select.value],
                            history_container
                        )
                finally:
                    event_db.close()

        # Update teams when server changes
        def on_team_change(e):
            import logging
            logger = logging.getLogger(__name__)

            # Get the actual value from team_select, not from event
            team_name = team_select.value
            logger.info(f"=== TEAM CHANGE EVENT === team_name={team_name}, server={server_select.value}")

            if team_name and server_select.value and hasattr(team_select, 'team_options'):
                server = server_options[server_select.value]
                team = team_select.team_options[team_name]
                logger.info(f"Loading databases for team: {team.name} (id={team.id})")

                # Save team selection to preferences
                event_db = get_db()
                try:
                    pref = event_db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if pref:
                        pref.last_selected_team_id = team.id
                        event_db.commit()
                finally:
                    event_db.close()

                load_databases(user, server, team, databases_container)
                load_sync_history(user, team, history_container)
            else:
                logger.warning(f"Team change event but missing values: team={team_name}, server={server_select.value}")

        server_select.on('update:model-value', on_server_change)
        team_select.on('update:model-value', on_team_change)

        # Load initial teams and databases
        if server_select.value:
            # Call without event parameter, function uses server_select.value directly
            logger.info("Loading initial teams...")
            on_server_change()

    finally:
        db.close()


async def generate_ai_changelog(
    user,
    server,
    team,
    database,
    github_mgr,
    repo,
    github_path: str,
    logger
):
    """
    Generate AI-powered changelog entry for the latest commit.
    Runs in background to not block the sync process.
    
    Args:
        user: Current user object
        server: Server object
        team: Team object  
        database: Database object
        github_mgr: GitHubManager instance
        repo: GitHub repository object
        github_path: Path to the database files in GitHub
        logger: Logger instance
    """
    from concurrent.futures import ThreadPoolExecutor
    from ..services.ai_changelog import get_ai_changelog_service
    from ..models.ai_config import AIConfig
    
    try:
        # Check if AI is configured
        db = get_db()
        ai_config = db.query(AIConfig).filter(
            AIConfig.is_default == True,
            AIConfig.is_active == True,
            AIConfig.api_key_encrypted != None
        ).first()
        db.close()
        
        if not ai_config:
            logger.info("AI changelog skipped: No AI provider configured")
            return
        
        logger.info(f"Generating AI changelog for {database.name}...")
        
        # Get the latest commit for this database's structure file
        db_name = sanitize_name(database.name)
        structure_path = f'{github_path}/{db_name}-structure.json'
        
        # Get latest commit
        latest_commit = github_mgr.get_latest_commit(repo, path=structure_path)
        
        if not latest_commit:
            logger.warning(f"No commits found for {structure_path}")
            return
        
        # Check if we already have a changelog for this commit
        db = get_db()
        existing = db.query(ChangeLog).filter(
            ChangeLog.database_id == database.id,
            ChangeLog.commit_sha == latest_commit.sha
        ).first()
        db.close()
        
        if existing:
            logger.info(f"Changelog already exists for commit {latest_commit.short_sha}")
            return
        
        # Get diff data for this commit
        diff_data = github_mgr.get_commit_diff_for_changelog(repo, latest_commit.sha, structure_path)
        
        if not diff_data or not diff_data.get('full_patch'):
            logger.info(f"No diff data for commit {latest_commit.short_sha} - skipping AI analysis")
            # Still create a basic changelog entry without AI
            db = get_db()
            changelog = ChangeLog(
                database_id=database.id,
                commit_sha=latest_commit.sha,
                commit_date=latest_commit.date,
                commit_message=latest_commit.message,
                commit_url=latest_commit.url,
                files_changed=latest_commit.files_changed,
                additions=latest_commit.additions,
                deletions=latest_commit.deletions,
                ai_summary=None,
                ai_details=None,
            )
            db.add(changelog)
            db.commit()
            db.close()
            logger.info(f"Created basic changelog entry (no AI) for {latest_commit.short_sha}")
            return
        
        # Run AI analysis in thread pool to not block
        loop = asyncio.get_event_loop()
        service = get_ai_changelog_service()
        
        def do_ai_analysis():
            """Blocking AI call"""
            context = {
                'database_name': database.name,
                'changed_items': diff_data.get('changed_items', []),
            }
            return service.analyze_diff(
                diff=diff_data.get('full_patch', ''),
                context=context
            )
        
        with ThreadPoolExecutor() as executor:
            analysis = await loop.run_in_executor(executor, do_ai_analysis)
        
        # Create changelog entry
        db = get_db()
        changelog = ChangeLog(
            database_id=database.id,
            commit_sha=latest_commit.sha,
            commit_date=latest_commit.date,
            commit_message=latest_commit.message,
            commit_url=latest_commit.url,
            files_changed=len(diff_data.get('files', [])),
            additions=latest_commit.additions,
            deletions=latest_commit.deletions,
            ai_summary=analysis.summary if analysis.success else None,
            ai_details=analysis.details if analysis.success else None,
            ai_provider=analysis.provider if analysis.success else None,
            ai_model=analysis.model if analysis.success else None,
            ai_generated_at=datetime.utcnow() if analysis.success else None,
            ai_error=analysis.error if not analysis.success else None,
            diff_patch=diff_data.get('full_patch', '')[:10000],  # Limit size
            changed_items=diff_data.get('changed_items', []),
        )
        db.add(changelog)
        db.commit()
        db.close()
        
        if analysis.success:
            logger.info(f"✓ AI changelog created for {database.name} ({analysis.provider}/{analysis.model})")
        else:
            logger.warning(f"AI changelog created but analysis failed: {analysis.error}")
        
    except Exception as e:
        logger.error(f"Error generating AI changelog: {e}")
        import traceback
        logger.error(traceback.format_exc())



def load_databases(user, server, team, container):
    """Load and display databases for a team"""
    import logging
    logger = logging.getLogger(__name__)

    container.clear()

    db = get_db()
    try:
        logger.info(f"Loading databases for team_id={team.id}, team_name={team.name}")
        databases = db.query(Database).filter(
            Database.team_id == team.id
        ).order_by(Database.name).all()
        logger.info(f"Found {len(databases)} databases for team {team.name}")

        if not databases:
            with container:
                EmptyState.render(
                    icon='folder',
                    title='No Databases',
                    message='No databases found for this team. Sync the team first.',
                    action_label='Go to Teams',
                    on_action=lambda: ui.navigate.to('/teams')
                )
        else:
            with container:
                # Bulk actions
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    ui.label('Databases').classes('text-h6 font-bold')
                    ui.button(
                        'Sync All',
                        icon='sync',
                        on_click=lambda: sync_all_databases(user, server, team, databases)
                    ).props('color=primary')

                # Database cards
                for database in databases:
                    render_database_card(user, server, team, database, container)

    finally:
        db.close()


def render_database_card(user, server, team, database, container):
    """Render a database card"""
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Database info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('folder', size='md').classes('text-primary')
                    ui.label(database.name).classes('text-h6 font-bold')

                    if database.is_excluded:
                        ui.badge('Excluded', color='warning')

                ui.label(f'Database ID: {database.database_id}').classes('text-grey-7')

                if database.github_path:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('github', size='sm').classes('text-grey-7')
                        ui.label(f'GitHub Path: {database.github_path}').classes('text-grey-7')

                if database.last_modified:
                    ui.label(f'Last Modified: {format_datetime(database.last_modified)}').classes(
                        'text-grey-7'
                    )

            # Actions
            with ui.column().classes('gap-2'):
                if not database.is_excluded:
                    sync_btn = ui.button(
                        'Sync Now',
                        icon='sync',
                        on_click=lambda d=database, btn=None: handle_sync_click(user, server, team, d, container, btn)
                    ).props('flat dense color=primary')
                    # Store reference for later
                    sync_btn._database = database

                if database.github_path and user.github_organization:
                    # View Structure button - opens JSON viewer dialog
                    ui.button(
                        'View JSON',
                        icon='data_object',
                        on_click=lambda s=server, t=team, d=database: show_json_viewer_from_sync(user, s, t, d)
                    ).props('flat dense color=primary')

                    # View ERD button - opens SVG viewer dialog
                    ui.button(
                        'View ERD',
                        icon='account_tree',
                        on_click=lambda s=server, t=team, d=database: show_erd_viewer_dialog(user, s, t, d)
                    ).props('flat dense color=secondary')
                    
                    # Timeline button - shows change history
                    ui.button(
                        'Timeline',
                        icon='timeline',
                        on_click=lambda d=database: show_database_timeline_dialog(d)
                    ).props('flat dense color=info')
                    
                    # Documentation button - generates AI documentation
                    ui.button(
                        'Doku',
                        icon='description',
                        on_click=lambda s=server, t=team, d=database: show_documentation_dialog(user, s, t, d)
                    ).props('flat dense color=purple')

                    # GitHub link to folder - get repo name from server
                    github_repo_name = get_repo_name_from_server(server)
                    github_url = f'https://github.com/{user.github_organization}/{github_repo_name}/tree/main/{database.github_path}'
                    ui.button(
                        'GitHub',
                        icon='open_in_new',
                        on_click=lambda url=github_url: ui.navigate.to(url, new_tab=True)
                    ).props('flat dense')

                if database.is_excluded:
                    ui.button(
                        'Include',
                        icon='add_circle',
                        on_click=lambda d=database: toggle_database_exclusion(
                            user, d, False, container
                        )
                    ).props('flat dense color=positive')
                else:
                    ui.button(
                        'Exclude',
                        icon='block',
                        on_click=lambda d=database: toggle_database_exclusion(
                            user, d, True, container
                        )
                    ).props('flat dense color=warning')


def handle_sync_click(user, server, team, database, container, button):
    """Handle sync button click with loading state"""
    import logging
    logger = logging.getLogger(__name__)

    # Create progress dialog
    with ui.dialog() as progress_dialog, ui.card().classes('p-6'):
        with ui.column().classes('items-center gap-4').style('min-width: 300px;'):
            ui.spinner(size='xl', color='primary')
            status_label = ui.label(f'Syncing "{database.name}"...').classes('text-h6 text-center')
            progress_label = ui.label('Initializing...').classes('text-grey-7 text-center')

    progress_dialog.open()

    # Run sync directly as button handler (not background task)
    async def run_sync():
        try:
            logger.info(f"=== SYNC START === Database: {database.name}")

            progress_label.text = 'Fetching from Ninox...'
            await asyncio.sleep(0.1)

            # Run the actual sync
            await sync_database(user, server, team, database, container, progress_label)

            progress_label.text = 'Complete!'
            await asyncio.sleep(0.5)
            progress_dialog.close()
            Toast.success(f'Database "{database.name}" synced successfully!')

        except Exception as e:
            logger.error(f"Sync error: {e}")
            progress_dialog.close()
            Toast.error(f'Error: {str(e)}')

    # Call async function directly (runs in UI context, not background)
    asyncio.create_task(run_sync())


async def sync_database(user, server, team, database, container, progress_label=None):
    """Sync a single database - includes Schema, Views, Reports, and Report Files"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"=== SYNC START === Database: {database.name} (id={database.id})")

        # Step 1: Decrypt credentials
        if progress_label:
            progress_label.text = 'Decrypting credentials...'
            await asyncio.sleep(0.1)

        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server.api_key_encrypted)

        # Step 2: Connect to Ninox
        if progress_label:
            progress_label.text = 'Connecting to Ninox server...'
            await asyncio.sleep(0.1)

        client = NinoxClient(server.url, api_key)

        # Step 3: Fetch database structure
        if progress_label:
            progress_label.text = 'Downloading database structure...'
            await asyncio.sleep(0.1)

        logger.info(f"Fetching structure from Ninox...")
        # Run in executor to avoid blocking UI
        loop = asyncio.get_event_loop()
        db_structure = await loop.run_in_executor(
            None,
            client.get_database_structure,
            team.team_id,
            database.database_id
        )
        logger.info(f"Structure fetched: {len(str(db_structure))} chars")

        # Step 3b: Fetch Views (Ansichten)
        if progress_label:
            progress_label.text = 'Downloading views...'
            await asyncio.sleep(0.1)

        views_data = []
        try:
            logger.info(f"Fetching views from Ninox...")
            views_data = await loop.run_in_executor(
                None,
                client.get_views,
                team.team_id,
                database.database_id,
                True  # full_view=True
            )
            logger.info(f"Views fetched: {len(views_data)} views")
        except Exception as e:
            logger.warning(f"Could not fetch views: {e}")
            views_data = []

        # Step 3c: Fetch Reports (Berichte)
        if progress_label:
            progress_label.text = 'Downloading reports...'
            await asyncio.sleep(0.1)

        reports_data = []
        report_files_data = {}
        try:
            logger.info(f"Fetching reports from Ninox...")
            reports_data = await loop.run_in_executor(
                None,
                client.get_reports,
                team.team_id,
                database.database_id,
                True  # full_report=True
            )
            logger.info(f"Reports fetched: {len(reports_data)} reports")

            # Step 3d: Fetch Report Files for each report
            if reports_data:
                if progress_label:
                    progress_label.text = 'Downloading report files...'
                    await asyncio.sleep(0.1)

                for report in reports_data:
                    report_id = report.get('id')
                    if report_id:
                        try:
                            files = await loop.run_in_executor(
                                None,
                                client.get_report_files,
                                team.team_id,
                                database.database_id,
                                str(report_id)
                            )
                            if files:
                                report_files_data[str(report_id)] = files
                                logger.info(f"Report {report_id} has {len(files)} files")
                        except Exception as e:
                            logger.warning(f"Could not fetch files for report {report_id}: {e}")

        except Exception as e:
            logger.warning(f"Could not fetch reports: {e}")
            reports_data = []

        # Check if GitHub is configured (now in user, not server)
        if user.github_token_encrypted and user.github_organization:
            if progress_label:
                progress_label.text = 'Preparing GitHub upload...'
                await asyncio.sleep(0.1)

            github_token = encryption.decrypt(user.github_token_encrypted)

            # Use helper function to get repo name from server
            repo_name = get_repo_name_from_server(server)

            # Create GitHub manager
            github_mgr = GitHubManager(
                access_token=github_token,
                organization=user.github_organization
            )

            # Step 4: Ensure repository exists
            if progress_label:
                progress_label.text = f'Creating/checking repository "{repo_name}"...'
                await asyncio.sleep(0.1)

            repo = github_mgr.ensure_repository(
                repo_name=repo_name,
                description=f'Ninox database backups from {server.name} ({server.url})'
            )
            logger.info(f"Repository ready: {repo_name}")

            # Create path: team/dbname-structure.json (NO server folder, since repo = server)
            team_name = sanitize_name(team.name)
            db_name = sanitize_name(database.name)

            github_path = team_name  # Just the team folder
            file_name = f'{db_name}-structure.json'
            full_path = f'{github_path}/{file_name}'

            # Step 5: Convert to JSON and create complete backup object
            if progress_label:
                progress_label.text = 'Converting to JSON format...'
                await asyncio.sleep(0.1)

            # Create complete backup structure (like Updatemanager)
            complete_backup = {
                'schema': db_structure,
                'views': views_data,
                'reports': reports_data,
                'report_files': report_files_data,
                '_metadata': {
                    'synced_at': datetime.utcnow().isoformat(),
                    'database_name': database.name,
                    'database_id': database.database_id,
                    'team_name': team.name,
                    'team_id': team.team_id,
                    'server_name': server.name,
                    'views_count': len(views_data),
                    'reports_count': len(reports_data),
                    'report_files_count': sum(len(f) for f in report_files_data.values())
                }
            }

            structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)
            logger.info(f"JSON size: {len(structure_json)} bytes")

            # Step 6: Upload structure to GitHub
            if progress_label:
                progress_label.text = f'Uploading structure to GitHub: {full_path}...'
                await asyncio.sleep(0.1)

            # Upload to GitHub in executor
            await loop.run_in_executor(
                None,
                github_mgr.update_file,
                repo,
                full_path,
                structure_json,
                f'Update {database.name} structure from {team.name}'
            )
            logger.info(f"Uploaded to GitHub: {full_path}")

            # Step 6b: Upload Views if available
            if views_data:
                if progress_label:
                    progress_label.text = 'Uploading views...'
                    await asyncio.sleep(0.1)

                views_path = f'{github_path}/{db_name}-views.json'
                views_json = json.dumps(views_data, indent=2, ensure_ascii=False)
                
                try:
                    await loop.run_in_executor(
                        None,
                        github_mgr.update_file,
                        repo,
                        views_path,
                        views_json,
                        f'Update {database.name} views'
                    )
                    logger.info(f"Uploaded views to GitHub: {views_path}")
                except Exception as e:
                    logger.error(f"Failed to upload views: {e}")

            # Step 6c: Upload Reports if available
            if reports_data:
                if progress_label:
                    progress_label.text = 'Uploading reports...'
                    await asyncio.sleep(0.1)

                reports_path = f'{github_path}/{db_name}-reports.json'
                reports_json = json.dumps(reports_data, indent=2, ensure_ascii=False)
                
                try:
                    await loop.run_in_executor(
                        None,
                        github_mgr.update_file,
                        repo,
                        reports_path,
                        reports_json,
                        f'Update {database.name} reports'
                    )
                    logger.info(f"Uploaded reports to GitHub: {reports_path}")
                except Exception as e:
                    logger.error(f"Failed to upload reports: {e}")

            # Step 6d: Upload complete backup JSON
            if progress_label:
                progress_label.text = 'Uploading complete backup...'
                await asyncio.sleep(0.1)

            backup_path = f'{github_path}/{db_name}-complete-backup.json'
            backup_json = json.dumps(complete_backup, indent=2, ensure_ascii=False)
            
            try:
                await loop.run_in_executor(
                    None,
                    github_mgr.update_file,
                    repo,
                    backup_path,
                    backup_json,
                    f'Update {database.name} complete backup (schema + views + reports)'
                )
                logger.info(f"Uploaded complete backup to GitHub: {backup_path}")
            except Exception as e:
                logger.error(f"Failed to upload complete backup: {e}")

            # Step 6e: Generate and upload SVG ERD diagram
            if progress_label:
                progress_label.text = 'Generating ERD diagram...'
                await asyncio.sleep(0.1)

            try:
                # Generate SVG ERD
                logger.info(f"Generating SVG ERD for {database.name}...")
                svg_content = generate_svg_erd(db_structure)

                if svg_content is None:
                    logger.error(f"generate_svg_erd returned None for {database.name}!")
                    raise Exception("SVG generation returned None")

                logger.info(f"Generated SVG ERD: {len(svg_content)} bytes")

                # Upload SVG file
                erd_file_path = f'{github_path}/{db_name}-erd.svg'

                if progress_label:
                    progress_label.text = 'Uploading ERD diagram...'
                    await asyncio.sleep(0.1)

                # Upload SVG in executor
                await loop.run_in_executor(
                    None,
                    github_mgr.update_file,
                    repo,
                    erd_file_path,
                    svg_content,
                    f'Update {database.name} ERD diagram'
                )
                logger.info(f"Uploaded SVG ERD: {erd_file_path}")

            except Exception as e:
                logger.error(f"Failed to generate/upload ERD for {database.name}: {e}")
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                # Don't fail the whole sync if ERD generation fails

            # Step 6f: Save structure.json locally and extract Ninox code files
            code_files_count = 0
            if progress_label:
                progress_label.text = 'Saving structure and extracting code...'
                await asyncio.sleep(0.1)

            try:
                import os
                server_name = sanitize_name(server.name)
                team_name_safe = sanitize_name(team.name)
                
                # Base path for local storage
                local_base_path = f'/app/data/code/{server_name}/{team_name_safe}/{db_name}'
                os.makedirs(local_base_path, exist_ok=True)
                
                # Save structure.json locally for code viewer
                structure_local_path = f'{local_base_path}/structure.json'
                with open(structure_local_path, 'w', encoding='utf-8') as f:
                    json.dump(db_structure, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved structure.json to {structure_local_path}")
                
                # Save complete-backup.json locally (includes views, reports, etc.)
                backup_local_path = f'{local_base_path}/complete-backup.json'
                with open(backup_local_path, 'w', encoding='utf-8') as f:
                    json.dump(complete_backup, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved complete-backup.json to {backup_local_path}")
                
                # Save reports.json separately for easier access
                if reports_data:
                    reports_local_path = f'{local_base_path}/reports.json'
                    with open(reports_local_path, 'w', encoding='utf-8') as f:
                        json.dump(reports_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Saved reports.json to {reports_local_path}")
                
                # Save views.json separately for easier access
                if views_data:
                    views_local_path = f'{local_base_path}/views.json'
                    with open(views_local_path, 'w', encoding='utf-8') as f:
                        json.dump(views_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"Saved views.json to {views_local_path}")
                
                logger.info(f"Extracting Ninox code for {database.name}...")
                
                # Extract code from structure
                code_files = extract_ninox_code(db_structure, database.name)
                
                if code_files:
                    code_files_count = len(code_files)
                    logger.info(f"Found {code_files_count} code files to save locally")
                    
                    if progress_label:
                        progress_label.text = f'Saving {code_files_count} code files...'
                        await asyncio.sleep(0.1)
                    
                    # Save each code file locally
                    for file_path, file_content in code_files.items():
                        full_local_path = f'{local_base_path}/{file_path}'
                        
                        # Create directory if needed
                        os.makedirs(os.path.dirname(full_local_path), exist_ok=True)
                        
                        # Write file
                        with open(full_local_path, 'w', encoding='utf-8') as f:
                            f.write(file_content)
                    
                    logger.info(f"Saved {code_files_count} code files to {local_base_path}")
                else:
                    logger.info(f"No code found in {database.name}")

            except Exception as e:
                logger.error(f"Failed to extract/save code for {database.name}: {e}")
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                # Don't fail the whole sync if code extraction fails

            # Step 7: Update database record
            if progress_label:
                progress_label.text = 'Updating database record...'
                await asyncio.sleep(0.1)

            db = get_db()
            db_obj = db.query(Database).filter(Database.id == database.id).first()
            db_obj.github_path = github_path
            db_obj.last_modified = datetime.utcnow()
            db.commit()

            # Create detailed audit log
            sync_details = f'Synced database "{database.name}" to GitHub at {full_path}'
            if views_data:
                sync_details += f' | {len(views_data)} views'
            if reports_data:
                sync_details += f' | {len(reports_data)} reports'
            if report_files_data:
                sync_details += f' | {sum(len(f) for f in report_files_data.values())} report files'
            if code_files_count > 0:
                sync_details += f' | {code_files_count} code files'

            create_audit_log(
                db=db,
                user_id=user.id,
                action='database_synced',
                resource_type='database',
                resource_id=database.id,
                details=sync_details,
                auto_commit=True
            )

            db.close()

            logger.info(f"✓ Sync completed successfully for {database.name}")
            
            # Step 8: Generate AI Changelog (non-blocking)
            if progress_label:
                progress_label.text = 'Generating AI changelog...'
                await asyncio.sleep(0.1)
            
            try:
                await generate_ai_changelog(
                    user=user,
                    server=server,
                    team=team,
                    database=database,
                    github_mgr=github_mgr,
                    repo=repo,
                    github_path=github_path,
                    logger=logger
                )
            except Exception as e:
                # Don't fail sync if AI changelog fails
                logger.warning(f"AI Changelog generation failed (non-critical): {e}")
            # Don't show toast here - it will be shown by the caller or the UI will be updated
        else:
            # Just save structure locally
            logger.info("GitHub not configured, saving locally...")
            db = get_db()
            db_obj = db.query(Database).filter(Database.id == database.id).first()
            db_obj.last_modified = datetime.utcnow()
            db.commit()

            # Create audit log
            create_audit_log(
                db=db,
                user_id=user.id,
                action='database_synced',
                resource_type='database',
                resource_id=database.id,
                details=f'Synced database "{database.name}" (GitHub not configured)'
            )

            db.close()

            logger.warning(
                f'Database "{database.name}" synced, but GitHub is not configured. '
                'Configure GitHub in Profile settings to push to repository.'
            )

        # Reload databases if container is provided
        if container:
            load_databases(user, server, team, container)

    except Exception as e:
        logger.error(f"=== SYNC ERROR === Database: {database.name}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise  # Re-raise to be caught by caller


def sync_all_databases(user, server, team, databases):
    """Sync all non-excluded databases with progress dialog"""
    import logging
    from nicegui import background_tasks
    logger = logging.getLogger(__name__)

    # Filter non-excluded databases
    databases_to_sync = [db for db in databases if not db.is_excluded]
    total_count = len(databases_to_sync)

    if total_count == 0:
        Toast.warning('No databases to sync (all are excluded)')
        return

    # Create progress dialog
    with ui.dialog() as progress_dialog, ui.card().classes('p-6'):
        with ui.column().classes('items-center gap-4').style('min-width: 400px;'):
            ui.spinner(size='xl', color='primary')
            status_label = ui.label(f'Syncing {total_count} databases...').classes('text-h6 text-center')
            progress_label = ui.label('Starting...').classes('text-grey-7 text-center')
            progress_bar = ui.linear_progress(value=0, show_value=True).props('size=20px color=primary')

    progress_dialog.open()

    # Run as background task with proper UI context
    async def run_sync_all():
        try:
            success_count = 0
            error_count = 0

            for idx, database in enumerate(databases_to_sync, 1):
                try:
                    logger.info(f"Syncing {idx}/{total_count}: {database.name}")

                    # Update progress
                    status_label.text = f'Syncing {idx}/{total_count}: {database.name}'
                    progress_bar.value = (idx - 1) / total_count
                    await asyncio.sleep(0.1)

                    # Sync the database (pass progress_label to suppress individual toasts)
                    await sync_database(user, server, team, database, None, progress_label)

                    success_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"✗ Error syncing {database.name}: {e}")

            # Final progress
            progress_bar.value = 1.0
            progress_label.text = f'Completed: {success_count} success, {error_count} errors'
            await asyncio.sleep(1.5)
            progress_dialog.close()

            # Log result (no Toast in background task)
            if error_count > 0:
                logger.warning(f'Synced {success_count}/{total_count} databases. {error_count} errors.')
            else:
                logger.info(f'Successfully synced all {success_count} databases!')

        except Exception as e:
            logger.error(f"Bulk sync error: {e}")
            progress_dialog.close()

    # Use background_tasks.create to maintain UI context
    background_tasks.create(run_sync_all())


def toggle_database_exclusion(user, database, is_excluded, container):
    """Toggle database exclusion status"""
    try:
        db = get_db()

        db_obj = db.query(Database).filter(Database.id == database.id).first()
        db_obj.is_excluded = is_excluded
        db.commit()

        # Create audit log
        action = 'database_excluded' if is_excluded else 'database_included'
        create_audit_log(
            db=db,
            user_id=user.id,
            action=action,
            resource_type='database',
            resource_id=database.id,
            details=f'{"Excluded" if is_excluded else "Included"} database: {database.name}',
            auto_commit=True
        )

        # Get server and team for reload
        team = db.query(Team).filter(Team.id == database.team_id).first()
        server = db.query(Server).filter(Server.id == team.server_id).first()

        db.close()

        status_text = 'excluded' if is_excluded else 'included'
        Toast.success(f'Database "{database.name}" {status_text} successfully!')

        # Reload databases
        load_databases(user, server, team, container)

    except Exception as e:
        Toast.error(f'Error updating database status: {str(e)}')


def show_json_viewer_from_sync(user, server, team, database):
    """Show JSON viewer dialog - wrapper to call json_viewer function"""
    from .json_viewer import show_json_viewer_dialog
    show_json_viewer_dialog(user, server, team, database)


def show_erd_viewer_dialog(user, server, team, database):
    """Show ERD viewer dialog with SVG from GitHub"""
    import logging
    logger = logging.getLogger(__name__)

    # Create dialog
    with ui.dialog().props('maximized') as dialog:
        with ui.card().classes('w-full h-full'):
            # Header
            with ui.row().classes('w-full items-center justify-between p-4 bg-primary text-white'):
                with ui.column().classes('gap-1'):
                    ui.label(f'ERD: {database.name}').classes('text-h5 font-bold')
                    ui.label(f'{server.name} / {team.name}').classes('text-sm opacity-80')

                with ui.row().classes('gap-2'):
                    ui.button('Zoom In', icon='zoom_in', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.zoomIn();}')).props('flat color=white')
                    ui.button('Zoom Out', icon='zoom_out', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.zoomOut();}')).props('flat color=white')
                    ui.button('Reset', icon='center_focus_strong', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.resetZoom();window._erdPanZoom.center();}')).props('flat color=white')
                    ui.button('Fit', icon='fit_screen', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.fit();window._erdPanZoom.center();}')).props('flat color=white')
                    ui.button(icon='close', on_click=dialog.close).props('flat color=white')

            # Content area with SVG pan zoom stage
            with ui.column().classes('w-full').style('height: calc(100vh - 100px);'):
                # Loading indicator
                loading_container = ui.column().classes('w-full items-center gap-4 p-8')
                with loading_container:
                    ui.spinner(size='xl', color='primary')
                    status_label = ui.label('Loading ERD from GitHub...').classes('text-h6')

                # SVG container - create the stage HTML NOW before background task
                svg_container = ui.column().classes('w-full h-full').style('display: none;')
                with svg_container:
                    erd_stage = ui.html('''
                    <div id="erd-stage" style="width:100%;height:calc(100vh - 200px);border:1px solid #ccc;overflow:hidden;background:#fff;">
                      <div id="erd-viewport" style="width:100%;height:100%;"></div>
                    </div>
                    ''', sanitize=False)

                # Error container (initially hidden)
                error_container = ui.column().classes('w-full').style('display: none;')

    dialog.open()

    # Load SVG in background - use context to access UI elements
    from nicegui import context
    client_context = context.client

    async def load_svg():
        try:
            logger.info(f"Loading SVG ERD for {database.name} from GitHub...")

            if not user.github_token_encrypted or not user.github_organization:
                raise Exception("GitHub not configured")

            # Access UI elements through the saved client context
            with client_context:
                status_label.text = 'Fetching ERD from GitHub...'
            await asyncio.sleep(0.1)

            encryption = get_encryption_manager()
            github_token = encryption.decrypt(user.github_token_encrypted)
            repo_name = get_repo_name_from_server(server)

            github_mgr = GitHubManager(access_token=github_token, organization=user.github_organization)

            logger.info(f"Looking for repository: {repo_name} in organization: {user.github_organization}")
            repo = github_mgr.get_repository(repo_name)

            if not repo:
                # Try to list all repos to see what's available
                all_repos = [r.name for r in github_mgr.list_repositories()[:10]]
                logger.error(f"Repository '{repo_name}' not found. Available repos: {all_repos}")
                raise Exception(f"Repository '{repo_name}' not found. Available: {', '.join(all_repos[:5])}")

            db_name = sanitize_name(database.name)
            erd_path = f'{database.github_path}/{db_name}-erd.svg'

            with client_context:
                status_label.text = f'Loading: {erd_path}...'
            await asyncio.sleep(0.1)

            content = github_mgr.get_file_content(repo, erd_path)
            if not content:
                raise Exception(f"ERD file not found. Please sync this database first to generate the ERD.")

            # Hide loading, show SVG (containers already created)
            with client_context:
                loading_container.style('display: none;')
                svg_container.style('display: block;')

            # Inject SVG and initialize pan/zoom via JavaScript only
            svg_escaped = content.replace('`', '\\`').replace('</script>', '<\\/script>')
            init_script = f'''
            // Load svg-pan-zoom library
            if (typeof svgPanZoom === 'undefined') {{
              const script = document.createElement('script');
              script.src = 'https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js';
              script.onload = function() {{ initErdViewer(); }};
              document.head.appendChild(script);
            }} else {{
              initErdViewer();
            }}

            function initErdViewer() {{
              const vp = document.getElementById('erd-viewport');
              if (!vp) return;

              vp.innerHTML = `{svg_escaped}`;
              const svg = vp.querySelector('svg');
              if (!svg) {{
                vp.innerHTML = '<div style="padding:40px;color:#b00;">No SVG found</div>';
                return;
              }}

              // Set SVG to fill container
              svg.removeAttribute('width');
              svg.removeAttribute('height');
              svg.setAttribute('width', '100%');
              svg.setAttribute('height', '100%');

              // Destroy existing instance
              if (window._erdPanZoom) {{
                try {{ window._erdPanZoom.destroy(); }} catch(e) {{}}
              }}

              // Initialize svg-pan-zoom
              window._erdPanZoom = svgPanZoom(svg, {{
                zoomEnabled: true,
                panEnabled: true,
                controlIconsEnabled: false,
                fit: true,
                center: true,
                minZoom: 0.1,
                maxZoom: 50,
                zoomScaleSensitivity: 0.3
              }});

              // Prevent default scroll
              const stage = document.getElementById('erd-stage');
              if (stage) {{
                stage.addEventListener('wheel', ev => ev.preventDefault(), {{ passive: false }});
              }}
            }}
            '''
            # Run JavaScript within client context
            with client_context:
                ui.run_javascript(init_script)

            logger.info(f"✓ SVG ERD loaded with pan/zoom: {len(content)} bytes")

        except Exception as e:
            logger.error(f"Error loading SVG: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Use client context to update UI
            with client_context:
                loading_container.style('display: none;')
                error_container.style('display: block;')
                with error_container:
                    with ui.card().classes('w-full p-4 bg-red-50'):
                        ui.icon('error', size='lg').classes('text-negative')
                        ui.label('Error Loading ERD').classes('text-h6 font-bold text-negative')
                        ui.label(str(e)).classes('text-sm mt-2')

    # Use asyncio.create_task instead of background_tasks (keeps UI context)
    asyncio.create_task(load_svg())


def load_sync_history(user, team, container):
    """Load and display sync history"""
    container.clear()

    db = get_db()
    try:
        # Get recent sync audit logs
        logs = db.query(AuditLog).filter(
            AuditLog.action.in_(['database_synced', 'databases_synced']),
            AuditLog.resource_type.in_(['database', 'team'])
        ).order_by(AuditLog.created_at.desc()).limit(10).all()

        with container:
            with Card(title='Sync History', icon='history'):
                if not logs:
                    ui.label('No sync history available.').classes('text-grey-7')
                else:
                    with ui.column().classes('w-full gap-2'):
                        for log in logs:
                            with ui.card().classes('w-full p-3').style(
                                'background-color: #f5f5f5;'
                            ):
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.column().classes('gap-1'):
                                        ui.label(log.details).classes('font-medium')
                                        ui.label(
                                            f'User ID: {log.user_id}'
                                        ).classes('text-caption text-grey-7')
                                    with ui.column().classes('gap-1 items-end'):
                                        with ui.row().classes('items-center gap-1'):
                                            ui.icon('check_circle', size='sm').classes(
                                                'text-positive'
                                            )
                                            ui.label('Success').classes(
                                                'text-caption text-positive'
                                            )
                                        ui.label(
                                            format_datetime(log.created_at)
                                        ).classes('text-caption text-grey-7')

    finally:
        db.close()


def show_documentation_dialog(user, server, team, database):
    """Show dialog for generating AI documentation"""
    import logging
    from concurrent.futures import ThreadPoolExecutor
    from ..services.doc_generator import DocumentationGenerator, get_documentation_generator
    from ..models.documentation import Documentation
    from ..models.ai_config import AIConfig, AIProvider
    from ..utils.encryption import decrypt_value
    from ..utils.github_utils import get_repo_name_from_server
    
    logger = logging.getLogger(__name__)
    
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 900px; max-height: 90vh;'):
        # Header
        with ui.row().classes('w-full items-center justify-between p-4').style(
            f'background: linear-gradient(135deg, #9333EA 0%, #7C3AED 100%);'
        ):
            with ui.row().classes('items-center gap-2'):
                ui.icon('description', size='md', color='white')
                ui.label(f'Dokumentation: {database.name}').classes('text-h6 text-white font-bold')
            ui.button(icon='close', on_click=dialog.close).props('flat color=white')
        
        # Content container
        content_container = ui.column().classes('w-full p-4 gap-4')
        
        with content_container:
            # Check if Gemini is configured
            db = get_db()
            try:
                gemini_config = db.query(AIConfig).filter(
                    AIConfig.provider == AIProvider.GEMINI.value,
                    AIConfig.is_active == True
                ).first()
                
                if not gemini_config or not gemini_config.api_key_encrypted:
                    with ui.card().classes('w-full p-4 bg-amber-50'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('warning', color='orange')
                            ui.label('Gemini ist nicht konfiguriert').classes('text-h6 font-bold')
                        ui.label('Bitte konfigurieren Sie einen Gemini API-Key unter Admin → KI-Konfiguration.').classes('text-grey-7')
                        ui.button('Zu KI-Konfiguration', icon='settings', on_click=lambda: ui.navigate.to('/admin')).props('color=primary')
                    return
                
                # Get latest documentation if exists
                latest_doc = db.query(Documentation).filter(
                    Documentation.database_id == database.id
                ).order_by(Documentation.generated_at.desc()).first()
                
            finally:
                db.close()
            
            # Info section
            with ui.card().classes('w-full p-4 bg-blue-50'):
                ui.label('KI-Dokumentation generieren').classes('text-subtitle1 font-bold')
                ui.label(
                    'Analysiert die Datenbankstruktur mit Gemini und erstellt eine ausführliche '
                    'Markdown-Dokumentation. Diese wird im GitHub-Repository als APPLICATION_DOCS.md gespeichert.'
                ).classes('text-grey-7')
                
                with ui.row().classes('items-center gap-4 mt-2'):
                    ui.label(f'Modell: gemini-2.5-pro').classes('text-sm text-grey-6')
                    if latest_doc:
                        ui.label(f'Letzte Generierung: {latest_doc.generated_at.strftime("%d.%m.%Y %H:%M")}').classes('text-sm text-grey-6')
            
            # Preview container (initially hidden)
            preview_container = ui.column().classes('w-full').style('display: none;')
            
            # Status container
            status_container = ui.column().classes('w-full items-center gap-4')
            
            # Buttons
            with ui.row().classes('w-full justify-end gap-2'):
                generate_btn = ui.button(
                    'Dokumentation generieren',
                    icon='auto_awesome',
                    color='purple'
                )
                save_btn = ui.button(
                    'In GitHub speichern',
                    icon='cloud_upload',
                    color='positive'
                ).props('disable')
        
        # Store generated content
        generated_content = {'markdown': None, 'result': None}
        
        async def generate_documentation():
            """Generate documentation using Gemini"""
            generate_btn.props('loading disable')
            
            with status_container:
                status_container.clear()
                ui.spinner(size='lg', color='purple')
                ui.label('Lade Datenbankstruktur aus GitHub...').classes('text-grey-7')
            
            try:
                # Get structure from GitHub
                db = get_db()
                try:
                    enc_manager = get_encryption_manager()
                    github_token = enc_manager.decrypt(user.github_token_encrypted)
                    github = GitHubManager(github_token, user.github_organization)
                    
                    repo_name = get_repo_name_from_server(server)
                    repo = github.ensure_repository(repo_name)
                    
                    # Find structure file
                    structure_path = f"{database.github_path}/{sanitize_name(database.name)}-structure.json"
                    structure_content = github.get_file_content(repo, structure_path)
                    
                    if not structure_content:
                        raise ValueError(f"Strukturdatei nicht gefunden: {structure_path}")
                    
                    structure_json = json.loads(structure_content)
                    
                    # Update status
                    status_container.clear()
                    with status_container:
                        ui.spinner(size='lg', color='purple')
                        ui.label('Generiere Dokumentation mit Gemini...').classes('text-grey-7')
                        ui.label('Dies kann 30-60 Sekunden dauern.').classes('text-sm text-grey-5')
                    
                    # Get generator
                    generator = get_documentation_generator()
                    if not generator:
                        raise ValueError("Gemini ist nicht konfiguriert")
                    
                    # Run in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor() as pool:
                        result = await loop.run_in_executor(
                            pool,
                            lambda: generator.generate(structure_json, database.name)
                        )
                    
                    if not result.success:
                        raise ValueError(result.error or "Unbekannter Fehler")
                    
                    # Store result
                    generated_content['markdown'] = result.content
                    generated_content['result'] = result
                    
                    # Show preview
                    status_container.clear()
                    preview_container.style('display: block;')
                    
                    with preview_container:
                        preview_container.clear()
                        with ui.card().classes('w-full'):
                            with ui.row().classes('w-full items-center justify-between p-2 bg-grey-2'):
                                ui.label('Vorschau').classes('font-bold')
                                with ui.row().classes('items-center gap-2'):
                                    if result.input_tokens:
                                        ui.badge(f'↓{result.input_tokens}', color='amber').props('dense')
                                    if result.output_tokens:
                                        ui.badge(f'↑{result.output_tokens}', color='amber').props('dense')
                            
                            # Markdown preview with scroll
                            with ui.scroll_area().classes('w-full').style('max-height: 400px;'):
                                ui.markdown(result.content).classes('p-4')
                    
                    # Enable save button
                    save_btn.props(remove='disable')
                    generate_btn.props(remove='loading disable')
                    generate_btn.text = 'Neu generieren'
                    
                    ui.notify('Dokumentation erfolgreich generiert!', type='positive')
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error generating documentation: {e}")
                status_container.clear()
                with status_container:
                    ui.icon('error', size='lg', color='red')
                    ui.label('Fehler bei der Generierung').classes('text-h6 text-negative')
                    ui.label(str(e)).classes('text-grey-7')
                
                generate_btn.props(remove='loading disable')
                ui.notify(f'Fehler: {str(e)}', type='negative')
        
        async def save_to_github():
            """Save documentation to GitHub"""
            if not generated_content['markdown']:
                ui.notify('Keine Dokumentation zum Speichern', type='warning')
                return
            
            save_btn.props('loading disable')
            
            try:
                db = get_db()
                try:
                    enc_manager = get_encryption_manager()
                    github_token = enc_manager.decrypt(user.github_token_encrypted)
                    github = GitHubManager(github_token, user.github_organization)
                    
                    repo_name = get_repo_name_from_server(server)
                    repo = github.ensure_repository(repo_name)
                    
                    # Save to GitHub
                    doc_path = f"{database.github_path}/APPLICATION_DOCS.md"
                    commit_result = github.update_file(
                        repo,
                        doc_path,
                        generated_content['markdown'],
                        f"Update APPLICATION_DOCS.md via AI ({database.name})"
                    )
                    
                    # Save to database
                    result = generated_content['result']
                    doc = Documentation(
                        database_id=database.id,
                        content=generated_content['markdown'],
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        github_synced=True,
                        github_synced_at=datetime.now(),
                        github_commit_sha=commit_result.sha if hasattr(commit_result, 'sha') else None
                    )
                    db.add(doc)
                    db.commit()
                    
                    ui.notify('Dokumentation erfolgreich in GitHub gespeichert!', type='positive')
                    save_btn.props(remove='loading')
                    save_btn.text = 'Gespeichert ✓'
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error saving documentation: {e}")
                save_btn.props(remove='loading disable')
                ui.notify(f'Fehler beim Speichern: {str(e)}', type='negative')
        
        generate_btn.on_click(generate_documentation)
        save_btn.on_click(save_to_github)
    
    dialog.open()
