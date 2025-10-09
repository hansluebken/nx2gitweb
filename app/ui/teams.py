"""
Team management page for Ninox2Git
"""
import asyncio
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


def sync_teams_from_api(user, server, container):
    """Sync teams from Ninox API with progress dialog"""
    # Create progress dialog
    with ui.dialog() as dialog, ui.card().classes('w-96 p-6'):
        with ui.column().classes('w-full gap-4'):
            ui.label('Syncing Teams').classes('text-h6 font-bold')

            # Progress message
            progress_msg = ui.label('Connecting to Ninox API...').classes('text-grey-8')

            # Spinner
            with ui.row().classes('w-full justify-center my-4'):
                ui.spinner(size='lg', color='primary')

            # Status details
            status_container = ui.column().classes('w-full gap-2')

    dialog.open()

    async def execute_sync():
        """Execute team sync in background without blocking UI"""
        try:
            # Update status
            progress_msg.set_text('Decrypting API credentials...')
            await asyncio.sleep(0.1)  # Allow UI to update

            # Decrypt API key
            encryption = get_encryption_manager()
            api_key = encryption.decrypt(server.api_key_encrypted)

            progress_msg.set_text('Connecting to Ninox server...')
            await asyncio.sleep(0.1)

            # Create Ninox client
            client = NinoxClient(server.url, api_key)

            progress_msg.set_text('Fetching teams from API...')
            await asyncio.sleep(0.1)

            # Fetch teams from API in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            teams_data = await loop.run_in_executor(None, client.get_teams)

            if not teams_data:
                progress_msg.set_text('No teams found on server')
                with status_container:
                    ui.label('⚠️ No teams available').classes('text-orange')
                await asyncio.sleep(2)
                dialog.close()
                return

            progress_msg.set_text(f'Found {len(teams_data)} teams. Saving to database...')
            await asyncio.sleep(0.1)

            # Save teams to database in thread pool
            def save_teams_sync():
                db = get_db()
                synced_count = 0
                status_items = []

                try:
                    for idx, team_data in enumerate(teams_data, 1):
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
                            status_items.append(('updated', team_name))
                        else:
                            # Create new team
                            new_team = Team(
                                server_id=server.id,
                                team_id=team_id,
                                name=team_name,
                                is_active=True
                            )
                            db.add(new_team)
                            status_items.append(('created', team_name))

                        synced_count += 1

                    db.commit()

                    # Create audit log
                    create_audit_log(
                        db=db,
                        user_id=user.id,
                        action='teams_synced',
                        resource_type='server',
                        resource_id=server.id,
                        details=f'Synced {synced_count} teams from server: {server.name}',
                        auto_commit=True
                    )

                    return synced_count, status_items

                finally:
                    db.close()

            # Execute save operation
            synced_count, status_items = await loop.run_in_executor(None, save_teams_sync)

            # Update UI with status items
            with status_container:
                for status_type, team_name in status_items:
                    if status_type == 'updated':
                        ui.label(f'✓ Updated: {team_name}').classes('text-positive text-sm')
                    else:
                        ui.label(f'+ Created: {team_name}').classes('text-primary text-sm')

            progress_msg.set_text(f'✓ Successfully synced {synced_count} teams!')
            progress_msg.classes('text-positive font-bold')

            # Reload teams
            load_teams(user, server, container)

            # Close dialog after short delay
            await asyncio.sleep(2)
            dialog.close()

        except Exception as e:
            progress_msg.set_text(f'❌ Error: {str(e)}')
            progress_msg.classes('text-negative')
            Toast.error(f'Error syncing teams: {str(e)}')

            # Close dialog after showing error
            await asyncio.sleep(3)
            dialog.close()

    # Execute sync in background without blocking UI
    asyncio.create_task(execute_sync())


def sync_databases_for_team(user, server, team, container):
    """Sync databases for a specific team with progress dialog"""
    # Create progress dialog
    with ui.dialog() as dialog, ui.card().classes('w-96 p-6'):
        with ui.column().classes('w-full gap-4'):
            ui.label(f'Syncing Databases for {team.name}').classes('text-h6 font-bold')

            # Progress message
            progress_msg = ui.label('Connecting to Ninox API...').classes('text-grey-8')

            # Spinner
            with ui.row().classes('w-full justify-center my-4'):
                ui.spinner(size='lg', color='primary')

            # Status details
            status_container = ui.column().classes('w-full gap-2')

            # Summary section (initially hidden)
            summary_container = ui.column().classes('w-full gap-2 mt-4')

    dialog.open()

    async def execute_sync():
        """Execute database sync in background without blocking UI"""
        try:
            # Update status
            progress_msg.set_text('Decrypting API credentials...')
            await asyncio.sleep(0.1)  # Allow UI to update

            # Decrypt API key
            encryption = get_encryption_manager()
            api_key = encryption.decrypt(server.api_key_encrypted)

            progress_msg.set_text('Connecting to Ninox server...')
            await asyncio.sleep(0.1)

            # Create Ninox client
            client = NinoxClient(server.url, api_key)

            progress_msg.set_text(f'Fetching databases for team "{team.name}"...')
            await asyncio.sleep(0.1)

            # Fetch databases from API in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            databases_data = await loop.run_in_executor(None, client.get_databases, team.team_id)

            if not databases_data:
                progress_msg.set_text('No databases found for this team')
                with status_container:
                    ui.label('⚠️ No databases available').classes('text-orange')
                await asyncio.sleep(2)
                dialog.close()
                return

            progress_msg.set_text(f'Found {len(databases_data)} databases. Saving to database...')
            await asyncio.sleep(0.1)

            # Save databases to database in thread pool
            def save_databases_sync():
                db = get_db()
                synced_count = 0
                new_count = 0
                updated_count = 0
                status_items = []

                try:
                    for idx, db_data in enumerate(databases_data, 1):
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
                            updated_count += 1
                            exclusion_status = " (excluded)" if existing_db.is_excluded else " (included)"
                            status_items.append(('updated', f'{db_name}{exclusion_status}'))
                        else:
                            # Create new database - EXCLUDED by default for safety
                            new_db = Database(
                                team_id=team.id,
                                database_id=db_id,
                                name=db_name,
                                is_excluded=True  # Default: excluded (safe default)
                            )
                            db.add(new_db)
                            new_count += 1
                            status_items.append(('created', f'{db_name} 🔒 (GESPERRT)'))

                        synced_count += 1

                    # Update team last sync time
                    team_obj = db.query(Team).filter(Team.id == team.id).first()
                    team_obj.last_sync = datetime.utcnow()

                    db.commit()

                    # Create audit log
                    create_audit_log(
                        db=db,
                        user_id=user.id,
                        action='databases_synced',
                        resource_type='team',
                        resource_id=team.id,
                        details=f'Synced {synced_count} databases for team: {team.name}',
                        auto_commit=True
                    )

                    return synced_count, new_count, updated_count, status_items

                finally:
                    db.close()

            # Execute save operation
            synced_count, new_count, updated_count, status_items = await loop.run_in_executor(None, save_databases_sync)

            # Update progress for each item
            for idx, (status_type, description) in enumerate(status_items, 1):
                progress_msg.set_text(f'Processing database {idx}/{len(status_items)}...')
                with status_container:
                    if status_type == 'updated':
                        ui.label(f'✓ Aktualisiert: {description}').classes('text-positive text-sm')
                    else:
                        # Highlight new databases more prominently
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('add_circle', size='sm').classes('text-orange-600')
                            ui.label(f'NEU: {description}').classes('text-sm font-bold text-orange-600')
                await asyncio.sleep(0.05)  # Small delay for UI updates

            progress_msg.set_text(f'✓ Successfully synced {synced_count} databases!')
            progress_msg.classes('text-positive font-bold')

            # Show summary with prominent warning for new databases
            with summary_container:
                ui.separator()

                # Show prominent warning if new databases were found
                if new_count > 0:
                    with ui.card().classes('w-full p-4 bg-orange-50 border-orange-500').style('border-width: 2px'):
                        with ui.column().classes('w-full gap-2'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('warning', size='md').classes('text-orange-600')
                                ui.label(f'⚠️ {new_count} NEUE DATENBANK{"EN" if new_count > 1 else ""} GEFUNDEN').classes('text-h6 font-bold text-orange-700')

                            ui.label('Neue Datenbanken sind aus Sicherheitsgründen standardmäßig GESPERRT.').classes('text-sm font-medium')
                            ui.label('Sie müssen diese manuell freigeben, bevor sie synchronisiert werden können.').classes('text-sm')

                            # Button to navigate to sync page
                            ui.button(
                                f'→ Zur Sync-Seite gehen und Datenbanken freigeben',
                                icon='lock_open',
                                on_click=lambda: ui.navigate.to(f'/sync?team={team.id}')
                            ).props('color=orange').classes('mt-2')

                # Show update summary
                if updated_count > 0:
                    with ui.row().classes('items-center gap-2 mt-2'):
                        ui.icon('update', size='sm').classes('text-positive')
                        ui.label(f'{updated_count} bestehende Datenbank{"en" if updated_count > 1 else ""} aktualisiert').classes('text-sm')

            # Reload teams to show updated sync time
            load_teams(user, server, container)

            # Close dialog after delay (longer if new databases were found)
            if new_count > 0:
                # Keep dialog open longer so user sees the warning
                await asyncio.sleep(8)
            else:
                await asyncio.sleep(3)
            dialog.close()

        except Exception as e:
            progress_msg.set_text(f'❌ Error: {str(e)}')
            progress_msg.classes('text-negative')
            Toast.error(f'Error syncing databases: {str(e)}')

            # Close dialog after showing error
            await asyncio.sleep(3)
            dialog.close()

    # Execute sync in background without blocking UI
    asyncio.create_task(execute_sync())


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
