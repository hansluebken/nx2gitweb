"""
YAML Code Viewer for Ninox2Git
3-Column layout for viewing Ninox code from ninox-dev-cli YAML files.

Features:
- Database browser (left column)
- Code locations tree with filtering (middle column)  
- Code viewer with syntax highlighting (right column)
- Global search across all code
- Category and type filtering
- Copy to clipboard
- Download trigger
"""
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from nicegui import ui

from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..services.ninox_cli_service import (
    get_ninox_cli_service,
    NinoxCLIService,
    NinoxEnvironment,
    DownloadResult
)
from ..services.ninox_sync_service import get_changed_files, get_git_log, get_commit_diff
from ..services.ai_changelog import get_ai_changelog_service
from ..utils.ninox_yaml_parser import (
    NinoxYAMLParser,
    NinoxDatabase,
    CodeLocation,
    CodeLevel,
    CodeCategory,
    CATEGORY_NAMES,
    CODE_TYPE_NAMES,
    filter_code_locations,
    search_code_locations,
    group_by_table,
    get_statistics
)
from ..utils.ninox_lexer import highlight_code, get_code_preview
from ..utils.svg_erd_generator import generate_svg_erd
from .components import NavHeader, Card, Toast, EmptyState, PRIMARY_COLOR


# Environment variable for ninox-cli data path
NINOX_CLI_DATA_PATH = os.getenv('NINOX_CLI_DATA_PATH', '/app/data/ninox-cli')


def change_team(team_name: str, team_options: dict, state: 'YAMLCodeViewerState', user_id: int = None):
    """Change the active team and reload databases from team-specific folder"""
    import logging
    logger = logging.getLogger(__name__)

    team = team_options.get(team_name)
    if not team:
        ui.notify('Team nicht gefunden', type='warning')
        return

    # Save team preference (if user_id is provided)
    if user_id:
        from ..models.user_preference import UserPreference
        db_pref = get_db()
        try:
            pref = db_pref.query(UserPreference).filter(UserPreference.user_id == user_id).first()
            if pref:
                pref.last_selected_team_id = team.id
                pref.last_selected_server_id = team.server_id
                db_pref.commit()
        finally:
            db_pref.close()

    logger.info(f"=== TEAM CHANGE DEBUG ===")
    logger.info(f"Team Name: {team_name}")
    logger.info(f"Team ID: {team.team_id}")
    logger.info(f"Team Object: {team}")

    # Team-specific folder structure using clear names
    cli_service = get_ninox_cli_service()
    logger.info(f"CLI Service project_path: {cli_service.project_path}")

    # NEW: Get server and use clear name paths
    from ..utils.path_resolver import get_team_path
    from ..models.server import Server

    db = get_db()
    try:
        server = db.query(Server).filter(Server.id == team.server_id).first()
        team_project_path = get_team_path(server, team)
    finally:
        db.close()

    logger.info(f"Team project path: {team_project_path}")

    # NEW: Discover databases in new structure (each DB has own folder)
    # Structure: team_path/{DatabaseName}/src/Objects/database_{Name}/
    state.databases = []

    if team_project_path.exists():
        for db_folder in team_project_path.iterdir():
            if not db_folder.is_dir():
                continue
            if db_folder.name in ['.git', '.gitignore', 'src']:
                continue  # Skip git and other meta folders

            # Each database folder should have src/Objects/
            try:
                parser = NinoxYAMLParser(str(db_folder))
                dbs = parser.get_all_databases()
                state.databases.extend(dbs)
                logger.info(f"Found {len(dbs)} database(s) in {db_folder.name}")
            except Exception as e:
                logger.warning(f"Could not parse {db_folder.name}: {e}")
    else:
        logger.warning(f"Team path does not exist: {team_project_path}")
        team_project_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loaded {len(state.databases)} total databases for team {team_name}")
    if state.databases:
        logger.info(f"Database names: {[db.name for db in state.databases[:5]]}")
    logger.info(f"=== END TEAM CHANGE DEBUG ===")

    # Clear cache and update UI
    YAMLCodeViewerState.clear_cache()
    state.current_database = None
    state.current_location = None

    if 'render_db_slider' in state.ui_elements:
        state.ui_elements['render_db_slider']()

    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()

    if len(state.databases) == 0:
        ui.notify(
            f'Team {team_name}: Keine Datenbanken synchronisiert. '
            f'Gehe zu "Teams" → "Sync Databases" → "Sync" → "Sync All YAML" um Datenbanken zu synchronisieren.',
            type='warning',
            timeout=8000
        )
    else:
        ui.notify(f'Team gewechselt: {team_name} ({len(state.databases)} DBs)', type='positive')


class YAMLCodeViewerState:
    """State management for the YAML Code Viewer"""
    
    # Class-level cache for databases (shared across all instances)
    _db_cache: Optional[List[NinoxDatabase]] = None
    _cache_time: Optional[float] = None
    _cache_ttl: float = 300  # 5 minutes
    
    def __init__(self):
        self.databases: List[NinoxDatabase] = []
        self.current_database: Optional[NinoxDatabase] = None
        self.current_location: Optional[CodeLocation] = None
        self.filtered_locations: List[CodeLocation] = []

        # Filters
        self.search_query: str = ""
        self.selected_categories: Set[CodeCategory] = set()
        self.selected_code_types: Set[str] = set()
        self.selected_tables: Set[str] = set()

        # Global search results
        self.global_search_results: List[tuple] = []

        # Selected databases (for multi-select) - store IDs instead of objects
        self.selected_database_ids: Set[str] = set()

        # UI references
        self.ui_elements: Dict[str, Any] = {}

        # Flag to prevent duplicate change_team calls during programmatic updates
        self.is_programmatic_update: bool = False
    
    @classmethod
    def get_cached_databases(cls, force_reload: bool = False) -> List[NinoxDatabase]:
        """Get databases from cache or load them"""
        import time
        
        # Check if cache is valid
        if not force_reload and cls._db_cache is not None and cls._cache_time is not None:
            age = time.time() - cls._cache_time
            if age < cls._cache_ttl:
                return cls._db_cache
        
        # Load databases
        cli_service = get_ninox_cli_service()
        parser = NinoxYAMLParser(str(cli_service.project_path))
        databases = parser.get_all_databases()
        cls._db_cache = databases
        cls._cache_time = time.time()
        
        return databases
    
    @classmethod
    def clear_cache(cls):
        """Clear the database cache"""
        cls._db_cache = None
        cls._cache_time = None
    
    def reset_filters(self):
        """Reset all filters"""
        self.search_query = ""
        self.selected_categories.clear()
        self.selected_code_types.clear()
        self.selected_tables.clear()
        self.global_search_results.clear()
    
    def apply_filters(self) -> List[CodeLocation]:
        """Apply current filters and return filtered locations"""
        if not self.current_database:
            return []
        
        locations = self.current_database.code_locations
        
        # Apply filters
        self.filtered_locations = filter_code_locations(
            locations,
            categories=self.selected_categories if self.selected_categories else None,
            code_types=self.selected_code_types if self.selected_code_types else None,
            tables=self.selected_tables if self.selected_tables else None,
            text_query=self.search_query if self.search_query else None
        )
        
        return self.filtered_locations


def has_git_changes(database: NinoxDatabase) -> bool:
    """
    Check if a database has uncommitted changes in git.
    
    Args:
        database: NinoxDatabase instance
        
    Returns:
        True if database has changes
    """
    try:
        cli_service = get_ninox_cli_service()
        from ..utils.github_utils import sanitize_name
        changed_files = get_changed_files(cli_service.project_path)
        
        # Check if any changed file belongs to this database
        # Files are in src/Objects/database_<id>/ or src/Files/database_<id>/
        db_pattern = f"database_{database.database_id}/"
        for file_path in changed_files:
            if db_pattern in file_path:
                return True
        
        return False
    except Exception:
        return False


def render(user):
    """Render the YAML Code Viewer page"""
    import logging
    logger = logging.getLogger(__name__)
    
    ui.colors(primary=PRIMARY_COLOR)
    
    # Navigation header
    NavHeader(user, 'yaml-code-viewer').render()
    
    # Initialize state
    state = YAMLCodeViewerState()
    state.user_id = user.id  # Store user ID for preference saving

    # Don't load databases initially - they will be loaded when a team is selected
    # This prevents showing databases from the wrong team
    logger.info("Initializing YAML Code Viewer - databases will be loaded when team is selected")
    state.databases = []
    
    # Check for database filter from URL parameter
    from urllib.parse import parse_qs, urlparse
    db_id_filter = None
    try:
        query_params = parse_qs(urlparse(ui.page.url).query)
        db_id_param = query_params.get('db', [None])[0]
        if db_id_param:
            db_id_filter = db_id_param
            logger.info(f"Database filter from URL: {db_id_filter}")
    except Exception as e:
        logger.warning(f"Could not parse URL parameters: {e}")
    
    # Main container - full width
    with ui.column().classes('w-full p-4 gap-2').style('max-width: 100%; margin: 0 auto;'):

        # Header row with title, team selection, search, and actions
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('YAML Code Viewer').classes('text-h5 font-bold')

            with ui.row().classes('gap-2 items-center'):
                # Server and Team selection
                from ..models.team import Team
                from ..models.server import Server
                from ..models.user_preference import UserPreference

                db_conn = get_db()
                try:
                    # Get or create user preferences
                    preferences = db_conn.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if not preferences:
                        preferences = UserPreference(user_id=user.id)
                        db_conn.add(preferences)
                        db_conn.commit()

                    # Get servers based on user permissions
                    if user.is_admin:
                        servers = db_conn.query(Server).filter(Server.is_active == True).all()
                    else:
                        servers = db_conn.query(Server).filter(
                            Server.user_id == user.id,
                            Server.is_active == True
                        ).all()

                    # Determine initial server from preferences
                    initial_server = None
                    if preferences.last_selected_server_id:
                        for server in servers:
                            if server.id == preferences.last_selected_server_id:
                                initial_server = server.name
                                break

                    # If no saved preference or server not found, use the first one
                    if not initial_server and servers:
                        initial_server = servers[0].name

                finally:
                    db_conn.close()

                if servers:
                    # Server selection
                    server_options = {f'{s.name}': s for s in servers}
                    server_select = ui.select(
                        label='Server',
                        options=list(server_options.keys()),
                        value=initial_server  # Use saved preference
                    ).classes('w-48').props('outlined dense')

                    # Team selection (filtered by selected server)
                    team_select = ui.select(
                        label='Team',
                        options=[],
                        value=None
                    ).classes('w-48').props('outlined dense')

                    state.ui_elements['server_select'] = server_select
                    state.ui_elements['server_options'] = server_options
                    state.ui_elements['team_select'] = team_select

                    def update_teams_for_server(server_name):
                        """Update team dropdown based on selected server"""
                        import logging
                        logger = logging.getLogger(__name__)

                        logger.info(f"Updating teams for server: {server_name}")

                        server = server_options.get(server_name)
                        if not server:
                            logger.warning(f"Server not found: {server_name}")
                            team_select.options = []
                            team_select.value = None
                            return

                        # Save server preference
                        db_pref = get_db()
                        try:
                            pref = db_pref.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                            if pref:
                                pref.last_selected_server_id = server.id
                                db_pref.commit()
                        finally:
                            db_pref.close()

                        # Get active teams for this server
                        db_conn = get_db()
                        try:
                            teams = db_conn.query(Team).filter(
                                Team.server_id == server.id,
                                Team.is_active == True
                            ).all()
                            logger.info(f"=== SERVER CHANGE DEBUG ===")
                            logger.info(f"Server: {server_name} (ID: {server.id})")
                            logger.info(f"Found {len(teams)} active teams")
                            for t in teams:
                                logger.info(f"  - Team: {t.name} (team_id: {t.team_id}, id: {t.id})")
                            logger.info(f"=== END SERVER CHANGE DEBUG ===")
                        finally:
                            db_conn.close()

                        if teams:
                            team_options = {f'{t.name}': t for t in teams}
                            team_select.options = list(team_options.keys())
                            # Update state.ui_elements BEFORE setting value to avoid race condition
                            state.ui_elements['team_options'] = team_options

                            logger.info(f"Team dropdown updated: {list(team_options.keys())}")

                            # Set flag to prevent event handler from firing during programmatic update
                            state.is_programmatic_update = True
                            team_select.value = list(team_options.keys())[0] if team_options else None

                            # Load databases for first team
                            if team_select.value:
                                change_team(team_select.value, team_options, state, state.user_id)

                            # Reset flag after update is complete
                            state.is_programmatic_update = False
                        else:
                            logger.warning(f"No active teams found for server {server_name}")
                            team_select.options = []
                            # Set flag to prevent event handler from firing
                            state.is_programmatic_update = True
                            team_select.value = None
                            state.is_programmatic_update = False
                            state.databases = []
                            if 'render_db_slider' in state.ui_elements:
                                state.ui_elements['render_db_slider']()
                            ui.notify(f'Keine aktiven Teams für Server {server_name}', type='warning')

                    # Server change handler
                    def on_server_change(e):
                        server_name = server_select.value
                        if server_name:
                            update_teams_for_server(server_name)

                    server_select.on('update:model-value', on_server_change)

                    # Team change handler
                    def on_team_change(e):
                        # Skip if this is a programmatic update (to avoid double calls)
                        if state.is_programmatic_update:
                            return

                        team_name = team_select.value
                        if team_name and 'team_options' in state.ui_elements:
                            change_team(team_name, state.ui_elements['team_options'], state, state.user_id)

                    team_select.on('update:model-value', on_team_change)

                    # Initialize with first server
                    ui.timer(0.1, lambda: update_teams_for_server(server_select.value) if server_select.value else None, once=True)

                ui.separator().props('vertical').classes('mx-2')

                # Inline search
                search_mode = ui.select(
                    options=['Felder/Elemente', 'Im Code'],
                    value='Felder/Elemente'
                ).classes('w-36').props('outlined dense borderless')

                global_search = ui.input(
                    placeholder='Suchen...'
                ).classes('w-64').props('outlined dense clearable')
                global_search.on('keydown.enter', lambda: perform_global_search(state, global_search.value, search_mode.value))

                ui.button(icon='search', on_click=lambda: perform_global_search(state, global_search.value, search_mode.value)).props('flat dense')

                global_results_label = ui.label('').classes('text-sm text-grey-7')
                state.ui_elements['global_results_label'] = global_results_label
                state.ui_elements['search_mode'] = search_mode

                ui.separator().props('vertical').classes('mx-2')

                # Refresh and download buttons
                ui.button(icon='refresh', on_click=lambda: refresh_databases(state, None, None, location_tree, code_panel)).props('flat dense').tooltip('Aktualisieren')
                ui.button(icon='cloud_download', on_click=lambda: show_download_dialog(user, state, None)).props('flat dense').tooltip('Download')
        
        # HORIZONTAL DATABASE SLIDER (always visible, single selection)
        with ui.card().classes('w-full p-3'):
            with ui.row().classes('items-center gap-3 mb-3'):
                ui.icon('storage', size='sm').classes('text-primary')
                ui.label('Datenbank auswählen').classes('text-h6 font-bold')

                # Database search
                db_search = ui.input(placeholder='Datenbank filtern...').classes('w-64 ml-4').props('outlined dense clearable')

                # Show only changed filter
                show_only_changed = ui.checkbox('Nur geänderte', value=False).classes('ml-2')

                # Stats
                db_stats_label = ui.label(f'{len(state.databases)} DBs').classes('text-sm text-grey-7 ml-auto')
                total_code = sum(len(db.code_locations) for db in state.databases)
                ui.label(f'{total_code} Code').classes('text-sm text-grey-7')

            # Horizontal scrollable database cards - single selection
            db_slider_container = ui.row().classes('w-full gap-3 overflow-x-auto pb-3 flex-nowrap').style(
                'scroll-behavior: smooth; scrollbar-width: thin;'
            )

            def render_db_slider(filter_text: str = "", only_changed: bool = False):
                db_slider_container.clear()
                filter_lower = filter_text.lower() if filter_text else ""
                filtered_count = 0

                with db_slider_container:
                    if not state.databases:
                        ui.label('Keine Datenbanken gefunden').classes('text-grey-7')
                        return

                    for db in state.databases:
                        if filter_lower and filter_lower not in db.name.lower():
                            continue

                        if only_changed and not has_git_changes(db):
                            continue

                        filtered_count += 1
                        is_selected = state.current_database and state.current_database.database_id == db.database_id
                        has_changes = has_git_changes(db)

                        # Flat horizontal database card - single selection
                        with ui.card().classes(
                            f'px-4 py-2 cursor-pointer flex-shrink-0 {"bg-primary text-white" if is_selected else "hover:bg-grey-2"}'
                        ).style('min-width: 200px; max-width: 250px; border: 2px solid ' + ('var(--q-primary)' if is_selected else 'transparent') + ';').on('click', lambda d=db: select_database(d, state)):
                            with ui.row().classes('items-center gap-3 w-full'):
                                # Icon
                                if has_changes:
                                    ui.icon('edit', size='sm').classes('text-orange' if not is_selected else 'text-white')
                                else:
                                    ui.icon('storage', size='sm').classes('text-primary' if not is_selected else 'text-white')

                                # Database name and stats in one row
                                with ui.column().classes('gap-0 flex-grow'):
                                    ui.label(db.name).classes(
                                        f'text-sm font-bold {"text-white" if is_selected else "text-grey-9"}'
                                    ).style('max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;')

                                    # Stats in one line
                                    ui.label(f'{db.table_count} Tab · {db.code_count} Code').classes(
                                        f'text-xs {"text-white opacity-80" if is_selected else "text-grey-6"}'
                                    )

                # Update stats label with filtered count
                if db_stats_label:
                    if filter_lower or only_changed:
                        db_stats_label.text = f'{filtered_count} von {len(state.databases)} DBs'
                    else:
                        db_stats_label.text = f'{len(state.databases)} DBs'

            # Initial render
            render_db_slider()

            # Filter handlers
            def on_db_filter():
                render_db_slider(db_search.value or "", show_only_changed.value)

            db_search.on('update:model-value', lambda: on_db_filter())
            show_only_changed.on('update:model-value', lambda: on_db_filter())

            state.ui_elements['render_db_slider'] = render_db_slider
        
        # Global search results container (hidden by default)
        global_results_container = ui.column().classes('w-full gap-2')
        global_results_container.visible = False
        state.ui_elements['global_results_container'] = global_results_container

        # FULL WIDTH TREE (Code opens in modal)
        with ui.card().classes('w-full').style('height: calc(100vh - 280px); overflow: auto;'):
            location_tree = render_location_tree_content(state)

        # Store references for compatibility
        db_list = None
        code_panel = None
        
        # Auto-select database if db parameter is provided
        if db_id_filter:
            logger.info(f"Auto-selecting database: {db_id_filter}")
            for db in state.databases:
                if db.database_id == db_id_filter:
                    logger.info(f"Found matching database: {db.name}")
                    ui.timer(0.2, lambda d=db: select_database(d, state), once=True)
                    break


# render_database_list function removed - using horizontal slider instead


def render_location_tree_content(state: YAMLCodeViewerState) -> ui.card:
    """Render the code locations tree content (always visible)"""

    with ui.card().classes('w-full h-full').style('overflow: auto;') as card:
        ui.label('Code-Locations').classes('text-h6 font-bold mb-2')
        # Search and filter row - horizontal layout
        with ui.row().classes('w-full gap-2 items-center'):
            # Search in code
            code_search = ui.input(
                placeholder='Im Code suchen...'
            ).classes('flex-grow').props('outlined dense clearable')

        # Filter controls
        with ui.expansion('Filter', icon='filter_list').classes('w-full mb-2').props('dense'):
            
            # Category filter
            ui.label('Kategorien').classes('text-sm font-medium mt-2 mb-1')
            category_container = ui.row().classes('w-full flex-wrap gap-1')
            
            # Code type filter
            ui.label('Code-Typen').classes('text-sm font-medium mt-2 mb-1')
            type_container = ui.row().classes('w-full flex-wrap gap-1')
            
            # Table filter
            ui.label('Tabellen').classes('text-sm font-medium mt-2 mb-1')
            table_select = ui.select(
                label='Tabelle filtern',
                options=[],
                multiple=True,
                value=[]
            ).classes('w-full').props('outlined dense clearable use-chips')
            
            # Clear filters button
            ui.button(
                'Filter zurücksetzen',
                icon='clear_all',
                on_click=lambda: clear_filters(state)
            ).props('flat dense').classes('mt-2')
        
        # Statistics display
        stats_label = ui.label('').classes('text-sm text-grey-7 mb-2')

        # Tree container - horizontal scrollable rows
        tree_container = ui.column().classes('w-full gap-2')
        
        def render_filters():
            """Render filter chips"""
            import logging
            logger = logging.getLogger(__name__)

            category_container.clear()
            type_container.clear()

            if not state.current_database:
                logger.warning("render_filters called but no database selected")
                return

            logger.info(f"=== RENDER FILTERS DEBUG ===")
            logger.info(f"Database: {state.current_database.name}")
            logger.info(f"Code locations: {len(state.current_database.code_locations)}")
            
            # Get unique categories and types from current database
            categories = set()
            code_types = set()

            for loc in state.current_database.code_locations:
                categories.add(loc.category)
                code_types.add(loc.code_type)

            # Category chips
            with category_container:
                for cat in sorted(categories, key=lambda c: c.name):
                    is_selected = cat in state.selected_categories
                    chip = ui.chip(
                        CATEGORY_NAMES.get(cat, cat.name),
                        icon='check' if is_selected else None,
                        on_click=lambda c=cat: toggle_category_filter(c, state)
                    ).props(f'clickable dense {"color=primary text-color=white" if is_selected else "outline"}')

            # Code type chips
            with type_container:
                for ct in sorted(code_types):
                    is_selected = ct in state.selected_code_types
                    chip = ui.chip(
                        CODE_TYPE_NAMES.get(ct, ct),
                        icon='check' if is_selected else None,
                        on_click=lambda t=ct: toggle_type_filter(t, state)
                    ).props(f'clickable dense {"color=primary text-color=white" if is_selected else "outline"}')

            # Collect tables from FILTERED locations
            # If no category/type filters active, show ALL tables
            # If filters active, show only tables with matching code
            tables = set()

            if not state.selected_categories and not state.selected_code_types:
                # No filters → Show ALL tables
                for loc in state.current_database.code_locations:
                    if loc.table_name:
                        tables.add(loc.table_name)
            else:
                # Filters active → Show only matching tables
                for loc in state.current_database.code_locations:
                    # Check if location matches filters
                    category_match = (not state.selected_categories) or (loc.category in state.selected_categories)
                    type_match = (not state.selected_code_types) or (loc.code_type in state.selected_code_types)

                    if category_match and type_match and loc.table_name:
                        tables.add(loc.table_name)

            # Get table_select from state (must use the same object!)
            if 'table_select' not in state.ui_elements:
                logger.error("table_select not in state.ui_elements!")
                return

            ts = state.ui_elements['table_select']

            # Update options
            ts.options = sorted(tables)
            ts.update()  # Force UI update

            logger.info(f"Tables found: {len(tables)}")
            if tables:
                logger.info(f"Table names: {sorted(tables)[:5]}")  # First 5
            logger.info(f"table_select.options set to: {len(ts.options)} items")
            logger.info(f"Selected categories: {state.selected_categories}")
            logger.info(f"Selected code types: {state.selected_code_types}")
            logger.info(f"=== END RENDER FILTERS DEBUG ===")
        
        def render_tree():
            """Render the location tree"""
            tree_container.clear()

            if not state.current_database:
                with tree_container:
                    ui.label('Wähle eine Datenbank aus.').classes('text-grey-7')
                return

            # Check if we have global search results for this database
            if state.global_search_results:
                # Filter to only show results from current database
                db_results = [loc for db, loc in state.global_search_results
                             if db.database_id == state.current_database.database_id]
                if db_results:
                    locations = db_results
                else:
                    # No results for this database
                    locations = state.apply_filters()
            else:
                # Apply normal filters
                locations = state.apply_filters()

            # Update stats
            total = len(state.current_database.code_locations)
            filtered = len(locations)
            if state.search_query or state.selected_categories or state.selected_code_types or state.selected_tables:
                stats_label.text = f'{filtered} von {total} Code-Locations'
            else:
                stats_label.text = f'{total} Code-Locations'
            
            if not locations:
                with tree_container:
                    ui.label('Keine Code-Locations gefunden.').classes('text-grey-7')
                return
            
            # Group by table
            grouped = group_by_table(locations)
            
            with tree_container:
                for table_name in sorted(grouped.keys()):
                    table_locations = grouped[table_name]
                    
                    # Table icon
                    if table_name == '(Database)':
                        table_icon = 'public'
                    elif table_name == '[Views]':
                        table_icon = 'view_list'
                    elif table_name == '[Reports]':
                        table_icon = 'assessment'
                    else:
                        table_icon = 'table_chart'
                    
                    # Table expansion
                    with ui.expansion(
                        f'{table_name} ({len(table_locations)})',
                        icon=table_icon
                    ).classes('w-full').props('dense'):

                        # Group by element/field name
                        from collections import defaultdict
                        field_groups = defaultdict(list)
                        for loc in table_locations:
                            field_name = loc.element_name or '(Ohne Feld)'
                            field_groups[field_name].append(loc)

                        # Render each field as sub-expansion
                        for field_name in sorted(field_groups.keys()):
                            field_locs = field_groups[field_name]

                            # Field icon based on type
                            field_icon = 'label'
                            if any('trigger' in loc.code_type.lower() for loc in field_locs):
                                field_icon = 'flash_on'
                            elif any('function' in loc.code_type.lower() for loc in field_locs):
                                field_icon = 'functions'

                            # Field expansion (nested under table)
                            with ui.expansion(
                                f'{field_name} ({len(field_locs)})',
                                icon=field_icon
                            ).classes('w-full ml-4').props('dense'):

                                # Render code locations for this field
                                for loc in sorted(field_locs, key=lambda l: l.code_type):
                                    render_location_button(loc, state, show_element=False)
        
        # Search handler
        def on_code_search(e):
            state.search_query = code_search.value or ""
            render_tree()
        
        code_search.on('update:model-value', on_code_search)
        
        # Table filter handler
        def on_table_filter(e):
            state.selected_tables = set(table_select.value) if table_select.value else set()
            render_tree()
        
        table_select.on('update:model-value', on_table_filter)
        
        # Store render functions
        state.ui_elements['render_filters'] = render_filters
        state.ui_elements['render_tree'] = render_tree
        state.ui_elements['stats_label'] = stats_label
        state.ui_elements['code_search'] = code_search
        state.ui_elements['table_select'] = table_select

    return card


def render_location_button(loc: CodeLocation, state: YAMLCodeViewerState, show_element: bool = True):
    """Render a single location as a clickable button"""
    
    # Build label
    if show_element and loc.element_name:
        label = f'{loc.element_name}.{loc.code_type}'
    else:
        label = loc.type_display_name
    
    # Preview
    preview = get_code_preview(loc.code, 40)
    
    is_selected = state.current_location and state.current_location.yaml_path == loc.yaml_path
    
    with ui.card().classes(
        f'w-full p-2 cursor-pointer {"bg-primary-50" if is_selected else ""}'
    ).on('click', lambda l=loc: select_location(l, state)):
        with ui.row().classes('items-center gap-2 w-full'):
            ui.icon(loc.icon, size='xs').classes(
                'text-primary' if is_selected else 'text-grey-7'
            )
            with ui.column().classes('gap-0 flex-grow overflow-hidden'):
                ui.label(label).classes(
                    f'text-sm {"text-primary font-medium" if is_selected else ""}'
                ).style('white-space: nowrap; overflow: hidden; text-overflow: ellipsis;')
                if preview:
                    ui.label(preview).classes('text-xs text-grey-6 font-mono').style(
                        'white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'
                    )


# render_code_panel removed - code now opens in modal via select_location()


def select_database(db: NinoxDatabase, state: YAMLCodeViewerState):
    """Handle database selection"""
    state.current_database = db
    state.current_location = None
    state.reset_filters()

    # Update filters
    if 'render_filters' in state.ui_elements:
        state.ui_elements['render_filters']()

    # Update tree
    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()

    # Re-render database slider to show selection
    if 'render_db_slider' in state.ui_elements:
        state.ui_elements['render_db_slider']()


def select_location(loc: CodeLocation, state: YAMLCodeViewerState):
    """Handle code location selection - opens code in modal"""
    state.current_location = loc

    # Open modal with code - maximized for full screen
    with ui.dialog() as dialog, ui.card().classes('w-full h-full').style('margin: 0; padding: 0;'):
        dialog.props('maximized')

        # Header - compact and fixed
        with ui.row().classes('w-full items-center justify-between px-4 py-3 bg-primary text-white').style('min-height: 60px;'):
            with ui.column().classes('gap-1 flex-grow'):
                ui.label(loc.short_path).classes('text-base font-bold font-mono text-white')
                with ui.row().classes('gap-2'):
                    ui.chip(loc.category_name, icon='category').props('dense color=white text-color=primary')
                    ui.chip(loc.type_display_name, icon='code').props('dense color=white text-color=primary')
                    ui.chip(f'{loc.line_count} Zeilen', icon='format_list_numbered').props('dense color=white text-color=primary')

            with ui.row().classes('gap-1'):
                ui.button(
                    icon='content_copy',
                    on_click=lambda c=loc.code: copy_code_to_clipboard(c)
                ).props('flat round color=white').tooltip('Code kopieren')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=white')

        # Code content - full height minus header
        with ui.column().classes('w-full').style('height: calc(100vh - 60px); overflow: hidden; padding: 0; margin: 0;'):
            # Highlight search query if present
            highlight = state.search_query if state.search_query else None
            html = highlight_code(loc.code, highlight_text=highlight, max_height='calc(100vh - 60px)')
            ui.html(html, sanitize=False).classes('w-full h-full')

    dialog.open()

    # Don't re-render tree - it would collapse everything!


def toggle_category_filter(category: CodeCategory, state: YAMLCodeViewerState):
    """Toggle a category filter"""
    if category in state.selected_categories:
        state.selected_categories.remove(category)
    else:
        state.selected_categories.add(category)
    
    if 'render_filters' in state.ui_elements:
        state.ui_elements['render_filters']()
    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()


def toggle_type_filter(code_type: str, state: YAMLCodeViewerState):
    """Toggle a code type filter"""
    if code_type in state.selected_code_types:
        state.selected_code_types.remove(code_type)
    else:
        state.selected_code_types.add(code_type)
    
    if 'render_filters' in state.ui_elements:
        state.ui_elements['render_filters']()
    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()


def clear_filters(state: YAMLCodeViewerState):
    """Clear all filters"""
    state.reset_filters()
    
    if 'code_search' in state.ui_elements:
        state.ui_elements['code_search'].value = ''
    if 'table_select' in state.ui_elements:
        state.ui_elements['table_select'].value = []
    if 'render_filters' in state.ui_elements:
        state.ui_elements['render_filters']()
    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()
    
    ui.notify('Filter zurückgesetzt', type='info')


async def copy_code_to_clipboard(code: str):
    """Copy code to clipboard"""
    try:
        await ui.run_javascript(f'navigator.clipboard.writeText({repr(code)})')
        ui.notify('Code kopiert!', type='positive', position='top')
    except Exception as e:
        ui.notify(f'Fehler beim Kopieren: {e}', type='negative')


def refresh_databases(
    state: YAMLCodeViewerState,
    parser,  # Not used anymore, kept for compatibility
    db_list: ui.card,
    location_tree: ui.column,
    code_panel: ui.column
):
    """Refresh the database list from the currently selected team"""
    # Reload databases from currently selected team
    if 'team_select' in state.ui_elements and 'team_options' in state.ui_elements:
        team_select = state.ui_elements['team_select']
        team_options = state.ui_elements['team_options']

        if team_select.value and team_options:
            # Clear cache and reload from team folder
            YAMLCodeViewerState.clear_cache()
            change_team(team_select.value, team_options, state, state.user_id)
            ui.notify(f'{len(state.databases)} Datenbanken neu geladen', type='positive')
        else:
            ui.notify('Kein Team ausgewählt', type='warning')
    else:
        # Fallback: clear databases if no team is selected
        state.databases = []
        state.current_database = None
        state.current_location = None

        if 'render_db_slider' in state.ui_elements:
            state.ui_elements['render_db_slider']()
        if 'render_tree' in state.ui_elements:
            state.ui_elements['render_tree']()

        ui.notify('Keine Datenbanken verfügbar', type='warning')


def show_download_dialog(
    user,
    state: YAMLCodeViewerState,
    db_list: ui.card
):
    """Show dialog to download a database from Ninox"""
    
    with ui.dialog() as dialog, ui.card().classes('p-4').style('min-width: 500px;'):
        ui.label('Datenbank herunterladen').classes('text-h6 font-bold mb-4')
        
        # Get available servers for the user
        db = get_db()
        try:
            if user.is_admin:
                servers = db.query(Server).filter(Server.is_active == True).all()
            else:
                servers = db.query(Server).filter(
                    Server.user_id == user.id,
                    Server.is_active == True
                ).all()
        finally:
            db.close()
        
        if not servers:
            ui.label('Keine Server konfiguriert.').classes('text-grey-7')
            ui.label('Bitte konfiguriere zuerst einen Server unter "Server".').classes('text-sm text-grey-6')
            ui.button('Schließen', on_click=dialog.close).props('flat')
            dialog.open()
            return
        
        # Server selection
        server_options = {s.name: s for s in servers}
        server_select = ui.select(
            label='Server',
            options=list(server_options.keys()),
            value=list(server_options.keys())[0] if server_options else None
        ).classes('w-full mb-2')
        
        # Database ID input
        db_id_input = ui.input(
            label='Datenbank-ID',
            placeholder='z.B. rm08kkxeoltw'
        ).classes('w-full mb-4')
        
        # Status display
        status_label = ui.label('').classes('text-sm mb-4')
        
        async def do_download():
            server_name = server_select.value
            db_id = db_id_input.value

            if not server_name or not db_id:
                ui.notify('Bitte Server und Datenbank-ID eingeben', type='warning')
                return

            server = server_options.get(server_name)
            if not server:
                ui.notify('Server nicht gefunden', type='negative')
                return

            status_label.text = 'Konfiguriere Umgebung...'

            # Get the currently selected team from UI
            current_team = None
            if 'team_select' in state.ui_elements and 'team_options' in state.ui_elements:
                team_name = state.ui_elements['team_select'].value
                if team_name:
                    current_team = state.ui_elements['team_options'].get(team_name)

            if not current_team:
                ui.notify('Bitte wähle zuerst ein Team aus', type='warning')
                return

            # Configure ninox-cli environment
            cli_service = get_ninox_cli_service()

            # Get server and create team-specific path using clear names
            from ..utils.path_resolver import get_team_path
            from ..models.server import Server

            db = get_db()
            try:
                server = db.query(Server).filter(Server.id == current_team.server_id).first()
                team_project_path = get_team_path(server, current_team)
            finally:
                db.close()
            team_project_path.mkdir(parents=True, exist_ok=True)

            # Create temporary CLI service for this team
            from ..services.ninox_cli_service import NinoxCLIService
            team_cli_service = NinoxCLIService(str(team_project_path))
            team_cli_service.init_project()

            env = NinoxEnvironment(
                name=server_name.lower().replace(' ', '_'),
                domain=f"https://{server.url}",
                api_key=server.api_key,
                workspace_id=current_team.team_id
            )
            team_cli_service.configure_environment(env)

            status_label.text = f'Lade Datenbank in Team-Ordner: team_{current_team.team_id}...'

            # Download database to team folder
            result = await team_cli_service.download_database_async(
                env_name=env.name,
                database_id=db_id
            )

            if result.success:
                status_label.text = f'Download erfolgreich! ({result.duration_seconds:.1f}s)'
                ui.notify('Datenbank erfolgreich heruntergeladen!', type='positive')

                # Reload databases for current team
                change_team(state.ui_elements['team_select'].value, state.ui_elements['team_options'], state, state.user_id)

                await asyncio.sleep(1)
                dialog.close()
            else:
                status_label.text = f'Fehler: {result.error}'
                ui.notify(f'Download fehlgeschlagen: {result.error}', type='negative')
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Abbrechen', on_click=dialog.close).props('flat')
            ui.button('Download', icon='cloud_download', on_click=do_download).props('color=primary')
    
    dialog.open()


def perform_global_search(state: YAMLCodeViewerState, query: str, mode: str = 'Felder/Elemente'):
    """Perform global search across all databases and filter tree view"""
    if not query or len(query) < 2:
        ui.notify('Bitte mindestens 2 Zeichen eingeben', type='warning')
        return
    
    results_label = state.ui_elements.get('global_results_label')
    
    # Search across all databases
    all_results = []
    query_lower = query.lower()
    
    if mode == 'Felder/Elemente':
        # Search in field/element/table names
        for db in state.databases:
            for loc in db.code_locations:
                # Search in element name, table name, or code type
                if (loc.element_name and query_lower in loc.element_name.lower()) or \
                   (loc.table_name and query_lower in loc.table_name.lower()) or \
                   (query_lower in loc.code_type.lower()) or \
                   (query_lower in loc.type_display_name.lower()):
                    all_results.append((db, loc))
    else:
        # Search in code content
        for db in state.databases:
            matches = search_code_locations(db.code_locations, query, case_sensitive=False)
            for loc in matches:
                all_results.append((db, loc))
    
    # Update results label
    if results_label:
        results_label.text = f'{len(all_results)} Ergebnisse gefunden'
    
    if not all_results:
        ui.notify('Keine Ergebnisse gefunden', type='warning')
        return
    
    # Store search results in state
    state.search_query = query
    state.global_search_results = all_results
    
    # If only one database has results, select it automatically
    dbs_with_results = set(db for db, loc in all_results)
    if len(dbs_with_results) == 1:
        # Auto-select the database
        db = list(dbs_with_results)[0]
        select_database(db, state)
        ui.notify(f'{len(all_results)} Ergebnisse in {db.name}', type='positive')
    else:
        # Multiple databases - show count per database
        from collections import Counter
        db_counts = Counter(db.name for db, loc in all_results)
        ui.notify(f'{len(all_results)} Ergebnisse in {len(dbs_with_results)} Datenbanken', type='positive')
        
        # Refresh database slider
        if 'render_db_slider' in state.ui_elements:
            state.ui_elements['render_db_slider']()


def jump_to_code(state: YAMLCodeViewerState, db: NinoxDatabase, loc: CodeLocation):
    """Jump to a specific code location from search results"""
    # Select the database
    state.current_database = db
    state.global_search_results.clear()  # Clear search after jumping
    
    # Update filters
    if 'render_filters' in state.ui_elements:
        state.ui_elements['render_filters']()
    
    # Update tree
    if 'render_tree' in state.ui_elements:
        state.ui_elements['render_tree']()
    
    # Select the location
    select_location(loc, state)
    
    # Update database slider to show selection
    if 'render_db_slider' in state.ui_elements:
        state.ui_elements['render_db_slider']()
    
    ui.notify(f'Springe zu: {loc.short_path}', type='info')


def show_erd_viewer(database: NinoxDatabase):
    """Show ERD viewer dialog with SVG for YAML database"""
    
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 95vw; max-height: 95vh;'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column().classes('gap-0'):
                ui.label(f'ERD: {database.name}').classes('text-h5 font-bold')
                ui.label(f'{database.table_count} Tabellen').classes('text-grey-7')
            
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')
        
        # Container for ERD content
        erd_container = ui.column().classes('w-full').style(
            'height: 80vh; overflow: hidden;'
        )
        
        with erd_container:
            status_label = ui.label('Generating ERD...').classes('text-h6')
            progress = ui.spinner('dots', size='lg')
        
        dialog.open()
        
        async def load_erd():
            """Generate and display ERD"""
            try:
                import logging
                logger = logging.getLogger(__name__)
                
                logger.info(f"Generating SVG ERD for YAML database {database.name}...")

                # Generate SVG directly from YAML (no conversion needed!)
                status_label.text = 'Generating diagram...'
                svg_content = generate_svg_erd(database)
                
                if not svg_content or '<svg' not in svg_content:
                    raise Exception("SVG generation failed - no valid SVG content")
                
                logger.info(f"Generated SVG ERD: {len(svg_content)} bytes")
                
                # Clear container and show SVG
                erd_container.clear()
                
                with erd_container:
                    # SVG viewer with pan/zoom
                    with ui.row().classes('w-full items-center gap-2 mb-2'):
                        ui.label('Zoom:').classes('text-sm')
                        ui.button('-', on_click=lambda: zoom_svg(-0.1)).props('dense flat')
                        ui.button('+', on_click=lambda: zoom_svg(0.1)).props('dense flat')
                        ui.button('Reset', on_click=lambda: reset_svg()).props('dense flat')
                        ui.button('Download SVG', on_click=lambda: download_svg(svg_content, database.name)).props('flat')
                    
                    # SVG container with pan/zoom
                    svg_viewer = ui.html('', sanitize=False).classes('w-full').style(
                        'height: 70vh; overflow: auto; border: 1px solid #ccc; background: white;'
                    )
                    
                    # Wrap SVG in a div for zoom control
                    svg_html = f'''
                    <div id="svg-wrapper" style="transform: scale(1); transform-origin: top left; transition: transform 0.2s;">
                        {svg_content}
                    </div>
                    '''
                    svg_viewer.content = svg_html
                    
                    # Add mouse wheel zoom functionality
                    ui.run_javascript('''
                        const svgViewer = document.querySelector('.q-page');
                        if (svgViewer) {
                            svgViewer.addEventListener('wheel', function(e) {
                                // Check if Cmd (Mac) or Ctrl (Windows/Linux) is pressed
                                if (e.metaKey || e.ctrlKey) {
                                    e.preventDefault();
                                    
                                    const wrapper = document.getElementById('svg-wrapper');
                                    if (!wrapper) return;
                                    
                                    const currentScale = parseFloat(wrapper.style.transform.match(/scale\\(([^)]+)\\)/)?.[1] || 1);
                                    
                                    // Determine zoom direction (negative deltaY = zoom in)
                                    const delta = e.deltaY > 0 ? -0.1 : 0.1;
                                    const newScale = Math.max(0.1, Math.min(5, currentScale + delta));
                                    
                                    wrapper.style.transform = `scale(${newScale})`;
                                }
                            }, { passive: false });
                        }
                    ''')
                    
                    # Zoom functions
                    def zoom_svg(delta):
                        ui.run_javascript(f'''
                            const wrapper = document.getElementById('svg-wrapper');
                            const currentScale = parseFloat(wrapper.style.transform.match(/scale\\(([^)]+)\\)/)?.[1] || 1);
                            const newScale = Math.max(0.1, Math.min(5, currentScale + {delta}));
                            wrapper.style.transform = `scale(${{newScale}})`;
                        ''')
                    
                    def reset_svg():
                        ui.run_javascript('''
                            document.getElementById('svg-wrapper').style.transform = 'scale(1)';
                        ''')
                    
                    def download_svg(content, db_name):
                        """Trigger SVG download"""
                        import base64
                        b64 = base64.b64encode(content.encode()).decode()
                        filename = f"{db_name.replace(' ', '_')}_erd.svg"
                        ui.run_javascript(f'''
                            const link = document.createElement('a');
                            link.href = 'data:image/svg+xml;base64,{b64}';
                            link.download = '{filename}';
                            link.click();
                        ''')
                    
                    # Add keyboard shortcuts for zoom
                    ui.keyboard(on_key=lambda e: zoom_svg(0.1) if e.key == '+' or e.key == '=' else 
                                                  zoom_svg(-0.1) if e.key == '-' else 
                                                  reset_svg() if e.key == '0' else None)
                
                logger.info(f"✓ SVG ERD loaded with pan/zoom: {len(svg_content)} bytes")
                ui.notify(f'ERD generiert - Zoom: Cmd/Ctrl+Mausrad, +/- oder 0', type='positive')
                
            except Exception as e:
                import traceback
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error generating ERD: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                
                erd_container.clear()
                with erd_container:
                    with ui.column().classes('items-center justify-center gap-4 p-8'):
                        ui.icon('error', size='64px', color='negative')
                        ui.label('Error Generating ERD').classes('text-h6 font-bold text-negative')
                        ui.label(str(e)).classes('text-grey-7')
                        ui.button('Close', on_click=dialog.close).props('flat')
                
                ui.notify(f'Error: {e}', type='negative')
        
        # Run async load
        ui.timer(0.1, load_erd, once=True)


def show_yaml_timeline(database: NinoxDatabase):
    """Show timeline/changelog for YAML database using Git history"""
    
    with ui.dialog() as dialog, ui.card().classes('w-full p-0').style('max-width: 900px; max-height: 90vh;'):
        # Header
        with ui.row().classes('w-full items-center justify-between p-4 bg-purple'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('timeline', size='md', color='white')
                ui.label(f'Change History: {database.name}').classes('text-h5 font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        # Content
        timeline_container = ui.scroll_area().classes('w-full').style('height: calc(90vh - 80px);')
        
        with timeline_container:
            status_label = ui.label('Loading Git history...').classes('text-h6 p-4')
            progress = ui.spinner('dots', size='lg').classes('mx-4')
        
        dialog.open()
        
        async def load_timeline():
            """Load and display Git timeline"""
            try:
                import logging
                logger = logging.getLogger(__name__)
                
                cli_service = get_ninox_cli_service()
                repo_path = cli_service.project_path
                
                logger.info(f"Loading Git history for database {database.database_id}...")
                
                # Get Git commits
                status_label.text = 'Reading Git history...'
                commits = get_git_log(repo_path, database.database_id, limit=50)
                
                if not commits:
                    timeline_container.clear()
                    with timeline_container:
                        with ui.column().classes('w-full items-center justify-center p-8 gap-4'):
                            ui.icon('history', size='4rem', color='grey')
                            ui.label('Keine Git-Historie gefunden').classes('text-h6 text-grey-7')
                            ui.label(
                                f'Für "{database.name}" wurden noch keine Commits gefunden. '
                                'Die Historie wird bei zukünftigen YAML-Syncs automatisch aufgezeichnet.'
                            ).classes('text-grey-6 text-center')
                    return
                
                logger.info(f"Found {len(commits)} commits")
                
                # Clear and show timeline
                timeline_container.clear()
                
                with timeline_container:
                    with ui.column().classes('w-full p-4 gap-4'):
                        # Stats
                        with ui.card().classes('w-full p-4 bg-purple-50'):
                            with ui.row().classes('w-full justify-around'):
                                with ui.column().classes('items-center'):
                                    ui.label(str(len(commits))).classes('text-h4 font-bold text-purple')
                                    ui.label('Commits').classes('text-sm text-grey-7')
                                
                                with ui.column().classes('items-center'):
                                    # Get first and last commit dates
                                    if commits[0]['date'] and commits[-1]['date']:
                                        days = (commits[0]['date'] - commits[-1]['date']).days
                                        ui.label(f'{days}').classes('text-h4 font-bold text-purple')
                                        ui.label('Tage').classes('text-sm text-grey-7')
                        
                        ui.separator().classes('my-4')
                        
                        ui.label('Änderungsverlauf').classes('text-h6 font-bold mb-2')
                        
                        # Timeline entries
                        for i, commit in enumerate(commits):
                            is_last = (i == len(commits) - 1)
                            render_timeline_commit(commit, database.database_id, repo_path, is_last)
                
                logger.info(f"✓ Timeline loaded with {len(commits)} commits")
                ui.notify(f'Timeline geladen: {len(commits)} Commits', type='positive')
                
            except Exception as e:
                import traceback
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error loading timeline: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                
                timeline_container.clear()
                with timeline_container:
                    with ui.column().classes('items-center justify-center gap-4 p-8'):
                        ui.icon('error', size='64px', color='negative')
                        ui.label('Error Loading Timeline').classes('text-h6 font-bold text-negative')
                        ui.label(str(e)).classes('text-grey-7')
                        ui.button('Close', on_click=dialog.close).props('flat')
                
                ui.notify(f'Error: {e}', type='negative')
        
        # Run async load
        ui.timer(0.1, load_timeline, once=True)


def render_timeline_commit(commit: dict, database_id: str, repo_path, is_last: bool):
    """Render a single commit in the timeline"""
    
    with ui.row().classes('w-full gap-3'):
        # Timeline line
        with ui.column().classes('items-center'):
            ui.icon('commit', size='sm', color='purple')
            if not is_last:
                ui.element('div').classes('w-0.5 h-full bg-purple-200').style('min-height: 80px;')
        
        # Commit content
        with ui.card().classes('flex-1 p-3 mb-4'):
            # Header with date and sha
            with ui.row().classes('w-full items-center justify-between mb-2'):
                with ui.column().classes('gap-0'):
                    ui.label(commit['message']).classes('font-bold')
                    with ui.row().classes('gap-2 items-center'):
                        ui.label(commit['author']).classes('text-xs text-grey-7')
                        ui.label('•').classes('text-xs text-grey-7')
                        if commit['date']:
                            from datetime import datetime
                            # Format date
                            date_str = commit['date'].strftime('%d.%m.%Y %H:%M')
                            ui.label(date_str).classes('text-xs text-grey-7')
                
                ui.label(commit['sha'][:8]).classes('text-xs font-mono bg-grey-100 px-2 py-1 rounded')
            
            # Show diff button (expandable)
            with ui.expansion('Details anzeigen', icon='code').classes('w-full text-sm'):
                diff_container = ui.column().classes('w-full')
                
                # Load diff on expand
                def load_diff():
                    diff_container.clear()
                    with diff_container:
                        ui.label('Loading diff...').classes('text-sm text-grey-7')
                        
                        # Get diff
                        diff_data = get_commit_diff(repo_path, commit['sha'], database_id)
                        
                        diff_container.clear()
                        with diff_container:
                            if diff_data['file_count'] > 0:
                                ui.label(f"{diff_data['file_count']} Dateien geändert").classes('text-sm font-bold mb-2')
                                
                                # Show files
                                for file_path in diff_data['files'][:10]:  # Limit to 10 files
                                    ui.label(f"• {file_path}").classes('text-xs font-mono text-grey-7')
                                
                                if len(diff_data['files']) > 10:
                                    ui.label(f"... und {len(diff_data['files']) - 10} weitere").classes('text-xs text-grey-6')
                            else:
                                ui.label('Keine Änderungen erkannt').classes('text-sm text-grey-7')
                
                ui.timer(0.1, load_diff, once=True)
