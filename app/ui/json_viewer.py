"""
JSON Viewer page for Ninox2Git
View and search database structures from GitHub
"""
from nicegui import ui, background_tasks
import asyncio
import json as json_lib
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..utils.encryption import get_encryption_manager
from ..utils.github_utils import get_repo_name_from_server
from ..api.github_manager import GitHubManager
from .components import (
    NavHeader, Card, FormField, Toast, EmptyState,
    StatusBadge, format_datetime, PRIMARY_COLOR
)


def render(user):
    """
    Render the JSON viewer page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'json-viewer').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1800px; margin: 0 auto;'):
        ui.label('Database Structure Viewer').classes('text-h4 font-bold mb-4')

        # Search section
        with ui.card().classes('w-full p-4 mb-4'):
            ui.label('Search Database Structures').classes('text-h6 font-bold mb-3')

            with ui.row().classes('w-full gap-4 items-end'):
                search_input = ui.input(
                    label='Search',
                    placeholder='Database name, server, team...'
                ).classes('flex-1').props('clearable')

                server_filter = ui.select(
                    label='Server (optional)',
                    options=['All Servers'],
                    value='All Servers'
                ).classes('w-64')

                team_filter = ui.select(
                    label='Team (optional)',
                    options=['All Teams'],
                    value='All Teams'
                ).classes('w-64')

                search_btn = ui.button(
                    'Search',
                    icon='search',
                    on_click=lambda: search_databases(
                        user, search_input.value, server_filter.value,
                        team_filter.value, results_container
                    )
                ).props('color=primary')

        # Results container
        results_container = ui.column().classes('w-full gap-4')

        # Load server and team options - store in accessible scope
        servers_list = []
        all_team_names = []

        db = get_db()
        try:
            if user.is_admin:
                servers_list = db.query(Server).filter(Server.is_active == True).all()
            else:
                servers_list = db.query(Server).filter(
                    Server.user_id == user.id,
                    Server.is_active == True
                ).all()

            server_names = ['All Servers'] + [s.name for s in servers_list]
            server_filter.options = server_names

            # Load teams for all servers
            all_teams = db.query(Team).join(Server).filter(
                Server.id.in_([s.id for s in servers_list]),
                Team.is_active == True
            ).all()
            all_team_names = ['All Teams'] + [t.name for t in all_teams]
            team_filter.options = all_team_names

        finally:
            db.close()

        # Create server mapping for quick lookup
        server_map = {s.name: s for s in servers_list}

        # Auto-search on enter
        search_input.on('keydown.enter', lambda: search_databases(
            user, search_input.value, server_filter.value,
            team_filter.value, results_container
        ))

        # Update team options when server changes
        def on_server_filter_change():
            import logging
            logger = logging.getLogger(__name__)

            selected_server = server_filter.value
            logger.info(f"Server filter changed to: {selected_server}")

            if selected_server == 'All Servers':
                # Show all teams
                team_filter.options = all_team_names
                team_filter.value = 'All Teams'
                logger.info(f"Reset team filter to show all {len(all_team_names)} teams")
            else:
                # Filter teams for selected server
                if selected_server in server_map:
                    server_obj = server_map[selected_server]
                    logger.info(f"Filtering teams for server: {server_obj.name} (id={server_obj.id})")

                    filter_db = get_db()
                    try:
                        # Get teams for this server
                        server_teams = filter_db.query(Team).filter(
                            Team.server_id == server_obj.id,
                            Team.is_active == True
                        ).all()
                        filtered_team_names = ['All Teams'] + [t.name for t in server_teams]
                        team_filter.options = filtered_team_names
                        team_filter.value = 'All Teams'
                        team_filter.update()
                        logger.info(f"Updated team filter to {len(filtered_team_names)} teams")
                    finally:
                        filter_db.close()

            # Trigger search
            search_databases(
                user, search_input.value, server_filter.value,
                team_filter.value, results_container
            )

        # Auto-search when filters change
        server_filter.on('update:model-value', lambda: on_server_filter_change())

        team_filter.on('update:model-value', lambda: search_databases(
            user, search_input.value, server_filter.value,
            team_filter.value, results_container
        ))

        # Initial load - show recent synced databases
        load_recent_databases(user, results_container)


def load_recent_databases(user, container):
    """Load recently synced databases"""
    container.clear()

    with container:
        ui.label('Recently Synced Databases').classes('text-h6 font-bold mb-2')

    db = get_db()
    try:
        # Get databases with github_path (recently synced)
        if user.is_admin:
            databases = db.query(Database).join(Team).join(Server).filter(
                Database.github_path.isnot(None),
                Server.is_active == True
            ).order_by(Database.last_modified.desc()).limit(20).all()
        else:
            databases = db.query(Database).join(Team).join(Server).filter(
                Database.github_path.isnot(None),
                Server.user_id == user.id,
                Server.is_active == True
            ).order_by(Database.last_modified.desc()).limit(20).all()

        if not databases:
            with container:
                EmptyState.render(
                    icon='folder_open',
                    title='No Synced Databases',
                    message='No databases have been synced to GitHub yet. Go to the Sync page to sync databases.',
                    action_label='Go to Sync',
                    on_action=lambda: ui.navigate.to('/sync')
                )
        else:
            with container:
                for database in databases:
                    # Get server and team info
                    team = db.query(Team).filter(Team.id == database.team_id).first()
                    server = db.query(Server).filter(Server.id == team.server_id).first()
                    render_database_result_card(user, server, team, database)

    finally:
        db.close()


def search_databases(user, query, server_filter, team_filter, container):
    """Search databases by name, server, or team"""
    container.clear()

    if not query and server_filter == 'All Servers' and team_filter == 'All Teams':
        # No search criteria - show recent
        load_recent_databases(user, container)
        return

    with container:
        ui.label('Search Results').classes('text-h6 font-bold mb-2')

    db = get_db()
    try:
        # Build query
        if user.is_admin:
            databases_query = db.query(Database).join(Team).join(Server).filter(
                Database.github_path.isnot(None),
                Server.is_active == True
            )
        else:
            databases_query = db.query(Database).join(Team).join(Server).filter(
                Database.github_path.isnot(None),
                Server.user_id == user.id,
                Server.is_active == True
            )

        # Apply filters
        if query:
            databases_query = databases_query.filter(
                Database.name.ilike(f'%{query}%')
            )

        if server_filter != 'All Servers':
            databases_query = databases_query.filter(Server.name == server_filter)

        if team_filter != 'All Teams':
            databases_query = databases_query.filter(Team.name == team_filter)

        databases = databases_query.order_by(Database.last_modified.desc()).limit(50).all()

        if not databases:
            with container:
                ui.label('No databases found matching your search criteria.').classes('text-grey-7')
        else:
            with container:
                ui.label(f'Found {len(databases)} database(s)').classes('text-grey-7 mb-2')
                for database in databases:
                    team = db.query(Team).filter(Team.id == database.team_id).first()
                    server = db.query(Server).filter(Server.id == team.server_id).first()
                    render_database_result_card(user, server, team, database)

    finally:
        db.close()


def render_database_result_card(user, server, team, database):
    """Render a database search result card"""
    with ui.card().classes('w-full p-4 hover:shadow-lg transition-shadow'):
        with ui.row().classes('w-full items-center justify-between'):
            # Database info
            with ui.column().classes('flex-1 gap-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('folder', size='md').classes('text-primary')
                    ui.label(database.name).classes('text-h6 font-bold')

                ui.label(f'Server: {server.name}').classes('text-sm text-grey-7')
                ui.label(f'Team: {team.name}').classes('text-sm text-grey-7')

                if database.last_modified:
                    ui.label(f'Last Modified: {format_datetime(database.last_modified)}').classes('text-caption text-grey-7')

                if database.github_path:
                    ui.label(f'GitHub Path: {database.github_path}').classes('text-caption text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'View JSON',
                    icon='visibility',
                    on_click=lambda: show_json_viewer_dialog(user, server, team, database)
                ).props('color=primary')


def show_json_viewer_dialog(user, server, team, database):
    """Show JSON viewer dialog for a database"""
    import logging
    logger = logging.getLogger(__name__)

    # Create dialog
    with ui.dialog().props('maximized') as dialog:
        with ui.card().classes('w-full h-full'):
            # Header
            with ui.row().classes('w-full items-center justify-between p-4 bg-primary text-white'):
                with ui.column().classes('gap-1'):
                    ui.label(database.name).classes('text-h5 font-bold')
                    ui.label(f'{server.name} / {team.name}').classes('text-sm opacity-80')

                ui.button(icon='close', on_click=dialog.close).props('flat color=white')

            # Content area
            with ui.column().classes('w-full p-4 gap-4').style('height: calc(100vh - 100px); overflow: auto;'):
                # Loading indicator
                loading_container = ui.column().classes('w-full items-center gap-4 p-8')
                with loading_container:
                    ui.spinner(size='xl', color='primary')
                    ui.label('Loading JSON from GitHub...').classes('text-h6')

                # JSON editor container (initially hidden)
                json_container = ui.column().classes('w-full').style('display: none;')
                with json_container:
                    # Create json_editor placeholder - will be replaced
                    json_editor_placeholder = ui.column().classes('w-full')

                # Error container (initially hidden)
                error_container = ui.column().classes('w-full').style('display: none;')

    dialog.open()

    # Load JSON and display with proper JSON editor
    def load_json_data():
        try:
            logger.info(f"Loading JSON for {database.name} from GitHub...")

            if not user.github_token_encrypted or not user.github_organization:
                raise Exception("GitHub not configured")

            encryption = get_encryption_manager()
            github_token = encryption.decrypt(user.github_token_encrypted)
            repo_name = get_repo_name_from_server(server)

            github_mgr = GitHubManager(access_token=github_token, organization=user.github_organization)
            repo = github_mgr.get_repository(repo_name)

            if not repo:
                raise Exception(f"Repository not found")

            from ..utils.github_utils import sanitize_name
            db_name = sanitize_name(database.name)
            file_path = f'{database.github_path}/{db_name}-structure.json'

            logger.info(f"Getting file content from: {file_path}")
            content = github_mgr.get_file_content(repo, file_path)

            if not content:
                raise Exception(f"File not found or empty")

            # Parse JSON to verify it's valid
            json_data = json_lib.loads(content)

            logger.info(f"JSON loaded successfully: {len(content)} characters")

            # Update UI - hide loading, show JSON container
            loading_container.style('display: none;')
            json_container.style('display: block;')

            # Create JSON editor with the loaded data - CORRECT FORMAT!
            with json_editor_placeholder:
                json_editor_placeholder.clear()  # Clear placeholder
                ui.json_editor({
                    'content': {'json': json_data},  # CORRECT: content wrapper needed!
                    'mode': 'view',
                    'modes': ['tree', 'view', 'code', 'text'],
                    'search': True,
                    'navigationBar': True
                }).classes('w-full').style('height: 80vh;')

        except Exception as e:
            logger.error(f"Error loading JSON: {e}")
            import traceback
            logger.error(traceback.format_exc())

            loading_container.style('display: none;')
            error_container.style('display: block;')
            with error_container:
                ui.label(f'Error: {str(e)}').classes('text-negative')

    # Use a timer to load after the dialog is rendered
    ui.timer(0.5, load_json_data, once=True)


def download_json(database):
    """Trigger JSON download"""
    Toast.info(f'Downloading {database.name}-structure.json...')
