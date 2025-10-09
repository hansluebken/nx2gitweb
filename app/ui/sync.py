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
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from ..api.ninox_client import NinoxClient
from ..api.github_manager import GitHubManager
from .components import (
    NavHeader, Card, FormField, Toast, EmptyState,
    StatusBadge, format_datetime, PRIMARY_COLOR, SUCCESS_COLOR
)
import json


def render(user):
    """
    Render the synchronization page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'sync').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Synchronization').classes('text-h4 font-bold mb-4')

        # Server and team selectors
        selector_container = ui.column().classes('w-full')
        databases_container = ui.column().classes('w-full gap-4 mt-4')
        history_container = ui.column().classes('w-full gap-4 mt-4')

        with selector_container:
            render_selectors(user, databases_container, history_container)


def render_selectors(user, databases_container, history_container):
    """Render server and team selectors"""
    db = get_db()
    try:
        # Get or create user preferences
        preferences = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
        if not preferences:
            preferences = UserPreference(user_id=user.id)
            db.add(preferences)
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
        if preferences.last_selected_server_id:
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
        def on_server_change(e):
            if e.value:
                # Use a NEW db session for this event
                event_db = get_db()
                try:
                    server = server_options[e.value]

                    # Save server selection to preferences
                    pref = event_db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if pref:
                        pref.last_selected_server_id = server.id
                        event_db.commit()

                    teams = event_db.query(Team).filter(
                        Team.server_id == server.id,
                        Team.is_active == True
                    ).all()
                    team_options = {team.name: team for team in teams}
                    team_select.options = list(team_options.keys())

                    # Check if there's a saved team preference for this server
                    initial_team = None
                    if pref and pref.last_selected_team_id:
                        for team in teams:
                            if team.id == pref.last_selected_team_id and team.server_id == server.id:
                                initial_team = team.name
                                break

                    # Use saved team or first available
                    team_select.value = initial_team if initial_team else (list(team_options.keys())[0] if team_options else None)
                    team_select.update()

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

        # Update databases when team changes
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
            on_server_change(type('Event', (), {'value': server_select.value})())

    finally:
        db.close()


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
                    repo_name = user.github_default_repo or 'ninox-backup'
                    github_url = f'https://github.com/{user.github_organization}/{repo_name}/tree/main/{database.github_path}'
                    ui.button(
                        'View on GitHub',
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

    # Create async task
    async def run_sync():
        try:
            logger.info(f"=== SYNC START === Database: {database.name}")

            progress_label.text = 'Fetching from Ninox...'
            await asyncio.sleep(0.1)  # Let UI update

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

    # Start background task
    background_tasks.create(run_sync())


async def sync_database(user, server, team, database, container, progress_label=None):
    """Sync a single database"""
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
        db_structure = client.get_database_structure(team.team_id, database.database_id)
        logger.info(f"Structure fetched: {len(str(db_structure))} chars")

        # Check if GitHub is configured (now in user, not server)
        if user.github_token_encrypted and user.github_organization:
            if progress_label:
                progress_label.text = 'Preparing GitHub upload...'
                await asyncio.sleep(0.1)

            github_token = encryption.decrypt(user.github_token_encrypted)

            # Sanitize names for filesystem/GitHub paths
            def sanitize_name(name):
                """Remove/replace characters that are problematic for file paths"""
                import re
                # Replace problematic characters with underscores or remove them
                safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
                # Replace spaces with underscores
                safe_name = safe_name.replace(' ', '_')
                # Remove leading/trailing dots and spaces
                safe_name = safe_name.strip('. ')
                return safe_name

            # Extract server hostname from URL for repository name
            # e.g. "https://hagedorn.ninoxdb.de" -> "hagedorn.ninoxdb.de"
            server_hostname = server.url.replace('https://', '').replace('http://', '').split('/')[0]
            repo_name = sanitize_name(server_hostname)

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

            # Step 5: Convert to JSON
            if progress_label:
                progress_label.text = 'Converting to JSON format...'
                await asyncio.sleep(0.1)

            structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)
            logger.info(f"JSON size: {len(structure_json)} bytes")

            # Step 6: Upload to GitHub
            if progress_label:
                progress_label.text = f'Uploading to GitHub: {full_path}...'
                await asyncio.sleep(0.1)

            github_mgr.update_file(
                repo=repo,
                file_path=full_path,
                content=structure_json,
                commit_message=f'Update {database.name} structure from {team.name}'
            )
            logger.info(f"Uploaded to GitHub: {full_path}")

            # Step 7: Update database record
            if progress_label:
                progress_label.text = 'Updating database record...'
                await asyncio.sleep(0.1)

            db = get_db()
            db_obj = db.query(Database).filter(Database.id == database.id).first()
            db_obj.github_path = github_path
            db_obj.last_modified = datetime.utcnow()
            db.commit()

            # Create audit log
            create_audit_log(
                db=db,
                user_id=user.id,
                action='database_synced',
                resource_type='database',
                resource_id=database.id,
                details=f'Synced database "{database.name}" to GitHub at {full_path}',
                auto_commit=True
            )

            db.close()

            logger.info(f"✓ Sync completed successfully for {database.name}")
            if not progress_label:  # Only show toast if not using progress dialog
                Toast.success(f'Database "{database.name}" synced to GitHub successfully!')
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

            Toast.warning(
                f'Database "{database.name}" synced, but GitHub is not configured. '
                'Configure GitHub in Profile settings to push to repository.'
            )

        # Reload databases
        load_databases(user, server, team, container)

    except Exception as e:
        logger.error(f"=== SYNC ERROR === Database: {database.name}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        Toast.error(f'Error syncing database: {str(e)}')


def sync_all_databases(user, server, team, databases):
    """Sync all non-excluded databases with progress dialog"""
    import logging
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

    # Create async task
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

                    # Sync the database
                    await sync_database(user, server, team, database, None, progress_label)

                    success_count += 1
                    logger.info(f"✓ Success: {database.name}")

                except Exception as e:
                    error_count += 1
                    logger.error(f"✗ Error syncing {database.name}: {e}")
                    progress_label.text = f'Error: {database.name}'
                    await asyncio.sleep(1)

            # Final progress
            progress_bar.value = 1.0
            progress_label.text = f'Completed: {success_count} success, {error_count} errors'
            await asyncio.sleep(1.5)
            progress_dialog.close()

            # Show result
            if error_count > 0:
                Toast.warning(
                    f'Synced {success_count}/{total_count} databases. {error_count} errors occurred.'
                )
            else:
                Toast.success(f'Successfully synced all {success_count} databases!')

        except Exception as e:
            logger.error(f"Bulk sync error: {e}")
            progress_dialog.close()
            Toast.error(f'Error during bulk sync: {str(e)}')

    # Start background task
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
