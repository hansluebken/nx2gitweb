"""
Team management page for Ninox2Git
"""
from nicegui import ui
from datetime import datetime
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from ..api.ninox_client import NinoxClient
from .components import (
    NavHeader, Card, FormField, Toast, EmptyState,
    StatusBadge, format_datetime, PRIMARY_COLOR
)


def render(user):
    """
    Render the teams management page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'teams').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Teams').classes('text-h4 font-bold mb-4')

        # Server selector
        server_select_container = ui.column().classes('w-full')
        teams_container = ui.column().classes('w-full gap-4 mt-4')

        with server_select_container:
            render_server_selector(user, teams_container)


def render_server_selector(user, teams_container):
    """Render server selector dropdown"""
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
            with teams_container:
                teams_container.clear()
                EmptyState.render(
                    icon='storage',
                    title='No Active Servers',
                    message='You need to add an active server before managing teams.',
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

            ui.button(
                'Sync Teams',
                icon='refresh',
                on_click=lambda: sync_teams_from_api(
                    user,
                    server_options[server_select.value],
                    teams_container
                )
            ).props('color=primary')

        # Load teams for selected server
        def on_server_change(e):
            if e.value:
                load_teams(user, server_options[e.value], teams_container)

        server_select.on('update:model-value', on_server_change)

        # Load initial teams
        if server_select.value:
            load_teams(user, server_options[server_select.value], teams_container)

    finally:
        db.close()


def load_teams(user, server, container):
    """Load and display teams for a server"""
    container.clear()

    db = get_db()
    try:
        teams = db.query(Team).filter(
            Team.server_id == server.id
        ).order_by(Team.name).all()

        if not teams:
            with container:
                EmptyState.render(
                    icon='group',
                    title='No Teams',
                    message='No teams found for this server. Click "Sync Teams" to fetch teams from Ninox.',
                    action_label='Sync Teams',
                    on_action=lambda: sync_teams_from_api(user, server, container)
                )
        else:
            with container:
                for team in teams:
                    render_team_card(user, server, team, container)

    finally:
        db.close()


def render_team_card(user, server, team, container):
    """Render a team card"""
    db = get_db()
    try:
        # Count databases for this team
        db_count = db.query(Database).filter(Database.team_id == team.id).count()
    finally:
        db.close()

    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Team info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('group', size='md').classes('text-primary')
                    ui.label(team.name).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if team.is_active else 'Inactive',
                        team.is_active
                    )

                ui.label(f'Team ID: {team.team_id}').classes('text-grey-7')
                ui.label(f'Databases: {db_count}').classes('text-grey-7')

                if team.last_sync:
                    ui.label(f'Last Sync: {format_datetime(team.last_sync)}').classes('text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'Sync Databases',
                    icon='sync',
                    on_click=lambda t=team: sync_databases_for_team(user, server, t, container)
                ).props('flat dense color=primary')

                ui.button(
                    'View Databases',
                    icon='folder',
                    on_click=lambda t=team: ui.navigate.to(f'/sync?team={t.id}')
                ).props('flat dense')

                if team.is_active:
                    ui.button(
                        'Deactivate',
                        icon='block',
                        on_click=lambda t=team: toggle_team_status(user, t, False, container)
                    ).props('flat dense color=warning')
                else:
                    ui.button(
                        'Activate',
                        icon='check_circle',
                        on_click=lambda t=team: toggle_team_status(user, t, True, container)
                    ).props('flat dense color=positive')


async def sync_teams_from_api(user, server, container):
    """Sync teams from Ninox API"""
    try:
        # Show loading message
        Toast.info('Syncing teams from Ninox...')

        # Decrypt API key
        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server.api_key_encrypted)

        # Create Ninox client
        client = NinoxClient(server.url, api_key)

        # Fetch teams from API
        teams_data = client.get_teams()

        if not teams_data:
            Toast.warning('No teams found on server')
            return

        # Save teams to database
        db = get_db()
        synced_count = 0

        for team_data in teams_data:
            # Extract team ID and name
            team_id = team_data.get('id') or team_data.get('teamId')
            team_name = team_data.get('name') or team_data.get('teamName', f'Team {team_id}')

            if not team_id:
                continue

            # Check if team already exists
            existing_team = db.query(Team).filter(
                Team.server_id == server.id,
                Team.team_id == team_id
            ).first()

            if existing_team:
                # Update existing team
                existing_team.name = team_name
            else:
                # Create new team
                new_team = Team(
                    server_id=server.id,
                    team_id=team_id,
                    name=team_name,
                    is_active=True
                )
                db.add(new_team)

            synced_count += 1

        db.commit()

        # Create audit log (with auto_commit since teams already committed)
        create_audit_log(
            db=db,
            user_id=user.id,
            action='teams_synced',
            resource_type='server',
            resource_id=server.id,
            details=f'Synced {synced_count} teams from server: {server.name}',
            auto_commit=True
        )

        db.close()

        Toast.success(f'Successfully synced {synced_count} teams!')

        # Reload teams
        load_teams(user, server, container)

    except Exception as e:
        Toast.error(f'Error syncing teams: {str(e)}')


async def sync_databases_for_team(user, server, team, container):
    """Sync databases for a specific team"""
    try:
        # Show loading message
        Toast.info(f'Syncing databases for team "{team.name}"...')

        # Decrypt API key
        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server.api_key_encrypted)

        # Create Ninox client
        client = NinoxClient(server.url, api_key)

        # Fetch databases from API
        databases_data = client.get_databases(team.team_id)

        if not databases_data:
            Toast.warning('No databases found for this team')
            return

        # Save databases to database
        db = get_db()
        synced_count = 0

        for db_data in databases_data:
            # Extract database ID and name
            db_id = db_data.get('id') or db_data.get('databaseId')
            db_name = db_data.get('name') or db_data.get('databaseName', f'Database {db_id}')

            if not db_id:
                continue

            # Check if database already exists
            existing_db = db.query(Database).filter(
                Database.team_id == team.id,
                Database.database_id == db_id
            ).first()

            if existing_db:
                # Update existing database name (keep exclusion status)
                existing_db.name = db_name
            else:
                # Create new database - EXCLUDED by default for safety
                # User must manually include databases they want to sync
                new_db = Database(
                    team_id=team.id,
                    database_id=db_id,
                    name=db_name,
                    is_excluded=True  # Default: excluded (safe default)
                )
                db.add(new_db)

            synced_count += 1

        # Update team last sync time
        team_obj = db.query(Team).filter(Team.id == team.id).first()
        team_obj.last_sync = datetime.utcnow()

        db.commit()

        # Create audit log (with auto_commit since databases already committed)
        create_audit_log(
            db=db,
            user_id=user.id,
            action='databases_synced',
            resource_type='team',
            resource_id=team.id,
            details=f'Synced {synced_count} databases for team: {team.name}',
            auto_commit=True
        )

        db.close()

        Toast.success(f'Successfully synced {synced_count} databases!')

        # Reload teams to show updated sync time
        load_teams(user, server, container)

    except Exception as e:
        Toast.error(f'Error syncing databases: {str(e)}')


def toggle_team_status(user, team, is_active, container):
    """Toggle team active status"""
    try:
        db = get_db()

        team_obj = db.query(Team).filter(Team.id == team.id).first()
        team_obj.is_active = is_active
        db.commit()

        # Create audit log (with auto_commit since team already committed)
        action = 'team_activated' if is_active else 'team_deactivated'
        create_audit_log(
            db=db,
            user_id=user.id,
            action=action,
            resource_type='team',
            resource_id=team.id,
            details=f'{"Activated" if is_active else "Deactivated"} team: {team.name}',
            auto_commit=True
        )

        db.close()

        status_text = 'activated' if is_active else 'deactivated'
        Toast.success(f'Team "{team.name}" {status_text} successfully!')

        # Reload teams
        server = db.query(Server).filter(Server.id == team.server_id).first()
        load_teams(user, server, container)

    except Exception as e:
        Toast.error(f'Error updating team status: {str(e)}')
