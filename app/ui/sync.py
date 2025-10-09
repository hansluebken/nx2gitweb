"""
Synchronization page for Ninox2Git
"""
from nicegui import ui
from datetime import datetime
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.audit_log import AuditLog
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

        with ui.row().classes('w-full items-center gap-4'):
            server_select = ui.select(
                label='Select Server',
                options=list(server_options.keys()),
                value=list(server_options.keys())[0] if server_options else None
            ).classes('flex-1')

            team_select = ui.select(
                label='Select Team',
                options=[],
                value=None
            ).classes('flex-1')

        # Update teams when server changes
        def on_server_change(e):
            if e.value:
                server = server_options[e.value]
                teams = db.query(Team).filter(
                    Team.server_id == server.id,
                    Team.is_active == True
                ).all()
                team_options = {team.name: team for team in teams}
                team_select.options = list(team_options.keys())
                team_select.value = list(team_options.keys())[0] if team_options else None
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

        # Update databases when team changes
        def on_team_change(e):
            if e.value and server_select.value:
                server = server_options[server_select.value]
                team = team_select.team_options[e.value]
                load_databases(user, server, team, databases_container)
                load_sync_history(user, team, history_container)

        server_select.on('update:model-value', on_server_change)
        team_select.on('update:model-value', on_team_change)

        # Load initial teams and databases
        if server_select.value:
            on_server_change(type('Event', (), {'value': server_select.value})())

    finally:
        db.close()


def load_databases(user, server, team, container):
    """Load and display databases for a team"""
    container.clear()

    db = get_db()
    try:
        databases = db.query(Database).filter(
            Database.team_id == team.id
        ).order_by(Database.name).all()

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
                    ui.button(
                        'Sync Now',
                        icon='sync',
                        on_click=lambda d=database: sync_database(user, server, team, d, container)
                    ).props('flat dense color=primary')

                if database.github_path and server.github_organization:
                    repo_name = server.github_repo_name or 'ninox-backup'
                    github_url = f'https://github.com/{server.github_organization}/{repo_name}/tree/main/{database.github_path}'
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


async def sync_database(user, server, team, database, container):
    """Sync a single database"""
    try:
        # Show loading message
        Toast.info(f'Syncing database "{database.name}"...')

        # Decrypt credentials
        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server.api_key_encrypted)

        # Create Ninox client
        client = NinoxClient(server.url, api_key)

        # Fetch database structure
        db_structure = client.get_database_structure(team.team_id, database.database_id)

        # Check if GitHub is configured
        if server.github_token_encrypted and server.github_organization:
            github_token = encryption.decrypt(server.github_token_encrypted)
            repo_name = server.github_repo_name or 'ninox-backup'

            # Create GitHub manager
            github_mgr = GitHubManager(
                token=github_token,
                organization=server.github_organization,
                repository=repo_name
            )

            # Create path for this database
            github_path = f'{team.name}/{database.name}'

            # Convert structure to JSON
            structure_json = json.dumps(db_structure, indent=2, ensure_ascii=False)

            # Upload to GitHub
            github_mgr.upload_file(
                file_path=f'{github_path}/structure.json',
                content=structure_json,
                commit_message=f'Update {database.name} structure'
            )

            # Update database record
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
                details=f'Synced database "{database.name}" to GitHub'
            )

            db.close()

            Toast.success(f'Database "{database.name}" synced to GitHub successfully!')
        else:
            # Just save structure locally
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
                'Configure GitHub in server settings to push to repository.'
            )

        # Reload databases
        load_databases(user, server, team, container)

    except Exception as e:
        Toast.error(f'Error syncing database: {str(e)}')


async def sync_all_databases(user, server, team, databases):
    """Sync all non-excluded databases"""
    try:
        Toast.info(f'Syncing all databases for team "{team.name}"...')

        success_count = 0
        error_count = 0

        for database in databases:
            if database.is_excluded:
                continue

            try:
                await sync_database(user, server, team, database, None)
                success_count += 1
            except Exception as e:
                error_count += 1
                print(f'Error syncing {database.name}: {e}')

        if error_count > 0:
            Toast.warning(
                f'Synced {success_count} databases with {error_count} errors. Check logs for details.'
            )
        else:
            Toast.success(f'Successfully synced all {success_count} databases!')

    except Exception as e:
        Toast.error(f'Error during bulk sync: {str(e)}')


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
            details=f'{"Excluded" if is_excluded else "Included"} database: {database.name}'
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
                                            f'By: {log.user.username}'
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
